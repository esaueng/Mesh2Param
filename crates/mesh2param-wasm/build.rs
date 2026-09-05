//! Records which kernel revision this binding was built against.
//!
//! The pin lives in `Cargo.lock`, which is committed; reading it here means the
//! `version()` a browser reports cannot drift from the kernel actually linked
//! into the `.wasm`, the way a hand-copied constant would.

use std::fs;
use std::path::PathBuf;

fn main() {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..");
    let lock = root.join("Cargo.lock");
    println!("cargo:rerun-if-changed={}", lock.display());

    let rev = fs::read_to_string(&lock)
        .ok()
        .and_then(|text| remus_rev(&text))
        .unwrap_or_else(|| "unknown".to_string());
    println!("cargo:rustc-env=MESH2PARAM_KERNEL_REV={rev}");
}

/// The revision every `remus-*` package in the lock file resolves to.
///
/// The four kernel crates are pinned to one revision by construction, so the
/// first `git+...#<rev>` source line is the answer; anything else means the
/// pin has been split and the caller is better off seeing "unknown".
fn remus_rev(lock: &str) -> Option<String> {
    let mut found: Option<String> = None;
    for line in lock.lines() {
        let Some(rest) = line.strip_prefix("source = \"git+https://github.com/esaueng/remus")
        else {
            continue;
        };
        let rev = rest.rsplit_once('#')?.1.trim_end_matches('"').to_string();
        match &found {
            Some(seen) if *seen != rev => return None,
            _ => found = Some(rev),
        }
    }
    found
}
