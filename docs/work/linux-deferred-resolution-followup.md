# Linux deferred-resolution parity — prerequisite for consolidated acceptance

**Active and blocking [#36](https://github.com/phantom-branch/PyTuflow/pull/36).**
The user has explicitly advanced the formerly deferred Linux investigation.
This work is no longer documentation-only. It must be accepted before the
consolidated upstream-readiness milestone is declared complete.

## Platform contract and provenance

The [2026.3 TUFLOW Classic/HPC manual](https://docs.tuflow.com/classic-hpc/manual/2026.3/11-RunningSimulations.html)
defines Linux `-cs0` (strict case sensitivity) as the default,
`-cs1` as case-insensitive **extensions only**, and `-cs2` as
case-insensitive **filenames and extensions but not directory components**.
The preflight must not claim success for a differently spelled POSIX file
under the default strict policy. Any future `-cs1/-cs2` mode must be explicit
and tested against its actual solver semantics; no solver is run by this PR.

PyTUFLOW retains its historical case-insensitive *discovery helper* for
compatibility. With two distinct POSIX files such as `Materials.csv` and
`materials.csv`, the exact requested filename now takes precedence over
fallback matching. A non-exact ambiguous lookup must fail closed. Lexical
path spelling, symlink paths and owner/row provenance must not be silently
canonicalised.

The downstream [ryan-tools PR #162](https://github.com/Chain-Frost/ryan-tools/pull/162)
fixes unconditional casefolding in bounded directory and wildcard checks.
That change is independent of ryan-tools performance PR #161. **#162 was
squash-merged with all four workflows passing** at
`993eb083dec15b1155d7ae61a28d65003357ff77`. Linux CI now pins this
accepted consumer commit rather than an unmerged development SHA.

## Native Linux strict archive classification (current evidence)

[Workflow 40214006051](https://github.com/phantom-branch/PyTuflow/actions/runs/40214006051)
examined all **161 TCFs and 174 run combinations** without changing the ZIP.
Only **8/174** were accepted because the original archive contains eight
known filename-case mismatches. All 183 eager-only references map exactly to
183 deferred-only references after *diagnostic* casefold comparison, with no
unmatched non-case variants; this is **not** a valid strict-mode parity pass.
The biggest mismatches are `Materials.csv` / `materials.csv` (137),
`2d_rf_EG03_007_R.shp` / `2d_RF_EG03_007_R.shp` (28), plus WLL and
`.SHP` extension differences. A corresponding 137 cached-material database
errors must be treated as invalid inputs, not silent successful resolution.
[Full eight-pair evidence](https://github.com/phantom-branch/PyTuflow/pull/4#issuecomment-6400696226).

The [merged downstream harness #164](https://github.com/Chain-Frost/ryan-tools/pull/164)
introduces an explicitly opt-in `--linux-case-overlay` mode that creates
bounded, logged case-alias symlinks **only in the temporary extracted model**,
including Shapefile sidecars. The immutable ZIP, hashes, member names and
original files remain unmodified. The separate case-corrected campaign uses
this valid-input fixture for full eager/deferred/batch acceptance; it does
**not** reclassify the raw strict Linux archive as passing.

## Historical diagnostic leads (not current acceptance)

- [Ubuntu run 39652484033](https://github.com/phantom-branch/PyTuflow/actions/runs/39652484033):
  161 TCFs / 174 runs; 21 TCFs accepted, two eager-only and 18
  deferred-only references. The eager Pandas 3 rainfall-index failure was
  fixed separately.
- [Ubuntu run 39654838025](https://github.com/phantom-branch/PyTuflow/actions/runs/39654838025):
  22/174 combinations accepted; 41 eager-only rainfall-index grids and two
  deferred-only curve/identifier references. Older downstream code lacked
  current deferred materialisation.
- On strict Linux `model/materials.csv` is not equivalent to archived
  `model/Materials.csv`. The former report was **not proof of 145
  distinct missing files**. When a public fixture itself requires
  `-cs1/-cs2`, distinguish genuinely incompatible fixture paths from
  parser or preflight implementation defects; do not silently rename or
  modify the immutable archived inputs.

## Implemented in this PR

- Prefer exact POSIX directory-entry matches when names differ only by case,
  retaining ambiguous non-exact lookups as errors.
- Linux-only regressions for exact/non-exact case matches, distinct siblings,
  symlink spelling and eager/deferred nested owner attribution.
- [Ubuntu Python 3.14 CI](../../.github/workflows/linux-deferred-resolution-parity.yml)
  installs the exact parser and consumer revisions, verifies the public archive,
  runs focused source tests and attempts complete 161-TCF / 174-run
  eager/deferred/batch parity, with machine-readable diagnostics.

## Acceptance — must complete before #36

- [x] ryan-tools #162 passed **Linux and Windows** tests, lint and consumer CI;
  squash-merged at `993eb083dec15b1155d7ae61a28d65003357ff77`.
  Remaining #161 performance work remains independently owned.
- [ ] PyTUFLOW Linux-focused regressions pass under native Python 3.14.
- [x] [ryan-tools #163](https://github.com/Chain-Frost/ryan-tools/pull/163) fixed casefold-conflated POSIX physical identities; merged at `aa191bb8987ae293e1aff80c9bc67d62713fac11` with six passing workflows. The unmerged, optional benchmark #158 retains a separately owned *owner-command* casefold follow-up before its later merge.
- [x] Raw public 161-TCF / 174-run **strict Linux** replay is classified: 8/174 valid, 183 exact pairs due eight case-only filenames, report retained. This invalid raw fixture is not marked passing.
- [x] ryan-tools #164 temporary case-correction harness merged and full cross-platform CI passed at `78e1637c7500a307449ce2b38a6fa7c60bf7043a`.
- [ ] Full **case-corrected temporary model copy** 161-TCF / 174-run Linux replay is classified case by case;
  no unclassified missing/extra identities, source exceptions or skipped scans.
- [ ] Resolve genuine implementation defects in this PR or linked narrow fixes,
  without weakening strict Linux filenames, modifying fixture hashes,
  introducing per-run I/O, or confusing identifiers with file paths.
- [ ] Establish and document the Linux support policy for the default strict
  solver mode and any optionally supported `-cs1/-cs2` compatibility mode.
  Case-mismatched inputs that cannot run in the chosen mode are not accepted.
- [ ] Preserve Windows full example parity, original-library/regression CI,
  and existing native QGIS behaviour. Re-run after the final production change.
- [ ] Freeze exact parser/consumer/harness SHAs with passing CI links and a
  sanitised acceptance matrix. Update [#36](https://github.com/phantom-branch/PyTuflow/pull/36)
  only after these gates are met.

No private SMB files are uploaded and no TUFLOW solver is executed by this PR.
