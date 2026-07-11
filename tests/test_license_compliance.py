from __future__ import annotations

import importlib.util
import subprocess
import sys
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


def test_javascript_inventory_retries_a_transient_pnpm_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checker = _checker()
    attempts = iter(
        [
            subprocess.CompletedProcess([], 143, "", ""),
            subprocess.CompletedProcess(
                [],
                0,
                '{"MIT":[{"name":"react","versions":["19.2.7"]}]}',
                "",
            ),
        ]
    )
    sleeps: list[float] = []
    monkeypatch.setattr(checker.subprocess, "run", lambda *args, **kwargs: next(attempts))
    monkeypatch.setattr(checker.time, "sleep", sleeps.append)

    records, errors = checker.javascript_records(checker.load_policy())

    assert errors == []
    assert records == [checker.LicenseRecord("javascript", "react", "19.2.7", "MIT")]
    assert sleeps == [0.5]


def test_javascript_inventory_stops_after_bounded_pnpm_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checker = _checker()
    attempts = 0

    def failed_process(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal attempts
        attempts += 1
        return subprocess.CompletedProcess([], -15, "", "")

    sleeps: list[float] = []
    monkeypatch.setattr(checker.subprocess, "run", failed_process)
    monkeypatch.setattr(checker.time, "sleep", sleeps.append)

    records, errors = checker.javascript_records(checker.load_policy())

    assert records == []
    assert errors == [
        "pnpm license inspection failed after 3 attempts "
        "(signal 15; signal 15; signal 15)"
    ]
    assert attempts == 3
    assert sleeps == [0.5, 1.0]


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
