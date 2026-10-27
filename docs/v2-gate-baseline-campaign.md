# Gate baselines and curriculum sanity, revision 1

This is a separate, registered campaign after the audited difficulty-2 Milestone 0 results. Matching difficulty-3 baselines are required before teacher qualification; the difficulty-1 check verifies the starting curriculum configuration. No teacher or student is trained by this campaign.

## Frozen implementation

Use the reviewed original engine and repaired M0 harness in `/Users/taylor/.t3/worktrees/dodge-native/t3-5d7162c0`, HEAD `d7ad95127ad7529c5217a51ae9dc5cfedd3f2365`. Recheck all original tracked files, the five harness/document hashes, and executable SHA256 `922485d26128dbdc4df0868a5df7d7e72bc8f4135addfd691a1e11484d785d39` before each run. Do not edit source or repeat profiling.

The difficulty-2 campaign took 175.06 seconds. A new 900-second cooperative native limit gives the difficulty-3 run a bounded budget without changing its episode cap or sample count. Failure retains partial receipts and stops the campaign; it does not authorize retries or a higher limit.

## Registered runs

Run the following sequentially, at most one long evaluation campaign at a time. Each uses random, neutral, and the same frozen AABB safe-powerup heuristic in that order, fresh native instances, K=4, theme 12/1, initially zero highscores, and verified 13-frame startup excluded from gameplay/survival. Seeds are paired `0xB0000000+i` within the run. They remain excluded from training. Death takes precedence over the raw-frame cap.

| Run | Episodes per policy | Difficulty | Patterns | Powerups | Raw gameplay cap | Native wall budget | Exclusive native output |
| --- | ---: | ---: | --- | --- | ---: | ---: | --- |
| Matching gate baseline | 1,000 | 3 | on | on | 18,000 | 900 s | `target/v2-gate-d3-r1` |
| Curriculum sanity | 100 | 1 | off | on | 2,000 | 120 s | `target/v2-curriculum-d1-r1` |

These are separate identities from the original D2 campaign. The D1 check's shorter cap and smaller sample are intentional sanity limits, not qualification evidence. Report cap censoring and avoid cross-configuration performance claims.

The supervisor samples native RSS against 6 GiB and permits 15 seconds of watchdog grace per native run. Stop only its owned process group on a resource/deadline failure, retaining native partial output. The full implementation/execution/audit stage has a 1,500-second budget and needs an additional ten minutes before the overnight cutoff. Do not launch if that reserve does not fit before `2026-10-24T13:00:00Z`.

## Audit and retention

Keep commands, timestamps, exact source/executable and script identities, resource samples, exit statuses, all complete/interrupted episodes, and failed checker attempts under `learning/runs/v2/gate-baselines-r1/`. Recompute every score/survival distribution and native aggregate independently. Verify paired seeds, startup/configuration, K ragged endings, score representations, actual alive/death/cap accounting, event semantics, active occupancy/overflow, and pattern coverage. Multiple Death events can occur on a single terminal raw frame; the shaped penalty remains once per terminated episode.

Mirror the native receipts into parent evidence without changing their contents. Preserve original native paths in provenance. This audit establishes receipt consistency and source identity, not an independent replay of every collision.

No score/survival gate threshold is relaxed by these measurements. Freeze final teacher evaluation margins and configuration before training/evaluation; the supplied two-times-score example remains illustrative.
