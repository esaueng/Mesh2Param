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
    assert set(job) == {'uses', 'permissions'}
    assert job['permissions'] == {'contents': 'read', 'id-token': 'write'}
    assert caller['permissions'] == {'contents': 'read'}


def test_only_compatible_jobs_can_use_the_selected_fleet_target() -> None:
    jobs = yaml.safe_load((ROOT / '.github/workflows/ci-jobs.yml').read_text())['jobs']
    quality = jobs['quality']
    expression = quality['runs-on']
    assert "(matrix.task == 'frontend' || matrix.task == 'backend')" in expression
    assert quality['needs'] == ['authorize', 'route']
    assert quality['strategy']['matrix']['task'] == ['static', 'frontend', 'backend', 'browser']
    assert quality['timeout-minutes'] == 60
    assert jobs['rust']['runs-on'] == jobs['containers']['runs-on'] == 'ubuntu-24.04'
    for job in jobs.values():
        for step in job.get('steps', []):
            if step.get('uses', '').startswith('actions/checkout@'):
                assert step['with']['persist-credentials'] is False


def test_fleet_selection_is_opt_in_and_uses_the_shared_slot_label() -> None:
    jobs = yaml.safe_load((ROOT / '.github/workflows/ci-jobs.yml').read_text())['jobs']
    assert jobs['route']['if'] == "needs.authorize.outputs.trusted == 'true' && vars.CI_FLEET_ENABLED == 'true'"
    assert jobs['route']['with']['enabled'] is True
    assert jobs['route']['permissions'] == {'id-token': 'write'}
    expression = jobs['quality']['runs-on']
    for target in ['ci-server-jane', 'ci-server-john']:
        assert f'"labels":"{target}"' in expression
    assert 'ci-small' not in expression
    assert 'ci-server-jane-1' not in expression
    assert 'ci-server-jane-2' not in expression
    assert expression.endswith("|| '\"ubuntu-24.04\"') }}")
