# Collector R1 source review

**One P2 source blocker: failed-reset snapshots misattribute episode assignments.** The collector's successful boundary path otherwise matches the reviewed contract within source scope. No runtime qualification or launch authority follows.

`T/` means `../progressive1000-collector-prepare-sol-20261026-r1/`. All line numbers refer to its sealed files.

## F1 — P2: distinguish unassigned returned resets in failed snapshots

**Location:** `T/successor/curriculum.py:346–349`; producer ordering at `T/successor/ppo.py:355–370`, assignment mutation at `T/successor/curriculum.py:299–301`.

**Trigger:** `reset_done()` successfully constructs the next episode, then the guard at `ppo.py:358` raises before `record_reset()`. `observe_returned_reset()` retains the new episode and startup cost, but `assignments[slot]` still describes the ended episode. `snapshot()` unconditionally joins that old assignment to the current active native episode by slot alone.

**Concrete static trace:** the existing `test_post_reset_guard_failure_keeps_startup_cost_without_assignment` (`tests/test_collector.py:215–232`) constructs exactly this state. Slot0's assignment event remains episode0/ordinal0, while `FakeEnv.reset_done()` (`tests/fakes.py:107–114`) creates episode1. The resulting `in_flight` row claims episode1 has ordinal0, although no assignment was issued to episode1. This trace is derived from source, not an executed reproduction. The test checks costs and assignment-event count, but never checks the `in_flight` identity join.

**Consequence:** the currently implemented in-memory failed-work snapshot gives false frozen-assignment provenance for a newly constructed episode. Returned startup costs remain available, and the wrapper still stops without promotion or retry; those protections do not correct this row. This concerns existing snapshot correctness, not the deferred durable telemetry implementation.

**Required successor fix:** bind assignments to episode identity. Represent returned-but-unaccepted reset episodes as unassigned/unaudited, or retain them separately without attaching an old assignment. Do not consume a new assignment merely to make a failed snapshot appear complete. Extend the existing failure test to check episode identity and absence of a falsely reused ordinal/horizon. No target repair was performed here.

## Reviewed behavior without additional blockers

- `curriculum.py:165–254` rejects live misalignment/overshoot before simulation, excludes true death including death on H, and invokes one whole-request `truncate_practice(indices, horizons)` for alive exact H<18000 only. Ordinary18000 remains native-cap behavior. Reconciliation precedes inherited audit/storage/value/reset (`ppo.py:318–355`). Exact recursive comparisons cover returned info, all current slot metadata, observations, and the original step payload. Native atomicity and hidden history preservation still need native proof.
- `ppo.py:343–375` copies and values actual final observations before one sorted combined subset reset. Death next-values are zero. Inherited GAE uses death-only bootstrap and death-or-truncation recurrence masks (`143–174`). Episode increments and reset counters are checked; no source change to GAE, reward scaling, PPO loss, KL stopping, buffers, or optional diagnostics was found.
- Frozen assignment tags and ordered completion rows persist across rollouts. The byte-identical scheduler processes the whole update before one promotion. `PreparedUpdates.update_once()` performs collection, PPO, then finish; exceptions consume that instance. Global60 rejects update61 without stepping or draining. Private test hooks are explicitly outside the future runner contract; durable cross-instance one-shot enforcement remains future work.
- Disabled-control parity is supported by inspected fake-oracle source and parent-reported results, not native evidence. Shared PPO JSON matches the design, including constant3e-5, KL0.03, four maximum epochs, minibatch512 and Adam epsilon1e-5. Actual optimizer steps are reported without top-ups. The wrapper checks LR/epsilon; full optimizer construction, Adam-state authentication and restoration remain external integration gates.
- `validate_seed_union()` requires explicit sorted, merged, bounded integer ranges with historical coverage, and checks environment metadata and actual seeds against that union. It is callable before future environment construction; the adapter receives an already constructed environment. The documentation correctly requires the future caller to perform the earlier check. Neither helper nor adapter proves exhaustive ancestry/freshness.
- Model inputs remain the four allowlisted neural observation arrays (`ppo.py:177–200`); assignment/exposure telemetry never enters model tensors. Tests include a separate scalar GAE recurrence, tagged final/reset values, frozen-source control comparison, death ties, decision255/cross-rollout behavior, corrupt native responses, missing native API, promotion ordering and failed-work costs. These are appropriate synthetic oracles, with F1's failure-row coverage gap.

## Identity and evidence

Verified all21 target seal entries, all19 manifest payload entries, all9 exact diff sections by in-memory reconstruction, all10 Python ASTs, and byte equality of all10 parent-validation Python copies. Removing only the collector argument/hooks restores the entire accepted PPO AST. Optional diagnostics and scheduler are byte-identical. [Source checks](source-checks.json) include exact input hashes; [checker](verify_source.py) imports only stdlib and never executes target code.

- Target manifest: `1839e0f89a08f1c79e0e2a26e26019b2ad951ac1f461a3a2de7a83ff7d214f24`
- PPO: `95cf870e5358e9bcb9c29567f04b7f6c2bbbe6e5532b735da0e44994b9c67d56`
- Curriculum: `e97d46b06cc21a2455f8a7a6f73c7e26e561433aaecb93648e26399d6152cede`
- Scheduler: `a467b7219a9cd801fa3b403a6af112fc693ec3d14c9d311e8845632ef61d844b`
- R3 experiment: `c20bd35188c4b4dd36687bc10c7998e6410c70d37300be92db9a42b3d01c43c0`
- Exact diff: `356cd34e77c0ee4fb49f2c2cbb168967e766197468efdf5bf8afd45aec4ac04b`
- Parent API contract: `f73c638f53960fb74b5227510f06abaf20e469578f6f5c9bda0961c87213c1a3`

Parent validation log reports **39 synthetic CPU tests passed in3.574s**; this review ran **zero tests**. Only stdlib source reading, hashing, AST and JSON inspection occurred. No target imports, Torch/NumPy/native imports, model/environment construction, builds, real checkpoint reads/deserialization, MPS, study cohort use, training/evaluation, repair, subdelegation, commits or pushes occurred.

Full runtime CLI/identity/evaluator/native integration, real restore/reseed, seed/cohort reservations, durable telemetry, resource/cleanup enforcement, registration, launch and acceptance remain parent-owned future gates. The supplied native link-failure/repair status was not independently investigated. Fake evidence does not qualify native behavior. F1–F7 remain resolved at design scope; no numeric design choices are reopened. B/E remain closed. Only this new review directory was written; listed-input hashes establish scoped preservation, not an exhaustive concurrent-workspace audit.
