# How we reached 2,704 frames

The practical recipe was more PPO training, smaller learning steps, and continuing from the strongest saved checkpoint. The verified starting milestone nearest “1,000” was 1,178 frames. Current retained performance is 2,704 frames: about 2.30 times longer, or a 130% gain, on the same 64 D2 development games. That is about 19.6 seconds of survival becoming 45.1 seconds.

| Retained milestone | Q1 alive frames | Q4 alive frames | Mean alive frames |
| --- | ---: | ---: | ---: |
| First accepted D2, 72 | 533.3125 | 2325.625 | 1178.0625 |
| 180 | 585.625 | 3502.5625 | 1854.46875 |
| 204 | 630.4375 | 3913.5625 | 1921.171875 |
| 276, LR 1e-4 | 566.75 | 5171.8125 | 2483.65625 |
| 300, LR 3e-5 | 808.875 | 5222.9375 | 2704.390625 |

Q1 and Q4 are the means of the bottom and top 16 games, ranked by survival.

## What helped

**More practice produced the early gains.** Continuing PPO training took the first accepted D2 policy from 1,178 to 1,854 frames. The network did not need a new architecture for this improvement.

**We stopped treating the latest checkpoint as the best checkpoint.** One continuation from 180 ended at only 1,604 frames. A separate branch from 180 produced the stronger 204 checkpoint at 1,921. Later runs also peaked before their endpoints. We retain the best fully audited candidate and restore its model, optimizer and random state together. Current300 survived longer than the later336 endpoint, so300 is the next parent. This preserves the best measured development result; individual updates can still regress.

**We reduced learning rate as the policy improved.** The branch using 1e-4 reached 2,484 frames, 29.3% above retained204. The 3e-5 branch reached 2,704, another8.9%. Smaller steps are a plausible way to refine a useful policy without disrupting it. The learning rate must be applied after restoring Adam, since an optimizer restore overwrites a config-only change. Each branch also used a fresh training seed, so these runs do not isolate the learning-rate effect.

**Run reliability and measurement improved.** Process, resource and cancellation fixes let experiments finish reliably. Survival quartiles, death causes and critic/gradient telemetry made results easier to interpret. These engineering changes enabled trustworthy experimentation; their direct effect on gameplay was not measured. We have not deployed gradient surgery, recurrence, or a gamma/lambda training change.

Training reward still includes score change, a small survival bonus and a death penalty. Removing score from the gate changed checkpoint acceptance, not the reward itself.

## Where we stand

All64 current evaluation games ended in death:26 normal enemies,16 static rectangles,15 kamikazes,6 moving rectangles and1 explosion. No episode hit its cap. Results describe the reused development cohort; held-out improvement and the3,060-frame competence gate remain unproven. The highest mean also does not guarantee that every lower-quartile game improves.

Sources: [Haiku report](../1000-to2700-progress-story-haiku-20261026-r1/report.md), [recomputed evidence](reconciliation.json), [current accepted candidate](../D2-retained276-lr3em5-parent-terminal-audit-20261026-r2/retained-best-candidate-receipt.json).
