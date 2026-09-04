"""Build, ingest and index the real-world benchmark corpus under ``samples/real``.

Every artifact this module writes is byte-deterministic: STEP headers are stripped of
their export timestamp, STL tessellation is driven by fixed tolerances, and JSON is
serialized with sorted keys.
"""

from __future__ import annotations

import importlib
import os
import re
import shutil
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol

import cadquery as cq
import trimesh
from OCP.BRepTools import BRepTools
from OCP.TopoDS import TopoDS_Shape

from .audit import (
    EXPORT_3MF_MESH_ROLE,
    EXPORT_MESH_ROLE,
    FINE_MESH_ROLE,
    GENERATED_MESH_ROLES,
    PART_JSON,
    SCHEMA_VERSION,
    SOURCE_FORMATS,
    STEP_FILE,
    CorpusError,
    MeshRole,
    PartMetadata,
    audit_directory,
    dump_json,
    load_step_shape,
    read_part_json,
    read_part_metadata,
    sha256_file,
    write_part_json,
)
from .threemf import read_3mf

DEFAULT_ROOT = Path("samples/real")
MANIFEST_FILE = "manifest.json"
README_FILE = "README.md"
REPOSITORY_LICENSE = "Apache-2.0 (repository)"

#: Fixed value substituted for the STEP header time stamp. Same width as the value OCCT
#: writes, so header line wrapping is untouched.
STEP_EPOCH = "1970-01-01T00:00:00"

_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_STEP_STRING = re.compile(r"'(?:[^']|'')*'")
#: OCCT appends a per-process export counter to its translator product name.
_STEP_TRANSLATOR = re.compile(r"(Open CASCADE STEP translator [0-9.]+) \d+")

#: Development override so the tooling can be exercised against a stand-in part library.
_PARTS_MODULE_ENV = "MESH2PARAM_REAL_CORPUS_PARTS"


class PartSpecLike(Protocol):
    """Structural view of ``scripts.real_corpus.parts.PartSpec``."""

    slug: str
    title: str
    tags: tuple[str, ...]
    build: Callable[[], cq.Workplane]
    units: str
    notes: str


def load_part_specs() -> tuple[PartSpecLike, ...]:
    name = os.environ.get(_PARTS_MODULE_ENV) or f"{__package__}.parts"
    try:
        module = importlib.import_module(name)
    except ImportError as exc:
        raise CorpusError(f"cannot import the part library {name!r}: {exc}") from exc
    specs: tuple[PartSpecLike, ...] = tuple(module.PARTS)
    return specs


def validate_slug(slug: str) -> str:
    if not _SLUG_PATTERN.match(slug):
        raise CorpusError(f"invalid slug {slug!r}; use lowercase words joined by hyphens")
    return slug


def _statement_end(text: str, start: int) -> int:
    """Index just past the ``;`` closing the STEP statement beginning at ``start``."""

    index = start
    in_string = False
    while index < len(text):
        char = text[index]
        if in_string:
            if char == "'":
                if text[index + 1 : index + 2] == "'":
                    index += 2
                    continue
                in_string = False
        elif char == "'":
            in_string = True
        elif char == ";":
            return index + 1
        index += 1
    raise CorpusError("unterminated STEP statement")


def normalize_step_file(path: Path, *, strict: bool = True) -> bool:
    """Strip the two things OCCT writes that differ between otherwise identical exports.

    Those are the ``FILE_NAME`` time stamp and the per-process counter OCCT appends to
    its translator product name (the second export in one process says ``... 7.9 2``).
    Returns ``True`` when the file was rewritten. With ``strict=False`` a file without a
    usable ``FILE_NAME`` entry (a hand-rolled or non-conforming STEP) keeps its header.
    """

    original = path.read_text(encoding="utf-8", errors="surrogateescape")
    text = _normalized_step_text(original, path, strict=strict)
    if text == original:
        return False
    path.write_text(text, encoding="utf-8")
    return True


def _normalized_step_text(text: str, path: Path, *, strict: bool) -> str:
    text = _STEP_TRANSLATOR.sub(r"\1 1", text)
    start = text.find("FILE_NAME(")
    if start < 0:
        if strict:
            raise CorpusError(f"STEP file has no FILE_NAME header: {path}")
        return text

    end = _statement_end(text, start)
    header = text[start:end]
    literals = list(_STEP_STRING.finditer(header))
    if len(literals) < 2:
        if strict:
            raise CorpusError(f"STEP FILE_NAME header has no time stamp: {path}")
        return text

    stamp = literals[1]
    header = f"{header[: stamp.start()]}'{STEP_EPOCH}'{header[stamp.end() :]}"
    return f"{text[:start]}{header}{text[end:]}"


def export_step(shape: cq.Shape | cq.Workplane, path: Path) -> Path:
    """Write a normalized STEP file for ``shape``."""

    cq.exporters.export(shape, str(path), "STEP")
    normalize_step_file(path)
    return path


def _raw_shape(shape: cq.Shape | cq.Workplane) -> TopoDS_Shape | None:
    inner = shape.val() if isinstance(shape, cq.Workplane) else shape
    if not isinstance(inner, cq.Shape):
        return None
    wrapped: TopoDS_Shape | None = inner.wrapped
    return wrapped


def export_meshes(
    shape: cq.Shape | cq.Workplane,
    directory: Path,
    roles: Iterable[MeshRole] = GENERATED_MESH_ROLES,
) -> list[Path]:
    """Tessellate ``shape`` once per role and write binary STLs into ``directory``."""

    written: list[Path] = []
    for role in roles:
        if role.linear_tolerance is None or role.angular_tolerance is None:
            raise CorpusError(f"mesh role {role.tessellation!r} has no tolerances to mesh with")
        raw = _raw_shape(shape)
        if raw is not None:
            # Drop any triangulation left by a previous role: OCCT keeps a stored mesh
            # when the new deflection is looser, which would make output order-dependent.
            BRepTools.Clean_s(raw)
        path = directory / role.filename
        cq.exporters.export(
            shape,
            str(path),
            exportType="STL",
            tolerance=role.linear_tolerance,
            angularTolerance=role.angular_tolerance,
        )
        written.append(path)
    return written


def _prune_stale_meshes(directory: Path, keep: Iterable[Path]) -> None:
    kept = {path.name for path in keep}
    for path in directory.glob("*.stl"):
        if path.name not in kept:
            path.unlink()


def part_directories(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(
        (path for path in root.iterdir() if path.is_dir() and (path / PART_JSON).is_file()),
        key=lambda path: path.name,
    )


def _tessellation_roles(with_fine: bool) -> tuple[MeshRole, ...]:
    return GENERATED_MESH_ROLES + ((FINE_MESH_ROLE,) if with_fine else ())


def generate(root: Path, only: str | None = None, *, with_fine: bool = False) -> list[str]:
    """Rebuild STEP + STL + ``part.json`` for every part in the library."""

    specs = load_part_specs()
    if only is not None:
        specs = tuple(spec for spec in specs if spec.slug == only)
        if not specs:
            raise CorpusError(f"no part with slug {only!r} in the part library")

    slugs: list[str] = []
    for spec in specs:
        slug = validate_slug(spec.slug)
        directory = root / slug
        directory.mkdir(parents=True, exist_ok=True)

        workplane = spec.build()
        solids = workplane.solids().vals()
        if len(solids) != 1:
            raise CorpusError(f"part {slug!r} built {len(solids)} solids; exactly one is required")
        shape = solids[0]
        if not isinstance(shape, cq.Shape):
            raise CorpusError(f"part {slug!r} did not build a shape")

        export_step(shape, directory / STEP_FILE)
        written = export_meshes(shape, directory, _tessellation_roles(with_fine))
        _prune_stale_meshes(directory, written)

        metadata = PartMetadata(
            slug=slug,
            title=spec.title,
            origin="generated",
            license=REPOSITORY_LICENSE,
            units=spec.units,
            tags=tuple(spec.tags),
            notes=spec.notes,
        )
        write_part_json(directory, audit_directory(directory, metadata))
        slugs.append(slug)
    return slugs


def write_binary_stl(vertices: Any, triangles: Any, path: Path) -> Path:
    """Write a triangle soup as a binary STL, without letting trimesh weld anything."""

    mesh = trimesh.Trimesh(vertices=vertices, faces=triangles, process=False)
    path.write_bytes(trimesh.exchange.stl.export_stl(mesh))
    return path


def _convert_3mf(source: Path, directory: Path, units: str) -> dict[str, Any]:
    parsed = read_3mf(source)
    scaled = parsed.scaled_to(units)
    path = directory / EXPORT_3MF_MESH_ROLE.filename
    write_binary_stl(scaled.vertices, scaled.triangles, path)
    return {
        "sourceFormat": "3mf",
        "sourceSha256": sha256_file(source),
        "sourceUnit": parsed.unit,
    }


def _classify_source(source: Path) -> str:
    if not source.is_file():
        raise CorpusError(f"source file not found: {source}")
    fmt = SOURCE_FORMATS.get(source.suffix.lower())
    if fmt is None:
        raise CorpusError(
            f"unsupported source type {source.suffix!r}; expected .step/.stp/.stl/.3mf"
        )
    return fmt


def ingest(
    sources: Path | Sequence[Path],
    root: Path,
    metadata: PartMetadata,
    *,
    force: bool = False,
    with_fine: bool = False,
) -> Path:
    """Copy user-supplied STEP/STL/3MF files into one corpus part and audit them.

    A STEP becomes the ground truth plus the standard tessellation ladder; every mesh
    file becomes an extra ``export`` entry that records the format it came from.
    """

    paths = [sources] if isinstance(sources, Path) else list(sources)
    if not paths:
        raise CorpusError("ingest needs at least one source file")

    by_format: dict[str, Path] = {}
    for source in paths:
        fmt = _classify_source(source)
        if fmt in by_format:
            raise CorpusError(f"two {fmt} sources given for one slug: {by_format[fmt]}, {source}")
        by_format[fmt] = source

    slug = validate_slug(metadata.slug)
    directory = root / slug
    if directory.exists() and any(directory.iterdir()) and not force:
        raise CorpusError(f"slug {slug!r} already exists at {directory}; pass --force to replace")
    if directory.exists():
        shutil.rmtree(directory)
    directory.mkdir(parents=True)

    provenance: dict[str, dict[str, Any]] = {}
    step_source = by_format.get("step")
    if step_source is not None:
        step_path = directory / STEP_FILE
        shutil.copyfile(step_source, step_path)
        normalize_step_file(step_path, strict=False)
        # Round-trip through the kernel so the STLs come from the same B-Rep the
        # audit reads back, not from whatever the authoring tool would have meshed.
        shape = cq.Shape(load_step_shape(step_path))
        for path in export_meshes(shape, directory, _tessellation_roles(with_fine)):
            provenance[path.name] = {
                "sourceFormat": "step",
                "sourceSha256": None,
                "sourceUnit": None,
            }

    stl_source = by_format.get("stl")
    if stl_source is not None:
        shutil.copyfile(stl_source, directory / EXPORT_MESH_ROLE.filename)
        provenance[EXPORT_MESH_ROLE.filename] = {
            "sourceFormat": "stl",
            "sourceSha256": sha256_file(stl_source),
            "sourceUnit": None,
        }

    threemf_source = by_format.get("3mf")
    if threemf_source is not None:
        provenance[EXPORT_3MF_MESH_ROLE.filename] = _convert_3mf(
            threemf_source, directory, metadata.units
        )

    write_part_json(directory, audit_directory(directory, metadata, provenance))
    return directory


def audit_all(root: Path, only: str | None = None) -> list[str]:
    """Recompute ``part.json`` for every existing part directory."""

    directories = part_directories(root)
    if only is not None:
        directories = [path for path in directories if path.name == only]
        if not directories:
            raise CorpusError(f"no audited part directory named {only!r} under {root}")
    if not directories:
        raise CorpusError(f"no part directories with {PART_JSON} under {root}")

    slugs: list[str] = []
    for directory in directories:
        metadata = read_part_metadata(directory)
        write_part_json(directory, audit_directory(directory, metadata))
        slugs.append(directory.name)
    return slugs


def _format_inventory(inventory: Mapping[str, int]) -> str:
    ordered = sorted(
        ((name, count) for name, count in inventory.items() if count),
        key=lambda item: (-item[1], item[0]),
    )
    return ", ".join(f"{name} {count}" for name, count in ordered) or "-"


def _surface_summary(ground_truth: dict[str, Any] | None) -> str:
    """Merged analytic surfaces: what a segmenter is actually expected to recover."""

    if not ground_truth:
        return "-"
    inventory: dict[str, int] = ground_truth.get(
        "surfaceInventoryMerged", ground_truth.get("surfaceInventory", {})
    )
    return _format_inventory(inventory)


def _raw_surface_summary(ground_truth: dict[str, Any] | None) -> str:
    """Per-face surface types, exactly as the STEP file splits them."""

    if not ground_truth:
        return "-"
    return _format_inventory(ground_truth.get("surfaceInventory", {}))


def _mesh_label(mesh: dict[str, Any]) -> str:
    """``coarse``/``fine``/... for tessellations, ``export(3mf)`` for ingested meshes."""

    if mesh["tessellation"] != "export":
        return str(mesh["tessellation"])
    return f"export({mesh.get('sourceFormat', 'stl')})"


def _triangle_summary(meshes: Sequence[dict[str, Any]]) -> str:
    if not meshes:
        return "-"
    return " / ".join(f"{_mesh_label(mesh)} {mesh['triangles']}" for mesh in meshes)


def _manifold_summary(meshes: Sequence[dict[str, Any]]) -> str:
    if not meshes:
        return "-"
    parts: list[str] = []
    for mesh in meshes:
        flags = [
            "watertight" if mesh["watertight"] else "!watertight",
            "manifold" if mesh["edgeManifold"] else "!manifold",
            "winding" if mesh["windingConsistent"] else "!winding",
        ]
        broken = [flag for flag in flags if flag.startswith("!")]
        parts.append(f"{_mesh_label(mesh)} {'ok' if not broken else ' '.join(broken)}")
    return ", ".join(parts)


_README_HEADER = """<!-- Generated by `pnpm corpus:index`; do not edit. -->

# Real-world benchmark corpus

Mesh-to-STEP reconstruction fixtures that look like parts a person would actually
model. Each subdirectory holds one part:

| file | meaning |
| --- | --- |
| `model.step` | exact B-Rep ground truth (absent for mesh-only parts) |
| `mesh-coarse.stl` | tessellation at linear 0.5 / angular 0.5 |
| `mesh-default.stl` | tessellation at linear 0.1 / angular 0.1 |
| `mesh-fine.stl` | linear 0.01 / angular 0.05; opt-in via `--with-fine`, not committed |
| `mesh-export.stl` | user-supplied STL, kept byte-for-byte |
| `mesh-export-3mf.stl` | user-supplied 3MF, converted to binary STL on ingest |
| `part.json` | metadata plus the audit of every file above |

Each `meshes[]` entry records `sourceFormat` (`step`, `stl` or `3mf`), the SHA-256 of the
original file when it was converted, and the unit the source declared.

Regenerate the procedural parts with `pnpm corpus:generate`, refresh `manifest.json`
and this table with `pnpm corpus:index`, and re-derive every `part.json` from the files
on disk with `uv run --frozen python -m scripts.real_corpus audit`.

The writer is deterministic: the STEP header time stamp and OCCT's per-process export
counter are normalized away, tessellation tolerances are fixed, and JSON is written with
sorted keys and 9-significant-digit floats. A handful of parts still re-export with
different bytes because OCCT's own modelling operations (chamfer, fillet, boolean plus
`clean`) emit an isomorphic B-Rep with its face bounds in a different order from run to
run. Where that happens the topology counts, surface inventory and triangle counts are
unchanged -- only the SHA-256 moves -- so compare those, not the bytes, when checking a
regeneration.

The `surfaces` column counts *analytic surfaces*, not STEP faces: adjacent faces that
share one carrier surface (a bore emitted as two half cylinders, a plane a boolean cut in
two) are merged, which is what `groundTruth.surfaceInventoryMerged` records and what a
segmenter is expected to recover. `raw surfaces` is the unmerged per-face inventory
(`groundTruth.surfaceInventory`). Merging needs a shared edge, so two coplanar but
disjoint pads stay two surfaces; b-splines and the other free-form types are never merged
and are counted together under `other`.

`holeCount` is a corpus statistic, not a feature recognizer. Inward-facing cylindrical
faces (surface normal, flipped for a `REVERSED` face, pointing back toward the axis) are
grouped by axis and radius; faces whose axial extents overlap are merged, and each merged
run whose angular sweeps add up to a full revolution counts as one hole. A bore that an
exporter split into two half-cylinders therefore counts once, while coaxial holes through
separate walls count separately. Blind holes and every stage of a stepped bore count;
countersinks, bosses, and the outer wall of a tube do not.

"""


def _featured_section(records: Sequence[dict[str, Any]]) -> str:
    featured = [record for record in records if record.get("featured")]
    if not featured:
        return ""
    names = ", ".join(f"`{record['slug']}` ({record['title']})" for record in featured)
    label = "Featured part" if len(featured) == 1 else "Featured parts"
    return f"## {label}\n\nStart here: {names}. Featured parts lead the table below.\n\n"


def render_readme(records: Sequence[dict[str, Any]]) -> str:
    rows = [
        "| slug | origin | license | tags | faces | surfaces | raw surfaces | holes "
        "| triangles | manifold |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for record in records:
        ground_truth: dict[str, Any] | None = record.get("groundTruth")
        meshes: list[dict[str, Any]] = record.get("meshes", [])
        rows.append(
            "| {slug} | {origin} | {license} | {tags} | {faces} | {surfaces} | {raw_surfaces} "
            "| {holes} | {triangles} | {manifold} |".format(
                slug=f"**{record['slug']}**" if record.get("featured") else record["slug"],
                origin=record["origin"],
                license=record["license"],
                tags=", ".join(record.get("tags", ())) or "-",
                faces=ground_truth["faceCount"] if ground_truth else "-",
                surfaces=_surface_summary(ground_truth),
                raw_surfaces=_raw_surface_summary(ground_truth),
                holes=ground_truth["holeCount"] if ground_truth else "-",
                triangles=_triangle_summary(meshes),
                manifold=_manifold_summary(meshes),
            )
        )
    return _README_HEADER + _featured_section(records) + "\n".join(rows) + "\n"


def sort_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Featured parts first, then alphabetically by slug."""

    return sorted(records, key=lambda record: (not record.get("featured"), str(record.get("slug"))))


def index(root: Path) -> int:
    """Write ``manifest.json`` and regenerate ``README.md``; returns the part count."""

    records = sort_records([read_part_json(directory) for directory in part_directories(root)])
    root.mkdir(parents=True, exist_ok=True)
    (root / MANIFEST_FILE).write_text(
        dump_json({"schemaVersion": SCHEMA_VERSION, "parts": records}), encoding="utf-8"
    )
    (root / README_FILE).write_text(render_readme(records), encoding="utf-8")
    return len(records)
