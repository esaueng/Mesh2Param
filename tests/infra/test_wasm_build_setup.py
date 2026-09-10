from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class WasmBuildSetupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        (self.root / "scripts").mkdir()
        for name in ("setup_core_wasm.sh", "build_core_wasm.sh"):
            shutil.copy(ROOT / "scripts" / name, self.root / "scripts" / name)
        shutil.copy(ROOT / "rust-toolchain.toml", self.root / "rust-toolchain.toml")
        for name in (
            "bash",
            "sh",
            "dirname",
            "sed",
            "mktemp",
            "rm",
            "mkdir",
            "wc",
            "tr",
            "gzip",
            "chmod",
        ):
            executable = shutil.which(name)
            assert executable is not None
            (self.bin / name).symlink_to(executable)
        self.env = {
            "PATH": str(self.bin),
            "HOME": str(self.root),
            "CARGO_HOME": str(self.root / "cargo"),
            "LOG": str(self.root / "calls"),
        }
        self.stub("rustup", 'echo "rustup $*" >> "$LOG"\n')
        self.stub("cargo", 'echo "cargo $*" >> "$LOG"\nexit 19\n')

    def stub(self, name: str, body: str) -> None:
        path = self.bin / name
        path.write_text("#!/bin/sh\nset -eu\n" + body)
        path.chmod(0o755)

    def run_build(self, script: str = "setup_core_wasm.sh") -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(self.bin / "bash"), str(self.root / "scripts" / script)],
            env=self.env,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_existing_pinned_pack_skips_install(self) -> None:
        self.stub("wasm-pack", 'echo "wasm-pack 0.15.0"\n')
        result = self.run_build()
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = (self.root / "calls").read_text()
        self.assertIn("--target wasm32-unknown-unknown", calls)
        self.assertNotIn("cargo install", calls)

    def test_missing_or_wrong_pack_installs_pin_and_propagates_failure(self) -> None:
        for version in (None, "0.14.0"):
            with self.subTest(version=version):
                if version:
                    self.stub("wasm-pack", f'echo "wasm-pack {version}"\n')
                result = self.run_build()
                self.assertEqual(result.returncode, 19)
                self.assertIn(
                    "cargo install --locked wasm-pack --version 0.15.0 --force",
                    (self.root / "calls").read_text(),
                )

    def test_missing_rustup_download_failure_stops_before_cargo(self) -> None:
        (self.bin / "rustup").unlink()
        self.stub("curl", "exit 22\n")
        result = self.run_build()
        self.assertEqual(result.returncode, 22)
        self.assertFalse((self.root / "calls").exists())

    def test_fresh_hosted_build_installs_and_uses_tools_from_cargo_home(self) -> None:
        (self.bin / "rustup").unlink()
        self.stub(
            "curl",
            'while [ "$1" != "--output" ]; do shift; done\n'
            'printf \'#!/bin/sh\\nmkdir -p "$CARGO_HOME/bin"\\n'
            'printf "#!/bin/sh\\\\nexit 0\\\\n" > "$CARGO_HOME/bin/rustup"\\n'
            'chmod +x "$CARGO_HOME/bin/rustup"\\n\' > "$2"\n',
        )
        self.stub(
            "cargo",
            "printf '#!/bin/sh\\n"
            'if [ "$1" = "--version" ]; then echo "wasm-pack 0.15.0"; exit 0; fi\\n'
            'while [ "$1" != "--out-dir" ]; do shift; done\\n'
            'mkdir -p "$2"\\nprintf wasm > "$2/mesh2param_wasm_bg.wasm"\\n'
            '\' > "$CARGO_HOME/bin/wasm-pack"\n'
            'chmod +x "$CARGO_HOME/bin/wasm-pack"\n',
        )
        self.env["WORKERS_CI"] = "1"
        result = self.run_build("build_core_wasm.sh")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("core-wasm: 4 bytes raw", result.stdout)

    def test_hosted_build_bootstraps_before_building(self) -> None:
        for flag in ("WORKERS_CI", "MESH2PARAM_BOOTSTRAP_WASM"):
            with self.subTest(flag=flag):
                self.env[flag] = "1"
                result = self.run_build("build_core_wasm.sh")
                self.assertEqual(result.returncode, 19)
                self.assertIn("cargo install", (self.root / "calls").read_text())
                del self.env[flag]

    def test_local_build_does_not_install_tools(self) -> None:
        result = self.run_build("build_core_wasm.sh")
        self.assertEqual(result.returncode, 1)
        self.assertIn("wasm-pack is not on PATH", result.stderr)
        self.assertFalse((self.root / "calls").exists())


class CleanCheckoutWasmTests(unittest.TestCase):
    def test_browser_job_builds_wasm_before_web_acceptance(self) -> None:
        workflow = (ROOT / ".github/workflows/fleet-ci.yml").read_text()
        steps = re.split(r"      - name: ", workflow)
        for name in ("Cache cargo build", "Install wasm-pack", "Build the WebAssembly package"):
            step = next(block for block in steps if block.startswith(name + "\n"))
            condition = next(line.strip() for line in step.splitlines() if "if:" in line)
            for task in ("static", "browser"):
                self.assertIn(f"matrix.task == '{task}'", condition)
        self.assertLess(
            workflow.index("run: pnpm core:wasm"), workflow.index("name: Run browser acceptance")
        )

    def test_web_image_has_workspace_inputs_and_builds_wasm(self) -> None:
        dockerfile = (ROOT / "infra/web.Dockerfile").read_text()
        builder, runtime = dockerfile.split("FROM ${NGINX_IMAGE} AS runtime", 1)
        install = builder.index("pnpm install --frozen-lockfile")
        self.assertLess(builder.index("COPY packages/core-wasm/package.json"), install)
        build = builder.index("RUN MESH2PARAM_BOOTSTRAP_WASM=1 pnpm build:web")
        for source in (
            "COPY packages/core-wasm packages/core-wasm",
            "COPY Cargo.toml Cargo.lock rust-toolchain.toml ./",
            "COPY crates crates",
            "COPY scripts/build_core_wasm.sh scripts/setup_core_wasm.sh scripts/",
        ):
            self.assertLess(builder.index(source), build)
        self.assertIn("--from=builder /build/apps/web/dist", runtime)
        self.assertNotIn("COPY crates", runtime)
        ignored = (ROOT / ".dockerignore").read_text().splitlines()
        self.assertIn("packages/core-wasm/pkg", ignored)
        self.assertIn("**/target", ignored)


if __name__ == "__main__":
    unittest.main()
