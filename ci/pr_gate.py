"""Path-aware, always-reported gates for existing substantive PR jobs."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path


def applicable(paths: list[str], mode: str) -> bool:
    workflow = 'original-library-quick.yml' if mode == 'fast' else 'original-library-regression.yml'
    for path in paths:
        if path == f'.github/workflows/{workflow}':
            return True
        # Documentation changes do not require numerical/build jobs. Text
        # fixtures (.txt/.csv/etc.) are deliberately not treated as docs.
        if path.endswith(('.md', '.rst')):
            continue
        if path.startswith(('pytuflow/', 'tests/', 'ci/')) or path.endswith(('.py', '.pyi')):
            return True
        if path in {'pyproject.toml', 'MANIFEST.in', 'requirements-dev.txt'}:
            return True
    return False


def require_results(expected: bool, changes: str, results: dict[str, str]) -> None:
    if changes != 'success':
        raise ValueError('Path classification did not succeed')
    required = 'success' if expected else 'skipped'
    if not results or any(result != required for result in results.values()):
        raise ValueError(f'Expected substantive jobs {required}: {results}')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['classify', 'verify'])
    parser.add_argument('--mode', choices=['fast', 'full'])
    args = parser.parse_args()
    if args.command == 'classify':
        if not args.mode:
            parser.error('classify requires --mode')
        event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
        if 'pull_request' in event:
            pr = event['pull_request']
            # No API 300-file truncation; include both sides of renames/deletes.
            raw = subprocess.check_output([
                'git', 'diff', '--name-only', '--no-renames', '-z',
                f"{pr['base']['sha']}...{pr['head']['sha']}",
            ])
            paths = [p for p in raw.decode('utf-8').split('\0') if p]
            expected = applicable(paths, args.mode)
        else:
            expected = True  # Preserve explicit workflow_dispatch execution.
        with Path(os.environ['GITHUB_OUTPUT']).open('a', encoding='utf-8') as output:
            output.write(f"required={str(expected).lower()}\n")
        print(f'Substantive {args.mode} jobs required: {expected}')
    else:
        value = os.environ['REQUIRED']
        if value not in {'true', 'false'}:
            raise ValueError(f'Invalid scope result: {value!r}')
        require_results(value == 'true', os.environ['CHANGES_RESULT'], json.loads(os.environ['JOB_RESULTS']))
        print('Applicable jobs succeeded' if value == 'true' else 'Documentation/unrelated scope: substantive jobs not required')


if __name__ == '__main__':
    main()
