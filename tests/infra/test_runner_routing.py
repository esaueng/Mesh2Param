"""Guard the self-hosted scheduling policy without executing contributor code."""

import re
from pathlib import Path

import yaml  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[2]


def test_ci_caller_is_immutable_and_passes_no_inputs_or_secrets() -> None:
    caller = yaml.safe_load((ROOT / '.github/workflows/ci.yml').read_text())
    job = caller['jobs']['checks']
    assert re.fullmatch(
        r'esaueng/Mesh2Param/\.github/workflows/ci-jobs\.yml@[0-9a-f]{40}', job['uses']
    )
    assert set(job) == {'uses'}
    assert caller['permissions'] == {'contents': 'read'}


def test_only_compatible_jobs_can_use_self_hosted_without_hosted_dependencies() -> None:
    jobs = yaml.safe_load((ROOT / '.github/workflows/ci-jobs.yml').read_text())['jobs']
    quality = jobs['quality']
    expression = quality['runs-on']
    assert "(matrix.task == 'frontend' || matrix.task == 'backend')" in expression
    assert 'needs' not in quality
    assert quality['strategy']['matrix']['task'] == ['static', 'frontend', 'backend', 'browser']
    assert quality['timeout-minutes'] == 60
    assert jobs['rust']['runs-on'] == jobs['containers']['runs-on'] == 'ubuntu-24.04'
    for job in jobs.values():
        for step in job['steps']:
            if step.get('uses', '').startswith('actions/checkout@'):
                assert step['with']['persist-credentials'] is False


def test_trust_predicates_cannot_be_removed_from_scheduling_expression() -> None:
    jobs = yaml.safe_load((ROOT / '.github/workflows/ci-jobs.yml').read_text())['jobs']
    expression = jobs['quality']['runs-on']
    for predicate in (
        "vars.CI_RUNNER_MODE == 'self-hosted'",
        "github.repository == 'esaueng/Mesh2Param'",
        "vars.CI_TRUSTED_ACTOR != ''",
        'github.actor == vars.CI_TRUSTED_ACTOR',
        'github.triggering_actor == vars.CI_TRUSTED_ACTOR',
        "github.event_name == 'push' && github.ref == 'refs/heads/main'",
        "github.event_name == 'pull_request'",
        'github.event.pull_request.head.repo.full_name == github.repository',
        'github.event.pull_request.user.login == vars.CI_TRUSTED_ACTOR',
        "startsWith(github.ref, 'refs/pull/')",
        "endsWith(github.ref, '/merge')",
    ):
        assert predicate in expression
    assert expression.endswith("|| '[\"ubuntu-24.04\"]') }}")
    assert 'pull_request_target' not in expression
