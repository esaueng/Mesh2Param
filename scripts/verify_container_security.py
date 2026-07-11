"""Inspect and exercise the hardened three-container Mesh2Param deployment."""

from __future__ import annotations

import argparse
import http.client
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

SERVICE_NAMES = ("api", "worker", "web")
BACKEND_DATA_PATH = "/var/lib/mesh2param"


class VerificationFailure(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class CheckResult:
    name: str
    passed: bool
    detail: str

    def to_dict(self) -> dict[str, object]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise VerificationFailure(f"{label} is not an object")
    return cast(dict[str, object], value)


def _sequence(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, list):
        raise VerificationFailure(f"{label} is not an array")
    return cast(list[object], value)


def _positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _run(
    command: Sequence[str], *, timeout: float = 30.0, check: bool = True
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        list(command),
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if check and result.returncode != 0:
        stderr = result.stderr.strip()[-2000:]
        raise VerificationFailure(f"command failed ({' '.join(command)}): {stderr}")
    return result


def _result(results: list[CheckResult], name: str, passed: bool, detail: str) -> None:
    results.append(CheckResult(name=name, passed=passed, detail=detail))


def validate_compose_model(model: Mapping[str, object]) -> list[CheckResult]:
    """Validate resolved Compose topology without relying on YAML text matching."""

    results: list[CheckResult] = []
    services = _mapping(model.get("services"), "Compose services")
    _result(
        results,
        "compose.services",
        set(services) == set(SERVICE_NAMES),
        "exactly api, worker, and web are defined",
    )
    for service_name in SERVICE_NAMES:
        service = _mapping(services.get(service_name), f"Compose service {service_name}")
        ports = service.get("ports")
        published = bool(ports)
        _result(
            results,
            f"compose.{service_name}.published-ports",
            published is (service_name == "web"),
            "only the web service may publish a host port",
        )
        _result(
            results,
            f"compose.{service_name}.read-only",
            service.get("read_only") is True,
            "root filesystem is read-only",
        )
        _result(
            results,
            f"compose.{service_name}.non-root-user",
            str(service.get("user", "")).split(":", 1)[0] not in {"", "0", "root"},
            "explicit non-root user is configured",
        )
    worker = _mapping(services.get("worker"), "Compose worker")
    _result(
        results,
        "compose.worker.no-network",
        worker.get("network_mode") == "none",
        "worker network namespace is disabled",
    )
    networks = _mapping(model.get("networks"), "Compose networks")
    backend = _mapping(networks.get("backend"), "Compose backend network")
    _result(
        results,
        "compose.backend.internal",
        backend.get("internal") is True,
        "backend network is internal-only",
    )
    return results


def _published_bindings(document: Mapping[str, object]) -> list[tuple[str, str, str]]:
    network = _mapping(document.get("NetworkSettings"), "NetworkSettings")
    ports = network.get("Ports")
    if ports is None:
        return []
    bindings: list[tuple[str, str, str]] = []
    for container_port, raw_bindings in _mapping(ports, "NetworkSettings.Ports").items():
        if raw_bindings is None:
            continue
        for raw_binding in _sequence(raw_bindings, f"bindings for {container_port}"):
            binding = _mapping(raw_binding, "port binding")
            bindings.append(
                (
                    container_port,
                    str(binding.get("HostIp", "")),
                    str(binding.get("HostPort", "")),
                )
            )
    return bindings


def validate_inspect_documents(
    documents: Mapping[str, Mapping[str, object]],
) -> list[CheckResult]:
    """Validate effective Docker controls from ``docker inspect`` documents."""

    results: list[CheckResult] = []
    for service_name in SERVICE_NAMES:
        document = documents[service_name]
        config = _mapping(document.get("Config"), f"{service_name}.Config")
        host = _mapping(document.get("HostConfig"), f"{service_name}.HostConfig")
        state = _mapping(document.get("State"), f"{service_name}.State")
        user = str(config.get("User", "")).split(":", 1)[0]
        _result(
            results,
            f"inspect.{service_name}.non-root",
            user not in {"", "0", "root"},
            f"effective user is {config.get('User', '')!s}",
        )
        _result(
            results,
            f"inspect.{service_name}.read-only",
            host.get("ReadonlyRootfs") is True,
            "ReadonlyRootfs is enabled",
        )
        raw_cap_drop = host.get("CapDrop")
        cap_drop = {
            str(item).upper()
            for item in _sequence(
                raw_cap_drop if raw_cap_drop is not None else [],
                f"{service_name}.HostConfig.CapDrop",
            )
        }
        _result(
            results,
            f"inspect.{service_name}.capabilities",
            "ALL" in cap_drop,
            "all Linux capabilities are dropped",
        )
        raw_security_options = host.get("SecurityOpt")
        security_options = {
            str(item).casefold()
            for item in _sequence(
                raw_security_options if raw_security_options is not None else [],
                f"{service_name}.HostConfig.SecurityOpt",
            )
        }
        _result(
            results,
            f"inspect.{service_name}.no-new-privileges",
            any(item.startswith("no-new-privileges") for item in security_options),
            "no-new-privileges is enabled",
        )
        for field, label in (
            ("NanoCpus", "cpu"),
            ("Memory", "memory"),
            ("PidsLimit", "pids"),
        ):
            _result(
                results,
                f"inspect.{service_name}.{label}-limit",
                _positive_int(host.get(field)),
                f"{field} is nonzero",
            )

        health = state.get("Health")
        health_status = (
            str(_mapping(health, f"{service_name}.State.Health").get("Status", ""))
            if health is not None
            else ""
        )
        _result(
            results,
            f"inspect.{service_name}.healthy",
            health_status == "healthy",
            f"container health is {health_status or 'missing'}",
        )

        allowed_writable = {BACKEND_DATA_PATH} if service_name in {"api", "worker"} else set()
        mounts = document.get("Mounts", [])
        safe_mounts = True
        mount_detail = "only declared volumes are writable"
        for raw_mount in _sequence(mounts, f"{service_name}.Mounts"):
            mount = _mapping(raw_mount, f"{service_name} mount")
            mount_type = str(mount.get("Type", ""))
            destination = str(mount.get("Destination", ""))
            if mount_type == "bind":
                safe_mounts = False
                mount_detail = f"bind mount is forbidden: {destination}"
                break
            if mount.get("RW") is True and destination not in allowed_writable:
                safe_mounts = False
                mount_detail = f"unexpected writable mount: {destination}"
                break
        _result(
            results,
            f"inspect.{service_name}.mounts",
            safe_mounts,
            mount_detail,
        )

        tmpfs = _mapping(host.get("Tmpfs", {}), f"{service_name}.HostConfig.Tmpfs")
        safe_tmpfs = bool(tmpfs) and all(
            {"noexec", "nosuid", "nodev"}.issubset(
                {option.split("=", 1)[0] for option in str(raw_options).split(",")}
            )
            for raw_options in tmpfs.values()
        )
        _result(
            results,
            f"inspect.{service_name}.tmpfs",
            safe_tmpfs,
            "tmpfs mounts use noexec,nosuid,nodev",
        )

        bindings = _published_bindings(document)
        if service_name == "web":
            safe_ports = bool(bindings) and all(
                port == "8080/tcp" and host_ip in {"127.0.0.1", "::1"}
                for port, host_ip, _host_port in bindings
            )
        else:
            safe_ports = not bindings
        _result(
            results,
            f"inspect.{service_name}.ports",
            safe_ports,
            "only web:8080 is published and it is loopback-bound",
        )

    worker_host = _mapping(documents["worker"].get("HostConfig"), "worker.HostConfig")
    _result(
        results,
        "inspect.worker.no-network",
        worker_host.get("NetworkMode") == "none",
        "worker NetworkMode is none",
    )
    return results


def _container_ids(project_name: str) -> dict[str, str]:
    container_ids: dict[str, str] = {}
    for service_name in SERVICE_NAMES:
        result = _run(
            (
                "docker",
                "container",
                "ls",
                "--all",
                "--quiet",
                "--no-trunc",
                "--filter",
                f"label=com.docker.compose.project={project_name}",
                "--filter",
                f"label=com.docker.compose.service={service_name}",
            )
        )
        matches = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        if len(matches) != 1:
            raise VerificationFailure(
                f"expected one {service_name} container for project {project_name}, "
                f"found {len(matches)}"
            )
        container_ids[service_name] = matches[0]
    return container_ids


def _inspect(container_ids: Mapping[str, str]) -> dict[str, Mapping[str, object]]:
    command = ["docker", "inspect", *container_ids.values()]
    raw = json.loads(_run(command).stdout)
    documents_by_id: dict[str, Mapping[str, object]] = {}
    for item in _sequence(raw, "docker inspect output"):
        document = _mapping(item, "docker inspect item")
        documents_by_id[str(document.get("Id", ""))] = document
    return {
        service: documents_by_id[container_id]
        for service, container_id in container_ids.items()
    }


def _docker_exec(container_id: str, code: str, *, timeout: float = 15.0) -> bool:
    result = _run(
        ("docker", "exec", container_id, "python", "-P", "-c", code),
        timeout=timeout,
        check=False,
    )
    return result.returncode == 0


def _request_json(
    url: str,
    *,
    method: str = "GET",
    payload: object | None = None,
    headers: Mapping[str, str] | None = None,
    timeout: float = 10.0,
) -> tuple[int, Mapping[str, object], Mapping[str, str]]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request_headers = {"Accept": "application/json", **(headers or {})}
    if body is not None:
        request_headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=request_headers, method=method)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = json.loads(response.read())
        return (
            response.status,
            _mapping(raw, f"response from {url}"),
            dict(response.headers.items()),
        )


def _http_runtime_checks(
    web_port: int,
    worker_container_id: str,
    results: list[CheckResult],
) -> None:
    base_url = f"http://127.0.0.1:{web_port}"
    browser_origin = base_url
    for path in ("/health", "/ready", "/openapi.json", "/api/projects"):
        try:
            status, _payload, _headers = _request_json(base_url + path)
            passed = status == 200
            detail = f"{path} returned {status} through the web origin"
        except (OSError, ValueError, VerificationFailure) as error:
            passed = False
            detail = f"{path} failed: {error}"
        _result(results, f"http{path}", passed, detail)

    try:
        with urllib.request.urlopen(base_url + "/", timeout=10) as response:
            root_body = response.read().decode("utf-8")
            root_csp = response.headers.get("Content-Security-Policy", "")
            root_passed = (
                response.status == 200
                and response.headers.get_content_type() == "text/html"
                and "<title>Mesh2Param</title>" in root_body
                and 'id="root"' in root_body
                and "default-src 'self'" in root_csp
                and "'unsafe-inline'" not in root_csp
            )
            root_detail = (
                f"/ returned {response.status} with the production shell and strict CSP"
            )
    except (OSError, UnicodeError) as error:
        root_passed = False
        root_detail = f"/ failed: {error}"
    _result(results, "http/static-shell", root_passed, root_detail)

    try:
        with urllib.request.urlopen(base_url + "/docs", timeout=10) as response:
            docs_body = response.read().decode("utf-8")
            docs_csp = response.headers.get("Content-Security-Policy", "")
            docs_passed = (
                response.status == 200
                and response.headers.get_content_type() == "text/html"
                and "default-src 'none'" in docs_csp
                and "'unsafe-inline'" not in docs_csp
                and "<script" not in docs_body.casefold()
                and "<style" not in docs_body.casefold()
            )
            docs_detail = (
                f"/docs returned {response.status} with a script-free strict CSP"
            )
    except (OSError, UnicodeError) as error:
        docs_passed = False
        docs_detail = f"/docs failed: {error}"
    _result(results, "http/docs-csp", docs_passed, docs_detail)

    status, project_response, project_headers = _request_json(
        base_url + "/api/projects",
        method="POST",
        payload={"name": "Container security smoke", "units": "mm"},
        headers={"Origin": browser_origin},
    )
    project_data = _mapping(project_response.get("data"), "project response data")
    project_id = str(project_data.get("id", ""))
    revision = project_headers.get("Etag") or project_headers.get("ETag") or '"rev-1"'
    cors_origin = next(
        (
            value
            for name, value in project_headers.items()
            if name.casefold() == "access-control-allow-origin"
        ),
        None,
    )
    _result(
        results,
        "http.project-create",
        status == 201
        and bool(project_id)
        and cors_origin == browser_origin,
        "same-origin project creation is accepted with an explicit CORS response",
    )

    upload_path = (
        f"/api/projects/{project_id}/upload?filename=smoke.stl&units=mm&unitsConfirmed=true"
    )
    connection = http.client.HTTPConnection("127.0.0.1", web_port, timeout=5)
    try:
        connection.request(
            "POST",
            upload_path,
            body=b"x",
            headers={
                "Content-Type": "application/octet-stream",
                "Content-Length": str(1025 * 1024 * 1024),
                "If-Match": revision,
                "Origin": browser_origin,
            },
        )
        oversized_status = connection.getresponse().status
    finally:
        connection.close()
    _result(
        results,
        "http.oversized-upload",
        oversized_status == 413,
        f"oversized upload returned {oversized_status}",
    )

    malformed_status = 0
    malformed_request = urllib.request.Request(
        base_url + upload_path,
        data=b"PK\x03\x04not-a-mesh",
        headers={
            "Content-Type": "application/octet-stream",
            "If-Match": revision,
            "Origin": browser_origin,
        },
        method="POST",
    )
    try:
        urllib.request.urlopen(malformed_request, timeout=10)
    except urllib.error.HTTPError as error:
        malformed_status = error.code
    _result(
        results,
        "http.malformed-upload",
        malformed_status in {415, 422},
        f"archive/polyglot upload returned {malformed_status}",
    )

    sample_status, sample_response, _sample_headers = _request_json(
        base_url + "/api/samples/rectangular-block/open",
        method="POST",
        headers={"Origin": browser_origin},
    )
    sample_data = _mapping(sample_response.get("data"), "sample response data")
    job = _mapping(sample_data.get("job"), "sample job")
    job_id = str(job.get("id", ""))
    sse_ok = False
    if sample_status == 202 and job_id:
        request = urllib.request.Request(
            base_url + f"/api/jobs/{job_id}/events",
            headers={"Accept": "text/event-stream", "Origin": browser_origin},
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            content_type = response.headers.get_content_type()
            for _ in range(40):
                line = response.readline()
                if not line:
                    break
                if line.startswith(b"data:"):
                    sse_ok = content_type == "text/event-stream"
                    break
    _result(
        results,
        "http.sse",
        sse_ok,
        "job SSE events stream through Nginx without a separate origin",
    )

    worker_document = _inspect({"worker": worker_container_id})["worker"]
    state = _mapping(worker_document.get("State"), "worker.State")
    health = _mapping(state.get("Health"), "worker.State.Health")
    _result(
        results,
        "runtime.worker-survived-rejections",
        state.get("Running") is True and health.get("Status") == "healthy",
        "worker remains running and healthy after rejected uploads",
    )


def _runtime_worker_checks(
    worker_container_id: str, results: list[CheckResult]
) -> None:
    writable_code = """
from pathlib import Path
import secrets
p = Path('/var/lib/mesh2param/jobs') / ('security-' + secrets.token_hex(12))
p.write_bytes(b'ok')
p.unlink()
"""
    _result(
        results,
        "runtime.worker-job-write",
        _docker_exec(worker_container_id, writable_code),
        "worker can create and remove a randomized job-volume file",
    )

    readonly_code = """
from pathlib import Path
import secrets
for parent in (Path('/app'), Path('/etc'), Path('/opt/venv')):
    target = parent / ('security-' + secrets.token_hex(8))
    try:
        target.write_bytes(b'forbidden')
    except OSError:
        continue
    target.unlink(missing_ok=True)
    raise SystemExit('unexpected write succeeded: ' + str(parent))
"""
    _result(
        results,
        "runtime.worker-read-only",
        _docker_exec(worker_container_id, readonly_code),
        "worker cannot write /app, /etc, or /opt/venv",
    )

    network_code = """
import socket
try:
    socket.getaddrinfo('example.com', 443)
except OSError:
    pass
else:
    raise SystemExit('DNS unexpectedly succeeded')
try:
    socket.create_connection(('1.1.1.1', 443), timeout=1)
except OSError:
    pass
else:
    raise SystemExit('outbound TCP unexpectedly succeeded')
"""
    _result(
        results,
        "runtime.worker-no-egress",
        _docker_exec(worker_container_id, network_code),
        "worker outbound DNS and TCP both fail",
    )


def _compose_command() -> tuple[str, ...]:
    candidates = (("docker", "compose"), ("docker-compose",))
    for candidate in candidates:
        try:
            result = _run((*candidate, "version"), timeout=10, check=False)
        except OSError:
            continue
        if result.returncode == 0:
            return candidate
    raise VerificationFailure("neither 'docker compose' nor 'docker-compose' is available")


def _compose_model(compose_file: Path, project_name: str) -> Mapping[str, object]:
    compose = _compose_command()
    output = _run(
        (
            *compose,
            "--file",
            str(compose_file),
            "--project-name",
            project_name,
            "config",
            "--format",
            "json",
        )
    ).stdout
    return _mapping(json.loads(output), "resolved Compose model")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-name",
        "--project",
        dest="project_name",
        default=os.environ.get("COMPOSE_PROJECT_NAME", "mesh2param"),
        help="isolated Compose project to inspect",
    )
    parser.add_argument(
        "--compose-file",
        type=Path,
        default=Path("docker-compose.yml"),
    )
    parser.add_argument("--web-port", type=int, default=8080)
    parser.add_argument("--inspect-only", action="store_true")
    parser.add_argument("--json-output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    results: list[CheckResult] = []
    try:
        results.extend(validate_compose_model(_compose_model(args.compose_file, args.project_name)))
        container_ids = _container_ids(args.project_name)
        documents = _inspect(container_ids)
        results.extend(validate_inspect_documents(documents))
        if not args.inspect_only:
            _runtime_worker_checks(container_ids["worker"], results)
            _http_runtime_checks(args.web_port, container_ids["worker"], results)
    except (OSError, ValueError, KeyError, VerificationFailure, subprocess.TimeoutExpired) as error:
        _result(results, "verifier.execution", False, str(error))

    payload = {
        "schemaVersion": 1,
        "projectName": args.project_name,
        "passed": bool(results) and all(result.passed for result in results),
        "checks": [result.to_dict() for result in results],
    }
    if args.json_output is not None:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    for result in results:
        marker = "PASS" if result.passed else "FAIL"
        print(f"[{marker}] {result.name}: {result.detail}")
    if not payload["passed"]:
        print(json.dumps(payload, indent=2, sort_keys=True), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "CheckResult",
    "VerificationFailure",
    "main",
    "validate_compose_model",
    "validate_inspect_documents",
]
