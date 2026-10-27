# r12 failed source-only handoff

The single registered stdlib stage failed. Stop-first-failure was honored. No source patch or test retry followed. Source ownership is released, with candidate/source/fixture bytes unchanged from the pre-test source manifest. This candidate is not accepted.

## Actual result

134 methods were registered: all 112 inherited method names/assertions/consumer bytes unchanged, plus 22 new scheduling methods. Execution reached 21 new methods: 20 passed, method 21 failed, zero errors, zero skips. 113 methods remain unrun: new method 22 and all 112 inherited methods. No prior result transfers. Raw child exit was 1; observed wrapper test wall was 0.3531107919989154 seconds. There was one invocation, no timeout, no retry, and the direct child was reaped. The owned cache stayed empty and forbidden imports were absent.

Failure: `test_r12.R12.test_21_registered_setter_assumption_and_unchanged_monitor_call_sites`, `test_r12.py:414`. Its source-text assertion was too broad: it scanned all original semantic-identity Python files, including `python/tests/test_env.py`. That file's `one_native_call_with_witness` helper calls `sys.setswitchinterval(60)` at line 413 and restores at line 419. It is test code, read as text only here. No competing production setter or production scheduling failure is inferred. The premise must be reconciled by the parent in a distinct authorized task; this candidate and its failed receipt remain intact.

Read `failure-reconciliation.json`, `unit-stage/command.json`, `unit-stage/raw-result.json`, `unit-stage/stderr.log`, `unit-stage/suite-result.json` and `test-method-inventory.json`. The exact assertion, traceback and all unrun names are retained.

## Candidate source and bounded passing evidence

Only production semantic change is the process-global CPython interval context around the existing `observation = self.verify()` in `Guard.full_check`, under its existing verification lock. Fixed cap: 0.0001 seconds; already shorter intervals stay shorter. Restoration checks exact observed equality and corrects saved-float microsecond truncation with the adjacent larger float. Nested finally recovery covers one exception interrupting first cleanup; failure still propagates. Arbitrary repeated asynchronous exceptions are not guaranteed recoverable. A leaked interval can affect guard outcomes as well as performance.

The helper explicitly requires main-thread entry. Registered real boundaries run synchronously on the main thread; the resource monitor uses `full=False`. A per-Guard lock cannot serialize arbitrary global setters. Cooperating code must not change the interval concurrently. The failed scan does not qualify a global no-setter assertion. Main-thread rejection, ordinary restoration, Stop/other BaseException, one modeled cleanup interruption, nested short/nondefault intervals, real simultaneous interval reader, original callback once, and fatal Guard failure were among the 20 passing new methods. Signals were modeled by directly calling unchanged `ProcessLatch.handle`; no OS signal delivery or handler/timer installation occurred.

New test 19 passed the complete source-byte projection: remove only the two scheduling helpers, scheduling constant, three mechanical candidate/protocol constants and one callback wrapper, then compare the entire controller with exact r11. Only existing `Guard.full_check` changed; all other Guard methods and controller blocks remain exact. `boundary_integrity.py`, `lifecycle.py`, `processes.py`, `long_d2_executor.py`, `freeze.py`, source-equality machinery, fixture sources/consumers, all 15 cases and unchanged stress contender/12 boundaries/120s cap remain exact r11 bytes. Full protected learner/worker/acceptance/lifecycle/IPC/escalation/checks/limits are unchanged source evidence, not runtime proof.

New test 20 passed exact protocol-delta/hash checks. `protocol-r9-proposal.json` derives from exact r8 and changes only r11 candidate paths to r12, registration timestamp and explicit process-global callback scheduling declaration. Exact proposal SHA256: `22110a3cb52c36c86934ce02bb0b5c82e2041dc1a00e39a11bb80dd23697d115`. Controller pins canonical future `learning/runs/v2-orchestration/postovernight-long-D2-r2-protocol-r9.json`. No external publication occurred.

## Existing test preservation and accommodation

All five existing test sources remain byte-identical to r11. Four inherited static methods hard-code r11 equality/r8 constants. The frozen runner registers those exact methods against the exact `r11-source/` historical snapshot and three historical path/hash constants; the other 108 inherited methods bind r12. New tests 19/20 supply strict current-candidate delta coverage. No method assertion, success consumer or production behavior is patched. This accommodation is explicit in the frozen runner and command. None of the 112 inherited methods was reached, so no full regression pass is claimed.

## Inputs, scope and publication

All eight r11 frozen byte bindings were verified before copying and rechecked at closeout. Exact input inventory includes 75 original semantic-source bindings, config and D1 checkpoint bytes without decoding, Sonnet qualified authorities, probe scripts/outputs/manifests and r11 review. `r11-source/` is an exact base fixture snapshot; required original/r6/r9/r10 fixture directories remain historical fixtures. No old attempts, runtime outputs, capsule/classification/identity/registration/lease/invocation are current envelopes. Mutable ledger bytes are retained in `state.context.snapshot.json` with relevant context; routine live updates are not drift.

Every write stayed under this new r12 output. No /tmp write, original/project/runtime/docs/ledger/external-protocol/lease/cache mutation, nested delegation, provider call, message, scheduler, commit, PR or deployment occurred. No production freeze, OS matrix, stress, startup, ML/native import, checkpoint decoding, environment/inference/gradients/training ran. No universal OS write audit is claimed.

`finalize_r12.py` was written and frozen before the test stage but was not executed. Failure-specific evidence publication instead records actual executed/unrun counts and the discovered source-scan error without editing any frozen source.

## Parent-owned next work

Reconcile the failure, complete source diff, exact base/input/source manifests and raw test receipts. Do not patch or rerun r12. Any subsequent source/test repair requires a distinct authorized candidate/stage. Parent owns whether to accept/revise the scheduling design, exact external protocol publication, fresh classification/manifests/identity/registration/capsule, independent frozen review, registered OS/stress/startup validation and any subsequent training decision.

Never reuse r11 classification: changed source changes its derived bytes. Preserve original 10091/9870/9675 source unions, disjoint B/R/A coverage and acyclic leaf-manifest/classification/identity/capsule/external-registration hash DAG. No fresh B/R/A/capsule counts or full actual endpoint verification were measured here. Preserve all forced active B and genuine legacy/origin/runtime/cache checks and operational no-writer/finite-observation limits. Missing/unproven stays unproven; transport cause remains unknown.

Unchanged experiment: config `2ac814d3842228017d09669364a8391344722da56ad19f41ad9030dbb930c2db`, seed `5562873868232098305`, eligible D1 `ce9c03c8d476f58d5edec9f95946fa808d1d65890728528f9a44993eb0f0544f`, model/Adam/RNG restoration before environment and 64-row/nine-field control before gradients. Limits stay 7200/7140/7170, shared `min(previous,earliest_failure+10,T0+7210)`, .05/.15/max .5 sampling, separate 6GiB RSS/MPS and inner1.0/outer.25 reserves. The unused 7200-second training authorization remains parent-owned.

The evidence manifest excludes itself and the final completion receipt. Completion receipt anchors the evidence manifest and actual elapsed time with no back-edge. Source manifest pins pre-test code and fixtures; logs closed before evidence hashing. Source bytes remain frozen at handoff.
