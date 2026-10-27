# Per-run signature memo: matched native comparison, 26 October 2026

Owner requested the initial benchmark despite failing CI, then a test repair and repeat.
No solver, merge, release, model edit or parallel benchmark was run. Raw paths,
input manifests, full identities and report projections remain local.

## Revisions and protocol

- A: correctness-fixed parser `079258eab25b1c2d7b0ee4c1c248ccff7f38f5dc`.
- Initial B: memo parser `5fb4185c0650248943a17ec7b83316ed79392152`.
- Post-fix B: `b6429edf7d28ebe7790f1c167b0b702101e24621`.
- Frozen consumer: `a710f24ffb1698e949937f56a0212b6ae599e54e`.
- Normal Windows CPython 3.14.6, unchanged host and retained 480-run plan.
- Both passes: fresh processes A/B/B/A; fragments ON everywhere; same consumer;
  file-only inspection, BC CSV header checks, four inventory workers.
- API plus CSV output timed; imports, source guards and metadata guards excluded.
  600-second deadline per timing pass; no retries, profiler or filesystem hooks.
- Immutable Git-archive snapshots supply imports. The runner verifies physical
  module locations, snapshot bytes and retained input size/mtime before/after
  each invocation. No new input-content hash or launcher extraction was performed.
- SMB/server caches and background load uncontrolled; no cache flush.
- Initial timing was deliberately performed before full provenance parity per
  owner instruction. The full parity gate passed before the second pass.

## Measurements

Positive change means slower. Two trials per condition per pass.

| Pass | A trials (s) | B trials (s) | A median (s) | B median (s) | B change |
| --- | --- | --- | ---: | ---: | ---: |
| initial | 20.447322, 18.777047 | 18.486391, 18.604132 | 19.612184 | 18.545261 | -5.440% |
| post_fix | 18.579800, 18.362565 | 18.619155, 18.499665 | 18.471182 | 18.559410 | +0.478% |

All eight invocations: 480 runs, 50 checked paths, 24 CSV headers, 480 column
selections, 5,256 fragment evaluations, 66,290 reuses, zero fallbacks and zero
issues. All complete consumer projections agree across both passes. Guards pass.
The JSON rows retain parse/context/inventory/total times. The remainder is
total minus those phases; do not describe these coarse consumer phases as a
separate parser-internal CPU/I/O attribution or add overlapping parser timers.

**Conclusion: no reproducible incremental memo speedup demonstrated.** Initial
median improvement is 5.44%, but the repeat is slightly slower. The runtime bytes
of B are identical across passes: the repair changes tests only. The observed
reversal and overlapping ranges do not satisfy improvement beyond plausible
measurement variation. Do not accept the memo on performance grounds from these
measurements; consider omitting it unless a narrowly scoped later experiment
demonstrates benefit. No runtime optimisation was removed in this task.

## Correctness and repair

The initial exact-head combined Windows CI failed on Python 3.12 and 3.14.
[Hosted evidence](https://github.com/phantom-branch/PyTuflow/actions/runs/40216608494)
reports 299 passed / 1 failed on Python 3.14. The regression tried to redefine
existing scenario/event slots, raising `ValueError: Context already has attribute s1`.
The repair removes the previous event slot/binding before loading its replacement,
retains the scenario, clears old event substitutions, and asserts memo invalidation
immediately after event reload rather than only after another variable update.

Full native current-head equality compares complete `BatchDependencyRun` tuples
from ordinary uncached, ordinary cached and fragments on the same parsed model:
480 ordered runs, original UUIDs, command ordinals, file/layer references, database
activations and CSV selectors/sources; zero errors. Raw complete records stay local.
This is stronger than consumer report parity. A separate cross-revision full parser
tuple gate was not run; cross-revision consumer projections agree. The full native
gate does not contain every negative/custom-hook case; focused synthetic tests do.

Local combined workflow set: 300 passed on Python 3.14 after the repair. Final
test-only typing/style follow-up: 25 fragment tests pass; Ruff lint and format
(120 columns), plus Git whitespace checks pass. Strict Pyright was restricted to
the modified test file: 24 diagnostics remain (untyped legacy surfaces/private
test access); this is not a clean strict-typing result. Hosted new-head CI and
review remain separate, unaccepted gates; no consumer repin was made.

## Audit and reproduction

- [Initial rows](initial.json), [post-fix rows](post_fix.json), [full parity](parity.json).
- [Runner audit copy](benchmark.py.txt), [dependency versions](environment.json).
- Runner differs from the executed file only by replacing its private workload
  directory literal with `BATCH_EXISTENCE_PRIVATE_WORKLOAD`.
- Recreate package snapshots from the exact Git SHAs under `sources/A`, `sources/B`
  and `sources/consumer`; set the private workload directory to the retained config,
  runs and input manifest. Generate source-heads/snapshot-hashes manifests as in
  the private campaign. Run `python benchmark.py` once for each fresh output root.
- Each JSON records the SHA-256 of its complete private source snapshot manifest.
  The manifest describes only public source files; raw measurement directories are
  not committed. Do not run the BAT or any engine to reproduce parser measurements.

Next action: review this inconclusive performance result and final-head CI/review.
No further native measurement queued. Owner: ChatGPT. Next review: 2026-11-02.
