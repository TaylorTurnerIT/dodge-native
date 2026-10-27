# Distinct r13 repair: first callback failure and current test scope

Taylor's authorized guard repair/test/review/one-held-D2 workflow continues. Work in `/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79`. Fresh output ONLY `learning/runs/v2/postovernight-long-D2-boundary-prepare-r13/`. Budget <=1,800 seconds including publication; exactly one fail-fast stdlib stage <=300 seconds. Stop first unexpected setup/test failure, retain partial evidence, no post-failure patch or retry. No nested delegation or provider calls.

Read the COMPLETE inherited brief `learning/runs/v2-orchestration/postovernight-long-D2-boundary-repair-r12-task.md`, full authoritative plan/spec and current ledger context. All protected contracts and output-only restrictions carry forward. This brief explicitly supersedes the test migration restrictions where stated below. No `/tmp` files, project/runtime/historical/source/ledger/docs/external-protocol/lease/cache edits, OS/stress/startup/ML/native imports/checkpoint decoding/environment/inference/training, scheduler/commit/PR/deployment/messages. Use `learning/.venv/bin/python` alias, `-B`, fresh owned cache and explicit VALIDATION_DIR.

## Exact inputs and failures

Read and verify:

- `learning/runs/v2/postovernight-long-D2-boundary-prepare-r12/` complete source, source/input/evidence manifests, completion/implementation results, failed unit receipts, diff and PARENT-NEXT. Verify229source/215input/514evidence bindings as registered, with actual measured counts. Source is released and frozen; do not patch or rerun it.
- Parent `learning/runs/v2-orchestration/postovernight-long-D2-r12-parent-reconciliation.json` (latest authority for this failure).
- `learning/runs/v2/postovernight-long-D2-r12-chronology-proof-r1/` plan/script/raw result/wrapper/evidence. Actual frozen r12 Guard/ProcessLatch/observed_failure were used; fake clock and direct handler, not real OS signals. Exactly one command, raw0/.216784625s; no source edits or suite rerun.
- Original frozen r11 eight `parent-frozen-pins.json` bindings, accepted policy, r8 external protocol and exact Sonnet/probe parent authorities from inherited brief.

r12 registered134methods but stopped after21newmethods:20passed,1failed,113unrun including ALL112inherited methods. Its scanner incorrectly looked for setters in every original semantic-source Python file, including `python/tests/test_env.py:413/419`, which contains an intentionally setter-using GIL witness test helper. No competing runtime setter was proven. No runtime freeze, external protocol publication or training followed.

Parent also reproduced a production reporting regression:
`R12-CALLBACK-FAILURE-OVERWRITTEN-DURING-RESTORE` (P1). Callback failure at modeled100, then SIGTERM at101 while restoring interval. Without that signal, actual Guard/observed_failure retains resource_stop at100. With it, the later cancelled error is latched at101 and the original callback survives only in exception context. This violates the preserved primary chronology contract. A new candidate must fix both the scanner and this source bug.

## Production change

Keep r12's scoped100us helper, exact CPython quantization restoration, main-thread ownership, single interruption recovery, lower-existing-interval behavior and all bounds. Only additional semantic production change: within `Guard.full_check`, catch/latch an exception from `self.verify()` BEFORE unwinding interval cleanup. Retain its actual observation timestamp and failure object before later restoration signals/errors can replace them. Preserve original callback exception/traceback and any valid preexisting `first_failure_descriptor` when control returns to unchanged `observed_failure`/worker reporting. A later cleanup cancellation still remains latched and represented, and can never produce success. Do not let a newly built exception or cleanup catch time become an earlier callback's timestamp.

One small approach: retain the callback exception in a local, set sticky Guard failure/failure_at at the inner actual catch, and if a later helper cleanup exception masks it, re-raise the retained callback exception with the cleanup exception as its cause after recording the failed boundary. Evaluate this against the actual reporting path rather than copying mechanically. Preserve prior guard/cancel/alarm/peer precedence, original descriptor authority and the same FailurePool; no new clock origin, exception-construction timestamps, event bus, changed allowances, lifetime handler/timer/mask or ACK policy.

Keep `observed_failure`, `primary_error`, worker_failure, full worker ML body and all other existing controller functions and Guard methods byte-identical. Only the two scheduling helpers and Guard.full_check may differ semantically from r11, with the new Guard chronology fix relative to r12. `boundary_integrity.py`, lifecycle.py, processes.py, executor, freeze and all fixture/consumer/stress sources stay exact r11/r12. Report a blocker if a correct narrow fix cannot preserve these contracts.

Copy required sources/fixtures into new r13 with an exact `r12-source/` snapshot and retained r11/earlier snapshots. Do not copy failed attempts, old capsules/identities/classification/registration/leases/caches as current evidence. Mechanical constants change to r13 and future canonical protocol-r10. Derive `protocol-r10-proposal.json` from exact r12 `protocol-r9-proposal.json` SHA256 `22110a3cb52c36c86934ce02bb0b5c82e2041dc1a00e39a11bb80dd23697d115`, changing only candidate paths/timestamp and explicit first-callback-failure-before-restoration semantics beside existing scheduling declaration. Never publish externally. Parent owns accepted protocol publication, fresh acyclic identity/classification/capsule/registration and measured counts.

## Correct test ownership scan

Every original identity binding remains hashed and protected. Classify scanned paths explicitly as registered runtime source versus test/evidence source; include actual controller helpers and registered production `dodge_rl` package sources. The known `python/tests/test_env.py` setter belongs to test evidence, not the launched production import closure. Do not exclude all inconvenient paths by a blanket substring or claim whole-program/third-party absence. Retain its exact hash and report its setters separately. Test that an injected setter in a runtime-classified source is rejected, while a setter in a test-classified source is reported without being a competing runtime setter. Validate classification coverage and no arbitrary omissions. Main-thread ownership remains operational cooperation, not enforcement against hostile setters.

## Explicit migration of four inherited static tests

The r12 runner planned four old methods against r11 with patched H and controller constants. Parent DOES NOT accept that as current-candidate regression evidence. Remove historical-target runner rebinding. Run current-candidate tests directly with current constants.

The following four names may have their static source/protocol expectations migrated to the authorized scheduling/chronology/candidate delta:

1. `test_r11.R11.test_C01_exact_success_consumers_transport_inner_fixtures_and_old91`
2. `test_r11.R11.test_C02_protocol_only_candidate_paths_and_qualified_semantics`
3. `test_r10.R10.test_exact_r9_transport_success_consumers_protected_blocks`
4. `test_r7.R7.test_success_consumers_and_protected_failure_helpers_byte_equal`

Preserve their method names and every still-applicable protected consumer/fixture/learner/worker/IPC/lifecycle/source-union assertion. Replace only now-false equality/protocol assumptions with explicit current scheduling delta checks. Keep the other108inherited methods byte-identical, including assertion and success-consumer bytes. Retain all old test sources in exact snapshots and publish complete diffs. No weakening, skips, xfails, mocks/rebinding of production constants or execution against historical H to manufacture a current pass. Historical fixture inputs remain permitted where the original test explicitly uses them.

Provide a strict byte projection/delta check of the ENTIRE current controller against exact r11: remove only the explicit new helper/constant/mechanical lines and transform the exact authorized full_check wrapper/early-catch/propagation additions. No blanket exclusion or AST normalization of the Guard, full_check or other protected bodies. Independent review must see the full allowed transformation. Protocol checks must bind current proposal bytes/config/seed/D1 and explicitly account for allowed r8->r9->r10 changes without replacing the tested current target with historical source.

## One fresh fail-fast stdlib stage

Write all tests before registration. Freeze source and commands, then run once <=300seconds. Include all112current inherited methods (four explicitly migrated) and r12 scheduling cases adapted to current candidate plus meaningful new chronology/scanner controls. No r12 result transfers. Record current versus historical fixture evidence precisely.

New chronology regressions must exercise actual Guard and unchanged observed_failure/FailurePool selection: callback failure at100 then restore cancellation at101 keeps source100 and cleanup deadline110, not111; plain Stop and non-Stop BaseException; callback carrying an earlier valid descriptor retains it; earlier cancel/alarm/guard/peer still wins; cleanup-only failure stays fatal; restored interval exact; no duplicate callback; later cancellation is still recorded. Keep a source-intact r12 negative control demonstrating the original bug where feasible in the same single suite, without rerunning its134-method stage. Model signals explicitly; no OS-signal claim.

Preserve meaningful success/failure/quantization/nesting/nonmain/reader/only-callback-scope coverage. Update the old callback-plus-cleanup test to assert correct primary chronology through actual Guard/reporting, rather than merely retaining original in exception context. Scanner negatives and exact current byte/protocol checks must accompany the migration. Audit inherited tests as text before launch so known hardcoded mismatches are addressed explicitly before the single stage; no exploratory test retries.

## Handoff and unchanged limits

Produce exact input/source/base/evidence manifests, complete diffs, source-equality report, one raw command/exit/wall and per-test executed/unrun results, json.tool validation, actual elapsed time, implementation-result and PARENT-NEXT. Preserve every setup failure. Release ownership and freeze source bytes at handoff. No production freeze or subsequent gate launch here.

Unchanged experiment config `2ac814d3842228017d09669364a8391344722da56ad19f41ad9030dbb930c2db`, seed5562873868232098305, D1 `ce9c03c8d476f58d5edec9f95946fa808d1d65890728528f9a44993eb0f0544f`; restore model/Adam/RNG before environment and64row/ninefield control before gradients. Full B/R/A endpoints and all forced activeB/genuine legacy/origin/runtime/cache checks stay. No cache/cadence skips/background verifier/fixed5s watchdog. Original10091/9870/9675 bindings and operational finite-observation limits stay. No student/D3/B/E/failed-weight resume/fallback/retry.

7200/7140/7170seconds; shared `min(previous,earliest_failure+10,T0+7210)`; .05/.15/max.5 resource/lease; separate observed6GiBRSS/MPS; inner1.0/outer.25 internal reserves; exact raw/exitwall/direct-parent waits/positiveabsence/mandatorysummary acceptance; transport unknown and unchanged. One7,200-second training authorization remains unused and parent-held behind passing relevant tests/review/runtime gates.
