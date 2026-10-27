# Independent failed long-D2 audit

The one-shot run failed after 1066.7562106660334 seconds, with outer return code 1 and raw wait status 256. The primary recorded guard failure was `Stop('Full input verification gap exceeded 5s')`. Its maximum full-input verification gap was 5.005385208001826 seconds against the unchanged 5-second bound. The worker's persisted `cancelled` outcome followed supervisor SIGTERM cleanup; the observer recorded no external cancellation, and the lease cancellation flag remained false.

The failure evidence is internally consistent: **True**. Failed audit checks: []. This is not a successful training verdict or continuation authority.

## Preserved training and evaluation evidence

There were 51 complete new PPO updates and 6528 new Adam steps, following 48 inherited updates and 6144 inherited Adam steps. The final counters report 99 total updates and 12672 total Adam steps. Complete new updates consumed 835584 decisions and 3335599 raw frames. The interrupted rollout added 13312 decisions and 53153 raw frames without an Adam step. Final new totals were 848896 decisions and 3388752 raw frames.

| New updates | Mean score | Mean alive frames | Deaths | Caps | Gate passed |
| --- | --- | --- | --- | --- | --- |
| 0 | 1.4765625 | 295.25 | 64 | 0 | false |
| 16 | 6.6796875 | 773.234375 | 64 | 0 | false |
| 32 | 5.0078125 | 615.234375 | 64 | 0 | false |
| 48 | 8.0859375 | 1093.03125 | 64 | 0 | false |

All four evaluations used the same 64 D2 development seeds and deterministic argmax actions. The fixed progression gate requires mean score 50 and mean alive frames 3060. No evaluation passed. Latest evaluated checkpoint was index 16 at phase update 48. Final checkpoint index 17 is a failure checkpoint at phase update 51, unevaluated and ineligible. Its `complete_update:true` metadata describes learner update state; the environment had consumed an additional partial rollout.

## Independent verification

The audit recomputed all development means and nine-field entry-control equality from JSON rows; all completed-episode rewards; fresh u32 training-seed tuple hashes, exclusions, and per-slot reset progression; full training raw-frame conservation; complete rollout and Adam-step accounting; checkpoint-byte hashes; evaluation cadence; schedule reserve formulas; resource maxima; observer manifests; campaign inventory; and all 9870 frozen pins. It checked exact read-only capsule inventory, source/mirror identity, and input hashes before and after this audit. No candidate code was imported.

The three owned process groups are currently positively absent. Outer and inner direct-child reap receipts exist. The worker wait receipt is null; group absence does not repair that evidence gap. Cleanup completed within the original ten-second failure window.

## Resources and limits

Worker sampled RSS maximum was 1001635840 bytes. Worker self-reported peak RSS was 1001701376 bytes. MPS driver allocation maximum was 2459009024 bytes. The largest resource sample gap was 0.2500741249532439 seconds. These observed memory values were below their separate registered caps. The input-observation gap gate failed.

- The first independent audit script stopped while reading an observer row without an owned field. Its exact script and stderr were retained. A corrected receipt-only audit used an empty owned list for that row; training was not retried.
- The run failed; this audit accepts only the internal consistency of preserved failure evidence. It does not accept a successful experiment, teacher qualification, or continuation authority.
- No ML or native modules were imported. Checkpoint bytes were hashed only; checkpoint contents, Adam/RNG/model restoration fingerprints, and update metadata were not independently deserialized.
- Positive process-group absence is not proof that the worker was directly reaped. The worker direct-child wait receipt is missing; the outer and inner direct-child reap receipts are present.
- No final campaign-owned manifest, finalization result, or long-run-result was produced. The observer inventory preserves 31 stable files after positive group absence.
- The four evaluations are deterministic development-seed evidence only. No B qualification, E replication, D3 evaluation, student work, or postrun inference was performed.
- The entry control and restoration receipts plus counters support entry-before-gradient ordering. schedule.jsonl has no timestamps; no independent per-event timing claim is made.
- Worker RSS sample maximum, worker self-reported peak RSS, and MPS driver maximum are separate quantities. Inner/outer on-disk resource receipts are absent; observer sampled maxima are bounded observations only.
- Finite filesystem sampling does not exclude transient mutation between reads or any later mutation. The current audit verifies all 9870 frozen pins, not every mutable parent ledger/state file.
- Earlier observer collector KeyError(monotonic) remains retained. Its read-only supplement repairs schedule interpretation without reexecuting training.
