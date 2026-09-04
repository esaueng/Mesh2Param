//! Binary little-endian PLY writer with per-face colour, written by hand so the
//! spike keeps a zero-crate dependency budget.

use std::io::Write;
use std::path::Path;

use crate::mesh::Mesh;

/// Distinct colour per patch: golden-angle hue walk, unknown patches grey.
pub fn patch_colour(patch_id: usize, known: bool) -> [u8; 3] {
    if !known {
        return [130, 130, 130];
    }
    #[allow(clippy::cast_precision_loss)]
    let hue = ((patch_id as f64) * 137.507_764_05_f64).rem_euclid(360.0);
    hsv_to_rgb(hue, 0.72, 0.95)
}

#[allow(clippy::cast_possible_truncation, clippy::cast_sign_loss)]
fn hsv_to_rgb(h: f64, s: f64, v: f64) -> [u8; 3] {
    let c = v * s;
    let hp = h / 60.0;
    let x = c * (1.0 - (hp.rem_euclid(2.0) - 1.0).abs());
    let (r, g, b) = match hp.clamp(0.0, 5.999) as u8 {
        0 => (c, x, 0.0),
        1 => (x, c, 0.0),
        2 => (0.0, c, x),
        3 => (0.0, x, c),
        4 => (x, 0.0, c),
        _ => (c, 0.0, x),
    };
    let m = v - c;
    #[allow(clippy::cast_possible_truncation, clippy::cast_sign_loss)]
    [
        (((r + m) * 255.0).clamp(0.0, 255.0)) as u8,
        (((g + m) * 255.0).clamp(0.0, 255.0)) as u8,
        (((b + m) * 255.0).clamp(0.0, 255.0)) as u8,
    ]
}

/// Write the welded mesh with one RGB triple per face.
pub fn write(path: &Path, mesh: &Mesh, colours: &[[u8; 3]]) -> Result<(), String> {
    let mut buf: Vec<u8> = Vec::with_capacity(mesh.verts.len() * 12 + mesh.faces.len() * 16 + 512);
    let header = format!(
        "ply\nformat binary_little_endian 1.0\ncomment segmentation spike\n\
         element vertex {}\nproperty float x\nproperty float y\nproperty float z\n\
         element face {}\nproperty list uchar int vertex_indices\n\
         property uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n",
        mesh.verts.len(),
        mesh.faces.len()
    );
    buf.extend_from_slice(header.as_bytes());
    #[allow(clippy::cast_possible_truncation)]
    for v in &mesh.verts {
        for c in [v.x, v.y, v.z] {
            buf.extend_from_slice(&(c as f32).to_le_bytes());
        }
    }
    #[allow(clippy::cast_possible_wrap)]
    for (i, f) in mesh.faces.iter().enumerate() {
        buf.push(3_u8);
        for idx in f.v {
            buf.extend_from_slice(&(idx as i32).to_le_bytes());
        }
        let c = colours.get(i).copied().unwrap_or([130, 130, 130]);
        buf.extend_from_slice(&c);
    }
    let mut file = std::fs::File::create(path).map_err(|e| format!("create {}: {e}", path.display()))?;
    file.write_all(&buf)
        .map_err(|e| format!("write {}: {e}", path.display()))
}
