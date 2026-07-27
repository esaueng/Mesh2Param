from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import replace
from pathlib import Path
from types import ModuleType

import pytest


def _checker() -> ModuleType:
    path = Path(__file__).resolve().parents[1] / "scripts" / "check_licenses.py"
    spec = importlib.util.spec_from_file_location("check_licenses", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_license_normalization_uses_expression_alias_and_classifier() -> None:
    checker = _checker()
    assert checker.normalize_license("MPL-2.0", None, []) == "MPL-2.0"
    assert checker.normalize_license(None, "MIT license", []) == "MIT"
    assert checker.normalize_license(
        None, None, ["License :: OSI Approved :: Apache Software License"]
    ) == "Apache-2.0"


def test_policy_rejects_gpl_but_allows_reviewed_copyleft_override() -> None:
    checker = _checker()
    policy = checker.load_policy()
    rejected = checker.LicenseRecord("python", "unexpected", "1.0", "GPL-3.0-only")
    unreviewed_lgpl = checker.LicenseRecord(
        "python", "unexpected-lgpl", "1.0", "LGPL-2.1-only"
    )
    reviewed = checker.LicenseRecord("python", "casadi", "3.7.2", "LGPL-3.0-or-later")
    errors = checker.policy_errors([rejected, unreviewed_lgpl, reviewed], policy)
    assert any("forbidden license" in error and "unexpected" in error for error in errors)
    assert any("forbidden license" in error and "unexpected-lgpl" in error for error in errors)
    assert not any("casadi" in error for error in errors)


def test_inventory_rendering_is_deterministic_and_escapes_pipes() -> None:
    checker = _checker()
    records = [
        checker.LicenseRecord("python", "zeta", "1", "MIT OR Apache-2.0"),
        checker.LicenseRecord("javascript", "alpha", "2", "BSD-3-Clause"),
        checker.LicenseRecord("javascript", "alpha", "2", "BSD-3-Clause"),
    ]
    first = checker.render_inventory(records)
    second = checker.render_inventory(reversed(records))
    assert first == second
    assert first.count("| javascript | alpha | 2 | BSD-3-Clause |") == 1


def test_python_marker_only_dependencies_are_platform_constrained(tmp_path: Path) -> None:
    checker = _checker()
    (tmp_path / "uv.lock").write_text(
        """
version = 1

[[package]]
name = "parent"
version = "1"
dependencies = [
  { name = "conditional", marker = "sys_platform == 'linux'" },
  { name = "interpreter", marker = "platform_python_implementation != 'PyPy'" },
  { name = "shared" },
]

[[package]]
name = "other"
version = "1"
dependencies = [
  { name = "shared", marker = "sys_platform == 'win32'" },
]
""",
        encoding="utf-8",
    )

    assert checker._python_platform_constrained_packages(root=tmp_path) == frozenset(
        {"conditional"}
    )


def test_dependency_configuration_rejects_gpl_package_in_nested_lock(
    tmp_path: Path,
) -> None:
    checker = _checker()
    (tmp_path / "packages" / "contracts").mkdir(parents=True)
    for relative in ("pyproject.toml", "packages/contracts/pyproject.toml"):
        (tmp_path / relative).write_text(
            'dependencies = ["jsonschema[format-nongpl]"]\n', encoding="utf-8"
        )
    (tmp_path / "uv.lock").write_text(
        'name = "rfc3987-syntax"\n', encoding="utf-8"
    )
    (tmp_path / "packages" / "contracts" / "uv.lock").write_text(
        'name = "rfc3987"\n', encoding="utf-8"
    )

    assert checker.dependency_configuration_errors(root=tmp_path) == [
        "packages/contracts/uv.lock still contains the GPL-3.0+ rfc3987 distribution",
        "packages/contracts/uv.lock is missing the non-GPL rfc3987-syntax replacement",
    ]


def _write_javascript_package(
    virtual_store: Path,
    virtual_directory: str,
    name: str,
    version: str,
    *,
    license_name: str | None = "MIT",
    constraints: dict[str, list[str]] | None = None,
) -> Path:
    package_directory = (
        virtual_store
        / virtual_directory
        / "node_modules"
        / Path(*name.split("/"))
    )
    package_directory.mkdir(parents=True)
    document: dict[str, object] = {"name": name, "version": version}
    if license_name is not None:
        document["license"] = license_name
    if constraints is not None:
        document.update(constraints)
    (package_directory / "package.json").write_text(
        json.dumps(document), encoding="utf-8"
    )
    return package_directory


def test_javascript_inventory_reads_all_installed_package_manifests(
    tmp_path: Path,
) -> None:
    checker = _checker()
    virtual_store = tmp_path / "node_modules" / ".pnpm"
    react = _write_javascript_package(
        virtual_store, "react@19.2.7", "react", "19.2.7"
    )
    parent = _write_javascript_package(
        virtual_store, "parent@1.0.0", "parent", "1.0.0", license_name="ISC"
    )
    _write_javascript_package(
        virtual_store, "@scope+tool@2.0.0", "@scope/tool", "2.0.0"
    )
    fallback = _write_javascript_package(
        virtual_store,
        "license-fallback@3.0.0",
        "license-fallback",
        "3.0.0",
        license_name=None,
    )
    (fallback / "LICENSE").write_text(
        "MIT License\n\nPermission is hereby granted, free of charge, to any person",
        encoding="utf-8",
    )
    duplicate = _write_javascript_package(
        virtual_store,
        "react@19.2.7_parent@1.0.0",
        "react",
        "19.2.7",
    )
    (parent.parent / "react").symlink_to(react, target_is_directory=True)

    records, errors = checker.javascript_records(checker.load_policy(), root=tmp_path)

    assert errors == []
    assert records == [
        checker.LicenseRecord("javascript", "@scope/tool", "2.0.0", "MIT"),
        checker.LicenseRecord("javascript", "license-fallback", "3.0.0", "MIT"),
        checker.LicenseRecord("javascript", "parent", "1.0.0", "ISC"),
        checker.LicenseRecord("javascript", "react", "19.2.7", "MIT"),
    ]
    assert duplicate.is_dir()


def test_platform_constrained_javascript_packages_are_audited_not_rendered(
    tmp_path: Path,
) -> None:
    checker = _checker()
    virtual_store = tmp_path / "node_modules" / ".pnpm"
    _write_javascript_package(
        virtual_store,
        "react@19.2.7",
        "react",
        "19.2.7",
    )
    _write_javascript_package(
        virtual_store,
        "@esbuild+darwin-arm64@0.28.1",
        "@esbuild/darwin-arm64",
        "0.28.1",
        constraints={"os": ["darwin"], "cpu": ["arm64"]},
    )
    _write_javascript_package(
        virtual_store,
        "@esbuild+linux-x64@0.28.1",
        "@esbuild/linux-x64",
        "0.28.1",
        license_name="GPL-3.0-only",
        constraints={"os": ["linux"], "cpu": ["x64"], "libc": ["glibc"]},
    )

    records, errors = checker.javascript_records(checker.load_policy(), root=tmp_path)

    assert errors == []
    assert len(records) == 3
    by_name = {record.name: record for record in records}
    assert not by_name["react"].platform_constrained
    assert by_name["@esbuild/darwin-arm64"].platform_constrained
    assert by_name["@esbuild/linux-x64"].platform_constrained
    neutral_inventory = checker.render_inventory([by_name["react"]])
    assert checker.render_inventory(
        [by_name["react"], by_name["@esbuild/darwin-arm64"]]
    ) == checker.render_inventory(
        [by_name["react"], by_name["@esbuild/linux-x64"]]
    ) == neutral_inventory
    assert checker.render_inventory(records) == neutral_inventory

    policy = replace(checker.load_policy(), required_notice_packages=frozenset())
    policy_failures = checker.policy_errors(records, policy)
    assert any(
        "forbidden license" in error and "@esbuild/linux-x64" in error
        for error in policy_failures
    )


def test_javascript_inventory_reports_missing_install(tmp_path: Path) -> None:
    checker = _checker()
    records, errors = checker.javascript_records(checker.load_policy(), root=tmp_path)

    assert records == []
    assert errors == [
        "cannot inspect installed JavaScript packages: "
        f"pnpm virtual store is missing at {tmp_path / 'node_modules' / '.pnpm'}"
    ]


def test_failed_inventory_does_not_report_missing_dependencies_or_stale_notices(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    checker = _checker()
    policy_records = [
        checker.LicenseRecord("python", "cadquery", "2", "Apache-2.0"),
        checker.LicenseRecord(
            "python",
            "cadquery-ocp",
            "7",
            "Apache-2.0 AND LGPL-2.1-only WITH OCCT-exception-1.0",
        ),
        checker.LicenseRecord("python", "casadi", "3", "LGPL-3.0-or-later"),
    ]
    monkeypatch.setattr(checker, "python_records", lambda policy: (policy_records, []))
    monkeypatch.setattr(
        checker,
        "javascript_records",
        lambda policy: ([], ["pnpm license inspection failed after 3 attempts"]),
    )
    monkeypatch.setattr(checker, "required_file_errors", lambda policy: [])
    monkeypatch.setattr(checker, "dependency_configuration_errors", lambda: [])
    monkeypatch.setattr(
        checker,
        "inventory_errors",
        lambda records: (_ for _ in ()).throw(AssertionError("incomplete inventory checked")),
    )

    assert checker.run() == 1
    output = capsys.readouterr().err
    assert output.count("ERROR:") == 1
    assert "pnpm license inspection failed" in output
    assert "required dependency is not installed" not in output
    assert "inventory is stale" not in output
