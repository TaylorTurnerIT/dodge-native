# Finite native/collector CPU integration units

Passed four old/new disabled-cutoff parity cases, actual-native synthetic collector units, eight native binding/API controls, and 41 inherited fake collector/scheduler controls. An owned harness import-path failure was preserved and repaired; only the affected fake controls were rerun. No collector or native integration bug was observed.

This is finite descriptive unit validation. It grants no global source-to-binary correspondence, runtime/training qualification, registration, or launch authority.

## Results

- **Parity:** D1 and D2, thread/chunk layouts `(1,1)` and `(2,2)`, four slots, 256 predetermined action vectors. Each slot uses the explicit list `31 + slot + 100*episode`, episode `0..256`. No ranking or seed replacement. Each old/new pair matched complete initial metadata and every step/reset typed digest exactly. Comparisons include every observation array's dtype, shape and C-order content, rewards, counters, masks, diagnostics, seed identity, episode metadata, reset results, and post-reset observations/batch metadata. Pixels and auxiliary arrays were enabled. No `truncate_practice` call occurred. D1 recorded 15 deaths per layout; D2 recorded 14. No configured 512-frame cap was reached. Full lists, vectors, rolling hashes and per-step hashes are in [old](results/parity-old.json), [new](results/parity-new.json), and [comparison](results/parity-comparison.json).
- **Native integration:** One shared new binary, real training mode `run_seed=777`, D1, eight slots, K4, cap18000, normal starts. The exact historical exclusion floor was validated before construction. A fixed observation-only avoidance policy, copied from the pinned native binding fixture, supplied deterministic synthetic actions. Its tiny CPU linear value head remained fixed. No native optimizer/PPO update occurred.
- **Enabled:** Seven actual H1000 survivors cut off at decision249. One actual death occurred at gameplay frame631, decision157. There were 8,191 gameplay frames including the fatal frame, eight accepted episode resets in two combined subset calls, and 104 reset startup frames. Flags and native EpisodeInfo synchronized before audit/storage. Final observations were valued before reset; reward/alive/fatal/counter conservation and one episode increment passed.
- **Disabled:** Same initial native configuration and policy, cutoff disabled. Initial metadata and raw trajectories matched the enabled arm through its first cutoff. One death/reset occurred; zero practice cutoffs. Each arm executed 256 vector decisions with 8,191 gameplay frames. Later episodes intentionally diverged after enabled resets.
- **GAE/storage:** Inherited scalar oracle matched exactly in float64 on actual death, alive cutoff and continuation data. Perturbing later episode rewards left preceding boundary advantages unchanged. Death bootstrap was zero; alive cutoffs used their actual final value. Native return ownership, copied collector storage, ascending combined resets and assignment identities passed.
- **Buffer continuity:** Two128-decision pieces of the same pending unit update produced exactly the full256 buffer digest. State and observation continuity crossed the buffer seam. Decision255 was reached as continuation. No native episode boundary happened at decision255; inherited fake controls cover that boundary.
- **Failure semantics:** An intentional guard exception immediately after the first actual native reset retained 13 returned startup frames and the new live episode as `unassigned_unaudited`, with no stale horizon/generation/ordinal attached. No retry or reassignment occurred.
- **Scheduler:** Actual-native fixtures ended with completed update0, pending update1, and generation0. Collection never promoted mastery. Inherited fake controls cover successful/failed PPO ordering and promotion.
- **API:** Six exact native binding controls plus two additional controls passed. Actual bindings reject Python-only constructor/boundary flags, wrong integer types/shapes, invalid horizons/slots and mixed invalid requests before mutation. H1000 whole-request rejection and owned results passed. Binding controls reached an actual configured cap8.

Detailed native records: [enabled](results/enabled_full256.json), [disabled](results/disabled_full256.json), [split](results/enabled_split128_128.json), [guard failure](results/enabled_post_reset_guard_failure.json), [summary](results/integration-summary.json).

## Pins and ownership

The extensions were loaded from their explicit original paths using `importlib.util.spec_from_file_location('_native', path)`, in separate old/new processes. Neither extension was copied, installed or overwritten.

| Input | SHA256 |
| --- | --- |
| New extension | `29d49a1317ebe1367932e88514f744242a8e67cf7e6d7d0ab64d5f008cbed567` |
| New native source manifest | `6a3c3a4c6b884fe59015d4dc299a15883d6dc7f108b55171e1e3dc800cf46aba` |
| Old accepted extension | `022d41dde9bace0b4f4c4c06b9b4ed007bc2c60013cd98734086e587d7bb997e` |
| Accepted collector source manifest | `16200c082f53f62eb01c068de18ebd826da8d3a06969ce82de1c218c70f9d8f9` |
| R3 design | `c20bd35188c4b4dd36687bc10c7998e6410c70d37300be92db9a42b3d01c43c0` |

[inputs.json](inputs.json) records all paths, acceptance metadata, 64 checked input hashes, and exact Python copies. Every copied collector/test source remained byte-identical. Native source manifests and their listed files, both extensions, collector acceptance and root README matched postflight. The inherited fake baseline comparison read frozen `ppo.py` source only; its additional post-run hash is recorded in the receipt. No checkpoint was read.

All writes stayed in this directory. No native/collector/frozen/runtime/root README/checkpoint/ledger/lease/marker edits, subdelegation, commit, push, MPS, accepted model, study cohort or B/E use occurred. Verification covers listed inputs and this lane's writes; it does not attribute concurrent whole-workspace changes.

## Execution and preserved failure

Essential commands, from the repository root:

```sh
python3 -B learning/runs/v2/progressive1000-native-collector-integration-sol-20261026-r1/prepare.py
python/.venv/bin/python3.12 -I -B learning/runs/v2/progressive1000-native-collector-integration-sol-20261026-r1/run_units.py
python/.venv/bin/python3.12 -I -B learning/runs/v2/progressive1000-native-collector-integration-sol-20261026-r1/finish_units.py
python3 -B learning/runs/v2/progressive1000-native-collector-integration-sol-20261026-r1/finalize.py
```

The first two commands created inputs and ran the initial bounded attempt. They must not be rerun in this evidence directory. `run_units.py` refuses an existing invocation. `finish_units.py` consumed one repair attempt and reused all passing native outputs. Reproduction requires a separately owned successor output directory and preserved input pins.

[invocation.json](invocation.json) contains exact child argv, environment, deadlines, durations and process-group cleanup. Each child had a120-second deadline; total child wall including failure and repair was **29.116314875194803 seconds**, under300. Maximum child wall was15.989594625076279 seconds. Python3.12.15, NumPy2.5.4, Torch2.14.1; CPU only, one Torch thread. Bytecode disabled with `-B`; cache and temporary paths owned here. All six owned child process groups were absent after termination.

Initial fake control discovery passed20 tests, then failed with `ModuleNotFoundError: No module named 'scheduler_reference'`. [First failure](logs/first-failure.log) and [detailed log](logs/fake-controls.log) remain unchanged. The [repair diff](repairs/control-import-r1.diff) adds the copied successor directory to the owned harness import path. [Repair invocation](repair-invocation.json) and [repaired log](logs/fake-controls-repaired.log) record41 passing controls. The inherited fake suite includes synthetic CPU PPO/optimizer contract tests; zero optimizer steps applies to the actual-native fixtures.

## Limits and remaining gates

The actual collector fixture is D1 only. It did not reach H2000, an ordinary18000 cap, exact-H death, a simultaneous native death/cutoff vector, or a decision255 boundary. Previous author Rust fixture claims were not rerun. Exact-H/mixed/late-boundary semantics here rely on explicitly identified inherited fake controls and prior native-source work, not newly observed native trajectories.

The split fixture divides one pending synthetic update. It is not a successful PPO/update transition or an actual two-update campaign. Historical exclusions establish a floor only, not exhaustive seed freshness. Finite hashes describe these tested trajectories; they do not establish global binary equivalence.

Independent review and parent acceptance remain open. Full runtime/build/model/evaluator identity, authenticated restore/RNG references, ancestry/future exclusions and reservations, resources/cleanup calibration, registration, lease/marker controls and launch authority belong to separate lanes.

[receipt.json](receipt.json) is the machine-readable result. [source-manifest.json](source-manifest.json) and [artifact-manifest.json](artifact-manifest.json) bind owned sources, logs and outputs.
