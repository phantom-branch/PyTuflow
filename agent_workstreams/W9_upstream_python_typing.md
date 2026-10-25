# W9 — Upstream Python compatibility and public typing baseline

## Purpose and comparison boundary

Audit **TUFLOW-Support/PyTuflow `master`**, not the modified fork, as the baseline for backward compatibility. Preserve source/public API behaviour; avoid a wholesale typing conversion or changing numerical, QGIS or deferred execution code.

- Upstream reference: `TUFLOW-Support/PyTuflow@cf908cc922ca8448ed6002834877b0b377329eae`.
- Initial fork base: `phantom-branch/PyTuflow@41c0c2a274c932f1ba236f796814f43e38155231` (PR #22 merged).
- Upstream `pyproject.toml`: `requires-python = ">= 3.9"`, classifiers through 3.12.
- Fork after #22: `requires-python = ">=3.12,<3.15"`, tested 3.12/3.13/3.14.
- The upstream advertisement is **not evidence** of actual Python 3.9 compatibility (retained below only as historical source evidence):
  1. `pytuflow/_tmf/tmf_types.py` evaluates `PathLike = str | Path` (and related unions), unsupported as runtime unions on 3.9.
  2. `pytuflow/_outputs/map_output.py` evaluates additional `X | Y` type aliases.
  3. The mandatory `pyvista>=0.48.2` dependency cannot be satisfied on 3.9: PyVista 0.48.2 declares Python >=3.10 (see <https://pypi.org/project/pyvista/0.48.2/>).
- **Decision (25 October 2026):** Python 3.9 is out of scope as a support/typing target. Treat the upstream >=3.9 metadata as an inherited inconsistency, not a contract to restore. Use Python **3.10 as the minimum syntax/typing target**, while retaining the fork's currently verified >=3.12,<3.15 package runtime metadata pending actual Python 3.10/3.11 installation and runtime acceptance.

## Required minimum for the active QGIS deployments

- **Python 3.12 is mandatory** for the current QGIS 3.44 LTR and QGIS 4 Windows runtimes (verify the precise `sys.version` in each installed QGIS Console). Earlier QGIS 3 LTRs may use Python 3.9 or a different minor version.
- Python 3.14 remains a supported consumer target; Python 3.13 is within existing #22 support.
- Python 3.10/3.11 may be evaluated as potential *runtime* support through full dependency, wheel, import, and functional tests. Python 3.9 is not required for the typing audit or future support.
- Python 3.12 supports PEP 585 built-in generics, 3.10-style union syntax, and PEP 695 aliases/generics. PEP 695 syntax is **not** valid in 3.10/3.11. Do not impose Python 3.14-only annotations on runtime code.
- **Typing policy:** use 3.10-compatible syntax in implementation and .pyi files even when analysis runs under Python 3.12–3.14. Built-in generics (`list[T]`, `dict[K,V]`) and `A | B` unions are permitted. Do **not** introduce 3.12-only `type Alias = ...` / PEP 695 parameter syntax, Python 3.14-specific annotation facilities, or metadata claims that lack runtime evidence.

## Implemented in this diagnostic PR

- `ci/typing_baseline.py`: read-only local Pyright diagnostic collection for Python 3.10–3.14 `--pythonversion` targets, optional `--verifytypes`, raw diagnostic JSON saved outside the repo and a path-free aggregate `summary.json`.
- `tests/ci/test_typing_baseline.py`: report parsing/sanitisation, fail-closed tool errors and prohibition on writing reports under the checkout.
- No source interface stubs (`.pyi`) or public annotations added yet, because the audit should identify *which* external symbols need them before a maintainer commits to duplicate signatures.
- No `pyproject.toml`, dependencies, `py.typed` or public exports changed.

## Local validation handoff (Windows, no virtual environments)

Use an existing separate upstream checkout and a separate updated fork checkout. Do not reset dirty branches, create an isolated worktree, install packages, alter QGIS, run private simulations, or commit local paths.

In PowerShell, replace the following locations with the agent's **actual existing** network-drive checkout/report directories (not C:).

```powershell
$Fork = 'F:\Repos\PyTuflow-fork'
$Upstream = 'F:\Repos\PyTuflow-upstream'
$Reports = 'F:\Temp\PyTuflowTyping_20261025'
Get-Command pyright
pyright --version
& py -3.14 "$Fork\ci\typing_baseline.py" --source-root $Upstream --output-dir "$Reports\upstream" --targets 3.10 3.11 3.12 3.13 3.14
& py -3.14 "$Fork\ci\typing_baseline.py" --source-root $Fork --output-dir "$Reports\fork" --targets 3.10 3.11 3.12 3.13 3.14 --verifytypes
```

The `py -3.14` interpreter only *runs the diagnostic script*; the `--pythonversion` switches ask Pyright to analyse source for other versions. **This is not evidence that Python 3.10 can install or import the wheel.** Running `--verifytypes` against a checkout assesses source-visible public interface completeness; a separate installed-wheel check is required before claiming a distributable typing contract.

If a locally installed `pyright` executable or Python launcher is unavailable, report that fact. Do not install anything without authorisation. Run `pytest tests/ci/test_typing_baseline.py` under the working local Python. Preserve full JSON locally. Only report sanitized aggregate counts and upstream/fork SHA comparisons to GitHub.

## Follow-up implementation acceptance

1. **Upstream-vs-fork parity**: compare the same public API entry points; reject accidental signature drift.
2. **Version support**: measure Python 3.10–3.14 *static syntax/type analysis*. Separately evaluate Python 3.10/3.11 dependency resolution, wheel installation and real import/operation behaviour **before** lowering fork runtime metadata from >=3.12. Do not conflate static analysis and runtime acceptance. Preserve native QGIS 3 LTR / QGIS 4 providers under bundled Python 3.12.
3. **Typed public exports first**: improve inline annotations for straightforward stable methods; add modern `.pyi` stubs only for difficult legacy interfaces and cover all exported symbols in any stubbed module. Ensure stubs do not mask source members.
4. **Installed consumer**: preserve #22's installed-wheel mypy strict consumer, and add a narrow Pyright `--verifytypes` improvement gate only after a measured baseline is recorded.
5. **Typing syntax floor**: Python 3.10: built-in generics and `A | B` are permitted; Python 3.12 `type Alias = ...` and generic-parameter syntax are prohibited for common source/stubs. Prefer `typing.TypeAlias` for explicit aliases and `typing.TypeVar` for generics where necessary. Do not add Python 3.14-only typing syntax.
6. **Feature drift**: do not alter solver outputs, numerical methods, interpolation, model saving, dependency semantics, or public import identities as a side effect of typing clean-up.
7. **Scope split**: abandon Python 3.9 compatibility restoration, document its upstream metadata discrepancy, and evaluate 3.10/3.11 **only if** actual runtime support is desired. Preserve the currently accepted #22 >=3.12,<3.15 runtime range until independently validated otherwise.

## Safety and limitations

- Local raw `pyright-*.json` and `verifytypes-*.json` reports can contain full personal/network paths, symbol names and excerpts: **do not commit or paste raw reports**.
- The aggregate script reports diagnostics; it does not itself install wheels, run QGIS, prove runtime compatibility or validate original numerical functionality.
- Compare pinned upstream/fork references and annotate later upstream or fork changes separately instead of treating modified fork `master` as upstream.
