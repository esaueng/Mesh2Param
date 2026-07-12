"""Mesh2Param exact CAD compiler and bounded mesh reconstruction engine."""

from .comparison import ComparisonReport, ComparisonSettings, compare_mesh_to_shape
from .compiler import CompilationResult, FeatureRecord, compile_cadgraph
from .errors import CompilationException, CompileError, FeatureBuildFailure
from .faceted import (
    FacetedFallbackError,
    FacetedFallbackResult,
    create_faceted_fallback,
)
from .frame import CoordinateFrame, FrameInferenceError, infer_coordinate_frame
from .ingest import IngestedMesh, MeshDiagnostics, MeshIngestionError, MeshLimits, ingest_mesh
from .prismatic import (
    ArcPrimitive,
    CirclePrimitive,
    ExtrusionCandidate,
    LinePrimitive,
    PrismaticSettings,
    detect_extrusion_candidate,
    fit_closed_line_arc_chain,
    validate_prismatic_candidate,
)
from .reconstruction import (
    PrismaticReconstructionResult,
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
    classify_face_surfaces,
    export_step_validated,
    import_step_shape,
    validate_shape,
)

__version__ = "0.1.0"

__all__ = [
    "ArcPrimitive",
    "CirclePrimitive",
    "ComparisonReport",
    "ComparisonSettings",
    "CompilationException",
    "CompilationResult",
    "CompileError",
    "CoordinateFrame",
    "ExtrusionCandidate",
    "FacetedFallbackError",
    "FacetedFallbackResult",
    "FeatureBuildFailure",
    "FeatureRecord",
    "FrameInferenceError",
    "IngestedMesh",
    "LinePrimitive",
    "MeshArtifact",
    "MeshDiagnostics",
    "MeshIngestionError",
    "MeshLimits",
    "PrismaticReconstructionResult",
    "PrismaticSettings",
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
    "classify_face_surfaces",
    "compare_mesh_to_shape",
    "compile_cadgraph",
    "create_faceted_fallback",
    "detect_extrusion_candidate",
    "export_binary_stl",
    "export_glb",
    "export_step_validated",
    "fit_closed_line_arc_chain",
    "generate_cadquery_source",
    "import_step_shape",
    "infer_coordinate_frame",
    "ingest_mesh",
    "reconstruct_file",
    "repair_mesh",
    "segment_mesh",
    "tessellate_shape",
    "validate_prismatic_candidate",
    "validate_shape",
    "write_cadquery_source",
]
