# Frozen long-D2 lifecycle review, round 3

**Verdict: changes required. `accepted=false`. One confirmed P1 blocker: SUP-001-R3.**

This review applies to the R3 identity supplied in the brief. It is read-only outside this new review directory. No real lease, ML/project/native import, checkpoint deserialization, inference, gradients, training, gameplay, provider retry, child agent, external message, install, commit, or launch approval occurred.

## SUP-001-R3 — P1, blocking: final normal verification outlives every independent outer bound

Source: `learning/runs/v2/postovernight-long-D2-prepare-r3/long_d2_executor.py:406-417`, particularly the forced `self.authority(True)` at line 417. That method performs lease IO, full verification, resource probes, and another lease read at lines 198-210. `lifecycle.py:96-105` supplies the relevant deferred-handler behavior.

The normal path changes the lifetime latch to `DEFER`, closes both Guard threads, sets the watchdog stop event, positively joins the watchdog, and closes the IPC endpoints. It then starts another complete normal authority check. The timer is still armed, but its deferred handler only records the alarm: it cannot interrupt a blocked read. There is no remaining watchdog to call `os._exit(1)` at the shared failure deadline. The synchronous hash observer runs only when control returns to it. A blocked final verification therefore prevents the finite exit leaf from being reached.

This is before finite D, inside normal verification. It is not the documented post-scan signal or final-memory-read observation limit. The probe uses an ordinary interruptible pipe read; it does not require an uninterruptible kernel task or a scheduler failure.

The independent probe retains the actual R3 `Execution`, `authority`, `Guard`, `supervise_owned`, private handoff, separate owned worker session, artifact validator and exit leaf. The existing stdlib synthetic fixture supplies owned roots, fake artifacts and shortened offsets. At the first `verify_files` call reached by the final post-watchdog authority check, an in-memory wrapper records the boundary and injects `os.read` on an empty owned pipe with its writer still open. No candidate file is changed. The injection is at verifier entry, before forwarding to the original verifier; it models blocked verification IO, rather than claiming a real frozen file hung on this machine.

The paired unblocked wrapper reached the same boundary and returned raw **2**, accepted by the parent-side predicate in **1.8133224160410464 seconds**. The blocked case used synthetic worker/inner/outer offsets **2.5/3/4 seconds** and the unchanged **10-second** cleanup allowance. At injection, the latch was `DEFER`, both Guard handles were dead, the watchdog was dead, no owned monitor thread remained, both child groups were already positively absent, and the one-shot timer had **2.270847 seconds** remaining.

The executor was still alive at **T0+14.505748457973823**, beyond even the latest possible shared cap, **T0+14**. The harness then killed only its direct owned executor. Raw exit was **-9**; external elapsed wall was **14.526113416999578 seconds**. The acceptance-shaped receipt remained `accepted=true`. The parent-side acceptance predicate correctly returned false. Both registered child groups were positively absent, and the executor was reaped.

Evidence: [probe_final_io.py](probe_final_io.py), [run_final_io.py](run_final_io.py), [boundary event](final-io-blocked-diagnostic/final-read-event.json), [observed command](final-io-blocked-diagnostic/observed-command.json), [paired results](final-io-summary.json), and [intentional contract assertion failure](final-io.log). The failure is an `AssertionError` about survival past the shared cap, not an import/API error. The harness SIGKILL is explicitly a test cleanup action, not candidate termination evidence.

Impact: this breaks the required bounded outer lifecycle and continuous observation through normal finalization. A compliant parent rejects the missing/late raw exit or eventual -9; this finding does **not** establish acceptance of an invalid campaign. Keep an effective independent deadline owner through every potentially blocking normal operation, and leave no new normal verification/probe/lease IO after that owner is stopped. Preserve process-lifetime handlers, the single alarm arm, the finite leaf, and the single shared cleanup pool.

The blocked execution was not retried. Qualification checks stopped at this first unexpected failure. Subsequent work only audited retained source/evidence and closed review receipts.

## Frozen identity and source review

All supplied R3 hashes match:

- Controller: `d26dd14d844c0e1c7b4414d44a753f913eb1f66560ec9a7cdd0860dec821f73a`.
- Executor: `a373e898eddf21547a7ff5bcc7d44928edc6e4ab562e1944b9f70f9efe6ea965`.
- Identity document: `0282c37d1b7d8751f858841913d5b6039a6c5b04ad82f4e3c668deef0b76df9c`.
- Capsule manifest: `617dcc46c9f6f0b14ac4d925192636d527e7ed202b915b9179f2070a9d4fba64`.
- Registration: `aa338aefa5a70d20ab6478089967ba67bc15119ccd32449792b790f7c9287581`.
- Protocol: `6a7ffe59551fd12f4a6fd316c6ab626d03e92a7ec25f77dc34fce30837fa592d`.
- Configuration: `2ac814d3842228017d09669364a8391344722da56ad19f41ad9030dbb930c2db`.

The controller, executor, lifecycle, process helpers, synthetic fixture, OS driver, unit definitions, legacy controls, freeze/finalization helpers and other active root Python helpers were read. So were the README, implementation result, worker hook diff, source comparison, registration/invocation/required lease, expanded pin inventory, protocol/configuration, governing plan/specification, both prior reviews/findings/probe implementations and relevant retained source/events, parent reconciliations/addendum, completed fallback design/plan, and failed partial Opus design/parent assessment.

Independent AST extraction confirms all 14 declared protected nodes remain byte-identical to R2. The worker hook remains a separately disclosed supervision exception; no actual ML/API behavior was tested here. The expanded input manifest contains **9,702 distinct files**, including all **9,675 registered full pins** and the initially observed review inputs. Registered digests match; the final comparison is recorded separately. This does not claim an otherwise clean shared worktree.

## Fresh controls and retained evidence

Before the blocker, **two fresh positive OS controls** accepted raw 2 and raw 0 with the actual Guard and owned worker. **Twenty-nine additional targeted OS controls** reached their expected rejection behavior. They cover both completion outcomes for late artifact cancellation, outer receipt pin changes, Guard close signals, watchdog join cancellation, final authority pin changes, pending real SIGINT/SIGTERM, executor-recorded forwarding after inner D, symlink/extra/binding corruption, and one fresh shortened late-terminal case per outcome. The remaining controls cover a worker ignoring TERM and ALRM, the spawn/registration race, and inner death with a separately owned worker. All reached requested injection seams; worker-blocking cases have no injection hook to claim.

With the paired final-IO control and blocker, this review retained **33 outer OS executions**. These are subprocess counts, not unittest-method counts. The three successful executions are the two initial positives and the unblocked final-IO control. The blocked execution is an unexpected retained failure, never a pass. `targeted-controls/summary.json`, per-case `observed-command.json`, source hashes, events, stdout and stderr retain the actual commands, raw exits and wall measurements. Final registered-group and direct-executor absence evidence is in `owned-processes-after.json`.

The old restoration operation is absent from the R3 production leaf. Fresh probes target remaining live boundaries; a removed restoration hook was not treated as a passing injection. Direct signals at the finite pending scan reject. Executor-recorded forwarding after inner D rejects. The documented direct post-scan and transient-filesystem limitations remain legitimate limits; no impossible atomicity requirement is added. The new late-terminal cases both rejected with raw 1; they do not explain the old R2 raw -14. Its cause remains unproven and it was not replayed.

Retained implementation evidence was inspected, not counted as fresh execution. All **165 final-matrix records** reconstruct exactly from their per-case command receipts, with event reachability and raw/expected outcomes agreeing. Source snapshots match their declared hashes, and all six runtime/fixture/OS-driver files match current frozen R3 source. The only declared post-matrix source change is the preparation finalizer; the retained final-unit receipt pins current helpers. The reported **63 methods** are retained evidence, not new methods run by this review.

The intermediate aggregate stdout loss is real and disclosed in `attempts/aggregate-log-note.json`. The overwritten original stdout was not recovered. Its loss must not become a claim that every aggregate log was retained. The surviving final 165-line aggregate log and exact per-case receipts/source snapshots support reconstruction of that final matrix independently of the missing intermediate stdout. [retained-evidence-audit.json](retained-evidence-audit.json) records the checks. Broader artifact-denominator and native/API auditing remains with the parent's separate auditor.

No result here establishes actual Torch/MPS restoration, entry equality, native pool behavior, gameplay, learning, throughput, future artifact timing, teacher qualification, training-parent eligibility, or D3/B/E/student authority. This review supplies a reproducible lifecycle blocker, not a production campaign or launch recommendation.
