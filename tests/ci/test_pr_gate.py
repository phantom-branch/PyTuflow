import pytest

from ci.pr_gate import applicable, require_results


@pytest.mark.parametrize('mode', ['fast', 'full'])
@pytest.mark.parametrize('path', ['README.md', 'docs/usage.rst', 'tests/README.md'])
def test_documentation_does_not_require_expensive_jobs(mode, path):
    assert not applicable([path], mode)


@pytest.mark.parametrize('mode', ['fast', 'full'])
@pytest.mark.parametrize('path', ['pytuflow/x.py', 'tests/data/input.txt', 'ci/pr_gate.py',
                                  'hatch_build.py', 'requirements-dev.txt', 'MANIFEST.in'])
def test_code_build_and_fixture_changes_require_jobs(mode, path):
    assert applicable(['README.md', path], mode)


def test_gate_workflow_edits_require_their_substantive_jobs():
    assert applicable(['.github/workflows/original-library-quick.yml'], 'fast')
    assert applicable(['.github/workflows/original-library-regression.yml'], 'full')


@pytest.mark.parametrize('result', ['failure', 'cancelled', 'skipped', 'pending'])
def test_required_job_cannot_be_skipped_or_fail(result):
    with pytest.raises(ValueError):
        require_results(True, 'success', {'regression': result, 'wheel': 'success'})


def test_successful_code_and_explicit_documentation_outcomes():
    require_results(True, 'success', {'regression': 'success', 'wheel': 'success'})
    require_results(False, 'success', {'regression': 'skipped', 'wheel': 'skipped'})


def test_classifier_failure_and_empty_results_fail_closed():
    with pytest.raises(ValueError):
        require_results(False, 'failure', {'regression': 'skipped'})
    with pytest.raises(ValueError):
        require_results(True, 'success', {})
