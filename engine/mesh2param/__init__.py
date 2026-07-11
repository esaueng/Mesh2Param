"""Mesh2Param M1 exact CADGraph compiler."""

from .compiler import CompilationResult, FeatureRecord, compile_cadgraph
from .errors import CompilationException, CompileError, FeatureBuildFailure
from .source import generate_cadquery_source, write_cadquery_source
from .tessellation import (
    MeshArtifact,
    Tessellation,
    export_binary_stl,
    export_glb,
    tessellate_shape,
)
from .validation import (
    ShapeValidation,
    StepValidation,
    export_step_validated,
    import_step_shape,
    validate_shape,
)

__version__ = "0.1.0"

__all__ = [
    "CompilationException",
    "CompilationResult",
    "CompileError",
    "FeatureBuildFailure",
    "FeatureRecord",
    "MeshArtifact",
    "ShapeValidation",
    "StepValidation",
    "Tessellation",
    "__version__",
    "compile_cadgraph",
    "export_binary_stl",
    "export_glb",
    "export_step_validated",
    "generate_cadquery_source",
    "import_step_shape",
    "tessellate_shape",
    "validate_shape",
    "write_cadquery_source",
]
