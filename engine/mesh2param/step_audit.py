"""OCCT-independent structural audit of STEP Part 21 files (Milestone 4).

The kernel round-trip in ``validation.py`` proves that OCCT can rebuild what
OCCT wrote; this module is the second, independent pair of eyes. It parses the
exchange structure directly -- no geometry kernel -- and checks that the file
is well-formed Part 21, that every entity reference resolves, and that the
B-Rep entity inventory matches what the reconstruction claims (one manifold
solid, expected surface-type counts). It cannot judge geometric validity;
verification inside an independent CAD application remains a manual release
step documented in the design doc.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SURFACE_ENTITY_KINDS: dict[str, str] = {
    "PLANE": "plane",
    "CYLINDRICAL_SURFACE": "cylinder",
    "CONICAL_SURFACE": "cone",
    "SPHERICAL_SURFACE": "sphere",
    "TOROIDAL_SURFACE": "torus",
    "B_SPLINE_SURFACE_WITH_KNOTS": "bspline",
    "RATIONAL_B_SPLINE_SURFACE": "bspline",
}

_INSTANCE = re.compile(r"#(\d+)\s*=\s*([A-Z0-9_]*)\s*(\(.*)$", re.DOTALL)
_REFERENCE = re.compile(r"#(\d+)")


class StepAuditError(ValueError):
    """A structural defect that makes the STEP file untrustworthy."""


@dataclass(frozen=True, slots=True)
class StepAudit:
    entity_count: int
    surface_counts: dict[str, int]
    solid_count: int
    closed_shell_count: int
    advanced_face_count: int
    edge_curve_count: int
    errors: tuple[str, ...] = field(default=())

    @property
    def valid(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "entityCount": self.entity_count,
            "surfaceCounts": dict(self.surface_counts),
            "solidCount": self.solid_count,
            "closedShellCount": self.closed_shell_count,
            "advancedFaceCount": self.advanced_face_count,
            "edgeCurveCount": self.edge_curve_count,
            "errors": list(self.errors),
            "valid": self.valid,
        }


def _strip_strings_and_comments(text: str) -> str:
    """Blank out string literals and comments without moving any offsets."""

    out = list(text)
    index = 0
    length = len(text)
    while index < length:
        character = text[index]
        if character == "'":
            index += 1
            while index < length:
                if text[index] == "'":
                    # Part 21 escapes quotes by doubling them.
                    if index + 1 < length and text[index + 1] == "'":
                        out[index] = " "
                        out[index + 1] = " "
                        index += 2
                        continue
                    break
                out[index] = " "
                index += 1
        elif character == "/" and index + 1 < length and text[index + 1] == "*":
            end = text.find("*/", index + 2)
            end = length if end < 0 else end + 2
            for position in range(index, end):
                if out[position] not in "\r\n":
                    out[position] = " "
            index = end
            continue
        index += 1
    return "".join(out)


def _data_section(text: str) -> str:
    if not text.lstrip().startswith("ISO-10303-21;"):
        raise StepAuditError("missing ISO-10303-21 header")
    if "END-ISO-10303-21;" not in text:
        raise StepAuditError("missing END-ISO-10303-21 terminator")
    match = re.search(r"\bDATA\s*;(.*?)ENDSEC\s*;", text, re.DOTALL)
    if match is None:
        raise StepAuditError("missing DATA section")
    return match.group(1)


def audit_step_file(path: str | Path, *, expected_solids: int = 1) -> StepAudit:
    """Parse and structurally audit a STEP file without any geometry kernel."""

    raw = Path(path).read_text(encoding="utf-8", errors="strict")
    text = _strip_strings_and_comments(raw)
    data = _data_section(text)

    entities: dict[int, str] = {}
    errors: list[str] = []
    for statement in data.split(";"):
        statement = statement.strip()
        if not statement:
            continue
        match = _INSTANCE.match(statement)
        if match is None:
            if statement.startswith("#"):
                errors.append(f"unparseable instance statement: {statement[:60]!r}")
            continue
        identifier = int(match.group(1))
        if identifier in entities:
            errors.append(f"duplicate entity id #{identifier}")
        # Complex (multi-record) instances have an empty simple name; keep the
        # full record text so surface kinds inside them are still counted.
        entities[identifier] = match.group(2) + " " + match.group(3)

    for identifier, body in sorted(entities.items()):
        for reference in _REFERENCE.finditer(body):
            target = int(reference.group(1))
            if target not in entities:
                errors.append(f"entity #{identifier} references missing #{target}")

    def count(name: str) -> int:
        pattern = re.compile(rf"\b{name}\b")
        return sum(1 for body in entities.values() if pattern.search(body))

    surface_counts = {kind: 0 for kind in sorted(set(SURFACE_ENTITY_KINDS.values()))}
    for entity_name, kind in SURFACE_ENTITY_KINDS.items():
        surface_counts[kind] += count(entity_name)

    solid_count = count("MANIFOLD_SOLID_BREP")
    closed_shell_count = count("CLOSED_SHELL")
    if solid_count != expected_solids:
        errors.append(f"expected {expected_solids} manifold solids, found {solid_count}")
    if closed_shell_count < solid_count:
        errors.append(f"{solid_count} solids reference only {closed_shell_count} closed shells")

    return StepAudit(
        entity_count=len(entities),
        surface_counts=surface_counts,
        solid_count=solid_count,
        closed_shell_count=closed_shell_count,
        advanced_face_count=count("ADVANCED_FACE"),
        edge_curve_count=count("EDGE_CURVE"),
        errors=tuple(errors),
    )


__all__ = ["SURFACE_ENTITY_KINDS", "StepAudit", "StepAuditError", "audit_step_file"]
