# Frozen long-D2 supervisor review, round 2

**Verdict: changes required. `accepted=false`. Two confirmed blocking findings remain at the final outer signal-mask restoration boundary: SUP-001-R2 (P1) and SUP-002-R2 (P2).**

This review applies only to the immutable r2 controller and `capsule-final`. It is a read-only supervisor, authority, resource-monitor, identity, cleanup and publication review. It does not accept a real learner run or authorize launch. All review writes and synthetic authority fixtures are inside this new review directory. No children were created. No real lease was created or activated; no training, inference, gameplay, Torch/native import, checkpoint deserialization or gradients occurred.

## Exact candidate

| Input | SHA256 |
| --- | --- |
| `postovernight-long-D2-prepare-r2/long_d2.py` | `0fe9970187e5c4c2576ff2929a475025cd5731a538325ffac78f172304af1d01` |
| Original r2 `long-identity.json` | `969d825968e7782bc377cfd4d9312cf186df351e5219bff64d849f3d79781ed0` |
| `capsule-final/capsule-manifest.json` | `b1ccbeefe219c24f33b34db19178f4af68baa9674a058b066738231282ef25a1` |
| `postovernight-long-D2-r1-protocol-r2.json` | `f662a4aba18e144098faeb01d398b67f489aea7549a9ebe4a5959f993e1cff09` |
| Registered raw configuration | `2ac814d3842228017d09669364a8391344722da56ad19f41ad9030dbb930c2db` |

The input inventory contains 8,917 distinct resolved files. Its SHA256 is `fba0c461b802719287ebdef5defb9ac5353f7f162fe3cfcc0dd8955b58185643`. Initial and final comparisons found no review-time changes. All 7,275 preparation artifact entries matched their frozen inventory. Pure stdlib preflight passed all 793 active pins, including the original LONG identity document and its capsule mirror. The separate protected-before inventory had two pre-existing mismatches at review entry: `docs/v2-foundation-progress.md` and `learning/runs/v2-orchestration/state.json`. These shared-workspace files were not written by this review; both stayed unchanged throughout the review. This review therefore does not restate the implementer's historical claim that all 1,637 protected files still match that older snapshot.

## SUP-001-R2 — P1, blocking: authority closes before the outer context finishes

Source: `learning/runs/v2/postovernight-long-D2-prepare-r2/long_d2.py:448-465`, `:1281-1297`, and `:1302-1317`.

The new `after_handler_restore` callback performs its final lease/resource/input/deadline checks **inside** `cancellation_signals`, before its final `pthread_sigmask(SIG_SETMASK, mask)`. Both Guard threads have already been joined. The context then releases its latch and restores the signal mask. After the context actually returns, `supervise` checks only the previously counted cancellation requests and returns `cancel.final_exit_code`. It never rechecks lease, input identity or the absolute deadline after that final context operation.

An independent subprocess reused the inspected `publication_probes.scenario` API with the actual r2 `supervise`, actual Guard and a real owned stdlib OS worker. Its only extra interception was the real final unmask syscall. It did not change candidate source. Immediately before the actual syscall, after every final authority callback and pending-signal scan had completed, it mutated its own synthetic lease or pinned input. Both completion outcomes reproduced the defect:

- Late lease cancellation followed by a 0.65-second delay returned **2** for clean closure and **0** for gate pass. The lease had `cancel_requested=true`. The manifest remained available and correctly bound; the terminal receipt remained complete.
- A changed pinned input followed by a 5.1-second delay also returned **2/0**, with a complete terminal receipt and correctly bound available manifest. The final observed input no longer matched its pin.
- With an independently shortened 0.8-second synthetic absolute budget, delaying the same final unmask by 1.0 second returned **2/0** and left complete receipts. This demonstrates the same unchecked teardown interval for the old deadline/return regression. The production source still declares 7,200 seconds; no production budget was changed.

These are context-teardown events before `supervise` returns, not mutations after a completed invocation. The injected delays exceed the required lease and full-input observation bounds. The event records show no live Guard threads. The same interception without mutation or delay returned the expected complete **2/0**, establishing that the fixture itself does not cause rejection.

Evidence: [delayed-unmask-summary.json](delayed-unmask-summary.json), each corresponding `final-unmask-event.json` and `independent-observation.json`, [independent-contract-assertions.log](independent-contract-assertions.log), and [probe_final_unmask.py](probe_final_unmask.py).

Expected: authority loss or deadline crossing during final outer context restoration must return failure 1 and revoke complete status and the manifest. A final check performed before that context's last operation does not establish the requested post-context authority guarantee. The compliant parent must continue measuring real process wall time and exit independently; this review does not claim the parent would accept a late raw exit.

## SUP-002-R2 — P2, blocking: final pending-signal scan races with unmask

Source: `long_d2.py:438-465`, especially `:461-465`, and `:1302-1317`.

The cancellation context restores SIGINT/SIGTERM handlers, drains pending requests, runs its final callbacks, and checks `sigpending()` again. There is still a separate final unmask operation after that last scan. A request queued between the scan and unmask is dispatched to the restored handler, after `_ACTIVE_CANCELLATION` has become `None`. SIGTERM is already `SIG_DFL`; SIGINT is the Python default interrupt handler. Neither request reaches the shared cancellation latch or the receipt revocation path.

The independent subprocess queued a **real** owned-process signal while the final mask still blocked it, immediately before calling the original, unmodified system unmask. Event records prove SIGINT/SIGTERM were blocked, the requested signal was pending, no Guard thread survived, and complete publication had finished. Results reproduced for both clean closure and gate pass:

- SIGTERM: raw subprocess exit **-15**, handler **0** (`SIG_DFL`), complete terminal receipt and available manifest survive.
- SIGINT: raw subprocess exit **-2**, with an uncaught `KeyboardInterrupt` trace at `long_d2.py:465`; complete terminal receipt and available manifest survive.

The exact earlier r1 outer-publication-alarm boundary is repaired in r2. This finding concerns the remaining later boundary at the outer latch's own final mask restoration. The existing probes inject at handler restoration and inside final resource checks, all before the last pending scan. They therefore miss this check-to-unmask race.

Evidence: [independent-probe-summary.json](independent-probe-summary.json), [SIGTERM closure event](final-unmask-SIGTERM-closure/final-unmask-event.json), [SIGTERM pass event](final-unmask-SIGTERM-pass/final-unmask-event.json), [SIGINT traceback](final-unmask-SIGINT-closure.log), and both retained terminal receipts per signal.

Expected: every delivered request through outer restoration must reach the effective latch; complete receipts must be revoked. A compliant parent rejects raw -15/-2, so this finding does not claim parent acceptance of the cancelled run. It establishes missing required latching and false complete artifacts.

## Positive evidence and one unresolved execution

The r1 review, findings, probe source, recorded-contract assertions, summary, cited observations/events, parent reconciliation and learner audit were inspected. The r2 implementation, receipts, source comparison, diff, README, freeze helpers, controller and test/probe APIs were inspected. The corrected v2 score-and-survival direction remains controlling.

- **83 fresh candidate synthetic methods passed in 19.716 seconds.** They include 13 new publication methods and 70 inherited methods executed afresh. This is not transferred evidence from the old 70, 72 or 312 tests. The 66 publication scenarios from this execution all used actual Guard and owned OS workers. They repaired the exact earlier lease/input hashing and outer-publication-alarm boundaries, including clean closure and gate pass. Their stable manifest bindings and absence of open manifest-bound writers were independently checked.
- **Six additional independent Guard methods passed in 1.330 seconds.** These checked resource sampling during a 0.7-second full hash, persistent background verification failure after recovery, refusal to claim a blocked verifier stopped, eventual positive thread absence after release, nonfinite/negative/noninteger resource observations, post-IO deadline enforcement and inclusive duration bounds. The two locks avoid serializing full hashing with resource sampling at the inspected paths.
- **Seventeen additional old-boundary OS scenarios were attempted.** Sixteen completed their failure/revocation assertions: final verification, artifact hash, manifest/terminal writes, publication-context return, unproven group, two deferred cleanup/final-verification signals, and the blocked worker watchdog. Both completion outcomes were exercised except the blocked worker. The blocked worker ignored SIGTERM and was still killed/reaped by the independent supervisor watchdog and bounded group cleanup. No real native call was run.
- **One unresolved execution:** `old-late-terminal-write-closure` exited **-14** instead of finishing its assertions. Its retained terminal receipt was already `failed / wall_guard`, the manifest was absent, and its owned worker group was reaped and positively absent. There was no traceback or final observation. This review cannot establish the SIGALRM race's precise cause, does not count it as a pass, and does not assign an unsupported additional finding. Evidence is retained without retry in `old-boundary-summary.json`, its log, events and campaign receipts.
- Ten independent final-unmask scenarios and six delayed variants were retained, including unmutated controls and the confirmed failures above. Nine recorded-evidence assertion methods produced four passing methods and ten intentional assertion failures across five finding methods. No API/import error caused these ten failures.
- Fourteen inherited negative controls were audited by exact source-replacement reconstruction, source/log hashes, actual `AssertionError` evidence and absence of API/import errors. The three exact-r1 control groups and the retained preclosure control remain historical inspected evidence, not new executions by this review. The separate evidence auditor owns the broader test/probe-claim audit.

All **99 retained owned OS-worker groups** were independently and positively absent at final verification. Their receipts are listed in [owned-groups-after.json](owned-groups-after.json). The ordinary suite also ran its temporary supervisor fixtures; those are not added to this retained-scenario count. The four deliberately signal-terminated supervisors had already stopped both Guard threads before signal delivery. The unexplained -14 process exit also ends its own threads; it is not treated as orderly Guard-close proof.

## Source and authority limits

T0 remains before ordinary imports and worker spawn. The declared worker/normal deadlines remain 7,140/7,200 seconds, and failure cleanup remains 10 seconds. RSS and MPS keep separate 6 GiB observed limits; no fallback or interval relaxation was introduced. SUP-001-R2 limits the guarantee at final outer restoration. Cleanup requires leader reaping and positive group absence before stable hashing; injected unproven absence blocked the manifest. Publication uses a closed disk observation snapshot and a later memory-only monitor, avoiding an open writer on a manifest-bound log at the tested hash points.

Independent AST/source comparison confirmed `Learner`, `Schedule`, `run_schedule`, `environment_kwargs`, `counter_report`, `compare_control`, `tree_fingerprint`, `assert_equal_tree`, `stop_owned`, `assert_lease` and `check_module_origins` are byte-identical to r1. The worker's only body change is the historical consumed-wall receipt label. Entry then 16-update evaluation cadence, update-8 periodic checkpoints, monotone U/E reserves, C=15, F=30, closure tagging, exact D1 lineage and no resume remain unchanged. The new protocol changes only controller path and registration timestamp. The strict 15-field lease, unknown/missing-field rejection, configuration, capsule, controller, identity and D1 terminal bindings remain enforced.

The legacy module-origin policy is unchanged; original and capsule mirror bytes match for all declared origins. Those statements are static identity evidence, not actual runtime imports of the package. Real MPS model/Adam/RNG restoration, entry comparison, environment behavior, throughput, resource use, PPO and qualification remain untested runtime gates. No evidence here opens D3/B/E/student work or transfers acceptance beyond this bounded review.

[execution-receipt.json](execution-receipt.json) records commands, environment, counts and result categories. [input-sha256-verification-after.json](input-sha256-verification-after.json) records the final input comparison. All attempts and failed receipts remain retained. The candidate must not be treated as accepted by this review.
