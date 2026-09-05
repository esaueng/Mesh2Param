//! A minimal binary glTF writer: positions and indices, nothing else.
//!
//! The viewer needs one thing from a reconstruction it cannot get from the
//! STEP file — the triangles to draw — and it already recomputes normals for
//! flat shading, so a full glTF exporter would be a dependency bought for
//! material and scene features nothing here emits.
//!
//! The output is a single-chunk-pair GLB: a JSON chunk describing one mesh
//! with one primitive, and a binary chunk holding the index and position
//! buffer views, in that order.

/// glTF component type for `u32`.
const COMPONENT_UNSIGNED_INT: u32 = 5125;
/// glTF component type for `f32`.
const COMPONENT_FLOAT: u32 = 5126;
/// glTF buffer view target `ELEMENT_ARRAY_BUFFER`.
const TARGET_ELEMENT_ARRAY: u32 = 34_963;
/// glTF buffer view target `ARRAY_BUFFER`.
const TARGET_ARRAY: u32 = 34_962;
/// `glTF` in ASCII, little-endian.
const MAGIC: u32 = 0x4654_6C67;
/// `JSON` in ASCII, little-endian.
const CHUNK_JSON: u32 = 0x4E4F_534A;
/// `BIN\0` in ASCII, little-endian.
const CHUNK_BIN: u32 = 0x004E_4942;

/// Write `positions` (three floats per vertex) and `indices` as a GLB.
///
/// An empty mesh still produces a valid file: a glTF asset with no meshes,
/// which a viewer loads and draws nothing for. That is the honest answer when
/// the kernel declined to tessellate.
#[must_use]
pub fn write(positions: &[f32], indices: &[u32]) -> Vec<u8> {
    let vertices = positions.len() / 3;
    let usable =
        vertices > 0 && !indices.is_empty() && indices.iter().all(|&i| (i as usize) < vertices);
    if !usable {
        return container(EMPTY_JSON, &[]);
    }

    let mut bin: Vec<u8> = Vec::with_capacity(indices.len() * 4 + positions.len() * 4 + 4);
    for index in indices {
        bin.extend_from_slice(&index.to_le_bytes());
    }
    let index_bytes = bin.len();
    // Accessor offsets must be aligned to the component size; indices are u32
    // so the position view already starts on a four-byte boundary, but the
    // padding is written rather than assumed.
    while !bin.len().is_multiple_of(4) {
        bin.push(0);
    }
    let position_offset = bin.len();
    for value in positions {
        bin.extend_from_slice(&value.to_le_bytes());
    }
    let position_bytes = bin.len() - position_offset;

    let (min, max) = bounds(positions);
    let json = format!(
        concat!(
            r#"{{"asset":{{"version":"2.0","generator":"mesh2param-wasm"}},"scene":0,"#,
            r#""scenes":[{{"nodes":[0]}}],"nodes":[{{"mesh":0}}],"meshes":[{{"primitives":"#,
            r#"[{{"attributes":{{"POSITION":1}},"indices":0,"mode":4}}]}}],"#,
            r#""buffers":[{{"byteLength":{total}}}],"bufferViews":["#,
            r#"{{"buffer":0,"byteOffset":0,"byteLength":{index_bytes},"target":{elements}}},"#,
            r#"{{"buffer":0,"byteOffset":{position_offset},"byteLength":{position_bytes},"#,
            r#""target":{array}}}],"accessors":[{{"bufferView":0,"componentType":{uint},"#,
            r#""count":{index_count},"type":"SCALAR"}},{{"bufferView":1,"componentType":{float},"#,
            r#""count":{vertices},"type":"VEC3","min":[{min0},{min1},{min2}],"#,
            r#""max":[{max0},{max1},{max2}]}}]}}"#,
        ),
        total = bin.len(),
        index_bytes = index_bytes,
        position_offset = position_offset,
        position_bytes = position_bytes,
        index_count = indices.len(),
        vertices = vertices,
        elements = TARGET_ELEMENT_ARRAY,
        array = TARGET_ARRAY,
        uint = COMPONENT_UNSIGNED_INT,
        float = COMPONENT_FLOAT,
        min0 = f(min[0]),
        min1 = f(min[1]),
        min2 = f(min[2]),
        max0 = f(max[0]),
        max1 = f(max[1]),
        max2 = f(max[2]),
    );
    container(&json, &bin)
}

/// The glTF asset written when there is nothing to draw.
const EMPTY_JSON: &str = r#"{"asset":{"version":"2.0","generator":"mesh2param-wasm"}}"#;

/// Wrap a JSON document and an optional binary blob in the GLB container.
fn container(json: &str, bin: &[u8]) -> Vec<u8> {
    let mut json_chunk = json.as_bytes().to_vec();
    // Chunks are four-byte aligned; JSON pads with spaces and BIN with zeros,
    // which is what every glTF reader expects to skip.
    while !json_chunk.len().is_multiple_of(4) {
        json_chunk.push(b' ');
    }
    let mut bin_chunk = bin.to_vec();
    while !bin_chunk.len().is_multiple_of(4) {
        bin_chunk.push(0);
    }

    let mut out = Vec::with_capacity(12 + 8 + json_chunk.len() + 8 + bin_chunk.len());
    let length = 12
        + 8
        + json_chunk.len()
        + if bin_chunk.is_empty() {
            0
        } else {
            8 + bin_chunk.len()
        };
    out.extend_from_slice(&MAGIC.to_le_bytes());
    out.extend_from_slice(&2_u32.to_le_bytes());
    out.extend_from_slice(&(length as u32).to_le_bytes());
    out.extend_from_slice(&(json_chunk.len() as u32).to_le_bytes());
    out.extend_from_slice(&CHUNK_JSON.to_le_bytes());
    out.extend_from_slice(&json_chunk);
    if !bin_chunk.is_empty() {
        out.extend_from_slice(&(bin_chunk.len() as u32).to_le_bytes());
        out.extend_from_slice(&CHUNK_BIN.to_le_bytes());
        out.extend_from_slice(&bin_chunk);
    }
    out
}

/// Per-axis minimum and maximum, which the POSITION accessor is required to
/// carry.
fn bounds(positions: &[f32]) -> ([f32; 3], [f32; 3]) {
    let mut min = [f32::INFINITY; 3];
    let mut max = [f32::NEG_INFINITY; 3];
    for point in positions.chunks_exact(3) {
        for axis in 0..3 {
            let Some(&v) = point.get(axis) else { continue };
            if v < min[axis] {
                min[axis] = v;
            }
            if v > max[axis] {
                max[axis] = v;
            }
        }
    }
    for axis in 0..3 {
        if !min[axis].is_finite() || !max[axis].is_finite() {
            min[axis] = 0.0;
            max[axis] = 0.0;
        }
    }
    (min, max)
}

/// A float as JSON. `NaN` and infinities are not JSON numbers and would make
/// the whole file unreadable, so they are written as zero.
fn f(value: f32) -> f32 {
    if value.is_finite() { value } else { 0.0 }
}

#[cfg(test)]
mod tests {
    #![allow(clippy::unwrap_used, clippy::panic)]

    use super::*;

    fn header(glb: &[u8]) -> (u32, u32, u32) {
        let word = |at: usize| u32::from_le_bytes([glb[at], glb[at + 1], glb[at + 2], glb[at + 3]]);
        (word(0), word(4), word(8))
    }

    #[test]
    fn a_triangle_round_trips_through_the_container() {
        let positions = [0.0_f32, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 2.0, 0.0];
        let glb = write(&positions, &[0, 1, 2]);

        let (magic, version, length) = header(&glb);
        assert_eq!(&magic.to_le_bytes(), b"glTF");
        assert_eq!(version, 2);
        assert_eq!(
            length as usize,
            glb.len(),
            "declared length is not the file"
        );
        assert!(glb.len().is_multiple_of(4), "chunks are not aligned");

        let json_len = u32::from_le_bytes([glb[12], glb[13], glb[14], glb[15]]) as usize;
        let json = core::str::from_utf8(&glb[20..20 + json_len]).unwrap();
        assert!(json.contains("\"POSITION\":1"), "{json}");
        assert!(json.contains("\"max\":[1,2,0]"), "{json}");
        assert!(json.contains("\"count\":3"), "{json}");
    }

    #[test]
    fn an_empty_mesh_is_still_a_valid_container() {
        let glb = write(&[], &[]);
        let (magic, _, length) = header(&glb);
        assert_eq!(&magic.to_le_bytes(), b"glTF");
        assert_eq!(length as usize, glb.len());
    }

    #[test]
    fn an_out_of_range_index_is_refused_rather_than_written() {
        let glb = write(&[0.0, 0.0, 0.0], &[0, 1, 2]);
        let json_len = u32::from_le_bytes([glb[12], glb[13], glb[14], glb[15]]) as usize;
        let json = core::str::from_utf8(&glb[20..20 + json_len]).unwrap();
        assert!(
            !json.contains("meshes"),
            "a broken mesh was written: {json}"
        );
    }
}
