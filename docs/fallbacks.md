# Fallbacks and honest limitations

## Open3D

Open3D was not introduced because the verified Python 3.12 geometry environment already provides
CadQuery/OCP, trimesh, NumPy, and SciPy, and deterministic custom fitting covers the current bounded
scope. Mesh2Param therefore uses:

- trimesh adjacency, topology, parsing, and deterministic sampling;
- NumPy total-least-squares plane fitting and normal covariance;
- SciPy bounded least-squares circle/cylinder refinement;
- deterministic seeded surface comparison with exact point-to-triangle queries.

This fallback is not presented as equivalent to a general point-cloud or organic-surface pipeline.
Full cylinders require at least 300 degrees of angular evidence, plane/cylinder fits must satisfy
explicit residual thresholds, and unsupported remainder stays freeform. A future Open3D integration
may add scale-aware robust estimation only if it installs cleanly and preserves deterministic seeds,
license compatibility, evidence links, and the same failure semantics.

## Damaged and coarse meshes

The engine never silently fills large holes or smooths detail. Missing patch boundaries are retained
as open loops and stop automatic L-profile inference. Very coarse cylinder tessellation can exceed
the 12 degree smooth-region threshold and create extra plane directions; this fails as an ambiguous
frame instead of guessing. Small-hole filling exists only as an explicit repair operation with a
configured edge-count and planarity limit.

## Self-intersection

The deterministic fallback has no robust self-intersection backend installed. Diagnostics therefore
emit an `unverified` warning. They never label the source clean on that dimension.

## Reconstructed feature selection

Patch selection is deterministic through `patches.glb` and `selection-map.json`, with the map bound
to the GLB SHA-256 and triangle ranges carrying `patchId`. Final reconstructed face-to-feature
selection is deferred until OCCT semantic topology can prove a final-face mapping without guessing;
the UI must not imply that whole-body highlighting identifies an individual feature.
