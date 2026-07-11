"""Run Mesh2Param's ordered release acceptance and write durable evidence.

The runner only invokes fixed, trusted command arrays with ``shell=False``.  It
never imports or executes generated CadQuery source.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import signal
import socket
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
ACCEPTANCE_ROOT = ROOT / "artifacts" / "acceptance"
REPORT_PATH = ROOT / "docs" / "acceptance-report.md"
Status = Literal["passed", "failed", "blocked", "skipped"]


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _git(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=False,
        shell=False,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _dirty_paths() -> list[str]:
    return [line[3:] for line in _git("status", "--short").splitlines() if len(line) > 3]


def _clean_mesh2param_environment() -> dict[str, str]:
    """Keep host tooling settings while removing accidental application-profile leakage."""

    return {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith("MESH2PARAM_")
    }


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_version(command: list[str]) -> str:
    try:
        result = subprocess.run(
            command,
            cwd=ROOT,
            check=False,
            shell=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return f"unavailable: {exc}"
    output = (result.stdout or result.stderr).strip().splitlines()
    return output[0] if output else f"exit {result.returncode}"


@dataclass(slots=True)
class Step:
    id: str
    command: list[str]
    status: Status
    started_at: str
    finished_at: str
    duration_ms: int
    exit_code: int | None
    log: str
    evidence: list[str] = field(default_factory=list)
    detail: str | None = None


class AcceptanceRun:
    def __init__(self, *, skip_install: bool, skip_e2e: bool, skip_docker: bool) -> None:
        self.started_at = _now()
        self.commit = _git("rev-parse", "--short=12", "HEAD") or "unknown"
        run_name = f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{self.commit[:8]}"
        self.output = ACCEPTANCE_ROOT / run_name
        self.logs = self.output / "logs"
        self.evidence = self.output / "evidence"
        self.logs.mkdir(parents=True, exist_ok=False)
        self.evidence.mkdir(parents=True, exist_ok=True)
        self.skip_install = skip_install
        self.skip_e2e = skip_e2e
        self.skip_docker = skip_docker
        self.steps: list[Step] = []
        self.red_gate = False
        self.blockers: list[dict[str, str]] = []
        self.fallbacks: list[str] = []
        self.docker: dict[str, object] = {
            "daemon": "not-checked",
            "compose": "not-checked",
            "securityChecks": [],
        }
        self.sample_evidence: dict[str, object] = {}
        raw_screenshots = os.environ.get("ACCEPTANCE_SCREENSHOTS", "")
        self.screenshots = [item for item in raw_screenshots.split("|") if item]

    def run_command(
        self,
        step_id: str,
        command: list[str],
        *,
        required: bool = True,
        env: dict[str, str] | None = None,
        evidence: list[str] | None = None,
    ) -> Step:
        if self.red_gate and required:
            return self.record(
                step_id,
                command,
                "skipped",
                detail="skipped after an earlier required gate failed",
                evidence=evidence,
            )
        started = _now()
        start = time.monotonic()
        log_path = self.logs / f"{len(self.steps) + 1:02d}-{step_id}.log"
        with log_path.open("w", encoding="utf-8", newline="\n") as log:
            log.write(f"command={json.dumps(command)}\nstartedAt={started}\n\n")
            try:
                completed = subprocess.run(
                    command,
                    cwd=ROOT,
                    env=env,
                    check=False,
                    shell=False,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
                exit_code = completed.returncode
                status: Status = "passed" if exit_code == 0 else "failed"
                detail = None
            except FileNotFoundError as exc:
                exit_code = None
                status = "failed" if required else "blocked"
                detail = str(exc)
                log.write(f"\n{exc}\n")
        if required and status == "failed":
            self.red_gate = True
        step = Step(
            id=step_id,
            command=command,
            status=status,
            started_at=started,
            finished_at=_now(),
            duration_ms=round((time.monotonic() - start) * 1000),
            exit_code=exit_code,
            log=str(log_path.relative_to(ROOT)),
            evidence=evidence or [],
            detail=detail,
        )
        self.steps.append(step)
        return step

    def record(
        self,
        step_id: str,
        command: list[str],
        status: Status,
        *,
        detail: str | None = None,
        evidence: list[str] | None = None,
    ) -> Step:
        now = _now()
        step = Step(
            id=step_id,
            command=command,
            status=status,
            started_at=now,
            finished_at=now,
            duration_ms=0,
            exit_code=0 if status == "passed" else None,
            log="",
            evidence=evidence or [],
            detail=detail,
        )
        self.steps.append(step)
        return step

    def tool_snapshot(self) -> None:
        tools = {
            "python": _safe_version(["python3", "--version"]),
            "node": _safe_version(["node", "--version"]),
            "pnpm": _safe_version(["pnpm", "--version"]),
            "uv": _safe_version(["uv", "--version"]),
            "docker": _safe_version(["docker", "--version"]),
            "dockerCompose": _safe_version(["docker", "compose", "version"]),
        }
        snapshot = {
            "platform": platform.platform(),
            "arch": platform.machine(),
            "python": platform.python_version(),
            "tools": tools,
            "safeEnvironment": {
                key: os.environ[key]
                for key in ("CI", "LANG", "TZ")
                if key in os.environ
            },
        }
        path = self.evidence / "host.json"
        path.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        self.record("host", ["tool-version-snapshot"], "passed", evidence=[str(path)])

    def backend_smoke(self) -> None:
        if self.red_gate:
            self.record(
                "backend-smoke",
                ["mesh2param-api"],
                "skipped",
                detail="earlier gate failed",
            )
            return
        started = _now()
        start = time.monotonic()
        log_path = self.logs / f"{len(self.steps) + 1:02d}-backend-smoke.log"
        port = _free_port()
        with tempfile.TemporaryDirectory(prefix="mesh2param-acceptance-api-") as temp:
            temp_path = Path(temp)
            env = _clean_mesh2param_environment()
            env.update(
                {
                    "MESH2PARAM_ENVIRONMENT": "test",
                    "MESH2PARAM_DATA_DIR": str(temp_path),
                    "MESH2PARAM_DATABASE_URL": f"sqlite:///{temp_path / 'api.sqlite3'}",
                    "MESH2PARAM_STORAGE_PATH": str(temp_path / "storage"),
                    "MESH2PARAM_WORKER_COUNT": "1",
                    "MESH2PARAM_JOB_RUNNER_MODE": "embedded",
                    "MESH2PARAM_BIND_HOST": "127.0.0.1",
                    "MESH2PARAM_PORT": str(port),
                }
            )
            command = [
                "uv",
                "run",
                "--frozen",
                "mesh2param-api",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ]
            status: Status = "failed"
            detail: str | None = None
            process: subprocess.Popen[str] | None = None
            with log_path.open("w", encoding="utf-8", newline="\n") as log:
                try:
                    process = subprocess.Popen(
                        command,
                        cwd=ROOT,
                        env=env,
                        shell=False,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        text=True,
                        start_new_session=True,
                    )
                    responses: dict[str, object] = {}
                    deadline = time.monotonic() + 45
                    for endpoint in ("health", "ready", "docs", "openapi.json"):
                        url = f"http://127.0.0.1:{port}/{endpoint}"
                        while True:
                            if process.poll() is not None:
                                raise RuntimeError(
                                    f"backend exited early with {process.returncode}"
                                )
                            try:
                                with urlopen(url, timeout=2) as response:
                                    responses[endpoint] = {
                                        "status": response.status,
                                        "contentType": response.headers.get_content_type(),
                                    }
                                break
                            except URLError:
                                if time.monotonic() >= deadline:
                                    raise TimeoutError(f"timed out waiting for {url}") from None
                                time.sleep(0.25)
                    smoke = self.evidence / "backend-smoke.json"
                    smoke.write_text(
                        json.dumps(responses, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
                    status = "passed"
                except (FileNotFoundError, RuntimeError, TimeoutError, OSError) as exc:
                    detail = str(exc)
                    log.write(f"\n{exc}\n")
                finally:
                    if process is not None and process.poll() is None:
                        os.killpg(process.pid, signal.SIGTERM)
                        try:
                            process.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            os.killpg(process.pid, signal.SIGKILL)
                            process.wait(timeout=5)
            if status != "passed":
                self.red_gate = True
            self.steps.append(
                Step(
                    id="backend-smoke",
                    command=command,
                    status=status,
                    started_at=started,
                    finished_at=_now(),
                    duration_ms=round((time.monotonic() - start) * 1000),
                    exit_code=0 if status == "passed" else 1,
                    log=str(log_path.relative_to(ROOT)),
                    evidence=[str(self.evidence / "backend-smoke.json")]
                    if status == "passed"
                    else [],
                    detail=detail,
                )
            )

    def collect_sample_evidence(self) -> None:
        output = self.evidence / "bracket-reconstruction"
        source = ROOT / "samples" / "generated" / "l-bracket-with-holes" / "source-high.stl"
        step = self.run_command(
            "sample-reconstruction",
            [
                "uv",
                "run",
                "--frozen",
                "mesh2param",
                "reconstruct",
                str(source),
                "--units",
                "mm",
                "--output",
                str(output),
            ],
            evidence=[str(output)],
        )
        if step.status != "passed":
            return
        validation = self.run_command(
            "sample-step-validation",
            [
                "uv",
                "run",
                "--frozen",
                "mesh2param",
                "validate",
                str(output / "model.step"),
                "--units",
                "mm",
                "--output",
                str(output),
            ],
            evidence=[str(output / "validation.json")],
        )
        if validation.status != "passed":
            return
        graph = json.loads((output / "model.cadgraph.json").read_text(encoding="utf-8"))
        comparison = json.loads((output / "comparison.json").read_text(encoding="utf-8"))
        validation_data = json.loads((output / "validation.json").read_text(encoding="utf-8"))
        artifacts = sorted(path.name for path in output.iterdir() if path.is_file())
        self.sample_evidence = {
            "sample": "l-bracket-with-holes",
            "cadgraphId": graph.get("id"),
            "featureHistory": [
                {
                    "id": item.get("id"),
                    "operation": item.get("operation"),
                    "suppressed": item.get("suppressed", False),
                }
                for item in graph.get("features", [])
                if isinstance(item, dict)
            ],
            "metrics": comparison.get("comparison", comparison),
            "validation": validation_data,
            "stepSha256": _sha256(output / "model.step"),
            "artifacts": artifacts,
            "parameterEditRestoreEvidence": (
                "tests/test_m2_reconstruction.py::"
                "test_geometry_acceptance_exact_sixteen_step_sequence"
            ),
            "projectSaveReloadEvidence": "tests/browser/primary-workflow.spec.ts",
        }

    def docker_acceptance(self) -> None:
        if self.red_gate:
            self.record(
                "docker", ["docker", "compose"], "skipped", detail="earlier gate failed"
            )
            return
        if self.skip_docker:
            self.fallbacks.append("Docker acceptance explicitly skipped by runner option")
            self.record(
                "docker", ["docker", "compose"], "skipped", detail="--skip-docker"
            )
            return
        daemon_available = False
        try:
            daemon = subprocess.run(
                ["docker", "version", "--format", "{{.Server.Version}}"],
                cwd=ROOT,
                check=False,
                shell=False,
                capture_output=True,
                text=True,
            )
            daemon_available = daemon.returncode == 0
            daemon_detail = (daemon.stderr or daemon.stdout).strip()
        except OSError as exc:
            daemon = None
            daemon_detail = str(exc)
        if not daemon_available:
            self.docker["daemon"] = "unavailable"
            self.blockers.append(
                {
                    "command": "docker version --format {{.Server.Version}}",
                    "failure": daemon_detail,
                    "affected": "runtime Compose health and container security acceptance",
                }
            )
            self.fallbacks.append("Docker runtime blocked; static Compose validation used")
        else:
            assert daemon is not None
            self.docker["daemon"] = f"available ({daemon.stdout.strip()})"
        compose = ["docker", "compose"]
        try:
            compose_version = subprocess.run(
                [*compose, "version"],
                cwd=ROOT,
                check=False,
                shell=False,
                capture_output=True,
                text=True,
            )
            compose_available = compose_version.returncode == 0
            compose_detail = (compose_version.stderr or compose_version.stdout).strip()
        except OSError as exc:
            compose_version = None
            compose_available = False
            compose_detail = str(exc)
        if not compose_available:
            self.docker["compose"] = "unavailable"
            self.blockers.append(
                {
                    "command": "docker compose version",
                    "failure": compose_detail,
                    "affected": "Compose config and runtime acceptance",
                }
            )
            self.record(
                "docker",
                ["docker", "compose", "version"],
                "blocked",
                detail=compose_detail,
            )
            return
        assert compose_version is not None
        self.docker["compose"] = compose_version.stdout.strip()
        env = os.environ.copy()
        env.setdefault("COMPOSE_WEB_PORT", "18080")
        web_port = env["COMPOSE_WEB_PORT"]
        env["MESH2PARAM_PUBLIC_URL"] = f"http://localhost:{web_port}"
        env["MESH2PARAM_CORS_ORIGINS"] = (
            f"http://localhost:{web_port},http://127.0.0.1:{web_port}"
        )
        config = self.run_command(
            "compose-config", [*compose, "config", "--quiet"], env=env
        )
        if config.status != "passed" or not daemon_available:
            return
        project = f"mesh2param-acceptance-{os.getpid()}-{int(time.time())}"
        up_command = [*compose, "-p", project, "up", "--build", "--wait"]
        try:
            up = self.run_command("compose-up", up_command, env=env)
            if up.status != "passed":
                return
            smoke_path = self.evidence / "compose-smoke.json"
            responses: dict[str, object] = {}
            for endpoint in ("health", "ready", "docs", "openapi.json"):
                url = f"http://127.0.0.1:{web_port}/{endpoint}"
                with urlopen(url, timeout=10) as response:
                    responses[endpoint] = {
                        "status": response.status,
                        "contentType": response.headers.get_content_type(),
                    }
            smoke_path.write_text(
                json.dumps(responses, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            security_path = self.evidence / "container-security.json"
            security = self.run_command(
                "container-security",
                [
                    "python3",
                    "scripts/verify_container_security.py",
                    "--project-name",
                    project,
                    "--web-port",
                    web_port,
                    "--json-output",
                    str(security_path),
                ],
                env=env,
                evidence=[str(smoke_path), str(security_path)],
            )
            if security.status == "passed":
                self.docker["securityChecks"] = json.loads(
                    security_path.read_text(encoding="utf-8")
                )["checks"]
        except (OSError, URLError) as exc:
            self.red_gate = True
            self.record(
                "compose-smoke",
                ["urlopen", "loopback endpoints"],
                "failed",
                detail=str(exc),
            )
        finally:
            subprocess.run(
                [*compose, "-p", project, "down", "--volumes", "--remove-orphans"],
                cwd=ROOT,
                env=env,
                check=False,
                shell=False,
                capture_output=True,
                text=True,
            )

    def render(self, repository: dict[str, object], host: dict[str, object]) -> tuple[Path, Path]:
        finished_at = _now()
        failed = any(step.status == "failed" for step in self.steps)
        skipped = any(step.status == "skipped" for step in self.steps)
        blocked = bool(self.blockers)
        overall = (
            "failed"
            if failed
            else "incomplete"
            if skipped
            else "passed-with-environment-blocker"
            if blocked
            else "passed"
        )
        limitations = [
            "Automatic reconstruction remains deliberately bounded to supported plane and "
            "full-cylinder mechanical geometry.",
            "Fillet, chamfer, pattern, revolve, pocket, and spline compilation exist, but "
            "general automatic inference for those operations is P1/P2.",
            "Open3D and build123d are not runtime dependencies; deterministic custom fitting "
            "and CadQuery/OCP are used.",
        ]
        visual_inspection = {
            "inspectedBy": os.environ.get("ACCEPTANCE_VISUAL_INSPECTED_BY"),
            "date": os.environ.get("ACCEPTANCE_VISUAL_INSPECTION_DATE"),
            "findings": os.environ.get("ACCEPTANCE_VISUAL_INSPECTION_FINDINGS"),
        }
        payload: dict[str, object] = {
            "schemaVersion": 1,
            "startedAt": self.started_at,
            "finishedAt": finished_at,
            "repository": repository,
            "host": host,
            "overallStatus": overall,
            "steps": [asdict(step) for step in self.steps],
            "sampleEvidence": self.sample_evidence,
            "screenshots": self.screenshots,
            "visualInspection": visual_inspection,
            "docker": self.docker,
            "fallbacks": self.fallbacks,
            "blockers": self.blockers,
            "limitations": limitations,
        }
        json_path = self.output / "acceptance.json"
        json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        raw_changed_files = repository.get("changedFiles", [])
        changed_files = (
            [path for path in raw_changed_files if isinstance(path, str)]
            if isinstance(raw_changed_files, list)
            else []
        )
        lines = [
            "# Mesh2Param acceptance report",
            "",
            f"- Status: **{overall}**",
            f"- Repository: `{repository['path']}`",
            f"- Branch/commit: `{repository['branch']}` / `{repository['commit']}`",
            f"- Started/finished: `{self.started_at}` / `{finished_at}`",
            "- Local URLs: web `http://127.0.0.1:5173`, API "
            "`http://127.0.0.1:8000`, docs `http://127.0.0.1:8000/docs`",
            "",
            "Mesh2Param reconstructs an editable, geometrically equivalent CAD model. It does not "
            "guarantee recovery of the source designer's exact original feature history.",
            "",
            "## Ordered evidence",
            "",
            "| Step | Status | Duration | Command | Log |",
            "|---|---:|---:|---|---|",
        ]
        for step in self.steps:
            command = " ".join(step.command).replace("|", "\\|")
            lines.append(
                f"| `{step.id}` | {step.status} | {step.duration_ms} ms | `{command}` | "
                f"`{step.log or '-'}` |"
            )
        lines.extend(
            [
                "",
                "## Architecture and workflow",
                "",
                "The React/Vite/Three.js workspace uses typed CADGraph contracts and a local-first "
                "Dexie cache. FastAPI owns project state in SQLite/WAL and immutable SHA-256 CAS "
                "artifacts. A standalone, single-concurrency geometry worker executes trusted "
                "operation mappings in isolated job directories; the production worker has no "
                "network. The workflow is Import, Repair, Surfaces, Features, Refine, Validate, "
                "and Export.",
                "",
                "## Sample and artifacts",
                "",
                "```json",
                json.dumps(self.sample_evidence, indent=2, sort_keys=True),
                "```",
                "",
                "## Visual inspection",
                "",
                "- Evidence: "
                + (", ".join(f"`{item}`" for item in self.screenshots) or "not supplied"),
                f"- Inspected by: `{visual_inspection['inspectedBy'] or 'not supplied'}`",
                f"- Inspection date: `{visual_inspection['date'] or 'not supplied'}`",
                "- Findings: " + str(visual_inspection["findings"] or "not supplied"),
                "- Screenshots are evidence; the named inspection is the visual-quality claim.",
                "",
                "## Primary files in the accepted commit",
                "",
                *[f"- `{path}`" for path in changed_files],
                "",
                "## Docker, blockers, and fallbacks",
                "",
                "```json",
                json.dumps(
                    {
                        "docker": self.docker,
                        "blockers": self.blockers,
                        "fallbacks": self.fallbacks,
                    },
                    indent=2,
                    sort_keys=True,
                ),
                "```",
                "",
                "## Remaining limitations",
                "",
                *[f"- {item}" for item in limitations],
                "",
                "Primary source, deployment, security, format, validation, and licensing details "
                "are in `README.md`, `docs/`, `SECURITY.md`, and `THIRD_PARTY_NOTICES.md`.",
                "",
            ]
        )
        markdown_path = self.output / "acceptance.md"
        markdown_path.write_text("\n".join(lines), encoding="utf-8")
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(markdown_path, REPORT_PATH)
        return json_path, markdown_path

    def execute(self) -> int:
        starting_dirty = _dirty_paths()
        repository: dict[str, object] = {
            "path": str(ROOT),
            "commit": _git("rev-parse", "HEAD") or "unknown",
            "branch": _git("branch", "--show-current") or "detached",
            "dirtyPaths": starting_dirty,
            "changedFiles": _git(
                "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"
            ).splitlines(),
        }
        self.tool_snapshot()
        if self.skip_install:
            self.record(
                "pnpm-install",
                ["pnpm", "install", "--frozen-lockfile"],
                "skipped",
                detail="--skip-install",
            )
            self.record(
                "uv-sync",
                ["uv", "sync", "--frozen", "--extra", "dev"],
                "skipped",
                detail="--skip-install",
            )
        else:
            self.run_command("pnpm-install", ["pnpm", "install", "--frozen-lockfile"])
            self.run_command("uv-sync", ["uv", "sync", "--frozen", "--extra", "dev"])
        self.run_command("typecheck", ["pnpm", "typecheck"])
        self.run_command("lint", ["pnpm", "lint"])
        self.run_command("test", ["pnpm", "test"])
        self.run_command("geometry", ["pnpm", "test:geometry"])
        self.run_command("build", ["pnpm", "build"])
        self.backend_smoke()
        if self.skip_e2e:
            self.record("e2e", ["pnpm", "test:e2e"], "skipped", detail="--skip-e2e")
            self.fallbacks.append("Playwright CLI acceptance explicitly skipped by runner option")
        else:
            self.run_command(
                "e2e",
                ["pnpm", "test:e2e"],
                env=_clean_mesh2param_environment(),
            )
        self.collect_sample_evidence()
        self.run_command("samples", ["pnpm", "samples:check"])
        self.run_command("licenses", ["pnpm", "licenses:check"])
        self.docker_acceptance()
        final_dirty = _dirty_paths()
        dirty_path = self.evidence / "dirty-paths.json"
        dirty_path.write_text(
            json.dumps({"starting": starting_dirty, "final": final_dirty}, indent=2) + "\n",
            encoding="utf-8",
        )
        clean = not starting_dirty and not final_dirty
        self.record(
            "final-dirty-check",
            ["git", "status", "--short"],
            "passed" if clean else "failed",
            detail=None
            if clean
            else "acceptance must start and finish from a clean tracked worktree",
            evidence=[str(dirty_path)],
        )
        host = json.loads((self.evidence / "host.json").read_text(encoding="utf-8"))
        json_path, markdown_path = self.render(repository, host)
        result = {
            "status": json.loads(json_path.read_text())["overallStatus"],
            "json": str(json_path),
            "markdown": str(markdown_path),
        }
        print(json.dumps(result, indent=2))
        return 0 if result["status"] in {"passed", "passed-with-environment-blocker"} else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-install", action="store_true")
    parser.add_argument("--skip-e2e", action="store_true")
    parser.add_argument("--skip-docker", action="store_true")
    args = parser.parse_args()
    return AcceptanceRun(
        skip_install=args.skip_install,
        skip_e2e=args.skip_e2e,
        skip_docker=args.skip_docker,
    ).execute()


if __name__ == "__main__":
    raise SystemExit(main())
