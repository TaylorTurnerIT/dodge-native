# Confirmed324 paired worker R2 source review

Source repair required: one P2 finding. Parent retains source acceptance and all registration, resource, launch, runtime, evaluation, and selection authority.

## Finding R2-01

**P2 — Preserve completed rollout episode events before fallible PPO work.** `runtime_adapter.py:153-157` collects a rollout and immediately runs PPO. Its subsequent metric/diagnostic checks can also raise before the collection returns. `worker.py:120-124` journals completed/reset events only after that return. A completed rollout containing episode boundaries followed by a PPO/diagnostic failure therefore loses those episode records. The failure receipt retains progress, but the collection is not retained and the environment is released. The one-shot claim remains spent. This contradicts the episode-evidence preservation promised at `README.md:24`; the pinned historical runner emits events before PPO at `runner.py:808-813`.

Persist those events immediately after collection, before PPO or diagnostics can fail. Verify with nonempty fake completed/reset records followed by failure; preserve the claim and diagnostic progress, and save no candidate. This finding does not assert that a runtime failure occurred or that an invalid candidate can be accepted. Exact locations, trigger, consequence, and repair appear in `findings.json`.

## Checks and repaired R1 defects

All **27 independent static checks passed**: 25 source-manifest members, 31 artifact-manifest members, 58 input pins, exact artifact/runtime inventories, 11 authoritative R5 members, five unchanged R5 implementation copies, exact regenerated diff, 14 Python AST parses, and independent reference/template/seed-arithmetic bindings. See `static-checks.json` and the reproducible stdlib-only `static_review.py`.

The concrete adapter/CLI, strict parent registration/source/marker/lease/cache gates, independent three-replica reference provenance, six raw RNG keys versus two measured CPU/MPS digests, zero-argument R5 restore, actual R5 evidence dictionary, and post-reseed model/Adam checks address the cited R1 defects in the inspected source. R5 restores accepted state exactly once after its durable claim, then reseeds and overrides LR. Disposable constructor seeding/model/Adam construction before that claim matches the explicitly accepted bootstrap boundary. Spent-path refusal precedes bootstrap; exclusive claim creation and retained failure files prevent a fresh instance from restoring again.

The inspected successful path preserves parent episode indices, exclusions, PPO/reward/GAE/KL controls, cumulative373–432/phase325–384 counters, linear LR endpoints, mutable PPO progress, full candidate saves at local12/24/36/48/60, and separate trajectory/resource clocks. No automatic replacement, evaluation, selection, or promotion is present. The failed-update fake control checks progress and absence of candidates, but supplies no rollout episode events and cannot cover R2-01 (`test_worker.py:343-361`).

## Exact identity

- Target source manifest: `60892ffc78f9b29e6c3c5c6734f71577a05acbf596c69bc7731fc77a18d13493`.
- Target exact diff: `cc289442b0739191b0b8d26355ce286ad5aa1802a85539acfb6d9e7a4e3f1190`.
- Authoritative R5 parent manifest: `2b0caf00a5d5e765726d080fd5647211190e472d74ffb33b3466e477cb2906a9`. The four stale historical entries in inherited R5 `source-hashes.json` were not used as authority.
- Initial-reference registration: `0150cfcdbec53ff4322f72e5fa224cb6a914f3505ea732c0722511b5e031c398`.
- Accepted checkpoint, read/hash only: `c10d90ec0e67503afef8f4d90c4968581d430ef2065117a75e81c445a04c8ddc`.

Other exact target file hashes appear in `static-checks.json`; reviewed source locations refer to the frozen R2 directory.

## Scope and limits

This review used only stdlib file reads, SHA-256, AST parsing, JSON inspection, diff reconstruction, and integer seed arithmetic under `python3 -B`. No target imports, target tests, function execution, Torch/NumPy/native imports, builds, model/environment construction, real checkpoint deserialization, MPS operations, training/evaluation campaigns, study-cohort execution, subdelegation, commits, or pushes occurred. Only this named review directory was written.

The author's 37 fake/stdlib controls and exit0 are reported evidence, not independently replayed. The reference audit reports raw supervisor/worker exits0 and 19 checks; those references establish initial CPU/MPS generator states only. None of this source/static/synthetic evidence qualifies accepted model/Adam/RNG restoration or real runtime behavior.

Remaining parent gates include this source repair and acceptance, supervisor/watchdog/cancellation/cleanup integration, calibration and caps, six final registrations, real loaded runtime/class/backend and accepted-state restoration qualification, native seed readbacks, rollout/PPO/diagnostics and true candidate serialization, terminal audit, and separate full normal-start evaluation/selection. The original paired-LR study remains independent of progressive1000 curriculum: three exploratory pairs, no formal method claim at n=3. Curriculum design/scheduler pins remain unchanged; B/E qualification remains closed.
