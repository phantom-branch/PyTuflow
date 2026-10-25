# W9 — Upstream Python compatibility and public typing baseline

## Purpose and comparison boundary

Audit **TUFLOW-Support/PyTuflow `master`**, not the modified fork, as the baseline for backward compatibility. Preserve source/public API behaviour; avoid a wholesale typing conversion or changing numerical, QGIS or deferred execution code.

- Upstream reference: `TUFLOW-Support/PyTuflow@cf908cc922ca8448ed6002834877b0b377329eae`.
- Initial fork base: `phantom-branch/PyTuflow@41c0c2a274c932f1ba236f796814f43e38155231` (PR #22 merged).
- Upstream `pyproject.toml`: `requires-python = ">= 3.9"`, classifiers through 3.12.
- Fork after #22: `requires-python = ">=3.12,<3.15"`, tested 3.12/3.13/3.14.
- The upstream advertisement is **not evidence** of actual Python 3.9 compatibility:
  1. `pytuflow/_tmf/tmf_types.py` evaluates `PathLike = str | Path` (and related unions), unsupported as runtime unions on 3.9.
  2. `pytuflow/_outputs/map_output.py` evaluates additional `X | Y` type aliases.
  3. The mandatory `pyvista>=0.48.2` dependency cannot be satisfied on 3.9: PyVista 0.48.2 declares Python >=3.10 (see <https://pypi.org/project/pyvista/0.48.2/>).
- Retain upstream's 3.9 *historical compatibility target* for evaluation. Do not re-advertise Python 3.9 or loosen the package's mandatory dependencies merely to match an incorrect metadata claim.

## Required minimum for the active QGIS deployments

- **Python 3.12 is mandatory** for the current QGIS 3.44 LTR and QGIS 4 Windows runtimes (verify the precise `sys.version` in each installed QGIS Console). Earlier QGIS 3 LTRs may use Python 3.9 or a different minor version.
- Python 3.14 remains a supported consumer target; Python 3.13 is within existing #22 support.
- Python 3.10/3.11 and Python 3.9 must be investigated separately against original upstream, default-install metadata and unchanged public operations.
- Python 3.12 supports PEP 585 built-in generics, 3.10-style union syntax, and PEP 695 aliases/generics. PEP 695 syntax is **not** valid in 3.10/3.11. Do not impose Python 3.14-only annotations on runtime code.
- If Python 3.9 restoration is technically feasible, do it in an independent, expressly reviewed compatibility PR with real 3.9 wheel/dependency acceptance; avoid silently weakening the original default install to achieve a misleading green test.

## Implemented in this diagnostic PR

- `ci/typing_baseline.py`: read-only local Pyright diagnostic collection with `--pythonversion` targets, optional `--verifytypes`, raw diagnostic JSON saved outside the repo and a path-free aggregate `summary.json`.
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
& py -3.14 "$Fork\ci\typing_baseline.py" --source-root $Upstream --output-dir "$Reports\upstream" --targets 3.9 3.10 3.11 3.12 3.13 3.14
& py -3.14 "$Fork\ci\typing_baseline.py" --source-root $Fork --output-dir "$Reports\fork" --targets 3.9 3.10 3.11 3.12 3.13 3.14 --verifytypes
```

The `py -3.14` interpreter only *runs the diagnostic script*; the `--pythonversion` switches ask Pyright to analyse source for other versions. **This is not evidence that Python 3.9 can install or import the wheel.** Running `--verifytypes` against a checkout assesses source-visible public interface completeness; a separate installed-wheel check is required before claiming a distributable typing contract.

If a locally installed `pyright` executable or Python launcher is unavailable, report that fact. Do not install anything without authorisation. Run `pytest tests/ci/test_typing_baseline.py` under the working local Python. Preserve full JSON locally. Only report sanitized aggregate counts and upstream/fork SHA comparisons to GitHub.

## Follow-up implementation acceptance

1. **Upstream-vs-fork parity**: compare the same public API entry points; reject accidental signature drift.
2. **Version support**: separately measure 3.9–3.14 *syntax analysis*, dependency resolution, wheel installation and runtime import/operation results. Do not collapse those distinct checks into one "supported" label. Run native QGIS 3 LTR / QGIS 4 provider checks under their bundled Python 3.12.
3. **Typed public exports first**: improve inline annotations for straightforward stable methods; add modern `.pyi` stubs only for difficult legacy interfaces and cover all exported symbols in any stubbed module. Ensure stubs do not mask source members.
4. **Installed consumer**: preserve #22's installed-wheel mypy strict consumer, and add a narrow Pyright `--verifytypes` improvement gate only after a measured baseline is recorded.
5. **Backwards-compatible typing**: `list[T]`/`dict[K,V]` work since 3.9; `A | B` needs 3.10 at runtime unless annotations are postponed. Explicit evaluated type aliases remain evaluated on 3.9 even if annotations use `from __future__ import annotations`.
6. **Feature drift**: do not alter solver outputs, numerical methods, interpolation, model saving, dependency semantics, or public import identities as a side effect of typing clean-up.
7. **Scope split**: if repair of upstream Python 3.9 genuinely needs dependency redesign, propose it separately with evidence and avoid silently changing the currently accepted #22 support range.

## Safety and limitations

- Local raw `pyright-*.json` and `verifytypes-*.json` reports can contain full personal/network paths, symbol names and excerpts: **do not commit or paste raw reports**.
- The aggregate script reports diagnostics; it does not itself install wheels, run QGIS, prove runtime compatibility or validate original numerical functionality.
- Compare pinned upstream/fork references and annotate later upstream or fork changes separately instead of treating modified fork `master` as upstream.
