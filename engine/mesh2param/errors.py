"""Structured errors produced by the deterministic CADGraph compiler."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class CompileError:
    """A feature-scoped rebuild failure with rollback context."""

    code: str
    feature_id: str
    feature_type: str
    order: int
    parameters: dict[str, Any]
    dependencies: tuple[str, ...]
    kernel_error: str
    last_valid_feature_id: str | None
    recommendation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "featureId": self.feature_id,
            "featureType": self.feature_type,
            "order": self.order,
            "parameters": self.parameters,
            "dependencies": list(self.dependencies),
            "kernelError": self.kernel_error,
            "lastValidFeatureId": self.last_valid_feature_id,
            "recommendation": self.recommendation,
        }


@dataclass(frozen=True, slots=True)
class TopologyIssue:
    """An explicitly surfaced semantic-topology resolution problem."""

    semantic_id: str
    producer_feature_id: str
    message: str
    severity: str = "error"

    def to_dict(self) -> dict[str, str]:
        return {
            "semanticId": self.semantic_id,
            "producerFeatureId": self.producer_feature_id,
            "message": self.message,
            "severity": self.severity,
        }


class FeatureBuildFailure(RuntimeError):
    """Expected, user-correctable failure while compiling one feature."""

    def __init__(self, code: str, message: str, recommendation: str) -> None:
        super().__init__(message)
        self.code = code
        self.recommendation = recommendation


class SemanticResolutionFailure(FeatureBuildFailure):
    """Raised instead of silently retargeting an unresolved semantic reference."""

    def __init__(self, semantic_id: str, message: str) -> None:
        super().__init__(
            "semantic_reference_unresolved",
            f"semantic topology reference {semantic_id!r} is unresolved: {message}",
            "Restore the referenced topology, select an unambiguous semantic edge or face, "
            "or suppress the dependent feature.",
        )
        self.semantic_id = semantic_id


@dataclass(slots=True)
class CompilationException(RuntimeError):
    """Raised by convenience APIs when a partial compilation is unacceptable."""

    message: str
    errors: list[CompileError] = field(default_factory=list)

    def __str__(self) -> str:
        return self.message
