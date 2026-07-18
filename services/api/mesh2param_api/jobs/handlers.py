from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import shutil
import time
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

Progress = Callable[[str, float, str | None], None]


class JobFailure(RuntimeError):
    def __init__(
        self,
        code: str,
        phase: str,
        summary: str,
        detail: str,
        *,
        recoverable: bool,
        recommended_action: str | None,
    ) -> None:
        super().__init__(detail)
        self.code = code
        self.phase = phase
        self.summary = summary
        self.detail = detail
        self.recoverable = recoverable
        self.recommended_action = recommended_action


@dataclass(frozen=True, slots=True)
class ArtifactOutput:
    name: str
    path: str
    media_type: str
    kind: str

    def to_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "path": self.path,
            "mediaType": self.media_type,
            "kind": self.kind,
        }


@dataclass(frozen=True, slots=True)
class HandlerOutput:
    result: dict[str, Any]
    state_patch: dict[str, Any]
    artifacts: tuple[ArtifactOutput, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "result": self.result,
            "statePatch": self.state_patch,
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
        }


def _json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _mesh_limits(payload: dict[str, Any]) -> Any:
    from mesh2param import MeshLimits

    limits = payload.get("limits", {})
    return MeshLimits(
        max_file_bytes=int(limits.get("maxFileBytes", 256 * 1024 * 1024)),
        max_triangles=int(limits.get("maxTriangles", 2_000_000)),
        max_vertices=int(limits.get("maxVertices", 6_000_000)),
        max_abs_coordinate=float(limits.get("maxAbsCoordinate", 1_000_000_000.0)),
    )


def _repair_settings(payload: dict[str, Any]) -> Any:
    from mesh2param import RepairSettings

    raw = payload.get("settings", {})
    if not isinstance(raw, dict) or set(raw) - {"operations"}:
        raise JobFailure(
            "invalid_repair_settings",
            "repairing",
            "Repair settings are invalid",
            "Repair settings must contain only the supported operation list.",
            recoverable=True,
            recommended_action="Choose only repair operations offered by the current UI.",
        )
    if "operations" not in raw:
        return RepairSettings()
    operations = raw["operations"]
    allowed = {
        "mergeDuplicateVertices": "merge_duplicate_vertices",
        "removeDegenerateFaces": "remove_degenerate_faces",
        "removeDuplicateFaces": "remove_duplicate_faces",
        "removeUnreferencedVertices": "remove_unreferenced_vertices",
        "orientWinding": "orient_winding",
        "repairNormals": "repair_normals",
        "keepLargestComponent": "keep_largest_component",
        "dropTinyComponents": "drop_tiny_components",
        "fillSmallHoles": "fill_small_holes",
    }
    if (
        not isinstance(operations, list)
        or len(operations) > len(allowed)
        or any(not isinstance(item, str) or item not in allowed for item in operations)
        or len(set(operations)) != len(operations)
    ):
        raise JobFailure(
            "invalid_repair_settings",
            "repairing",
            "Repair settings are invalid",
            "The requested repair operation list contains an unsupported value.",
            recoverable=True,
            recommended_action="Choose only repair operations offered by the current UI.",
        )
    selected = set(operations)
    return RepairSettings(**{field: operation in selected for operation, field in allowed.items()})


def _segmentation_settings(payload: dict[str, Any]) -> Any:
    from mesh2param import SegmentationSettings

    raw = payload.get("settings", {})
    allowed = {"maxDeviation", "minPatchArea", "maxAngleDeg"}
    if not isinstance(raw, dict) or set(raw) - allowed:
        raise JobFailure(
            "invalid_segmentation_settings",
            "fitting planes",
            "Segmentation settings are invalid",
            "Segmentation settings contain an unsupported field.",
            recoverable=True,
            recommended_action="Use the tolerance fields offered by the current UI.",
        )
    if not raw:
        return SegmentationSettings()
    try:
        defaults = SegmentationSettings()
        deviation = _bounded_number(
            raw.get("maxDeviation", defaults.planar_fit_tolerance_mm),
            name="maximum deviation",
            minimum=0.0,
            maximum=1_000_000.0,
            minimum_inclusive=False,
        )
        minimum_area = _bounded_number(
            raw.get("minPatchArea", defaults.minimum_patch_area_mm2),
            name="minimum patch area",
            minimum=0.0,
            maximum=1_000_000_000_000.0,
        )
        maximum_angle = _bounded_number(
            raw.get("maxAngleDeg", defaults.smooth_angle_deg),
            name="maximum angle",
            minimum=0.0,
            maximum=90.0,
            minimum_inclusive=False,
            maximum_inclusive=False,
        )
        settings = SegmentationSettings(
            smooth_angle_deg=maximum_angle,
            planar_fit_tolerance_mm=(
                deviation if "maxDeviation" in raw else defaults.planar_fit_tolerance_mm
            ),
            cylinder_fit_tolerance_mm=(
                deviation if "maxDeviation" in raw else defaults.cylinder_fit_tolerance_mm
            ),
            minimum_patch_area_mm2=minimum_area,
        )
        settings.validate()
        return settings
    except (TypeError, ValueError) as exc:
        raise JobFailure(
            "invalid_segmentation_settings",
            "fitting planes",
            "Segmentation settings are invalid",
            str(exc),
            recoverable=True,
            recommended_action="Use positive finite tolerances and an angle below 90 degrees.",
        ) from exc


def _reconstruction_segmentation_settings(payload: dict[str, Any]) -> Any:
    """Replay the exact user-facing settings that produced persisted analysis patches."""

    from mesh2param import SegmentationSettings

    project_state = payload.get("projectState")
    if not isinstance(project_state, dict):
        return _segmentation_settings({"settings": {}})
    analysis = project_state.get("analysis")
    persisted = analysis.get("settings") if isinstance(analysis, dict) else None
    patches = project_state.get("patches")
    if persisted is None:
        if isinstance(patches, list) and patches:
            raise JobFailure(
                "analysis_settings_missing",
                "starting reconstruction",
                "Analysis settings are unavailable",
                "Persisted surface patches do not include the settings that produced them.",
                recoverable=True,
                recommended_action="Re-run surface analysis before automatic reconstruction.",
            )
        return _segmentation_settings({"settings": {}})
    if not isinstance(persisted, dict):
        raise JobFailure(
            "invalid_analysis_settings",
            "starting reconstruction",
            "Analysis settings are invalid",
            "Persisted segmentation settings must be an object.",
            recoverable=True,
            recommended_action="Re-run surface analysis before automatic reconstruction.",
        )
    required = {
        "smoothAngleDeg",
        "planarFitToleranceMm",
        "cylinderFitToleranceMm",
        "minimumCylinderCoverageDeg",
        "maximumCylinderAxisNormalComponent",
        "minimumPatchAreaMm2",
        "stableIdResolutionMm",
    }
    missing = sorted(required - set(persisted))
    if missing:
        raise JobFailure(
            "invalid_analysis_settings",
            "starting reconstruction",
            "Analysis settings are invalid",
            f"Persisted segmentation settings omit: {', '.join(missing)}.",
            recoverable=True,
            recommended_action="Re-run surface analysis before automatic reconstruction.",
        )
    try:
        defaults = SegmentationSettings()
        faceted_side_count = _bounded_number(
            persisted.get(
                "minimumFacetedCylinderSideCount",
                defaults.minimum_faceted_cylinder_side_count,
            ),
            name="persisted minimum faceted-cylinder side count",
            minimum=6.0,
            maximum=10_000.0,
        )
        if not faceted_side_count.is_integer():
            raise ValueError("persisted minimum faceted-cylinder side count must be an integer")
        settings = SegmentationSettings(
            smooth_angle_deg=_bounded_number(
                persisted["smoothAngleDeg"],
                name="persisted smooth angle",
                minimum=0.0,
                maximum=90.0,
                minimum_inclusive=False,
                maximum_inclusive=False,
            ),
            planar_fit_tolerance_mm=_bounded_number(
                persisted["planarFitToleranceMm"],
                name="persisted planar fit tolerance",
                minimum=0.0,
                maximum=1_000_000.0,
                minimum_inclusive=False,
            ),
            cylinder_fit_tolerance_mm=_bounded_number(
                persisted["cylinderFitToleranceMm"],
                name="persisted cylinder fit tolerance",
                minimum=0.0,
                maximum=1_000_000.0,
                minimum_inclusive=False,
            ),
            minimum_cylinder_coverage_deg=_bounded_number(
                persisted["minimumCylinderCoverageDeg"],
                name="persisted minimum cylinder coverage",
                minimum=0.0,
                maximum=360.0,
                minimum_inclusive=False,
            ),
            maximum_cylinder_axis_normal_component=_bounded_number(
                persisted["maximumCylinderAxisNormalComponent"],
                name="persisted maximum cylinder axis-normal component",
                minimum=0.0,
                maximum=1.0,
            ),
            minimum_faceted_cylinder_side_count=int(faceted_side_count),
            maximum_faceted_cylinder_sagitta_mm=_bounded_number(
                persisted.get(
                    "maximumFacetedCylinderSagittaMm",
                    defaults.maximum_faceted_cylinder_sagitta_mm,
                ),
                name="persisted maximum faceted-cylinder sagitta",
                minimum=0.0,
                maximum=1_000_000.0,
                minimum_inclusive=False,
            ),
            minimum_patch_area_mm2=_bounded_number(
                persisted["minimumPatchAreaMm2"],
                name="persisted minimum patch area",
                minimum=0.0,
                maximum=1_000_000_000_000.0,
            ),
            stable_id_resolution_mm=_bounded_number(
                persisted["stableIdResolutionMm"],
                name="persisted stable-ID resolution",
                minimum=0.0,
                maximum=1_000_000.0,
                minimum_inclusive=False,
            ),
        )
        settings.validate()
        return settings
    except ValueError as exc:
        raise JobFailure(
            "invalid_analysis_settings",
            "starting reconstruction",
            "Analysis settings are invalid",
            str(exc),
            recoverable=True,
            recommended_action="Re-run surface analysis before automatic reconstruction.",
        ) from exc


def _bounded_number(
    value: object,
    *,
    name: str,
    minimum: float,
    maximum: float,
    minimum_inclusive: bool = True,
    maximum_inclusive: bool = True,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a JSON number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite")
    minimum_valid = number >= minimum if minimum_inclusive else number > minimum
    maximum_valid = number <= maximum if maximum_inclusive else number < maximum
    if not minimum_valid or not maximum_valid:
        left = "[" if minimum_inclusive else "("
        right = "]" if maximum_inclusive else ")"
        raise ValueError(f"{name} must be in {left}{minimum}, {maximum}{right}")
    return number


def _validation_surface_deviation(payload: dict[str, Any]) -> float | None:
    raw = payload.get("settings", {})
    if not isinstance(raw, dict) or set(raw) - {"surfaceDeviation"}:
        raise JobFailure(
            "invalid_validation_settings",
            "building B-Rep",
            "Validation settings are invalid",
            "Validation settings must contain only surfaceDeviation.",
            recoverable=True,
            recommended_action="Use the surface-deviation field offered by the current UI.",
        )
    if "surfaceDeviation" not in raw:
        return None
    try:
        return _bounded_number(
            raw["surfaceDeviation"],
            name="surface deviation",
            minimum=0.0,
            maximum=1_000_000.0,
            minimum_inclusive=False,
        )
    except ValueError as exc:
        raise JobFailure(
            "invalid_validation_settings",
            "building B-Rep",
            "Validation settings are invalid",
            str(exc),
            recoverable=True,
            recommended_action="Use a positive finite surface-deviation tolerance.",
        ) from exc


def _source_path(payload: dict[str, Any]) -> Path:
    raw = payload.get("sourcePath")
    if not isinstance(raw, str):
        raise JobFailure(
            "source_missing",
            "validating upload",
            "Source mesh is missing",
            "The project does not have a source blob for this operation.",
            recoverable=True,
            recommended_action="Upload or reopen the source mesh and retry.",
        )
    path = Path(raw)
    if not path.is_file() or path.is_symlink():
        raise JobFailure(
            "source_missing",
            "validating upload",
            "Source mesh is unavailable",
            "The content-addressed source blob is absent or unsafe.",
            recoverable=True,
            recommended_action="Re-upload the original source mesh.",
        )
    return path


def _mesh_tessellation(mesh: Any) -> Any:
    from mesh2param import Tessellation

    vertices = cast(
        tuple[tuple[float, float, float], ...],
        tuple(tuple(float(value) for value in vertex) for vertex in mesh.vertices),
    )
    triangles = cast(
        tuple[tuple[int, int, int], ...],
        tuple(tuple(int(value) for value in face) for face in mesh.faces),
    )
    return Tessellation(vertices, triangles, ())


def _upload(payload: dict[str, Any], workdir: Path, progress: Progress) -> HandlerOutput:
    from mesh2param import ingest_mesh

    progress("validating upload", 5.0, "Parsing the allowlisted mesh format")
    source = ingest_mesh(_source_path(payload), limits=_mesh_limits(payload))
    progress("diagnostics", 85.0, "Mesh diagnostics completed")
    analysis = source.to_dict()
    _json(workdir / "analysis.json", analysis)
    return HandlerOutput(
        result={"diagnostics": analysis["diagnostics"], "source": analysis["metadata"]},
        state_patch={"diagnostics": analysis["diagnostics"], "analysis": analysis},
        artifacts=(
            ArtifactOutput("analysis.json", "analysis.json", "application/json", "analysis"),
        ),
    )


def _repair(payload: dict[str, Any], workdir: Path, progress: Progress) -> HandlerOutput:
    from mesh2param import ingest_mesh, repair_mesh
    from mesh2param.tessellation import write_binary_stl, write_glb

    source = ingest_mesh(_source_path(payload), limits=_mesh_limits(payload))
    progress("repairing", 25.0, "Applying explicit configured repair operations")
    repaired = repair_mesh(
        source,
        settings=_repair_settings(payload),
        limits=_mesh_limits(payload),
    )
    result = repaired.to_dict()
    _json(workdir / "analysis.json", source.to_dict())
    _json(workdir / "repair.json", result)
    write_glb(_mesh_tessellation(source.mesh), workdir / "source.glb")
    write_binary_stl(_mesh_tessellation(repaired.mesh), workdir / "repaired.stl")
    write_glb(_mesh_tessellation(repaired.mesh), workdir / "repaired.glb")
    progress("finalizing artifacts", 95.0, "Repair artifacts written")
    return HandlerOutput(
        result=result,
        state_patch={"diagnostics": source.diagnostics.to_dict(), "repair": result},
        artifacts=(
            ArtifactOutput("analysis.json", "analysis.json", "application/json", "analysis"),
            ArtifactOutput("source.glb", "source.glb", "model/gltf-binary", "source-mesh"),
            ArtifactOutput("repair.json", "repair.json", "application/json", "repair"),
            ArtifactOutput("repaired.stl", "repaired.stl", "model/stl", "repaired-mesh"),
            ArtifactOutput("repaired.glb", "repaired.glb", "model/gltf-binary", "repaired-mesh"),
        ),
    )


def _analyze(payload: dict[str, Any], workdir: Path, progress: Progress) -> HandlerOutput:
    from mesh2param import (
        detect_extrusion_candidate,
        ingest_mesh,
        repair_mesh,
        segment_mesh,
        validate_prismatic_candidate,
    )
    from mesh2param.selection import write_patch_selection_artifacts
    from mesh2param.tessellation import write_binary_stl, write_glb

    source = ingest_mesh(_source_path(payload), limits=_mesh_limits(payload))
    progress("repairing", 15.0, "Preparing a non-destructive analysis mesh")
    repaired = repair_mesh(source, limits=_mesh_limits(payload))
    write_glb(_mesh_tessellation(source.mesh), workdir / "source.glb")
    write_binary_stl(_mesh_tessellation(repaired.mesh), workdir / "repaired.stl")
    write_glb(_mesh_tessellation(repaired.mesh), workdir / "repaired.glb")
    write_glb(_mesh_tessellation(repaired.mesh), workdir / "analysis-proxy.glb")
    progress("sharp boundaries", 35.0, "Computing adjacency and sharp boundaries")
    segmentation = segment_mesh(repaired.mesh, settings=_segmentation_settings(payload))
    progress("fitting curves", 65.0, "Testing bounded line and circular-arc extrusion evidence")
    prismatic = validate_prismatic_candidate(
        detect_extrusion_candidate(repaired.mesh, segmentation.patches)
    )
    progress("fitting curves", 75.0, "Plane, cylinder, line, and arc fitting completed")
    selection = write_patch_selection_artifacts(
        repaired.mesh,
        segmentation.patches,
        workdir / "patches.glb",
        workdir / "selection-map.json",
    )
    analysis = source.to_dict()
    repair = repaired.to_dict()
    segmented = segmentation.to_dict()
    segmented["prismaticCandidate"] = prismatic.to_dict()
    _json(workdir / "analysis.json", analysis)
    _json(workdir / "repair.json", repair)
    _json(workdir / "patches.json", segmented)
    return HandlerOutput(
        result={
            "diagnostics": analysis["diagnostics"],
            "repair": repair,
            "segmentation": segmented,
            "patchSelection": selection.to_dict(),
        },
        state_patch={
            "diagnostics": analysis["diagnostics"],
            "repair": repair,
            "analysis": segmented,
            "patches": segmented["patches"],
        },
        artifacts=(
            ArtifactOutput("analysis.json", "analysis.json", "application/json", "analysis"),
            ArtifactOutput("source.glb", "source.glb", "model/gltf-binary", "source-mesh"),
            ArtifactOutput("repair.json", "repair.json", "application/json", "repair"),
            ArtifactOutput("repaired.stl", "repaired.stl", "model/stl", "repaired-mesh"),
            ArtifactOutput("repaired.glb", "repaired.glb", "model/gltf-binary", "repaired-mesh"),
            ArtifactOutput(
                "analysis-proxy.glb",
                "analysis-proxy.glb",
                "model/gltf-binary",
                "analysis-proxy",
            ),
            ArtifactOutput("patches.json", "patches.json", "application/json", "patches"),
            ArtifactOutput("patches.glb", "patches.glb", "model/gltf-binary", "patches"),
            ArtifactOutput(
                "selection-map.json",
                "selection-map.json",
                "application/json",
                "selection-map",
            ),
        ),
    )


def _reconstruction_project_settings(
    payload: dict[str, Any], result: dict[str, Any]
) -> dict[str, Any]:
    project_state = payload.get("projectState")
    previous_settings = project_state.get("settings") if isinstance(project_state, dict) else None
    settings = copy.deepcopy(previous_settings) if isinstance(previous_settings, dict) else {}
    candidates = result.get("candidates")
    selected = result.get("selectedCandidate")
    if not isinstance(candidates, list) or not isinstance(selected, str):
        raise RuntimeError("reconstruction result omitted candidate histories")
    settings["candidateHistories"] = copy.deepcopy(candidates)
    settings["selectedCandidate"] = selected
    detail_mode = result.get("detailMode")
    if detail_mode in {"functional", "full"}:
        settings["detailMode"] = detail_mode
    return settings


def _automatic_detail_mode(payload: dict[str, Any]) -> Literal["functional", "full"]:
    """Validate the one bounded setting accepted by automatic reconstruction."""

    raw = payload.get("settings", {})
    if not isinstance(raw, dict):
        raise JobFailure(
            "invalid_reconstruction_settings",
            "recovering details",
            "Reconstruction settings are invalid",
            "Reconstruction settings must be an object.",
            recoverable=True,
            recommended_action="Use the reconstruction controls offered by the current UI.",
        )
    if "mode" in raw:
        raise JobFailure(
            "invalid_reconstruction_mode",
            "starting reconstruction",
            "Reconstruction mode is invalid",
            "Automatic reconstruction does not accept an explicit mode field.",
            recoverable=True,
            recommended_action="Choose automatic, curved, or faceted reconstruction.",
        )
    if set(raw) - {"detailMode"}:
        raise JobFailure(
            "invalid_reconstruction_settings",
            "recovering details",
            "Reconstruction settings are invalid",
            "Automatic reconstruction settings contain an unsupported field.",
            recoverable=True,
            recommended_action="Use only the displayed detail-recovery control.",
        )
    detail_mode = raw.get("detailMode", "functional")
    if detail_mode not in {"functional", "full"}:
        raise JobFailure(
            "invalid_detail_mode",
            "recovering details",
            "Detail recovery mode is invalid",
            "detailMode must be either 'functional' or 'full'.",
            recoverable=True,
            recommended_action="Choose functional suppression or full detail recovery.",
        )
    return "full" if detail_mode == "full" else "functional"


def _faceted_sewing_tolerance(payload: dict[str, Any]) -> float | None:
    from mesh2param.units import (
        DEFAULT_FACETED_SEWING_TOLERANCE_MM,
        MAXIMUM_FACETED_SEWING_TOLERANCE_MM,
        MILLIMETERS_PER_UNIT,
        millimeters_to_project_units,
    )

    raw = payload.get("settings", {})
    if not isinstance(raw, dict):
        raise JobFailure(
            "invalid_reconstruction_settings",
            "starting reconstruction",
            "Reconstruction settings are invalid",
            "Reconstruction settings must be an object.",
            recoverable=True,
            recommended_action="Use the reconstruction controls offered by the current UI.",
        )
    if raw.get("mode") != "faceted":
        return None
    if set(raw) - {"mode", "sewingTolerance"}:
        raise JobFailure(
            "invalid_faceted_settings",
            "sewing facets",
            "Faceted fallback settings are invalid",
            "Faceted fallback settings contain an unsupported field.",
            recoverable=True,
            recommended_action="Use only the displayed sewing-tolerance control.",
        )
    units = payload.get("units")
    if not isinstance(units, str) or units not in MILLIMETERS_PER_UNIT:
        raise JobFailure(
            "invalid_faceted_settings",
            "sewing facets",
            "Faceted fallback settings are invalid",
            "Faceted sewing requires explicit mm, cm, m, in, or ft project units.",
            recoverable=True,
            recommended_action="Restore a supported project unit before retrying.",
        )
    default_tolerance = millimeters_to_project_units(
        DEFAULT_FACETED_SEWING_TOLERANCE_MM,
        units,
    )
    maximum_tolerance = millimeters_to_project_units(
        MAXIMUM_FACETED_SEWING_TOLERANCE_MM,
        units,
    )
    try:
        return _bounded_number(
            raw.get("sewingTolerance", default_tolerance),
            name="sewing tolerance",
            minimum=0.0,
            maximum=maximum_tolerance,
            minimum_inclusive=False,
        )
    except ValueError as exc:
        raise JobFailure(
            "invalid_faceted_settings",
            "sewing facets",
            "Faceted fallback settings are invalid",
            str(exc),
            recoverable=True,
            recommended_action=(
                "Use a positive sewing tolerance no larger than "
                f"{maximum_tolerance:g} {units} (10 mm)."
            ),
        ) from exc


def _curved_settings(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Validate the bounded curved-reconstruction settings, or return None."""

    from mesh2param.units import MILLIMETERS_PER_UNIT, millimeters_to_project_units

    raw = payload.get("settings")
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise JobFailure(
            "invalid_reconstruction_settings",
            "fitting surface",
            "Reconstruction settings are invalid",
            "Reconstruction settings must be an object.",
            recoverable=True,
            recommended_action="Use the reconstruction controls offered by the current UI.",
        )
    if raw.get("mode") != "curved":
        return None
    allowed = {"mode", "fitTolerance", "surfaceDeviationTolerance", "forceSplit"}
    if set(raw) - allowed:
        raise JobFailure(
            "invalid_curved_settings",
            "fitting surface",
            "Curved reconstruction settings are invalid",
            "Curved reconstruction settings contain an unsupported field.",
            recoverable=True,
            recommended_action="Use only the displayed curved reconstruction controls.",
        )
    units = payload.get("units")
    if not isinstance(units, str) or units not in MILLIMETERS_PER_UNIT:
        raise JobFailure(
            "invalid_curved_settings",
            "fitting surface",
            "Curved reconstruction settings are invalid",
            "Curved reconstruction requires explicit mm, cm, m, in, or ft project units.",
            recoverable=True,
            recommended_action="Restore a supported project unit before retrying.",
        )
    maximum_tolerance = millimeters_to_project_units(10.0, units)
    default_fit = millimeters_to_project_units(0.25, units)
    default_deviation = millimeters_to_project_units(0.3, units)
    try:
        fit_tolerance = _bounded_number(
            raw.get("fitTolerance", default_fit),
            name="fit tolerance",
            minimum=0.0,
            maximum=maximum_tolerance,
            minimum_inclusive=False,
        )
        deviation_tolerance = _bounded_number(
            raw.get("surfaceDeviationTolerance", default_deviation),
            name="surface deviation tolerance",
            minimum=0.0,
            maximum=maximum_tolerance,
            minimum_inclusive=False,
        )
    except ValueError as exc:
        raise JobFailure(
            "invalid_curved_settings",
            "fitting surface",
            "Curved reconstruction settings are invalid",
            str(exc),
            recoverable=True,
            recommended_action=(
                f"Use positive tolerances no larger than {maximum_tolerance:g} {units} (10 mm)."
            ),
        ) from exc
    force_split = raw.get("forceSplit", False)
    if not isinstance(force_split, bool):
        raise JobFailure(
            "invalid_curved_settings",
            "fitting surface",
            "Curved reconstruction settings are invalid",
            "forceSplit must be a boolean.",
            recoverable=True,
            recommended_action="Use only the displayed curved reconstruction controls.",
        )
    return {
        "units": units,
        "fitTolerance": fit_tolerance,
        "surfaceDeviationTolerance": deviation_tolerance,
        "forceSplit": force_split,
    }


def _user_patch_overrides(payload: dict[str, Any]) -> dict[str, dict[str, Any]] | None:
    """Collect persisted user patch edits (reclassifications and locks)."""

    project_state = payload.get("projectState")
    patches = project_state.get("patches") if isinstance(project_state, dict) else None
    if not isinstance(patches, list):
        return None
    overrides: dict[str, dict[str, Any]] = {}
    for patch in patches:
        if not isinstance(patch, dict) or not isinstance(patch.get("id"), str):
            continue
        entry: dict[str, Any] = {}
        if patch.get("userOverriddenClassification") and isinstance(patch.get("type"), str):
            entry["kind"] = patch["type"]
        if patch.get("locked") is True:
            entry["locked"] = True
        smooth = patch.get("smoothBoundaryIds")
        if isinstance(smooth, list) and all(isinstance(item, str) for item in smooth) and smooth:
            entry["smooth_boundaries"] = sorted(set(smooth))
        if entry:
            overrides[patch["id"]] = entry
    return overrides or None


def _curved_reconstruct(
    payload: dict[str, Any],
    workdir: Path,
    progress: Progress,
    curved: dict[str, Any],
) -> HandlerOutput:
    from mesh2param.curved_conversion import CurvedConversionError, create_curved_conversion
    from mesh2param.curved_patch import CurvedNetworkSettings, CurvedPatchSettings

    units = curved["units"]
    source_descriptor = payload.get("source")
    if not isinstance(source_descriptor, dict):
        raise JobFailure(
            "curved_source_metadata_required",
            "validating upload",
            "Curved source metadata is required",
            "The preserved source descriptor is unavailable for this conversion.",
            recoverable=True,
            recommended_action="Re-upload the original STL before retrying.",
        )
    settings = CurvedPatchSettings(
        fit_tolerance_mm=float(curved["fitTolerance"]),
        surface_deviation_tolerance_mm=float(curved["surfaceDeviationTolerance"]),
    )
    network_settings = CurvedNetworkSettings(force_split=bool(curved["forceSplit"]))

    def engine_progress(phase: str, fraction: float) -> None:
        progress(phase, 5.0 + fraction * 0.85, None)

    patch_overrides = _user_patch_overrides(payload)
    try:
        conversion = create_curved_conversion(
            _source_path(payload),
            workdir,
            units=units,
            settings=settings,
            network_settings=network_settings,
            source_descriptor=source_descriptor,
            mesh_limits=_mesh_limits(payload),
            progress=engine_progress,
            patch_overrides=patch_overrides,
        )
    except CurvedConversionError as exc:
        raise JobFailure(
            exc.code,
            exc.phase,
            "Curved reconstruction could not complete",
            str(exc),
            recoverable=True,
            recommended_action=(
                "Use the explicit faceted STEP fallback for this geometry."
                if exc.code
                in {
                    "curved_patch_unsupported_topology",
                    "curved_patch_not_disk",
                    "curved_patch_boundary_not_straight",
                    "curved_patch_holes_unsupported_split",
                    "curved_patch_tolerance_not_met",
                    "curved_patch_regions_detached",
                    "curved_patch_crease_corners",
                    "curved_patch_multiregion_holes",
                    "curved_patch_cone_multiregion_unsupported",
                }
                else "Review the reconstruction evidence or adjust the tolerances."
            ),
        ) from exc
    progress("reimporting STEP", 96.0, "Kernel and structural STEP validation completed")

    graph_document = conversion.graph.model_dump(mode="json", by_alias=True)
    validation = json.loads((workdir / "validation.json").read_text(encoding="utf-8"))
    artifact_map: dict[str, tuple[str, str, str]] = {
        "analysis": ("analysis.json", "application/json", "analysis"),
        "sourceOriginal": ("source.original.stl", "model/stl", "source"),
        "sourceGlb": ("source.glb", "model/gltf-binary", "source-mesh"),
        "repair": ("repair.json", "application/json", "repair"),
        "curvedPlate": ("curved-plate.json", "application/json", "curved-plate"),
        "cadgraph": ("model.cadgraph.json", "application/json", "cadgraph"),
        "cadquerySource": ("model.cq.py", "text/x-python", "cadquery-source"),
        "step": ("model.step", "model/step", "step"),
        "modelGlb": ("reconstructed.glb", "model/gltf-binary", "reconstructed-mesh"),
        "validation": ("validation.json", "application/json", "validation"),
        "curvedReconstruction": (
            "curved-reconstruction.json",
            "application/json",
            "curved-reconstruction",
        ),
    }
    artifacts = [
        ArtifactOutput(name, name, media_type, kind)
        for key, (name, media_type, kind) in artifact_map.items()
        if key in conversion.artifacts
    ]
    if (workdir / "manifest.json").is_file():
        artifacts.append(
            ArtifactOutput("manifest.json", "manifest.json", "application/json", "manifest")
        )
    project_state = payload.get("projectState")
    prior_settings = project_state.get("settings") if isinstance(project_state, dict) else None
    settings_state = copy.deepcopy(prior_settings) if isinstance(prior_settings, dict) else {}
    settings_state.pop("candidateHistories", None)
    settings_state.pop("selectedCandidate", None)
    settings_state["curvedReconstruction"] = {
        "scope": "approximate curved B-Rep",
        "approximate": True,
        "designHistoryRecovered": False,
        "fitTolerance": curved["fitTolerance"],
        "surfaceDeviationTolerance": curved["surfaceDeviationTolerance"],
        "forceSplit": curved["forceSplit"],
        "units": units,
        "sourceSha256": conversion.source.metadata.sha256,
        "artifactSha256": graph_document["features"][0]["artifactSha256"],
        "faceSurfaces": dict(conversion.reconstruction.face_surfaces),
        "residualMaximumMm": conversion.reconstruction.residual_maximum,
        "appliedPatchOverrides": sorted(patch_overrides) if patch_overrides else [],
        "appliedSmoothBoundaries": sorted(
            {
                "|".join(sorted((patch_id, neighbor_id)))
                for patch_id, entry in (patch_overrides or {}).items()
                for neighbor_id in entry.get("smooth_boundaries", [])
            }
        ),
    }
    return HandlerOutput(
        result=conversion.to_dict(),
        state_patch={
            "diagnostics": conversion.source.diagnostics.to_dict(),
            "repair": conversion.repair.to_dict(),
            "cadgraph": graph_document,
            "validation": validation,
            "metrics": graph_document["fitMetrics"],
            "settings": settings_state,
        },
        artifacts=tuple(artifacts),
    )


def _faceted_reconstruct(
    payload: dict[str, Any],
    workdir: Path,
    progress: Progress,
    sewing_tolerance: float,
) -> HandlerOutput:
    from mesh2param import FacetedFallbackError, create_faceted_fallback
    from mesh2param.units import MILLIMETERS_PER_UNIT

    units = payload.get("units")
    if not isinstance(units, str) or units not in MILLIMETERS_PER_UNIT:
        raise JobFailure(
            "invalid_faceted_settings",
            "sewing facets",
            "Faceted fallback settings are invalid",
            "Faceted sewing requires explicit mm, cm, m, in, or ft project units.",
            recoverable=True,
            recommended_action="Restore a supported project unit before retrying.",
        )
    source_descriptor = payload.get("source")
    if not isinstance(source_descriptor, dict):
        raise JobFailure(
            "faceted_source_metadata_required",
            "validating upload",
            "Faceted source metadata is required",
            "The preserved source descriptor is unavailable for this conversion.",
            recoverable=True,
            recommended_action="Re-upload the original STL before retrying.",
        )
    progress(
        "sewing facets",
        12.0,
        f"Sewing preserved source facets within {sewing_tolerance:g} {units}",
    )
    try:
        fallback = create_faceted_fallback(
            _source_path(payload),
            workdir,
            units=units,
            sewing_tolerance=sewing_tolerance,
            source_descriptor=source_descriptor,
            mesh_limits=_mesh_limits(payload),
        )
    except FacetedFallbackError as exc:
        raise JobFailure(
            exc.code,
            exc.phase,
            "Faceted STEP fallback could not complete",
            str(exc),
            recoverable=True,
            recommended_action=(
                "Re-import with source units matching project units and scale factor 1."
                if exc.code == "faceted_source_transform_unsupported"
                else "Inspect the open boundaries and increase the tolerance only when the "
                "intended seam gap is known."
            ),
        ) from exc
    progress("reimporting STEP", 94.0, "Kernel-validated faceted STEP reimport completed")
    graph_document = fallback.graph.model_dump(mode="json", by_alias=True)
    validation = json.loads((workdir / "validation.json").read_text(encoding="utf-8"))
    artifact_map: dict[str, tuple[str, str, str]] = {
        "analysis": ("analysis.json", "application/json", "analysis"),
        "sourceOriginal": ("source.original.stl", "model/stl", "source"),
        "sourceGlb": ("source.glb", "model/gltf-binary", "source-mesh"),
        "repair": ("repair.json", "application/json", "repair"),
        "repairedMesh": ("repaired.stl", "model/stl", "repaired-mesh"),
        "repairedGlb": ("repaired.glb", "model/gltf-binary", "repaired-mesh"),
        "cadgraph": ("model.cadgraph.json", "application/json", "cadgraph"),
        "cadquerySource": ("model.cq.py", "text/x-python", "cadquery-source"),
        "step": ("model.step", "model/step", "step"),
        "modelGlb": (
            "reconstructed.glb",
            "model/gltf-binary",
            "preserved-source-proxy",
        ),
        "validation": ("validation.json", "application/json", "validation"),
        "facetedFallback": (
            "faceted-fallback.json",
            "application/json",
            "faceted-fallback",
        ),
    }
    artifacts = [
        ArtifactOutput(name, name, media_type, kind)
        for key, (name, media_type, kind) in artifact_map.items()
        if key in fallback.artifacts
    ]
    if (workdir / "manifest.json").is_file():
        artifacts.append(
            ArtifactOutput("manifest.json", "manifest.json", "application/json", "manifest")
        )
    project_state = payload.get("projectState")
    prior_settings = project_state.get("settings") if isinstance(project_state, dict) else None
    settings = copy.deepcopy(prior_settings) if isinstance(prior_settings, dict) else {}
    settings.pop("candidateHistories", None)
    settings.pop("selectedCandidate", None)
    settings["facetedFallback"] = {
        "nonParametric": True,
        "sewingTolerance": sewing_tolerance,
        "units": units,
        "sourceSha256": fallback.source.metadata.sha256,
    }
    return HandlerOutput(
        result=fallback.to_dict(),
        state_patch={
            "diagnostics": fallback.source.diagnostics.to_dict(),
            "repair": fallback.repair.to_dict(),
            "cadgraph": graph_document,
            "validation": validation,
            "metrics": graph_document["fitMetrics"],
            "settings": settings,
        },
        artifacts=tuple(artifacts),
    )


def _reconstruct(payload: dict[str, Any], workdir: Path, progress: Progress) -> HandlerOutput:
    from mesh2param import ReconstructionError, ReconstructionSettings, reconstruct_file

    curved = _curved_settings(payload)
    if curved is not None:
        return _curved_reconstruct(payload, workdir, progress, curved)
    sewing_tolerance = _faceted_sewing_tolerance(payload)
    if sewing_tolerance is not None:
        return _faceted_reconstruct(payload, workdir, progress, sewing_tolerance)
    detail_mode = _automatic_detail_mode(payload)

    try:
        reconstruction_settings = ReconstructionSettings(
            mesh_limits=_mesh_limits(payload),
            segmentation=_reconstruction_segmentation_settings(payload),
            detail_mode=detail_mode,
        )
        reconstruction = reconstruct_file(
            _source_path(payload),
            workdir,
            units=str(payload.get("units", "mm")),
            settings=reconstruction_settings,
            progress_callback=lambda phase, value: progress(phase, value, None),
        )
    except ReconstructionError as exc:
        raise JobFailure(
            exc.code,
            exc.stage,
            "Automatic reconstruction could not complete",
            str(exc),
            recoverable=True,
            recommended_action=(
                "Use the explicit faceted STEP fallback for freeform geometry."
                if exc.code == "unsupported-freeform-remainder"
                else "Review the partial diagnostics or use manual feature tools."
            ),
        ) from exc

    graph_document = reconstruction.graph.model_dump(mode="json", by_alias=True)
    result = reconstruction.to_dict()
    artifact_map: dict[str, tuple[str, str, str]] = {
        "analysis": ("analysis.json", "application/json", "analysis"),
        "sourceGlb": ("source.glb", "model/gltf-binary", "source-mesh"),
        "repair": ("repair.json", "application/json", "repair"),
        "repairedMesh": ("repaired.stl", "model/stl", "repaired-mesh"),
        "repairedGlb": ("repaired.glb", "model/gltf-binary", "repaired-mesh"),
        "analysisProxyGlb": (
            "analysis-proxy.glb",
            "model/gltf-binary",
            "analysis-proxy",
        ),
        "patches": ("patches.json", "application/json", "patches"),
        "patchesGlb": ("patches.glb", "model/gltf-binary", "patches"),
        "selectionMap": ("selection-map.json", "application/json", "selection-map"),
        "frame": ("frame.json", "application/json", "frame"),
        "sketches": ("sketches.json", "application/json", "sketches"),
        "candidates": ("candidates.json", "application/json", "candidates"),
        "cadgraph": ("model.cadgraph.json", "application/json", "cadgraph"),
        "cadquerySource": ("model.cq.py", "text/x-python", "cadquery-source"),
        "step": ("model.step", "model/step", "step"),
        "modelGlb": ("reconstructed.glb", "model/gltf-binary", "reconstructed"),
        "comparison": ("metrics.json", "application/json", "metrics"),
        "residualHeatmap": ("residual.glb", "model/gltf-binary", "residual"),
        "suppressedRegions": (
            "suppressed-regions.json",
            "application/json",
            "suppressed-regions",
        ),
        "detailRegions": ("detail-regions.json", "application/json", "detail-regions"),
        "reconstruction": ("reconstruction.json", "application/json", "reconstruction"),
    }
    artifacts: list[ArtifactOutput] = []
    for key, (logical_name, media_type, kind) in artifact_map.items():
        raw_path = reconstruction.artifacts.get(key)
        if raw_path is None:
            continue
        source_path = Path(raw_path)
        destination = workdir / logical_name
        if source_path != destination:
            shutil.copyfile(source_path, destination)
        artifacts.append(ArtifactOutput(logical_name, logical_name, media_type, kind))
    if (workdir / "manifest.json").is_file():
        artifacts.append(
            ArtifactOutput("manifest.json", "manifest.json", "application/json", "manifest")
        )
    return HandlerOutput(
        result=result,
        state_patch={
            "diagnostics": reconstruction.source.diagnostics.to_dict(),
            "repair": reconstruction.repair.to_dict(),
            "analysis": reconstruction.segmentation.to_dict(),
            "patches": [patch.to_dict() for patch in reconstruction.segmentation.patches],
            "cadgraph": graph_document,
            "validation": graph_document["validation"],
            "metrics": graph_document["fitMetrics"],
            "settings": _reconstruction_project_settings(payload, result),
        },
        artifacts=tuple(artifacts),
    )


def _graph_build(
    payload: dict[str, Any], workdir: Path, progress: Progress, *, export_bundle: bool
) -> HandlerOutput:
    from mesh2param import (
        compile_cadgraph,
        export_glb,
        export_step_validated,
        ingest_mesh,
        write_cadquery_source,
    )
    from mesh2param.tessellation import write_glb
    from mesh2param_contracts import CADGraph, canonical_json
    from mesh2param_contracts.models import ImportedFacetedFeature

    payload_graph = payload.get("cadgraph")
    if not isinstance(payload_graph, dict):
        raise JobFailure(
            "cadgraph_missing",
            "building B-Rep",
            "CADGraph is missing",
            "This operation requires a validated project CADGraph.",
            recoverable=True,
            recommended_action="Reconstruct or restore a CADGraph before retrying.",
        )
    raw_graph = copy.deepcopy(payload_graph)
    surface_deviation = _validation_surface_deviation(payload)
    if surface_deviation is not None:
        project_tolerance = raw_graph.get("projectTolerance")
        if not isinstance(project_tolerance, dict):
            raise JobFailure(
                "invalid_validation_settings",
                "building B-Rep",
                "Validation settings are invalid",
                "CADGraph project tolerance is missing.",
                recoverable=True,
                recommended_action="Restore a valid CADGraph and retry validation.",
            )
        project_tolerance["surfaceDeviation"] = surface_deviation
    graph = CADGraph.model_validate(raw_graph)
    imported_features = [
        feature for feature in graph.features if isinstance(feature, ImportedFacetedFeature)
    ]
    faceted_derived = bool(imported_features)
    faceted_base = (
        len(graph.features) == 1
        and len(imported_features) == 1
        and imported_features[0].boolean_mode == "base"
    )
    artifact_resolver: dict[str, Path] = {}
    if imported_features:
        source_path = _source_path(payload)
        artifact_resolver = {
            feature.source_artifact_id: source_path for feature in imported_features
        }
    progress("building B-Rep", 30.0, "Compiling the authoritative CADGraph")
    compilation = (
        compile_cadgraph(graph, artifact_resolver=artifact_resolver)
        if artifact_resolver
        else compile_cadgraph(graph)
    )
    if not compilation.success:
        error = compilation.errors[0] if compilation.errors else None
        raise JobFailure(
            "boolean_failure" if error is not None else "invalid_brep",
            "building B-Rep",
            "CADGraph rebuild failed",
            error.kernel_error if error is not None else "The CAD kernel rejected the graph.",
            recoverable=True,
            recommended_action=(
                error.recommendation
                if error is not None
                else "Correct the failed feature and retry."
            ),
        )
    shape = compilation.require_shape()
    progress("exporting STEP", 65.0, "Exporting the validated solid")
    step = (
        export_step_validated(
            shape,
            workdir / "model.step",
            units=graph.units,
            linear_resolution=float(graph.project_tolerance.linear_resolution),
            require_tessellation=False,
        )
        if faceted_base
        else export_step_validated(shape, workdir / "model.step", units=graph.units)
    )
    progress("reimporting STEP", 82.0, "STEP reimport validation completed")
    tolerance_satisfied = (
        None
        if faceted_derived
        else (
            graph.fit_metrics.p95_surface_distance <= graph.project_tolerance.surface_deviation
            and graph.fit_metrics.max_surface_distance <= graph.project_tolerance.surface_deviation
        )
    )
    validation_status = (
        "partial"
        if faceted_derived and step.valid
        else "valid"
        if step.valid and tolerance_satisfied is True
        else "invalid"
    )
    graph_document = graph.model_dump(mode="json", by_alias=True)
    graph_document["validation"] = {
        "status": validation_status,
        "brepValid": step.source.valid,
        "stepReimportValid": step.reimport.valid,
        "toleranceSatisfied": tolerance_satisfied,
        "checkedAt": graph.validation.checked_at,
        "lastValidFeatureId": graph.validation.last_valid_feature_id,
        "issues": [
            issue.model_dump(mode="json", by_alias=True) for issue in graph.validation.issues
        ],
    }
    final_graph = CADGraph.model_validate(graph_document)
    graph_path = workdir / "model.cadgraph.json"
    graph_path.write_text(canonical_json(final_graph), encoding="utf-8", newline="\n")
    generated_artifact_paths = (
        {feature.source_artifact_id: "source.original.stl" for feature in imported_features}
        if imported_features
        else None
    )
    if generated_artifact_paths is None:
        write_cadquery_source(final_graph, workdir / "model.cq.py")
    else:
        write_cadquery_source(
            final_graph,
            workdir / "model.cq.py",
            artifact_paths=generated_artifact_paths,
        )
    if imported_features:
        shutil.copyfile(_source_path(payload), workdir / "source.original.stl")
    if faceted_base:
        faceted_source = ingest_mesh(_source_path(payload), limits=_mesh_limits(payload))
        write_glb(_mesh_tessellation(faceted_source.mesh), workdir / "reconstructed.glb")
    else:
        export_glb(shape, workdir / "reconstructed.glb")
    validation = {
        "status": validation_status,
        "brepValid": step.source.valid,
        "stepReimportValid": step.reimport.valid,
        "toleranceSatisfied": tolerance_satisfied,
        "step": step.to_dict(),
        "compilation": compilation.to_dict(),
    }
    if faceted_derived:
        validation["facetedFallback"] = {
            "nonParametric": True,
            "sewingTolerance": imported_features[0].sewing_tolerance,
            "sewingToleranceUnits": graph.units,
            "importedFeatureCount": len(imported_features),
            "sourcePreserved": True,
            "geometricDeviationMeasured": False,
            "browserTessellation": ("preserved-source-proxy" if faceted_base else "kernel-result"),
            "browserTessellationRepresentsKernelResult": not faceted_base,
        }
    _json(workdir / "validation.json", validation)
    artifacts = [
        ArtifactOutput("model.step", "model.step", "model/step", "step"),
        ArtifactOutput(
            "model.cadgraph.json", "model.cadgraph.json", "application/json", "cadgraph"
        ),
        ArtifactOutput("model.cq.py", "model.cq.py", "text/x-python", "cadquery-source"),
        ArtifactOutput(
            "reconstructed.glb",
            "reconstructed.glb",
            "model/gltf-binary",
            "preserved-source-proxy" if faceted_base else "reconstructed",
        ),
        ArtifactOutput("validation.json", "validation.json", "application/json", "validation"),
    ]
    if imported_features:
        artifacts.append(
            ArtifactOutput("source.original.stl", "source.original.stl", "model/stl", "source")
        )
    if export_bundle:
        from mesh2param_api.storage import validate_artifact_name

        reserved_names = {artifact.name for artifact in artifacts} | {
            "manifest.json",
            "mesh2param-export.zip",
            "project.mesh2param.json",
        }
        prior_artifacts = payload.get("priorArtifacts", [])
        if not isinstance(prior_artifacts, list) or len(prior_artifacts) > 128:
            raise JobFailure(
                "invalid_prior_artifacts",
                "finalizing artifacts",
                "Prior artifact list is invalid",
                "The persisted export artifact list exceeded its structural limit.",
                recoverable=True,
                recommended_action="Rebuild project artifacts and retry export.",
            )
        for raw in prior_artifacts:
            if not isinstance(raw, dict):
                raise JobFailure(
                    "invalid_prior_artifacts",
                    "finalizing artifacts",
                    "Prior artifact descriptor is invalid",
                    "A persisted export artifact descriptor was not an object.",
                    recoverable=True,
                    recommended_action="Rebuild project artifacts and retry export.",
                )
            name = validate_artifact_name(str(raw.get("name", "")))
            if name in reserved_names:
                continue
            relative = Path(str(raw.get("path", "")))
            candidate = (workdir / relative).resolve()
            try:
                candidate.relative_to(workdir.resolve())
            except ValueError as exc:
                raise JobFailure(
                    "unsafe_prior_artifact",
                    "finalizing artifacts",
                    "Prior artifact path is unsafe",
                    "A staged prior artifact escaped the isolated job directory.",
                    recoverable=False,
                    recommended_action=None,
                ) from exc
            if not candidate.is_file() or candidate.is_symlink():
                raise JobFailure(
                    "prior_artifact_missing",
                    "finalizing artifacts",
                    "Prior artifact is unavailable",
                    f"The staged artifact {name!r} is missing or unsafe.",
                    recoverable=True,
                    recommended_action="Rebuild project artifacts and retry export.",
                )
            artifacts.append(
                ArtifactOutput(
                    name,
                    str(relative),
                    str(raw.get("mediaType", "application/octet-stream"))[:160],
                    str(raw.get("kind", "artifact"))[:40],
                )
            )
            reserved_names.add(name)
        project_document = payload.get("projectState", {})
        _json(workdir / "project.mesh2param.json", project_document)
        artifacts.append(
            ArtifactOutput(
                "project.mesh2param.json",
                "project.mesh2param.json",
                "application/json",
                "project",
            )
        )
        manifest_records = []
        for artifact in artifacts:
            artifact_path = workdir / artifact.path
            content = artifact_path.read_bytes()
            manifest_records.append(
                {
                    "name": artifact.name,
                    "byteSize": len(content),
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "mediaType": artifact.media_type,
                }
            )
        manifest = {
            "schemaVersion": "1.0.0",
            "projectId": payload.get("projectId"),
            "projectName": payload.get("projectName"),
            "modelVersionId": payload.get("versionId"),
            "parentVersionId": payload.get("parentVersionId"),
            "source": payload.get("source"),
            "internalUnits": final_graph.units,
            "engineVersion": final_graph.engine_versions.mesh2param,
            "schemaVersions": {
                "cadgraph": final_graph.schema_version,
                "manifest": "1.0.0",
            },
            "dependencyVersions": final_graph.engine_versions.model_dump(
                mode="json", by_alias=True
            ),
            "settings": payload.get("settings", {}),
            "validation": validation,
            "timestamp": payload.get("timestamp"),
            "artifacts": sorted(manifest_records, key=lambda item: str(item["name"])),
        }
        _json(workdir / "manifest.json", manifest)
        artifacts.append(
            ArtifactOutput("manifest.json", "manifest.json", "application/json", "manifest")
        )
        bundle_path = workdir / "mesh2param-export.zip"
        with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for artifact in sorted(artifacts, key=lambda item: item.name):
                info = zipfile.ZipInfo(artifact.name, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, (workdir / artifact.path).read_bytes())
        artifacts.append(
            ArtifactOutput(
                "mesh2param-export.zip",
                "mesh2param-export.zip",
                "application/zip",
                "export-bundle",
            )
        )
    progress("finalizing artifacts", 98.0, "Validated output artifacts finalized")
    return HandlerOutput(
        result={
            "validation": validation,
            "artifactValidationState": validation_status,
        },
        state_patch={"cadgraph": graph_document, "validation": validation},
        artifacts=tuple(artifacts),
    )


def _sample_open(payload: dict[str, Any], workdir: Path, progress: Progress) -> HandlerOutput:
    from mesh2param import ingest_mesh
    from mesh2param.samples import (
        AUTOMATIC_RECONSTRUCTION_SAMPLE_SCOPE,
        generate_sample,
        sample_spec,
    )
    from mesh2param.tessellation import write_glb

    slug = str(payload.get("sampleId", ""))
    spec = sample_spec(slug)
    progress("building B-Rep", 15.0, "Generating the procedural sample through CADGraph")
    generated = generate_sample(spec, workdir)
    sample_dir = Path(generated.directory)
    graph = json.loads((sample_dir / "model.cadgraph.json").read_text(encoding="utf-8"))
    metadata = json.loads((sample_dir / "metadata.json").read_text(encoding="utf-8"))
    source = ingest_mesh(sample_dir / "source-random.stl", limits=_mesh_limits(payload))
    write_glb(_mesh_tessellation(source.mesh), workdir / "source.glb")
    automatic_reconstruction: dict[str, Any] = {
        "supported": spec.automatic_reconstruction_supported,
        "sampleId": slug,
    }
    if not spec.automatic_reconstruction_supported:
        automatic_reconstruction["reason"] = (
            f"{AUTOMATIC_RECONSTRUCTION_SAMPLE_SCOPE} "
            "This exact sample already includes an editable CADGraph."
        )
    artifacts = (
        ArtifactOutput("source-high.stl", f"{slug}/source-high.stl", "model/stl", "source"),
        ArtifactOutput("source-low.stl", f"{slug}/source-low.stl", "model/stl", "source"),
        ArtifactOutput("source-random.stl", f"{slug}/source-random.stl", "model/stl", "source"),
        ArtifactOutput("source.glb", "source.glb", "model/gltf-binary", "source-mesh"),
        ArtifactOutput("model.step", f"{slug}/model.step", "model/step", "step"),
        ArtifactOutput(
            "model.cadgraph.json",
            f"{slug}/model.cadgraph.json",
            "application/json",
            "cadgraph",
        ),
        ArtifactOutput("model.cq.py", f"{slug}/model.cq.py", "text/x-python", "cadquery-source"),
        ArtifactOutput("reconstructed.glb", f"{slug}/model.glb", "model/gltf-binary", "model"),
        ArtifactOutput("manifest.json", f"{slug}/manifest.json", "application/json", "manifest"),
        ArtifactOutput("metadata.json", f"{slug}/metadata.json", "application/json", "metadata"),
    )
    progress("finalizing artifacts", 98.0, "Procedural sample artifacts validated")
    return HandlerOutput(
        result={
            "sampleId": slug,
            "metadata": metadata,
            "sourceAsset": {
                "artifactName": "source-random.stl",
                "originalFileName": "source-random.stl",
                "format": "stl",
                "encoding": "binary",
                "declaredUnits": "mm",
                "scaleFactor": 1.0,
            },
        },
        state_patch={
            "cadgraph": graph,
            "validation": graph["validation"],
            "metrics": graph["fitMetrics"],
            "settings": {"automaticReconstruction": automatic_reconstruction},
        },
        artifacts=artifacts,
    )


def run_handler(
    kind: str, payload: dict[str, Any], workdir: Path, progress: Progress
) -> HandlerOutput:
    if kind == "upload":
        return _upload(payload, workdir, progress)
    if kind == "repair":
        return _repair(payload, workdir, progress)
    if kind == "analyze":
        return _analyze(payload, workdir, progress)
    if kind == "reconstruct":
        return _reconstruct(payload, workdir, progress)
    if kind in {"rebuild", "validate"}:
        return _graph_build(payload, workdir, progress, export_bundle=False)
    if kind == "export":
        return _graph_build(payload, workdir, progress, export_bundle=True)
    if kind == "sample_open":
        return _sample_open(payload, workdir, progress)
    if kind == "test_crash":
        os._exit(73)
    if kind == "test_hang":
        while True:
            time.sleep(60)
    raise JobFailure(
        "unsupported_operation",
        "starting worker",
        "Unsupported job operation",
        f"The trusted worker has no handler for {kind!r}.",
        recoverable=False,
        recommended_action=None,
    )


__all__ = ["ArtifactOutput", "HandlerOutput", "JobFailure", "run_handler"]
