from __future__ import annotations

import ipaddress
import re
import unicodedata
from collections.abc import Iterable, Mapping
from urllib.parse import quote, urlsplit

from mesh2param_api.storage import validate_display_filename


class SecurityPolicyError(ValueError):
    """A request origin, host, or reflected header value violates policy."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(detail)

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "detail": self.detail}


def safe_header_value(value: str) -> str:
    """Reject response-header injection and invisible control characters."""

    if not isinstance(value, str):
        raise SecurityPolicyError("unsafe_header", "header value must be a string")
    if not value or any(ord(character) < 0x20 or ord(character) == 0x7F for character in value):
        raise SecurityPolicyError("unsafe_header", "header value contains control characters")
    return value


def _idna_hostname(hostname: str) -> str:
    hostname = hostname.rstrip(".").casefold()
    if not hostname:
        raise SecurityPolicyError("invalid_host", "hostname cannot be empty")
    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        try:
            ascii_hostname = hostname.encode("idna").decode("ascii")
        except UnicodeError as error:
            raise SecurityPolicyError("invalid_host", "hostname is not valid IDNA") from error
        labels = ascii_hostname.split(".")
        if any(
            not label
            or len(label) > 63
            or label.startswith("-")
            or label.endswith("-")
            or re.fullmatch(r"[a-z0-9-]+", label) is None
            for label in labels
        ):
            raise SecurityPolicyError(
                "invalid_host", "hostname contains an invalid label"
            ) from None
        return ascii_hostname
    return ip.compressed


def normalize_origin(origin: str) -> str:
    """Return the serialized HTTP(S) origin used for exact CORS comparison."""

    safe_header_value(origin)
    if origin == "null":
        raise SecurityPolicyError("invalid_origin", "opaque 'null' origins are not allowed")
    try:
        parsed = urlsplit(origin)
        port = parsed.port
    except ValueError as error:
        raise SecurityPolicyError("invalid_origin", "origin contains an invalid port") from error
    if (
        parsed.scheme.casefold() not in {"http", "https"}
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise SecurityPolicyError(
            "invalid_origin", "origin must be an HTTP(S) scheme and authority"
        )
    scheme = parsed.scheme.casefold()
    hostname = _idna_hostname(parsed.hostname)
    default_port = 80 if scheme == "http" else 443
    port_suffix = "" if port is None or port == default_port else f":{port}"
    host_text = f"[{hostname}]" if ":" in hostname else hostname
    return f"{scheme}://{host_text}{port_suffix}"


def parse_allowed_origins(
    origins: str | Iterable[str], *, production: bool = True
) -> tuple[str, ...]:
    """Parse comma-delimited or iterable CORS origins with no production wildcard."""

    raw_origins = origins.split(",") if isinstance(origins, str) else list(origins)
    normalized: list[str] = []
    for raw_origin in raw_origins:
        candidate = raw_origin.strip()
        if not candidate:
            continue
        if candidate == "*":
            if production:
                raise SecurityPolicyError(
                    "wildcard_cors_not_allowed", "production CORS cannot use a wildcard origin"
                )
            normalized.append(candidate)
        else:
            normalized.append(normalize_origin(candidate))
    if production and not normalized:
        raise SecurityPolicyError(
            "cors_origins_required", "production requires at least one explicit CORS origin"
        )
    return tuple(dict.fromkeys(normalized))


def parse_allowed_hosts(
    hosts: str | Iterable[str], *, production: bool = True
) -> tuple[str, ...]:
    """Parse trusted hosts and reject wildcard production exposure."""

    raw_hosts = hosts.split(",") if isinstance(hosts, str) else list(hosts)
    normalized: list[str] = []
    for raw_host in raw_hosts:
        candidate = raw_host.strip()
        if not candidate:
            continue
        if candidate == "*":
            if production:
                raise SecurityPolicyError(
                    "wildcard_host_not_allowed",
                    "production trusted hosts cannot contain a wildcard",
                )
            normalized.append(candidate)
        else:
            normalized.append(normalize_host(candidate))
    if production and not normalized:
        raise SecurityPolicyError(
            "allowed_hosts_required", "production requires at least one trusted host"
        )
    return tuple(dict.fromkeys(normalized))


def is_origin_allowed(origin: str | None, allowed_origins: Iterable[str]) -> bool:
    if origin is None:
        return False
    try:
        normalized = normalize_origin(origin)
        allowed = parse_allowed_origins(allowed_origins, production=False)
    except SecurityPolicyError:
        return False
    return "*" in allowed or normalized in allowed


def require_allowed_origin(origin: str | None, allowed_origins: Iterable[str]) -> str:
    if origin is None:
        raise SecurityPolicyError("origin_required", "request Origin header is required")
    normalized = normalize_origin(origin)
    if not is_origin_allowed(normalized, allowed_origins):
        raise SecurityPolicyError("origin_not_allowed", "request origin is not allowed")
    return normalized


def _split_host(value: str) -> tuple[str, int | None]:
    safe_header_value(value)
    if any(character.isspace() for character in value) or any(
        character in value for character in "/\\?#,@;"
    ):
        raise SecurityPolicyError("invalid_host", "Host header contains forbidden characters")
    if value.endswith(":"):
        raise SecurityPolicyError("invalid_host", "Host header has an empty port")
    try:
        parsed = urlsplit(f"//{value}")
        port = parsed.port
    except ValueError as error:
        raise SecurityPolicyError("invalid_host", "Host header contains an invalid port") from error
    if parsed.hostname is None or parsed.username is not None or parsed.password is not None:
        raise SecurityPolicyError("invalid_host", "Host header is not a valid authority")
    return _idna_hostname(parsed.hostname), port


def normalize_host(host: str) -> str:
    hostname, port = _split_host(host)
    host_text = f"[{hostname}]" if ":" in hostname else hostname
    return host_text if port is None else f"{host_text}:{port}"


def is_host_allowed(host: str, allowed_hosts: Iterable[str]) -> bool:
    try:
        request_hostname, request_port = _split_host(host)
    except SecurityPolicyError:
        return False
    for allowed_host in allowed_hosts:
        candidate = allowed_host.strip()
        if candidate == "*":
            return True
        try:
            allowed_hostname, allowed_port = _split_host(candidate)
        except SecurityPolicyError:
            continue
        if request_hostname == allowed_hostname and (
            allowed_port is None or allowed_port == request_port
        ):
            return True
    return False


def require_allowed_host(host: str | None, allowed_hosts: Iterable[str]) -> str:
    if host is None:
        raise SecurityPolicyError("host_required", "request Host header is required")
    normalized = normalize_host(host)
    if not is_host_allowed(normalized, allowed_hosts):
        raise SecurityPolicyError("host_not_allowed", "request host is not allowed")
    return normalized


def api_security_headers(*, tls: bool = False) -> Mapping[str, str]:
    """Strict defaults for API and artifact responses.

    Callers may add route-specific cache and content-disposition headers, but should not weaken
    these values for user-controlled upload responses.
    """

    headers = {
        "Cache-Control": "no-store",
        "Content-Security-Policy": (
            "default-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'"
        ),
        "Cross-Origin-Opener-Policy": "same-origin",
        "Cross-Origin-Resource-Policy": "same-origin",
        "Permissions-Policy": "camera=(), geolocation=(), microphone=(), payment=(), usb=()",
        "Referrer-Policy": "no-referrer",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
    }
    if tls:
        headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    return headers


def attachment_content_disposition(display_filename: str) -> str:
    """Build an injection-safe attachment value with ASCII and RFC 5987 names."""

    normalized = validate_display_filename(display_filename)
    decomposed = unicodedata.normalize("NFKD", normalized)
    ascii_name = decomposed.encode("ascii", "ignore").decode("ascii")
    ascii_name = re.sub(r"[^A-Za-z0-9._ -]", "_", ascii_name).strip(" .")
    if not ascii_name:
        ascii_name = "download"
    ascii_name = ascii_name.replace("\\", "_").replace('"', "_")[:150]
    encoded = quote(normalized.encode("utf-8"), safe="!#$&+-.^_`|~")
    return safe_header_value(
        f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{encoded}"
    )


__all__ = [
    "SecurityPolicyError",
    "api_security_headers",
    "attachment_content_disposition",
    "is_host_allowed",
    "is_origin_allowed",
    "normalize_host",
    "normalize_origin",
    "parse_allowed_hosts",
    "parse_allowed_origins",
    "require_allowed_host",
    "require_allowed_origin",
    "safe_header_value",
]
