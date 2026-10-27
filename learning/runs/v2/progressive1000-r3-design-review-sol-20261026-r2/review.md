# R3 source-only design review

**No blocking findings. F1–F7 are closed at design scope.** Exact R3 supports isolated implementation preparation; it does not authorize training or establish runtime qualification.

Scope: `R3/` means `learning/runs/v2/progressive1000-curriculum-replica-parent-20261026-r3/`; `E` is its `experiment.json`, `S` its `scheduler_reference.py`. `R5/` means `learning/runs/v2/confirmed324-private-bindings-repair-luna-20261026-r5/`.

## Closure

- **F1:** E:20–30,38–42 preserves KL0.03 and identical PPO settings. Equality is 983040 transitions/run and maximum7680 Adam steps; actual KL-limited steps are reported without top-ups. All inherited PPO fields match the pinned config.
- **F2:** E:53–59 and S:107–158 agree: validate all rows, sort decision/slot within ordered updates, consume all eligible completions, charge the entry generation once, then promote at most once. Nonoverlapping100-row windows, >=90 successes, >=200 targets, >=10 completed updates, surviving preminimum streaks and neutral partial windows are explicit. Frozen old-generation episodes cannot earn new mastery.
- **F3:** E:64–75 and S:18–56,97–105 agree on canonical UTF-8 JSON, six-field paired-vector hash, 100-assignment blocks, exact70/30 quotas, rotating remainders and SHA256/index sorting. Generation0 is all1000; partial blocks need not balance. Normal starts preserve reachable state/history; actual interval exposure is logged (E:60–61). No RNG imports occur in S.
- **F4:** E:85–98 fixes all six terminal60 endpoints plus accepted324, shared1024 fresh seeds and7168 episodes. Full normal starts disable cutoffs. Fatal-frame exclusion, milestone ties, exact256-row quarter means, death/cap/unknown/unavailable accounting and visible per-replica regressions are defined. Comparison remains descriptive, with no automatic replacement.
- **F5:** E:62 fixes60 global updates: at most six mastered stages; terminal7000 entry may have zero training. Entered, exposed, mastered and untested stages remain distinct.
- **F6:** E:100–109 fixes sequential execution, cost categories and fail-closed partial comparisons. Exact train/eval/aggregate caps and enforcement remain future parent calibration/registration work; proposed1800seconds and separate6GiB ceilings are not measurements.
- **F7:** E:111–116 requires complete consumed-seed ancestry, future exclusions, accepted324 episode indices, paired full-vector forks and durable authenticated restore/reseed. Exact cohort, vectors, collision controls and measured references remain future parent registration work.

## R3 and inherited R5 consistency

R3's exact diff changes only replica numbering and associated tests; its plan is byte-identical to R2. Replica1..3 satisfies R5's positive-integer checks (`attempt_claim.py:17–18`, `rng_reference.py:47–48`). Canonical vector encoding matches `rng_reference.py:27–32`; scheduler seed bounds match `transition.py:18–23`. R5 additionally rejects historical environment masters; the scheduler hash helper is not a freshness validator.

E:114–115 requires successor bindings rather than direct LR-study execution. Preserve R5's claim-before-restore, accepted fingerprints, externally pinned independent CPU/MPS digests and post-reseed model/Adam checks (`transition.py:91–159`). Adapt LR arm names/controller and expanded exclusions only in successor sources; never import the LR controller as curriculum behavior. R5 parent acceptance remains preparation-only, with real reference and driver qualification pending.

## Evidence and limits

Verified all39 upstream R2 manifest entries, all11 authoritative R5 entries, four R3 before/after file pins, exact diff reconstruction and budget arithmetic. Exact input hashes and review hash are in [receipt.json](receipt.json). R3 experiment SHA256 is `c20bd35188c4b4dd36687bc10c7998e6410c70d37300be92db9a42b3d01c43c0`; scheduler SHA256 is `a467b7219a9cd801fa3b403a6af112fc693ec3d14c9d311e8845632ef61d844b`.

Only stdlib reading, hashing, AST and JSON inspection occurred. Parent logs report20 R2 and21 R3 synthetic tests; this review ran none and imported no target code. No Torch/NumPy/native/RNG/MPS, checkpoint deserialization, model/environment construction, build, training or evaluation occurred. No subdelegation.

Native cutoff, collector/GAE, evaluator/source identity parity, seed ancestry and resource calibration remain necessary later. The early-practice hypothesis is unproven;90% and70/30 remain draft choices, with no fixed95% user threshold. Only this new review directory was written; protected sources, ledger, leases, markers and root README were untouched. Hash coverage is listed-input evidence, not an exhaustive concurrent-workspace audit.
