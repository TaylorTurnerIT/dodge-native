# From about 1,000 to 2,704 frames: how the D2 agent improved

## Short answer

The agent now survives about 2.3 times longer on the fixed development games than the first accepted D2 checkpoint did. Most of the gain came from two process choices, not new model ideas. We kept the best complete checkpoint and continued from it instead of from the newest endpoint, and we lowered the learning rate in small steps. Real, bounded, auditable runs also became possible only after several lifecycle and resource bugs were fixed. The result is still a development result. It uses one fixed set of 64 games, the agent dies in all 64, and it is well below the 3,060-frame competence threshold.

## What we have been doing

We train a PPO agent on difficulty D2, with movement patterns and power-ups on. The goal is to survive longer. The training reward still includes score, so it is `score change + 0.01 per alive frame - 5 on death`, scaled by 0.1 for PPO. Score was removed from the progression gate only. We measure survival as alive frames on 64 fixed seeds using deterministic argmax actions. The reported Q1 and Q4 are the means of the bottom and top 16 games, ranked by alive frames.

## Milestones

The closest exact comparable start is 1,178 frames, not 1,000. The lineage started at 295 frames, and the first accepted D2 run reached 1,178 after 72 updates. The 1,000 figure is a nominal level, so we compute gains from the exact values.

| Milestone | Mean frames | Q1 | Q4 | Status |
| --- | ---: | ---: | ---: | --- |
| D2 entry (update 0) | 295.25 | 165.44 | 566.38 | Start of first accepted D2 run |
| First accepted D2 run, update 72 | 1,178.06 | 533.31 | 2,325.63 | Nearest to "1,000" |
| Best at the time, update 180 | 1,854.47 | 585.63 | 3,502.56 | Retained |
| Update 252, from 180 | 1,604.08 | 532.81 | 3,192.31 | Regressed, not a parent |
| Retained 204 | 1,921.17 | 630.44 | 3,913.56 | Lower LR branch parent |
| Retained 276 (LR 1e-4) | 2,483.66 | 566.75 | 5,171.81 | Retained |
| Endpoint 348 (LR 1e-4) | 2,273.17 | 861.25 | 4,004.88 | Not retained |
| Current accepted 300 (LR 3e-5) | 2,704.39 | 808.88 | 5,222.94 | Current parent |

The current checkpoint is 300 from the LR 3e-5 ablation, with checkpoint hash `e2c8fbe4…4710`. Its 64 deaths were 26 normal enemies, 16 static rectangles, 15 kamikazes, 6 moving rectangles and 1 explosion. There were no caps. Relative to the 1,178 exact comparable, 2,704 is +130%. Relative to the 295 entry, it is about 9.2 times higher.

## What improved us

**Choosing the parent.** A later checkpoint is not always better. Continuing from 180 produced 252, which fell 13.5%. The 204 checkpoint from the same run was better, and we kept it. Later, the 348 endpoint fell 8.5% below 276. Continuing from the best complete checkpoint, with its optimizer state and random state restored together, kept the retained mean from falling. This makes the retained development mean monotonic by selection. It does not make each PPO update better.

**Lower learning rate.** The 3e-4 to 1e-4 branch from 204 raised the mean 29.3% to 2,484. The 1e-4 to 3e-5 ablation from exact 276 raised it another 8.9% to 2,704. Restoring an optimizer state overwrites a config-only learning-rate change, so the rate had to be set explicitly after the restore. This is a reasonable but confounded signal. Each branch used a new training seed and was chosen from many candidates on the same 64 games. The 1e-4 branch also lowered Q1 from 630 to 567, so the gains are not uniform.

**Working experiments.** Early runs failed on lifecycle, resource and interprocess bugs. One M3 attempt hit its 1,800-second guard. Fixing these let us finish bounded runs and audit them. That made the later comparisons trustworthy, but the fixes did not themselves make the policy better.

**Better diagnosis.** Death-cause logs and critic and gradient telemetry clarified what was limiting the agent. Current deaths are spread across several hazards. The critic-to-actor gradient norm ratio averages about 0.019, and the combined update vector rotates about 1.09 degrees on average (1.97 at most). This weakens the interference hypothesis but does not prove the critic is accurate. Explained variance uses self-bootstrapped targets and is not a policy-quality score.

**Credit timing checked.** A research pass corrected two earlier claims: a decision lasts 4/60 s (66.7 ms), not 0.25 s, and resume uses saved episode indices. No GAE or reset bug was found. No PCGrad, recurrent model, gamma or lambda change, or new architecture is in use.

## What regressions taught us

Endpoints fell in three of four continuations. Update 252 fell 13.5%, endpoint 336 fell 9.6% from 300, and endpoint 348 fell 8.5% from 276. Individual endpoints are noisy. The useful unit is the audited best checkpoint, and longer training does not reliably help.

## Uncertainty

- Each milestone is one run. The LR changes came with new training seeds, so the LR effect is mixed with seed and selection effects.
- All development means come from one 64-game deterministic cohort. There is no held-out, generalization, D3 or student claim.
- The 3,060-frame competence threshold is not met.
- Some receipts label phases and cumulative counters differently. This report uses the recorded phase labels.
- The historical 2,240-frame best after 320 updates was not verified in this pass.
- The failed M3 run hit 1,149 frames at phase 96, but it is ineligible.

## Key artifacts

- [D2 training summary](../../../../docs/v2-D2-training-2026-10-25.md)
- [Implementation plan](../../../../docs/implementation-plan-v2.md)
- [Current retained receipt](../D2-retained276-lr3em5-parent-terminal-audit-20261026-r2/retained-best-candidate-receipt.json)
- [Retained 276 terminal receipt](../D2-retained204-lr1e4-parent-terminal-audit-20261026-r1/parent-terminal-receipt.json)
- [Plateau reconciliation](../D2-plateau-parent-reconciliation-20261026-r1/reconciliation.json)
- [Temporal credit reconciliation](../PPO-temporal-credit-parent-reconciliation-20261026-r1/reconciliation.json)
- Machine-readable evidence with hashes: [evidence.json](evidence.json)
