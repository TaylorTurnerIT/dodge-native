# Independent r3 evidence/API audit

Changes required: one confirmed launch blocker, WORKER-ACK-001 (P1). This audit verifies retained evidence and selected static API/source relationships. It does not accept the supervisor or authorize a campaign.

## Missing ACK still permits failure persistence

At `long_d2.py:777-782`, `worker_failure` sets the learner deadline only after failure notification returns an acknowledgment. If notification or ACK validation raises, the first worker exception handler at lines 855-857 exits before updating the result. Its unconditional `finally` still sees the initial failed result and starts the emergency checkpoint at lines 860-864, then writes the checkpoint index at line 871. The learner deadline remains the normal 7,140-second bound.

The independent stdlib probe executes the original helper and except/finally AST, replacing only the guarded try body with an injected failure. It records an emergency checkpoint with no ACK and stale deadline 7,140, followed by index persistence. The corrected two-method contract test has one positive-control pass and one `AssertionError` failure, with no API/import errors. Fake callbacks record calls in memory; no real checkpoint or ML file is created. The first fixture attempt and its source/log remain retained.

The outer executor should reject worker failure/IPC loss; this audit does not show acceptance of a failed experiment. The defect is persistence before the required ACK/shared deadline. Add an explicit acknowledged-persistence gate and regression coverage of the actual worker exception/finally path.

## Verified evidence

- All 19,269 preparation artifact entries and 9,515 current immutable protected files match.
- All 9,675 full pins match, including the exact retained 793-pin r2 union and 75 legacy source/mirror inputs. The final read-only capsule has 141 files; the source inventory has 17 entries, including 15 root Python files.
- All 63 selected unit methods are unique in AST and match the final passing log. The 165 distinct full-lifecycle OS scenario rows match their per-case raw/wall/command records, expected return codes, reached injections, receipt outcomes and writer checks. These are separate denominators. One unit method also launches six latch subprocesses.
- All 329 recorded owned groups are currently absent in an independent process-table check. No non-child worker waitpid proof is invented.
- Fourteen protected learner/config/geometry/counter/control/validator source nodes are byte-identical to r2. The worker diff is supervision-only; the ACK ordering defect remains in that new path.
- Final matrix runtime sources match current bytes. Only the preparation finalizer changed after the matrix; the final unit receipt records that final source hash.

## Coverage and provenance boundaries

The OS matrix uses actual outer execution, actual Guard, real private directed IPC, `owned_handoff`, `worker_gate`, `supervise_owned`, artifact validation and finite process exits. It overrides capsule/identity fixture context and uses command factories pointing at `synthetic.py`. That worker invokes `fake_worker`, not the real `worker()` body. Consequently the full matrix never exercises the newly required failure-notification ACK and emergency persistence branch; the independent contract probe supplies the missing discriminating check.

The historical exact-r2 negative controls were inspected and rehashed; no r2 campaign or unexplained -14 probe was retried. One intermediate aggregate stdout log was overwritten and is unrecoverable. Its loss is disclosed; per-case evidence and source snapshots remain. This audit does not upgrade those records to a claim that every aggregate log survived.

No candidate module or ML package was imported, no actual checkpoint was deserialized, and no inference/gameplay/training ran. The separate supervisor review owns lifecycle race/resource/cleanup acceptance. Every audit write is confined to this new audit directory.
