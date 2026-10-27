# Review: D2 retained324 parent closeout

Reviewer: haiku-r1 (read-only). Scope: `learning/runs/v2/D2-retained300-parent-terminal-audit-20261026-r1/` plus the upstream evidence it cites. Method: stdlib hashing and JSON reads (`verify_receipts.py`, `python3 -I`). No runtime, checkpoint, or torch imports; `finalize_parent.py` not run; no training, lease, or ledger edits.

## Verdict

No blocking findings. All 64 input/output hashes match the values the closeout records. All 177 checks pass: hashes, cohort, selection, counters, cost and clock arithmetic, receipt linkage, authority flags, process absence, and the ledger diff. Authority is unchanged: the selected324 receipt grants continuation only. It does not grant acceptance, promotion, competence, or qualification.

## Verified

- **Hashes.** Registration `8a60dc80…`, full audit `e991bfd0…`, observer `036688f1…`, parent terminal receipt `ccc73fbc…`, parent checkpoint 300 `e2c8fbe4…`, selected checkpoint 324 `c10d90ec…`, sidecar `cedb2070…`, certificate `73f9ee72…`, JSONL `8777375…`, completed receipt `7c6f250b…`, retained receipt `76cb1573…`, audit `bc49fe9d…`, and state before clear `4d034282…` (equals the observer postflight state hash). All match. The six candidates' cert/JSONL/checkpoint/sidecar hashes match the full audit.
- **Cohort and performance.** Each of the six candidates has 64 unique episode indices and seeds, all terminated, with identical seed sets across candidates. Recomputed mean, Q1 and Q4 for every candidate match the full audit. For 324: deaths 35 normal, 14 static, 9 kamikaze, 3 moving, 3 explosion (sum 64); sum alive 188122; raw frames 188186 = sum(gameplay) = sum(alive)+64.
- **Selection.** 324 is the highest mean (2939.40625). The previous best was 2704.390625, so the gain is +8.69%. Q1 767.5 is below the old 808.875, as stated. Competence is false (below 3060).
- **Counters.** 16384 decisions and 128 optimizer steps per update. Local 24 and cumulative 372 for the selected checkpoint; local 60 and cumulative 408 for completed. Inherited 348 plus 24 = 372, and plus 60 = 408. Phase offset is 48. All sums match.
- **Clocks and cost.** Outer monotonic delta = 1137.0270813 s. Cost after = 8621.338345875141 + 1137.027… = 9758.365427209174. Future baseline = 5190.209660791156 + 488.7727023329353 = 5678.9823631240915. Discarded-branch highwater = 5190.2097 + 1137.0271 = 6327.2367. Caps: outer ≤ 1800 and worker ≤ 1790 both pass; RSS and MPS peaks are under 6442450944.
- **Observer.** One launch. Raw exits 0/0. `success_authoritative` true. Pins 13827 checked, none failed. `ps` for pids 26658, 26659 and 26662 returns rc 1 with no output (absent now).
- **Authority.** Retained receipt: `training_continuation_eligible` true, `stage_promotion_eligible` false. Completed receipt: `training_continuation_eligible` false. Original executor status is still `failed`, with `provider_failure` recorded. Actual campaign outcome is recorded separately.
- **Ledger diff.** Changes are limited to the lease clear, the monitor task, the performance and receipt pointers, and the next actions. The executor task keeps its status.

## Findings

Severity is low or info. None blocks the closeout. Each is a naming, accounting, or evidence-limit note.

1. **low: ambiguous parent-hash key in retained receipt.** `retained-best-candidate-receipt.json:128` `parent_checkpoint_sha256` = `e2c8…`, the producing-run parent. Line 31 `continuation_parent_checkpoint_sha256` = `c10d…`, the selected resume point. Line 19 `candidate_parent_checkpoint_sha256` also = `e2c8…`. A consumer that binds the next continuation on the generic `parent_checkpoint_sha256` would resume from the wrong ancestor. Written by `finalize_parent.py:169`. The prior naming note is addressed by the explicit key, and the brief says not to demand metadata edits, so this is a residual note only.

2. **low: hardcoded provenance flags.** `finalize_parent.py:136`, `:144`, and `:160` write `resource_limits_passed`, `checkpoint_metadata_unchanged`, and `stage_promotion_eligible` as literal `True`/`False`. They are not computed from checks in the script. The `need()` guards above them do cover the limits, and the full audit's per-candidate sidecar hash supports the metadata claim. The claim is therefore supported by other evidence, but the script's own flag is not a check.

3. **low: two cost figures.** The receipt uses observer outer 1137.0271 s, giving cost 9758.365 s (`retained-best-candidate-receipt.json:171`). The worker reports cumulative 9754.963 s from `current_iteration_observed_outer_seconds` = 1133.6248 s (`worker-result.json`). The difference is 3.40 s. The outer figure is the chosen basis, and the receipt does not cite the worker figure. Budget accounting should use one basis. Outer is the one stated in the authority text, so this is a note.

4. **info: UTC span exceeds monotonic.** Outer UTC span is 17:18:17.551 to 18:02:48.936, which is 2671.39 s. The monotonic outer duration is 1137.03 s. The 1534 s gap is not explained by any artifact. The `UTC_annotation` says monotonic governs, which matches the stated policy. If a system suspend occurred, monotonic clocks on macOS do not count it. Evidence of suspension is not recorded here. The gap should be noted in the limits. It does not change the policy result.

5. **info: stale acceptance text on the executor task.** `state-after-lease-clear.json:6234` still reads `acceptance: agent_transport_failure_only;actual_campaign_remains_running;no_relaunch`. Its `actual_outcome` field says the campaign completed. This is historical wording, and the status `failed` is preserved correctly. No action needed.

6. **info: sidecar still provisional.** `checkpoint-000324-candidate.pt.json` says `eligibility_status: provisional_pending_parent_terminal_receipt` and `training_eligible: false`. This matches the stated design, in which the external receipt grants continuation. Any reader of the sidecar alone must check the receipt.

## Limits

- The 13827 registration pins were counted, and the observer postflight checked them. I did not re-hash them all.
- Checkpoints were not loaded. The selected mean and death counts come from the certificate rows, not from re-running evaluation. Learner fingerprints and inherited counters are taken from the receipts and are not independently recomputed.
- `finalize_parent.py` was read but not run.
- The original executor's provider failure is documented in the ledger only. No independent transport log was read.
- The next324 continuation prep was not read, per the brief.
- Process absence was checked at review time. It is not evidence of the state at the moment of finalize, which the observer's postflight already covers.
