# D4 terminal60 full-run evaluation (seed-priority study)

Preparation only. No launch authority. Nothing here loaded a model or checkpoint, constructed a native environment, opened D4 outcomes or touched D5.

Study `fullgame-seed-priority-luna-20261027-r1`: six fixed terminal60 endpoints (`replica-{1,2,3}-{uniform,opening_priority}`) plus accepted parent324, each evaluated once on the same 1,024 seeds `0xD4000000..0xD40003FF`. D5 `0xD5000000..0xD50007FF` stays unopened (and inside the exclusion union). D4 ranking is development evidence, not D5 confirmation.

Reused unchanged from the proven progressive1000 evaluator: clean common evaluator source/runtime (`progressive1000-opening-maintenance-runtime-parent-20261027-r1`), copied supervisor (`observe.py`, `execute_once.py` byte-identical), launcher shape, lifecycle/audit flow, dependency binding, native evaluation loop. New: study/cohort/lineage binding, six-producer audit chain, six-milestone priority-minus-uniform statistics, constructor/step budgets, unsorted-union normalization.

## Fixed contract
- Normal full starts, difficulty 2, patterns/powerups on, cap 18000, action repeat 4, sampled categorical actions, no cutoff, unchanged reward/transformer. Inference on MPS; native simulation on CPU.
- Sampling RNG: `evaluation_rng_seed` 2026102802; random/numpy/torch/mps are reseeded before each policy (same stream start, not per-seed draws). Bootstrap seed 2026102801, 2000 draws, 95%, paired over evaluation seeds.
- Limits: RSS = MPS = 6 GiB; raw frames 7168x(18000+13); constructors 7168; native steps 7168x18000; resets 0; retries 0. Wall = ceil(3 x 684.92 s / 15,487,746 frames x raw ceiling + 10) = 17,141 s from the proven evaluator's terminal cost; cleanup 10 s. Worker guard, observer watchdog and terminal journal audit each enforce independently.
- Report: Worst=min, Q1=bottom-256 mean, Mean, Q4=top-256 mean, Best=max; milestones 1000/2000/4000/8000/12000/18000; cause of death. Primary: priority minus uniform per replica; three-pair descriptive summary; parent comparisons descriptive. No selection, best-of-N or promotion.
- Provenance: disjointness proof covers recorded accepted324 learner-family history only; 122 historical roles remain unresolved; no universal nonuse claim; the live ledger is not pinned as immutable history.

## Files
`policy-plan.json` predeclared run IDs and terminal60 paths. `registration-schema.json` field contract. `binding.py` contract, producer chain, limits. `comparison.py`, `paired_statistics.py` statistics. `worker.py`, `terminal.py`, `audit.py`, `launch.py`, `observe.py`, `execute_once.py` execution. `build_registration.py`, `finalize_registration.py` hash-only registration. `monitor.py` read-only counts. `seal.py`, `source-manifest.json`. `tests.py`.

## Finalization once all six producer audits exist (parent)
1. `python -B monitor.py readiness`, or `build_registration.py --check`: all six must print `ready`.
2. With the lexical venv interpreter, `-B`, `PYTHONDONTWRITEBYTECODE=1`, `PYTHONPYCACHEPREFIX=<package>/empty-pycache`: `build_registration.py --output <package>/registration-draft.json`. It refuses (exit 3) until every audit is accepted, then pins each registration, audit, worker result, sidecar, artifact manifest, lease release, parent execution/exit, producer manifests and checkpoint hash.
3. Independent source review of `source-manifest.json`; then write source acceptance `{status: accepted_source_review_only, source_manifest_sha256}`.
4. Accept the wall/resource calibration in a pinned record; run `finalize_registration.py --draft ... --draft-sha256 ... --calibration-acceptance ... --calibration-acceptance-sha256 ...`. It copies the unchanged draft to `registration-final.json` with `status: parent_registered`.
5. Write gate acceptance (`fullgame_priority_d4_evaluation_gate_acceptance_v1`, status `approved_exactly_once_fixed_terminal60_d4_evaluation`, every `binding.GATES` entry `passed`, exact `registration_sha256`, byte-pinned review records in `pins`).
6. Launch: `launch.py --registration ... --registration-sha256 ... --gate ... --gate-sha256 ... --source-acceptance ... --source-acceptance-sha256 ...`. It refuses if any campaign lease is active, installs the lease and marker, and waits on the watchdog.
7. After terminal exit run `audit.py --envelope <package>/launch-envelope.json --envelope-sha256 <SHA>`; it proves process-group absence, cache and input identity, journal cost conservation, all 7,168 rows, comparison and bootstrap reconstruction, then releases only this lease. A failed run needs parent incident handling; never retry.
