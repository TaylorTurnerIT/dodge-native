# Difficulty-3 gate baseline and difficulty-1 sanity

Both registered runs completed once, followed by independent receipt audits. Parent verified all 37 evidence-file hashes, the native JSON/JSONL hashes, paired seed order, and recomputed score/survival means. The [final inventory](../learning/runs/v2/gate-baselines-r1/final-verification-r2.json) and [full summaries](../learning/runs/v2/gate-baselines-r1/results-summary-r2.json) retain exact identities and checks. These are baseline measurements, not a trained teacher result.

## Difficulty 3: matching qualification baseline

Each policy ran 1,000 fresh episodes, patterns/powerups on, K=4, theme 12/1, paired seeds `0xB0000000+i`, and an 18,000-raw-gameplay-frame cap. Thirteen startup frames were excluded. Scores are raw numeric scores, and survival counts alive raw frames.

| Policy | Score mean | Score median | Score p90 | Survival mean, frames | Survival median, frames | Survival p90, frames | Capped episodes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Random | 0.338 | 0 | 1 | 198.354 | 180 | 309 | 0/1,000 |
| Neutral | 1.884 | 2 | 2 | 152.966 | 153 | 153 | 0/1,000 |
| AABB safe-powerup heuristic | 88.633 | 62 | 219.5 | 4,030.038 | 3,559.5 | 8,123 | 2/1,000 |

Heuristic mean survival is 67.1673 seconds. Its two cap-truncated episodes are censored; no cap, seed, or limit was changed. The heuristic observed all 39 pattern entries across 1,680,045 active-pattern frames. Raw occupancy maxima were 15 enemy-family records and 16 active rectangles, with zero observed overflow.

## Difficulty 1: bounded curriculum sanity

Each policy ran 100 fresh episodes with patterns off, powerups on, K=4, and a 2,000-raw-gameplay-frame cap. This shorter run checks the initial curriculum configuration; it is not qualification evidence.

| Policy | Score mean | Score median | Score p90 | Survival mean, frames | Survival median, frames | Survival p90, frames | Capped episodes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Random | 0.26 | 0 | 1 | 312.53 | 276 | 481 | 0/100 |
| Neutral | 0.03 | 0 | 0 | 209 | 209 | 209 | 0/100 |
| AABB safe-powerup heuristic | 17.89 | 18 | 20 | 1,992.56 | 2,000 | 2,000 | 99/100 |

The heuristic's 99% cap fraction prevents interpreting its result as uncensored survival. The run observed up to 18 enemy-family records and no pattern rectangles. This raises the combined measured enemy maximum from 15 to 18. Retain the supplied 64/16 capacities and overflow safeguards; these observations do not prove every future trajectory fits.

## Provenance, resources, and limits

Both runs used original engine HEAD `d7ad95127ad7529c5217a51ae9dc5cfedd3f2365` and the reviewed repaired harness. All 33 original tracked files, five harness/document hashes, and executable SHA256 `922485d26128dbdc4df0868a5df7d7e72bc8f4135addfd691a1e11484d785d39` matched before each run. No M2 source entered these measurements. Native receipts remain unchanged in the isolated worktree and their verified parent mirror.

D3 took 120.463 seconds with peak sampled native RSS of 5,652,480 bytes. D1 took 8.097 seconds with 4,964,352 bytes. The full execution/audit task took 435.264 seconds of its 1,500-second budget. No process was terminated, and neither native experiment was retried. One packaging inventory attempt hashed an active stdout log; its failure and correction remain preserved. These packaging checks are distinct from Rust/Python tests.

The audit establishes receipt consistency and pinned source identity, not an independent collision replay. Individual lethal-frame pickups are not separately logged; aggregate fixed score deltas include them. Occupancy is sampled after native calls. RSS uses cooperative one-second sampling. Score and survival caps remain censored. All evaluation seeds remain excluded from training.

Matching D2 and D3 heuristic baselines now exist. Final teacher score/survival margins, evaluation action mode, and bounded PPO experiments must be fixed before teacher qualification. M2 wrapper/binding validation remains a prerequisite; no teacher training has started.
