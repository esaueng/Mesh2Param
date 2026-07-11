"""Audit installed Python and pnpm dependency licenses against repository policy."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import re
import subprocess
import sys
import time
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
PNPM_LICENSE_ATTEMPTS = 6
PNPM_LICENSE_RETRY_DELAYS = (1.0, 2.0, 4.0, 8.0, 15.0)


@dataclass(frozen=True, order=True)
class LicenseRecord:
    ecosystem: str
    name: str
    version: str
    license: str

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


def python_records(policy: LicensePolicy) -> tuple[list[LicenseRecord], list[str]]:
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
        records.add(LicenseRecord("python", name, distribution.version, license_name))
    return sorted(records), errors


def javascript_records(
    policy: LicensePolicy, *, root: Path = ROOT
) -> tuple[list[LicenseRecord], list[str]]:
    failures: list[str] = []
    process: subprocess.CompletedProcess[str] | None = None
    for attempt in range(PNPM_LICENSE_ATTEMPTS):
        try:
            process = subprocess.run(
                ["pnpm", "licenses", "list", "--json"],
                cwd=root,
                check=False,
                capture_output=True,
                text=True,
                timeout=120,
            )
        except FileNotFoundError as exc:
            return [], [f"cannot inspect pnpm licenses: {exc}"]
        except subprocess.TimeoutExpired:
            failures.append("timed out after 120 seconds")
        else:
            if process.returncode == 0:
                break
            status = (
                f"signal {-process.returncode}"
                if process.returncode < 0
                else f"exit code {process.returncode}"
            )
            details = process.stderr.strip() or process.stdout.strip()
            failures.append(f"{status}: {details}" if details else status)
        if attempt < len(PNPM_LICENSE_RETRY_DELAYS):
            time.sleep(PNPM_LICENSE_RETRY_DELAYS[attempt])
    else:
        return [], [
            "pnpm license inspection failed after "
            f"{PNPM_LICENSE_ATTEMPTS} attempts ({'; '.join(failures)})"
        ]

    assert process is not None
    try:
        raw = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        return [], [f"pnpm returned invalid license JSON: {exc}"]
    if not isinstance(raw, dict):
        return [], ["pnpm license output must be an object"]

    records: set[LicenseRecord] = set()
    errors: list[str] = []
    for license_name, packages in raw.items():
        if not isinstance(license_name, str) or not isinstance(packages, list):
            errors.append("pnpm license output contains an invalid group")
            continue
        for package in packages:
            if not isinstance(package, dict):
                errors.append(f"pnpm {license_name} group contains an invalid package")
                continue
            name = package.get("name")
            versions = package.get("versions")
            if not isinstance(name, str) or not isinstance(versions, list):
                errors.append(f"pnpm {license_name} group contains incomplete metadata")
                continue
            package_key = f"javascript:{name.casefold()}"
            if package_key in policy.ignored_packages:
                continue
            override = policy.overrides.get(package_key)
            resolved = override.license if override is not None else normalize_license(
                license_name, license_name, []
            )
            if resolved is None:
                errors.append(f"unresolved JavaScript license: {name} ({license_name})")
                continue
            for version in versions:
                if isinstance(version, str):
                    records.add(LicenseRecord("javascript", name, version, resolved))
                else:
                    errors.append(f"pnpm package {name} has a non-string version")
    return sorted(records), errors


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
    for record in sorted(set(records)):
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
