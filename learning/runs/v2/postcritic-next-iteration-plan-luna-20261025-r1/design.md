# Next bounded PPO iteration design

## Recommendation

Prepare one fresh, eligible D2 PPO campaign from the accepted D1 checkpoint, capped at 48 updates. Evaluate at updates 0, 24, and 48. Keep all learner settings and reward unchanged. Do not import diagnostic checkpoints or failed D2 weights.

This best serves the requested goal of more teacher training. All 48 same-batch critic fits improved after optimization: mean EV rose from 0.6098003 to 0.7033030, and residual MSE fell from 0.0273812 to 0.0196050. This gives no basis for changing PPO settings or treating EV as the success metric. Fresh diagnostic-cohort survival improved across its three evaluations, but remained below the D2 gate.

## Named-cohort results

| Cohort | Update | Survival Q1 | Survival Q4 | Survival mean |
|---|---:|---:|---:|---:|
| critic-diagnostic-D2-20261025-r2 | 0 | 165.4375 | 566.375 | 295.25 |
| critic-diagnostic-D2-20261025-r2 | 24 | 490.3125 | 1,648.0625 | 886.609375 |
| critic-diagnostic-D2-20261025-r2 | 48 | 521.0625 | 2,401.1875 | 1,101.9375 |
| historical best development cohort, separate 384-update run | selected among 24 evaluations | 648.25 | 4,508.8125 | 2,240 |

Historical best is selection-biased development evidence from a different run. Do not use it to infer a duration effect. D2 requires mean survival at least 3,060 frames; the fresh diagnostic cohort did not pass.

The same-batch fit evidence supports unchanged learner settings. Window 9–16 had pre-update EV 0.6943, target variance 0.06736, residual variance 0.02013. Window 41–48 had EV 0.5620, target variance 0.06284, residual variance 0.02747. These early windows show both target variance and residual variance changed. They do not identify causality, support an arbitrary EV cutoff, or explain the historical late-384-update decline.

## Budget and execution boundary

Register one campaign only: maximum 48 updates, one inclusive 1,800-second wall budget, with 1,500 seconds for work and 300 seconds reserved for finalization and parent audit. The accepted diagnostic used 796.99 seconds for 48 updates. The proposed work allowance is 1.88 times that observed full duration. It leaves headroom without promising completion. Stop at a completed update boundary when work time expires. No retries.

Apply separate 6 GiB cooperative RSS and sampled MPS limits. Preserve partial receipts on failure. Report that sampled resource limits cannot prove continuous unsampled peak usage. Parent must verify exact receipts, exit status, wall time, resources, hashes, and process absence before accepting terminal evidence.

## Required prospective migration

Current v3 policy removes score from pass/fail, while the frozen original D2 runner remains bound to v2 and the v3 document marks runner migration pending. Before training, make a narrow prospective migration of the runner gate and identity/config binding to `teacher_qualification_v3_survival_only`. Keep historical v2 source, receipts, failed-run metadata, and identity checks intact. Add focused tests, freeze exact inputs, and obtain independent review.

Then register a fresh D2 run from the exact accepted D1 checkpoint. Keep D2 learner parameters, architecture, reward, source/native/runtime identity and memory limits unchanged. Allow only protocol-listed phase, difficulty, pattern, seed, evaluation cap, and phase-derived budget changes. Use a new valid D2 training seed. The accepted D1 remains the sole parent; no replay from diagnostic D2 weights.

Use existing trainer and supervision machinery after v3 migration. Avoid a general-purpose new runner. Add only a small prospective adapter if existing machinery cannot express the corrected v3 contract. Never flip diagnostic eligibility or edit prior run metadata.

## Gates and evidence

Prelaunch requires accepted D1 parent revalidation, exact v3 policy pins, a new unique run registration and empty output, no conflicting lease, independent source review, parent pin audit, and complete cooperative limits. During the run, retain finite-loss, reward-accounting, and nonzero actor/critic-gradient checks. Report survival Q1/Q4/mean on each completed evaluation; score remains diagnostic only. Record death counts when measured.

Only a complete validated D2 evaluation from the final checkpoint with mean survival at least 3,060 passes D2 development progress. Otherwise retain evidence and stop without retry, promotion, D3, B/E, or student qualification.

## Authorization and evidence boundary

Existing user direction authorizes preparation and blocker repair. This request says design only, so it does not authorize this new training campaign. This plan also grants no execution authority. A later explicit go is needed after the v3 migration, registration, and review are ready.

No checkpoint decode/import, model or native execution, inference, training, or source edits occurred for this design. Diagnostic checkpoints remain training-ineligible.
