"""Mesh2Param exact CAD compiler and bounded mesh reconstruction engine."""

from .comparison import ComparisonReport, ComparisonSettings, compare_mesh_to_shape
from .compiler import CompilationResult, FeatureRecord, compile_cadgraph
from .errors import CompilationException, CompileError, FeatureBuildFailure
from .frame import CoordinateFrame, FrameInferenceError, infer_coordinate_frame
from .ingest import IngestedMesh, MeshDiagnostics, MeshIngestionError, MeshLimits, ingest_mesh
from .reconstruction import (
    ReconstructionError,
    ReconstructionResult,
    ReconstructionSettings,
    reconstruct_file,
)
from .repair import RepairResult, RepairSettings, repair_mesh
from .segmentation import SegmentationResult, SegmentationSettings, SurfacePatch, segment_mesh
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
    "ComparisonReport",
    "ComparisonSettings",
    "CompilationException",
    "CompilationResult",
    "CompileError",
    "CoordinateFrame",
    "FeatureBuildFailure",
    "FeatureRecord",
    "FrameInferenceError",
    "IngestedMesh",
    "MeshArtifact",
    "MeshDiagnostics",
    "MeshIngestionError",
    "MeshLimits",
    "ReconstructionError",
    "ReconstructionResult",
    "ReconstructionSettings",
    "RepairResult",
    "RepairSettings",
    "SegmentationResult",
    "SegmentationSettings",
    "ShapeValidation",
    "StepValidation",
    "SurfacePatch",
    "Tessellation",
    "__version__",
    "compare_mesh_to_shape",
    "compile_cadgraph",
    "export_binary_stl",
    "export_glb",
    "export_step_validated",
    "generate_cadquery_source",
    "import_step_shape",
    "infer_coordinate_frame",
    "ingest_mesh",
    "reconstruct_file",
    "repair_mesh",
    "segment_mesh",
    "tessellate_shape",
    "validate_shape",
    "write_cadquery_source",
]
