"""Run the real project CLI with a disposable template cache for regression tests.

Only the cache location is changed. Production code, templates, CLI arguments,
working directory, stdout/stderr and exit semantics are preserved.
"""

import argparse
from pathlib import Path
import runpy
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    sys.path.insert(0, str(args.source_root.absolute()))
    from pytuflow.project.config import settings
    from pytuflow.project.template import manager

    manager.CACHE_ROOT = settings.CACHE_ROOT = args.cache_root.absolute()
    arguments = args.arguments[1:] if args.arguments[:1] == ["--"] else args.arguments
    sys.argv = ["pytuflow.project", *arguments]
    runpy.run_module("pytuflow.project", run_name="__main__")


if __name__ == "__main__":
    main()
