# Milestone 0 results: original engine, difficulty 2

The registered campaign completed and its independent [receipt audit](../learning/runs/v2/milestone0-audit-tool/full-audit-r3.json) passed. It ran 1,000 fresh episodes per policy with paired seeds `0xB0000000..0xB00003E7`, difficulty 2, patterns and powerups enabled, theme 12/1, K=4, and an 18,000-raw-gameplay-frame cap. Startup used 13 frames, excluded from gameplay and survival.

## Score and survival

Scores are raw numeric game score, before display rounding. Survival counts only alive raw frames at 60 Hz.

| Policy | Score mean | Score median | Score p90 | Survival mean, frames | Survival median, frames | Survival p90, frames | Capped episodes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Random | 0.353 | 0 | 1 | 255.323 | 237.5 | 383 | 0/1,000 |
| Neutral | 0.340 | 0 | 1 | 187.861 | 187 | 190 | 0/1,000 |
| AABB safe-powerup heuristic | 100.1075 | 68.25 | 250 | 6,114.593 | 5,189 | 13,132 | 15/1,000 |

The heuristic's mean survival is 101.909883 seconds. Its maximum observed score is 475.5; 985 episodes ended in death and 15 reached the cap. Those 1.5% are censored observations. The cap and seeds were not changed or retried. Display score and stored highscore are recorded separately: their heuristic means are 100.34 and 93.954. A live capped game may never save a highscore, and pickups after a lethal collision can make final score differ from the stored value.

## Capacity decision

The campaign sampled maxima of 15 enemy-family records and 16 active pattern rectangles, with zero observed overflow above the proposed 64/16 caps. The heuristic encountered all 39 catalog entries across 2,700,835 active-pattern frames. Counts include all native active records, including hidden control geometry; the eventual model applies its own admission rule.

Retain the supplied initial capacities: 64 enemy-family slots plus 16 rectangle slots, giving 81 teacher tokens with the global/player token. The enemy buffer keeps headroom above this measurement. Preserve deterministic enemy overflow selection and a hard rectangle-overflow error. Post-call samples and this difficulty-2 campaign do not prove all future trajectories fit.

## Original-engine throughput and resources

The separate ten-second release benchmark ran nonoverlapping single-thread and four-thread phases with fresh short random episodes, stopping at death or 2,000 gameplay frames. Original full `advance_frame` wall throughput was:

- One thread: 216,738 gameplay frames in 5.000061 seconds, **43,347 frames/s**.
- Four threads: 689,268 gameplay frames in about 4.99054 seconds, **138,115 frames/s**.

Wall rates include startup and thread lifecycle. Summed worker simulation time is a separate metric. These measurements do not establish mature-pattern, vectorized, or PPO throughput. They are distinct from the modified-core M1 headless microbenchmark.

The supervisor observed peak native RSS of 6,553,600 bytes for profiling and 6,029,312 bytes for the baseline campaign. Profiling took 11.13 supervisor wall seconds; the 3,000-episode campaign took 175.06 seconds. Sampling is cooperative and is not a hard memory-ceiling proof.

## Evidence and corrections

Original engine HEAD is `d7ad95127ad7529c5217a51ae9dc5cfedd3f2365`; all 33 tracked files remained unchanged. Release executable SHA256 is `922485d26128dbdc4df0868a5df7d7e72bc8f4135addfd691a1e11484d785d39`. The audit verified source/executable identity, all 3,000 episode records, paired seeds and configuration, score/alive/death/cap accounting, independent recomputation of distributions, aggregate counts, profile rates, and resource samples. Parent rechecked all 40 artifact hashes retained by the audit.

Native results remain in the isolated worktree and have an unmodified [parent mirror](../learning/runs/v2/milestone0-campaign-r2/native-results/copy-manifest.json), including the source archive and executable. [Supervisor receipts](../learning/runs/v2/milestone0-campaign-r2/supervisor.json) retain commands, timestamps, process IDs, and resource limits. The auditor source SHA256 is `4c8b9c93cd4ffdacdf1a28d70888db020dd77967d49c8aa6b81f3bd995c6291f`.

Two failed checker assumptions were corrected without rerunning any native experiment. One frozen review capsule omitted `.cargo/config.toml`; the auditor verifies it directly against pinned HEAD alongside all original tracked files. It also initially expected exactly one Death event. Native collision iteration can call `die()` repeatedly on one frame: observed Death-event multiplicities were `{0:15, 1:2685, 2:13, 3:287}`. Exactly 2,985 terminal events correspond to the 2,985 terminated episodes. The shaped death penalty applies once per terminated episode, regardless of repeated Death events. Failed checker logs and outputs remain in the audit-tool directory.

Free OpenCode reviews could not return a verdict because the provider reported its free usage limit. Exact blocked tasks were cancelled and errors preserved. Independent Codex audits found no blocking source defects before this campaign. The missing completed free-model verdict remains a review limitation; it is not represented as a pass.

Difficulty-3 gate baselines and difficulty-1 curriculum sanity are still pending. No v2 teacher has trained or passed a score/survival gate. M2 core observation metadata and geometry/raster primitives are now separate implementation tasks; their validation must use their changed source.
