# Progressive1000 collector preparation

Preparation only. No native build/import, real checkpoint read, MPS, study seed reservation, training/evaluation campaign, qualification, registration, or launch occurred. Accepted parent324/cumulative372 SHA is a supplied pin, not reverified checkpoint evidence here.

The owned successor copies accepted Python PPO and its optional diagnostics. Only collector hooks differ; reward, GAE, PPO loss, buffers, and epoch-end KL logic remain unchanged. The reviewed scheduler is byte-identical (`a467b7219a9cd801fa3b403a6af112fc693ec3d14c9d311e8845632ef61d844b`). [Exact diff](accepted-to-successor.diff), [source checks](logs/source-checks.json), [manifest](source-manifest.json), and [receipt](receipt.json) record scope and pins.

## Call contract

Keep one `CurriculumAdapter` and one `PreparedUpdates` instance across rollouts. Before future environment construction, validate the explicitly supplied parent-owned exclusion union with `validate_seed_union`; shape/historical coverage does not establish freshness. Both arms use identical successor code and [shared settings](shared-config-contract.json), differing only in `enabled`. The full runner configuration and source identity remain unimplemented gates.

```python
adapter = CurriculumAdapter(
    existing_normal_start_env,
    enabled=enabled,
    digest=reviewed_full_vector_hash,
    replica=replica,                       # integer 1..3
    exclusion_ranges=parent_owned_union,
)
updates = PreparedUpdates(existing_cpu_fake_model, existing_adam, adapter)
collection, metrics, boundary = updates.update_once()
```

This is a CPU source prototype, not a real-run recipe. `update_once()` owns all256 decisions, PPO, and exactly one successful post-PPO scheduler finish. Collection alone cannot promote through this entry point. Failure consumes the instance; no implicit retry, rollback, top-up, or update61. At update60 it stops without an episode drain. Direct collector hooks/private finish calls exist for synthetic unit tests; future runners must use the wrapper. Model/optimizer/environment creation, restore, evaluator, CLI, and registration are deliberately external.

Initial assignments use ascending slots. Each normal reset freezes generation, horizon, ordinal/block/position, digest, and seed identity outside model tensors. Ended slots record `(update, decision, slot)` before one combined sorted subset reset. Promotion happens after PPO success, so resets in that rollout and existing in-flight episodes keep the old generation. Control has no mastery scheduler or practice calls.

The adapter checks alignment before simulation. After each actual step it selects only alive, non-ended slots exactly at H<18000, calls `truncate_practice(indices, horizons)`, and checks complete returned EpisodeInfo, all slot identities/counters, unchanged step payload and final observations. It then replaces only selected info/truncation masks before inherited audit, storage, final-value computation, and reset. True death wins, including death on H; H18000 uses the ordinary cap. There is no Python flag-only fallback or `reset_all`. Hidden native history preservation still needs native proof.

`snapshot()` exposes replica/arm-tagged assignments, completions, scheduler boundaries, actual interval and update exposure, initial construction/reset startup13 costs, fatal-inclusive gameplay frames, and unfinished episodes without stepping. Returned unaudited work remains separate when a guard/audit fails. `PreparedUpdates.snapshot()` also retains successful metrics and partial PPO progress. This is in-memory telemetry plumbing; durable streaming, native exception costs without returned results, wall/memory/cleanup enforcement, and evaluation cost accounting remain integration gates. Scheduler state and exposure distinguish entered, exposed, mastered, and untested stages; no promise of reaching18000.

## Synthetic evidence

[Final test log](logs/tests-attempt-03.log): **39 tests passed** on project Python3.12.15/Torch2.14.1 CPU, one Torch thread. [Fake controls](logs/fake-controls.json) retain measured fixture outputs. The suite covers mixed death/cutoff/continuing/cap, independent scalar GAE, tagged final-before-reset values, death H-1/H/H+1, decision255 and cross-rollout episodes, one subset reset/seed increment, corruption/missing native API rejection, old-generation promotion, fatal-inclusive exposure, failed-work costs, wrapper ordering/failure/global60, strict injected union, and all21 reviewed scheduler tests.

Disabled control matches frozen-source collection exactly for all15 buffer tensors, observations, completions, resets, and post-collection RNG on identical fake inputs. Synthetic eight-transition PPO fixtures retain target_kl0.03 and report actual4 versus1 optimizer steps without top-ups. One64x256 fake-net/fake-env update reports16384 transitions and128 actual Adam steps. These are unit tests, not a training campaign or runtime parity proof.

[First failure](logs/tests-attempt-01.log) remains intact: relocated scheduler test referenced the wrong owned sibling path; the import guard also misidentified `torch._native`. Only owned harness paths/guard were corrected. [Second run](logs/tests-attempt-02.log) passed36 tests. Final run added explicit ordering and failed-work-cost checks. Frozen sources/tests were not edited.

To reproduce in a **writable successor copy**, keep all outputs/cache inside that copy, precreate an empty `empty-pycache`, and run:

```sh
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 \
PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX="$PWD/empty-pycache" \
/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/learning/.venv/bin/python -B run_tests.py
```

The suite writes `logs/fake-controls.json`; preserve existing receipts/logs when using a new successor. No bytecode or pytest cache was created here.

## Remaining gates

- Integrate the independent native lane and build a single successor binary for both arms. Prove whole-request atomic rejection, ownership, poison/overflow handling, history/counters/reward conservation, exact H1000/H2000 and ordinary18000 behavior, death ties, seed increments, and thread/chunk layouts. The fake API is only a fixture.
- Prove cutoff-disabled accepted/native/runtime parity on separately authorized fixed seeds/actions. Neither current Rust source nor fake equality proves accepted binary correspondence.
- Bind full successor runtime/model/PPO/native/dependencies/config/evaluator hashes. Adapt only successor identity/evaluator validation; preserve full normal starts, sampled action semantics, terminal60 endpoint rules, cohort accounting, death/milestone/quartile metrics, and per-replica regressions.
- Authenticate accepted324 model/full Adam/RNG restoration, accepted slot indices, paired replica1..3 vector forks, independent measured CPU/MPS references, and durable one-shot claim. No checkpoint was opened here.
- Parent must provide exhaustive consumed-seed ancestry, exact future union and1024 shared cohort before construction. This helper does not weaken the frozen exact-five-range validator and does not certify the supplied union complete.
- Complete durable telemetry, native failure receipts, train/eval/aggregate wall/raw-frame/startup/memory/cleanup calibration and enforcement, resource limits, review, identity, registration, and parent launch authority. All remain unqualified.

Only this directory was written. Existing dirty workspace state was left alone. Files and directories are frozen read-only after packaging; listed input before/after hashes establish scoped source integrity, not an exhaustive concurrent-workspace audit.
