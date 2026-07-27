"""Audit installed Python and pnpm dependency licenses against repository policy."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import re
import sys
import tomllib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = ROOT / "licenses" / "overrides.toml"
DEFAULT_NOTICES = ROOT / "THIRD_PARTY_NOTICES.md"
INVENTORY_START = "<!-- BEGIN GENERATED DEPENDENCY INVENTORY -->"
INVENTORY_END = "<!-- END GENERATED DEPENDENCY INVENTORY -->"


@dataclass(frozen=True, order=True)
class LicenseRecord:
    ecosystem: str
    name: str
    version: str
    license: str
    platform_constrained: bool = False

    @property
    def package_key(self) -> str:
        return f"{self.ecosystem}:{self.name.casefold()}"


@dataclass(frozen=True)
class LicenseOverride:
    ecosystem: str
    name: str
    license: str
    source: str
    reason: str

    @property
    def package_key(self) -> str:
        return f"{self.ecosystem}:{self.name.casefold()}"


@dataclass(frozen=True)
class RequiredFile:
    path: str
    sha256: str
    source: str


@dataclass(frozen=True)
class LicensePolicy:
    allowed_tokens: tuple[str, ...]
    forbidden_fragments: tuple[str, ...]
    allowed_copyleft_packages: frozenset[str]
    ignored_packages: frozenset[str]
    required_notice_packages: frozenset[str]
    overrides: Mapping[str, LicenseOverride]
    required_files: tuple[RequiredFile, ...]


CLASSIFIER_LICENSES = {
    "Apache Software License": "Apache-2.0",
    "BSD License": "BSD-3-Clause",
    "ISC License (ISCL)": "ISC",
    "MIT License": "MIT",
    "Mozilla Public License 2.0 (MPL 2.0)": "MPL-2.0",
    "Python Software Foundation License": "PSF-2.0",
}

LICENSE_ALIASES = {
    "apache 2.0": "Apache-2.0",
    "apache license 2.0": "Apache-2.0",
    "apache public license 2.0": "Apache-2.0",
    "bsd": "BSD-3-Clause",
    "bsd 3-clause": "BSD-3-Clause",
    "bsd license": "BSD-3-Clause",
    "gnu lesser general public license v3 or later (lgplv3+)": "LGPL-3.0-or-later",
    "isc": "ISC",
    "mit": "MIT",
    "mit license": "MIT",
    "modified bsd license": "BSD-3-Clause",
    "mpl 2.0": "MPL-2.0",
    "python-2.0": "Python-2.0",
}


def _strings(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{field} must be an array of strings")
    return tuple(value)


def _tables(value: object, field: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError(f"{field} must be an array of tables")
    return value


def _required_string(table: Mapping[str, object], field: str) -> str:
    value = table.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value


def load_policy(path: Path = DEFAULT_POLICY) -> LicensePolicy:
    with path.open("rb") as stream:
        document = tomllib.load(stream)
    if document.get("schema_version") != 1:
        raise ValueError("unsupported license policy schema")
    raw_policy = document.get("policy")
    if not isinstance(raw_policy, dict):
        raise ValueError("license policy is missing [policy]")

    overrides: dict[str, LicenseOverride] = {}
    for table in _tables(document.get("overrides", []), "overrides"):
        override = LicenseOverride(
            ecosystem=_required_string(table, "ecosystem"),
            name=_required_string(table, "name"),
            license=_required_string(table, "license"),
            source=_required_string(table, "source"),
            reason=_required_string(table, "reason"),
        )
        if override.package_key in overrides:
            raise ValueError(f"duplicate license override for {override.package_key}")
        overrides[override.package_key] = override

    required_files = tuple(
        RequiredFile(
            path=_required_string(table, "path"),
            sha256=_required_string(table, "sha256"),
            source=_required_string(table, "source"),
        )
        for table in _tables(document.get("required_files", []), "required_files")
    )
    return LicensePolicy(
        allowed_tokens=_strings(raw_policy.get("allowed_license_tokens"), "allowed tokens"),
        forbidden_fragments=_strings(
            raw_policy.get("forbidden_fragments"), "forbidden fragments"
        ),
        allowed_copyleft_packages=frozenset(
            item.casefold()
            for item in _strings(
                raw_policy.get("allowed_copyleft_packages"), "allowed copyleft packages"
            )
        ),
        ignored_packages=frozenset(
            item.casefold()
            for item in _strings(raw_policy.get("ignored_packages"), "ignored packages")
        ),
        required_notice_packages=frozenset(
            item.casefold()
            for item in _strings(
                raw_policy.get("required_notice_packages"), "required notice packages"
            )
        ),
        overrides=overrides,
        required_files=required_files,
    )


def normalize_license(
    expression: str | None,
    license_text: str | None,
    classifiers: Sequence[str],
) -> str | None:
    if expression and expression.strip():
        return expression.strip()
    raw = (license_text or "").strip()
    alias = LICENSE_ALIASES.get(raw.casefold())
    if alias is not None:
        return alias
    if raw.casefold() != "unknown" and re.fullmatch(
        r"[A-Za-z0-9.+-]+(?:\s+(?:AND|OR|WITH)\s+[A-Za-z0-9.+-]+)*", raw
    ):
        return raw
    for classifier in classifiers:
        prefix = "License :: OSI Approved :: "
        if classifier.startswith(prefix):
            resolved = CLASSIFIER_LICENSES.get(classifier.removeprefix(prefix))
            if resolved is not None:
                return resolved
    lowered = raw.casefold()
    if "permission is hereby granted" in lowered or "the mit license" in lowered:
        return "MIT"
    if "apache license" in lowered and "version 2" in lowered:
        return "Apache-2.0"
    if "redistribution and use in source and binary forms" in lowered:
        return "BSD-3-Clause"
    return None


def _python_platform_constrained_packages(*, root: Path = ROOT) -> frozenset[str]:
    """Return packages whose every lockfile edge is constrained by OS or architecture."""

    references: dict[str, list[bool]] = {}
    platform_marker_fields = (
        "os_name",
        "platform_machine",
        "platform_system",
        "sys_platform",
    )

    def inspect(value: object) -> None:
        if isinstance(value, dict):
            name = value.get("name")
            if isinstance(name, str):
                marker = value.get("marker")
                references.setdefault(name.casefold(), []).append(
                    isinstance(marker, str)
                    and any(field in marker for field in platform_marker_fields)
                )
                return
            for nested in value.values():
                inspect(nested)
        elif isinstance(value, list):
            for nested in value:
                inspect(nested)

    for relative in ("uv.lock", "packages/contracts/uv.lock"):
        path = root / relative
        if not path.is_file():
            continue
        with path.open("rb") as stream:
            document = tomllib.load(stream)
        packages = document.get("package", [])
        if not isinstance(packages, list):
            continue
        for package in packages:
            if not isinstance(package, dict):
                continue
            for field, value in package.items():
                if field != "name":
                    inspect(value)
    return frozenset(
        name for name, markers in references.items() if markers and all(markers)
    )


def python_records(
    policy: LicensePolicy, *, root: Path = ROOT
) -> tuple[list[LicenseRecord], list[str]]:
    platform_constrained = _python_platform_constrained_packages(root=root)
    records: set[LicenseRecord] = set()
    errors: list[str] = []
    for distribution in importlib.metadata.distributions():
        name = distribution.metadata.get("Name") or ""
        if not name:
            errors.append("Python distribution without a Name field")
            continue
        package_key = f"python:{name.casefold()}"
        if package_key in policy.ignored_packages:
            continue
        override = policy.overrides.get(package_key)
        license_name = override.license if override is not None else normalize_license(
            distribution.metadata.get("License-Expression"),
            distribution.metadata.get("License"),
            distribution.metadata.get_all("Classifier") or [],
        )
        if license_name is None:
            errors.append(f"unresolved Python license: {name}=={distribution.version}")
            continue
        records.add(
            LicenseRecord(
                "python",
                name,
                distribution.version,
                license_name,
                platform_constrained=name.casefold() in platform_constrained,
            )
        )
    return sorted(records), errors


def javascript_records(
    policy: LicensePolicy, *, root: Path = ROOT
) -> tuple[list[LicenseRecord], list[str]]:
    """Read package metadata directly from pnpm's installed virtual store.

    ``pnpm licenses list`` consults package-index files in the content-addressable
    store. Those indexes are not part of the installed workspace and can be
    missing even when the frozen install itself is complete. Every package that
    pnpm installs for this isolated-linker workspace has one real package
    directory under ``node_modules/.pnpm/*/node_modules``; dependency edges in
    those directories are symlinks. Reading only the real package directories
    therefore inventories every installed transitive package/version without a
    network request, store-index lookup, or install mutation.
    """

    virtual_store = root / "node_modules" / ".pnpm"
    if not virtual_store.is_dir():
        return [], [
            "cannot inspect installed JavaScript packages: "
            f"pnpm virtual store is missing at {virtual_store}"
        ]

    records_by_package: dict[tuple[str, str], LicenseRecord] = {}
    errors: list[str] = []

    for manifest_path in _javascript_manifest_paths(virtual_store):
        relative_path = manifest_path.relative_to(root)
        try:
            document = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            errors.append(f"cannot read JavaScript package metadata at {relative_path}: {exc}")
            continue
        if not isinstance(document, dict):
            errors.append(f"JavaScript package metadata is not an object: {relative_path}")
            continue

        name = document.get("name")
        version = document.get("version")
        if not isinstance(name, str) or not name.strip():
            errors.append(f"JavaScript package has no valid name: {relative_path}")
            continue
        if not isinstance(version, str) or not version.strip():
            errors.append(f"JavaScript package {name} has no valid version: {relative_path}")
            continue

        package_key = f"javascript:{name.casefold()}"
        if package_key in policy.ignored_packages:
            continue
        override = policy.overrides.get(package_key)
        declared_license = _javascript_declared_license(document)
        license_text = None
        if declared_license is None:
            license_text = _javascript_license_file_text(manifest_path.parent)
        resolved = override.license if override is not None else normalize_license(
            declared_license,
            license_text,
            [],
        )
        if resolved is None:
            errors.append(
                f"unresolved JavaScript license: {name}=={version} ({relative_path})"
            )
            continue

        record = LicenseRecord(
            "javascript",
            name,
            version,
            resolved,
            platform_constrained=_javascript_platform_constrained(document),
        )
        identity = (name.casefold(), version)
        existing = records_by_package.get(identity)
        if existing is not None and existing.license != record.license:
            errors.append(
                f"conflicting JavaScript licenses for {name}=={version}: "
                f"{existing.license} and {record.license}"
            )
            continue
        if existing is not None and not existing.platform_constrained:
            record = existing
        records_by_package[identity] = record
    return sorted(records_by_package.values()), errors


def _javascript_manifest_paths(virtual_store: Path) -> list[Path]:
    manifests: list[Path] = []
    for virtual_package in sorted(virtual_store.iterdir(), key=lambda path: path.name):
        installed = virtual_package / "node_modules"
        if not installed.is_dir():
            continue
        for candidate in sorted(installed.iterdir(), key=lambda path: path.name):
            if candidate.is_symlink():
                continue
            if candidate.name.startswith("@") and candidate.is_dir():
                for scoped_candidate in sorted(
                    candidate.iterdir(), key=lambda path: path.name
                ):
                    if scoped_candidate.is_symlink():
                        continue
                    manifest = scoped_candidate / "package.json"
                    if manifest.is_file():
                        manifests.append(manifest)
                continue
            manifest = candidate / "package.json"
            if manifest.is_file():
                manifests.append(manifest)
    return manifests


def _javascript_declared_license(document: Mapping[str, object]) -> str | None:
    license_value = document.get("license")
    if isinstance(license_value, str) and license_value.strip():
        return license_value.strip()
    if isinstance(license_value, dict):
        legacy_type = license_value.get("type")
        if isinstance(legacy_type, str) and legacy_type.strip():
            return legacy_type.strip()

    legacy_licenses = document.get("licenses")
    if not isinstance(legacy_licenses, list):
        return None
    expressions: list[str] = []
    for value in legacy_licenses:
        if isinstance(value, str) and value.strip():
            expressions.append(value.strip())
        elif isinstance(value, dict):
            legacy_type = value.get("type")
            if isinstance(legacy_type, str) and legacy_type.strip():
                expressions.append(legacy_type.strip())
    return " OR ".join(expressions) or None


def _javascript_platform_constrained(document: Mapping[str, object]) -> bool:
    for field in ("os", "cpu", "libc"):
        value = document.get(field)
        if isinstance(value, str):
            constrained = bool(value.strip())
        elif isinstance(value, Sequence):
            constrained = bool(value)
        else:
            constrained = value is not None
        if constrained:
            return True
    return False


def _javascript_license_file_text(package_directory: Path) -> str | None:
    candidates = sorted(
        (
            path
            for path in package_directory.iterdir()
            if path.is_file()
            and path.name.casefold().split(".", maxsplit=1)[0]
            in {"license", "licence", "copying"}
        ),
        key=lambda path: path.name.casefold(),
    )
    for candidate in candidates:
        try:
            text = candidate.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        if text.strip():
            return text
    return None


def policy_errors(
    records: Iterable[LicenseRecord],
    policy: LicensePolicy,
    *,
    unavailable_ecosystems: frozenset[str] = frozenset(),
) -> list[str]:
    records_list = list(records)
    errors: list[str] = []
    present = {record.package_key for record in records_list}
    missing_required = (
        package
        for package in policy.required_notice_packages - present
        if package.partition(":")[0] not in unavailable_ecosystems
    )
    for required in sorted(missing_required):
        errors.append(f"required dependency is not installed: {required}")
    for record in records_list:
        upper = record.license.upper()
        if record.package_key not in policy.allowed_copyleft_packages:
            for fragment in policy.forbidden_fragments:
                if fragment.upper() in upper:
                    errors.append(
                        f"forbidden license for {record.package_key}=={record.version}: "
                        f"{record.license}"
                    )
        if not any(token.upper() in upper for token in policy.allowed_tokens):
            errors.append(
                f"license is not allowlisted for {record.package_key}=={record.version}: "
                f"{record.license}"
            )
    return errors


def required_file_errors(policy: LicensePolicy, *, root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    for required in policy.required_files:
        path = root / required.path
        if not path.is_file():
            errors.append(f"required license file is missing: {required.path}")
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != required.sha256:
            errors.append(
                f"required license file hash changed: {required.path} "
                f"(expected {required.sha256}, got {digest})"
            )
    return errors


def dependency_configuration_errors(*, root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    for relative in ("pyproject.toml", "packages/contracts/pyproject.toml"):
        text = (root / relative).read_text(encoding="utf-8")
        if "jsonschema[format-nongpl]" not in text:
            errors.append(f"{relative} must use jsonschema[format-nongpl]")
        if "jsonschema[format]" in text:
            errors.append(f"{relative} still enables the GPL-bearing jsonschema[format] extra")
    for relative in ("uv.lock", "packages/contracts/uv.lock"):
        lock_text = (root / relative).read_text(encoding="utf-8")
        if 'name = "rfc3987"' in lock_text:
            errors.append(
                f"{relative} still contains the GPL-3.0+ rfc3987 distribution"
            )
        if 'name = "rfc3987-syntax"' not in lock_text:
            errors.append(f"{relative} is missing the non-GPL rfc3987-syntax replacement")
    return errors


def render_inventory(records: Iterable[LicenseRecord]) -> str:
    rows = [
        INVENTORY_START,
        "",
        "| Ecosystem | Package | Version | Declared/effective license |",
        "| --- | --- | --- | --- |",
    ]
    for record in sorted(
        {record for record in records if not record.platform_constrained}
    ):
        values = (
            record.ecosystem,
            record.name,
            record.version,
            record.license,
        )
        rows.append("| " + " | ".join(value.replace("|", "\\|") for value in values) + " |")
    rows.extend(("", INVENTORY_END))
    return "\n".join(rows)


def inventory_errors(
    records: Iterable[LicenseRecord], *, notices_path: Path = DEFAULT_NOTICES
) -> list[str]:
    if not notices_path.is_file():
        return [f"third-party notice file is missing: {notices_path.relative_to(ROOT)}"]
    text = notices_path.read_text(encoding="utf-8")
    expected = render_inventory(records)
    start = text.find(INVENTORY_START)
    end = text.find(INVENTORY_END)
    if start < 0 or end < start:
        return ["THIRD_PARTY_NOTICES.md is missing generated inventory markers"]
    actual = text[start : end + len(INVENTORY_END)]
    if actual != expected:
        return [
            "THIRD_PARTY_NOTICES.md dependency inventory is stale; run "
            "`uv run --extra dev python scripts/check_licenses.py --write-notices`"
        ]
    return []


def write_inventory(
    records: Iterable[LicenseRecord], *, notices_path: Path = DEFAULT_NOTICES
) -> None:
    text = notices_path.read_text(encoding="utf-8")
    start = text.find(INVENTORY_START)
    end = text.find(INVENTORY_END)
    if start < 0 or end < start:
        raise ValueError("THIRD_PARTY_NOTICES.md is missing generated inventory markers")
    end += len(INVENTORY_END)
    replacement = render_inventory(records)
    notices_path.write_text(text[:start] + replacement + text[end:], encoding="utf-8")


def run(*, write_notices: bool = False) -> int:
    policy = load_policy()
    python, python_errors = python_records(policy)
    javascript, javascript_errors = javascript_records(policy)
    errors = python_errors + javascript_errors
    records = sorted(set(python + javascript))
    unavailable_ecosystems = frozenset(
        ecosystem
        for ecosystem, ecosystem_errors in (
            ("python", python_errors),
            ("javascript", javascript_errors),
        )
        if ecosystem_errors
    )
    errors.extend(
        policy_errors(
            records,
            policy,
            unavailable_ecosystems=unavailable_ecosystems,
        )
    )
    errors.extend(required_file_errors(policy))
    errors.extend(dependency_configuration_errors())
    if write_notices and not errors:
        write_inventory(records)
    if not python_errors and not javascript_errors:
        errors.extend(inventory_errors(records))
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(
        f"License audit passed: {len(python)} Python and "
        f"{len(javascript)} JavaScript package/version records"
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check",
        action="store_true",
        help="audit policy, required texts, lockfiles, and the generated notice inventory",
    )
    mode.add_argument(
        "--write-notices",
        action="store_true",
        help="replace the generated dependency table in THIRD_PARTY_NOTICES.md",
    )
    args = parser.parse_args(argv)
    return run(write_notices=args.write_notices)


if __name__ == "__main__":
    raise SystemExit(main())
