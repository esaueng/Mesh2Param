from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

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
    from mesh2param.tessellation import write_binary_stl

    source = ingest_mesh(_source_path(payload), limits=_mesh_limits(payload))
    progress("repairing", 25.0, "Applying explicit configured repair operations")
    repaired = repair_mesh(source, limits=_mesh_limits(payload))
    result = repaired.to_dict()
    _json(workdir / "analysis.json", source.to_dict())
    _json(workdir / "repair.json", result)
    write_binary_stl(_mesh_tessellation(repaired.mesh), workdir / "repaired.stl")
    progress("finalizing artifacts", 95.0, "Repair artifacts written")
    return HandlerOutput(
        result=result,
        state_patch={"diagnostics": source.diagnostics.to_dict(), "repair": result},
        artifacts=(
            ArtifactOutput("analysis.json", "analysis.json", "application/json", "analysis"),
            ArtifactOutput("repair.json", "repair.json", "application/json", "repair"),
            ArtifactOutput("repaired.stl", "repaired.stl", "model/stl", "repaired-mesh"),
        ),
    )


def _analyze(payload: dict[str, Any], workdir: Path, progress: Progress) -> HandlerOutput:
    from mesh2param import ingest_mesh, repair_mesh, segment_mesh
    from mesh2param.selection import write_patch_selection_artifacts
    from mesh2param.tessellation import write_binary_stl

    source = ingest_mesh(_source_path(payload), limits=_mesh_limits(payload))
    progress("repairing", 15.0, "Preparing a non-destructive analysis mesh")
    repaired = repair_mesh(source, limits=_mesh_limits(payload))
    write_binary_stl(_mesh_tessellation(repaired.mesh), workdir / "repaired.stl")
    progress("sharp boundaries", 35.0, "Computing adjacency and sharp boundaries")
    segmentation = segment_mesh(repaired.mesh)
    progress("fitting cylinders", 75.0, "Plane and cylinder fitting completed")
    selection = write_patch_selection_artifacts(
        repaired.mesh,
        segmentation.patches,
        workdir / "patches.glb",
        workdir / "selection-map.json",
    )
    analysis = source.to_dict()
    repair = repaired.to_dict()
    segmented = segmentation.to_dict()
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
            ArtifactOutput("repair.json", "repair.json", "application/json", "repair"),
            ArtifactOutput("repaired.stl", "repaired.stl", "model/stl", "repaired-mesh"),
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


def _reconstruct(payload: dict[str, Any], workdir: Path, progress: Progress) -> HandlerOutput:
    from mesh2param import ReconstructionError, reconstruct_file

    try:
        reconstruction = reconstruct_file(
            _source_path(payload),
            workdir,
            units=str(payload.get("units", "mm")),
            progress_callback=lambda phase, value: progress(phase, value, None),
        )
    except ReconstructionError as exc:
        raise JobFailure(
            exc.code,
            exc.stage,
            "Automatic reconstruction could not complete",
            str(exc),
            recoverable=True,
            recommended_action="Review the partial diagnostics or use manual feature tools.",
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
        write_cadquery_source,
    )
    from mesh2param_contracts import CADGraph, canonical_json

    raw_graph = payload.get("cadgraph")
    if not isinstance(raw_graph, dict):
        raise JobFailure(
            "cadgraph_missing",
            "building B-Rep",
            "CADGraph is missing",
            "This operation requires a validated project CADGraph.",
            recoverable=True,
            recommended_action="Reconstruct or restore a CADGraph before retrying.",
        )
    graph = CADGraph.model_validate(raw_graph)
    progress("building B-Rep", 30.0, "Compiling the authoritative CADGraph")
    compilation = compile_cadgraph(graph)
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
    step = export_step_validated(shape, workdir / "model.step", units=graph.units)
    progress("reimporting STEP", 82.0, "STEP reimport validation completed")
    graph_path = workdir / "model.cadgraph.json"
    graph_path.write_text(canonical_json(graph), encoding="utf-8", newline="\n")
    write_cadquery_source(graph, workdir / "model.cq.py")
    export_glb(shape, workdir / "reconstructed.glb")
    validation = {
        "status": "valid" if step.valid else "step-reimport-failed",
        "brepValid": step.source.valid,
        "stepReimportValid": step.reimport.valid,
        "toleranceSatisfied": graph.validation.tolerance_satisfied,
        "step": step.to_dict(),
        "compilation": compilation.to_dict(),
    }
    _json(workdir / "validation.json", validation)
    artifacts = [
        ArtifactOutput("model.step", "model.step", "model/step", "step"),
        ArtifactOutput(
            "model.cadgraph.json", "model.cadgraph.json", "application/json", "cadgraph"
        ),
        ArtifactOutput("model.cq.py", "model.cq.py", "text/x-python", "cadquery-source"),
        ArtifactOutput(
            "reconstructed.glb", "reconstructed.glb", "model/gltf-binary", "reconstructed"
        ),
        ArtifactOutput(
            "validation.json", "validation.json", "application/json", "validation"
        ),
    ]
    if export_bundle:
        from mesh2param_api.storage import validate_artifact_name

        reserved_names = {
            artifact.name for artifact in artifacts
        } | {"manifest.json", "mesh2param-export.zip", "project.mesh2param.json"}
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
            "internalUnits": graph.units,
            "engineVersion": graph.engine_versions.mesh2param,
            "schemaVersions": {"cadgraph": graph.schema_version, "manifest": "1.0.0"},
            "dependencyVersions": graph.engine_versions.model_dump(mode="json", by_alias=True),
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
            "artifactValidationState": "valid" if step.valid else "invalid",
        },
        state_patch={"cadgraph": raw_graph, "validation": validation},
        artifacts=tuple(artifacts),
    )


def _sample_open(payload: dict[str, Any], workdir: Path, progress: Progress) -> HandlerOutput:
    from mesh2param.samples import generate_sample, sample_spec

    slug = str(payload.get("sampleId", ""))
    spec = sample_spec(slug)
    progress("building B-Rep", 15.0, "Generating the procedural sample through CADGraph")
    generated = generate_sample(spec, workdir)
    sample_dir = Path(generated.directory)
    graph = json.loads((sample_dir / "model.cadgraph.json").read_text(encoding="utf-8"))
    metadata = json.loads((sample_dir / "metadata.json").read_text(encoding="utf-8"))
    artifacts = (
        ArtifactOutput("source-high.stl", f"{slug}/source-high.stl", "model/stl", "source"),
        ArtifactOutput("source-low.stl", f"{slug}/source-low.stl", "model/stl", "source"),
        ArtifactOutput(
            "source-random.stl", f"{slug}/source-random.stl", "model/stl", "source"
        ),
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
