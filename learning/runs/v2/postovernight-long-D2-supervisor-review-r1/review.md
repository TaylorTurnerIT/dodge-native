# Frozen long-D2 supervisor review

**Verdict: changes required. Two blocking findings: SUP-001 (P1) and SUP-002 (P2). This candidate is not accepted for launch.**

This is an independent, read-only review of supervisor authority, guards, finalization, freeze construction, and synthetic evidence. It is not an actual learner/API runtime acceptance. The separate learner/API reviewer owns that integration audit. No production source, capsule, protocol, configuration, checkpoint metadata, state, or documentation was edited. All review writes are in this new directory. Synthetic state files below this directory are fixtures, not production leases.

## Frozen identity

- Controller `long_d2.py`: `62ece46ba9a59d3c116013580ce29875aa76eaceed59eb56480a804649c8ffca`.
- Raw identity document: `f163c3e0d76ed9d839d8f9838840f6427c0e8ad379b24da6efc585f7f6e51ab4`.
- Capsule manifest: `6284b4389b1fdd1eadbd3f7d1c9104831a49af9482b78e21d84e1b19cb89227e`.
- Registered protocol: `119e3daba7c8112f4a7a30d467f57ed9d4cd6fb3b14da4252a60e45722e8039b`.
- Registered configuration: `2ac814d3842228017d09669364a8391344722da56ad19f41ad9030dbb930c2db`.
- Canonical semantic identity: `5a64550c7103d23c371f0677b5739990602c08b3a95bc93368eec5f13d9301cb`.

The 362 preparation artifact entries, 188 capsule file entries, 883 protected input files, 105 original input pins, and 75 historical source pins matched. These counts overlap; they are not additive. The identity covers exactly 82 helper/test/historical Python source files. The three final positive source snapshots match the current controller, tests, and fake worker. The full raw input inventory is [input-sha256-manifest.json](input-sha256-manifest.json): 1,259 distinct files, all unchanged at the final comparison.

## SUP-001 — P1, blocking: authority and input checking stop before terminal publication

Source: `learning/runs/v2/postovernight-long-D2-prepare-r1/long_d2.py:1073-1080`, `:1094-1108`, and `:924-992`; especially `:937-939`, whose publication check tests only the clock.

`supervise` closes its Guard, then checks the lease and input pins once. It subsequently hashes output artifacts and publishes the manifest and authoritative receipt without another lease or input check. The worker is already reaped, so its guard cannot detect a new parent cancellation either. Publication may consume the remaining supervisor reserve. The required lease interval of at most 0.5 seconds therefore ends before normal publication ends.

Reproduction used the actual `supervise`, actual `Guard`, and an actual new-session stdlib OS worker. At the first output artifact hash, after final input verification and guard shutdown, the fixture wrote `cancel_requested=true` to its own synthetic state file and delayed hashing by 0.65 seconds. The controller returned **2**, with a **complete** terminal receipt and available, correctly bound manifest. A gate-pass variant returned **0** under the same late cancellation (that variant uses the existing synthetic guard fixture). An additional actual-Guard case changed a pinned synthetic input after final verification; it also returned **2** with complete receipts. The latter shows the same finalization blind interval for frozen input identity.

Evidence:

- [Actual-Guard cancellation observation](late-lease-cancel-real-guard/observation.json) and [ordered events](late-lease-cancel-real-guard/events.json).
- [Gate-pass cancellation observation](late-lease-cancel-pass/observation.json).
- [Actual-Guard changed-input observation](late-input-change-real-guard/observation.json).
- [Contract assertion failures](independent-contract-assertions.log), first three failing methods.

Expected: failure exit 1 after authority loss; no complete terminal receipt may survive. Keep lease and input validation effective through normal publication, including a final check before completion becomes authoritative. Preserve the existing deadline and writer-stability rules. This review makes no implementation changes.

The live fixture is [probes.py](probes.py). From the repository root, use `PYTHONDONTWRITEBYTECODE=1`, set `TMPDIR` to this review directory's `tmp`, and run `learning/.venv/bin/python -B learning/runs/v2/postovernight-long-D2-supervisor-review-r1/probes.py late-lease-cancel-fresh-real-guard`. It uses a new owned scenario directory and refuses overwrite. To replay only the retained evidence assertions, run `learning/.venv/bin/python -B learning/runs/v2/postovernight-long-D2-supervisor-review-r1/test_recorded_contract.py`; its four finding assertions intentionally fail.

## SUP-002 — P2, blocking: SIGTERM is unhandled at outer publication-context exit

Source: `long_d2.py:960-992`, `:1088-1097`, and `:1097-1108`; handler restoration is at `:418-420`.

The first supervisor cancellation context ends before publication. `publish_terminal` installs its own context, then restores the old handlers before returning. Consequently, when the enclosing publication `absolute_alarm` context exits, SIGTERM has already reverted to `SIG_DFL`. The surrounding `except BaseException` cannot catch an OS default termination. This violates the explicit requirement to latch SIGINT/SIGTERM through the outer context.

An independent subprocess ran the actual supervisor and a real owned OS worker. The fixture delivered real SIGTERM at outer publication-alarm context exit, after the inner publication had completed. The retained event records handler **0** (`SIG_DFL`). The supervisor process exited **-15**. Its authoritative terminal receipt still said **complete / budget_closed_below_gate**, and `artifact-manifest.json` remained available. The owned worker had already been reaped and its group was positively absent. No signal was sent to a real campaign or another process group.

Evidence: [signal event](outer-alarm-SIGTERM/events.json), [retained terminal receipt](outer-alarm-SIGTERM/campaign/finalization-result.json), [process exit in probe summary](probe-summary.json), and the fourth failure in [contract assertions](independent-contract-assertions.log). The matching SIGINT probe returned failure and removed the manifest; it does not establish SIGTERM coverage.

The outer executor's required raw exit-code check would reject -15. This finding does **not** claim a compliant parent would accept the run. The defect is the missing cancellation latch and surviving complete authoritative artifacts at a specifically required boundary. Keep one cancellation envelope active through publication and outer-context restoration, and invalidate completion when cancellation is observed there.

For a fresh isolated reproduction, use the same fixture command with scenario `outer-alarm-fresh-SIGTERM`. That command intentionally terminates only its own synthetic supervisor after the owned fake worker has been reaped. The existing retained reproduction needs no rerun.

## Results within the reviewed scope

All six active preparation sources were read: `long_d2.py` (1,139 lines), `test_long_d2.py` (750), `fake_worker.py` (28), `freeze.py` (124), `finalize_preparation.py` (102), and `negative_controls.py` (79). The 82-file source inventory includes historical snapshots and deliberate mutants; those were verified by hashes, inventory equality, and exact declared mutation reconstruction rather than being treated as active runtime modules. The registered protocol/config, proposal, Opus design and plan, parent reconciliation, API audit, implementation/test/negative-control receipts, README, invocation, required lease, implementation plan v2, and corrected specification were inspected. The corrected v2 score-and-survival direction governs this review.

The following source checks and synthetic probes support narrower positive conclusions:

- T0 precedes ordinary imports and worker spawn. Worker and normal publication deadlines are 7,140 and 7,200 seconds. Failure cleanup cannot restore complete status after a detected deadline failure. The independent alarm bounds a blocked worker; actual ML/native blocking behavior was not exercised.
- The strict 15-field lease rejects missing/unknown fields and changed nested D1 anchors. The original 75 source/runtime proof and unchanged old transition functions remain distinct from new authorization. Old 1,800-second and cutoff guards were not edited or bypassed.
- RSS and MPS are separate observed 6 GiB limits. Guard sampling/gap logic and latched failures are exercised synthetically. Their actual Torch/MPS behavior is unverified; SUP-001 limits the claimed finalization coverage.
- Entry evaluation is update 0, subsequent evaluation is at 16-update cadence, and periodic checkpoints occur at update 8 within each block. `U=max(25,1.25*max update wall)` includes periodic checkpoint time, `E=max(150,3*max evaluation wall)` grows only, `C=15`, and `F=30`. Admission uses the registered block, remaining-block, and pre-evaluation reserves. Slow closure produces `long_closure_unevaluated`, with no off-cadence evaluation or futility rule.
- Signals are blocked through `Popen` assignment. Reaped leader plus positively empty owned group is required before hashing. Unproven group absence prevents a manifest. Existing tests also run a real descendant cleanup case.
- Late final verification and artifact hashing were independently delayed against a shortened synthetic absolute budget: both failed and removed the manifest. Existing finalization tests additionally delay run-result, manifest, and terminal writes. Deferred cleanup/final-verification SIGINT and SIGTERM were counted and returned failure. SUP-002 identifies the uncovered outer boundary.
- Normal clean closure returns 2; gate pass returns 0; failure returns 1. Successful terminal receipts bind both the manifest and run-result bytes. Wall receipts explicitly exclude their own write and process exit; the parent must measure actual wall and raw exit.
- Freeze construction avoids a hash cycle: identity excludes its own document hash and capsule manifest; the manifest includes the identity and excludes itself. Raw document hashes remain distinct from checkpoint semantic identity. Loaded `dodge_rl` origins and original/mirror bytes are checked before parent deserialization in the source path. No actual parent deserialization or module-origin runtime acceptance occurred here.

## Executed evidence and limits

[execution-receipt.json](execution-receipt.json) records the commands' result categories. The candidate's current 70 synthetic test methods passed in 6.143 seconds. That is fresh evidence, not transferred historical test counts. Twelve independent OS-supervisor scenarios were retained. Eight additional assertions against those retained runs produced four passes for repaired boundaries and **four assertion failures** demonstrating the two findings; no API/import errors caused them.

All 14 retained r4 negative controls were inspected: exact declared source replacements, matching log hashes, real `AssertionError` failures, and no API/import errors. The three controls for late hashing, unstable manifests, and deferred cancellation were rerun into this directory. All three were killed by assertions, not import/API failures. All attempts, expected failures, synthetic outputs, and the deliberately SIGTERM-terminated subprocess evidence remain available. [owned-groups-after.json](owned-groups-after.json) positively confirms absence of all 12 retained owned groups.

Pure stdlib capsule preflight also passed into [pure-preflight.json](pure-preflight.json). No Torch/native/project runtime import, parent tensor deserialization, inference, gameplay, training, gradients, lease activation, scheduler change, provider retry, child delegation, external message, or production launch occurred. Synthetic probes use owned fake workers and state under this directory only. No result here proves actual learner API integration, entry determinism, MPS throughput/memory behavior, teacher qualification, or a training gate pass. There is no authorization or opening for D3/B/E/student work in this review.
