# Post-overnight D1→D2 transfer and plateau diagnosis (Opus, r1)

Read-only diagnosis of retained source and saved run data. No training, gameplay inference, evaluation, benchmark, source/config/ledger edit, or scheduler change was made. The only computation was Python parsing of JSONL/JSON logs and CPU `torch.load(weights_only=True)` of six checkpoints, with a narrow numpy allowlist and no forward passes. Peak RSS of that load was 223,363,072 bytes. All outputs are in this directory.

## Decision

1. **D2 is still learning, and no code defect was found.** The run stopped because its 1,800 s budget expired. That was not a behavioral failure, but the observed learning rate means the protocol's "just retry" would fail again. Repeating 1,800 s from the eligible D1 checkpoint is predicted to end near the same point: dev alive about 1,150 and score about 9.
2. **The largest "missing transfer" at D2 entry is an argmax-extraction failure, not a skill failure.** At the exact entry weights, the argmax policy died within 200 alive frames on 42/64 D seeds. The stochastic policy died that early in only 1/63 first training episodes.
3. **After entry, D2's dominant hazard is pattern content that D1 never contained.** The pattern-related inputs had provably never been trained before D2. The stochastic entry policy survived to the first pattern window and died there, which is what transferred D1 skill predicts.
4. **Recommended next step:** a ~5-minute, inference-only, paired action-mode and death-cause diagnostic on frozen checkpoints. It must be authorized separately. Then run a new, separately registered D2-r2 stage from the eligible D1 checkpoint, with a budget sized from measured throughput. Do not lengthen, resume, or reuse failed D2-r1, and do not change gates, reward, model, or learner settings.

## Observed facts (from retained data)

### Learning curve and budget (D2-r1, `training-episodes.jsonl`, `training-metrics.jsonl`)

- **Completed work:** 104 complete updates (collections 48–151) and 7,915 completed training episodes, all terminated with none truncated. There were 64 separately tagged abandoned parent episodes, 105 `collection_accepted` rows, and 15 `checkpoint_resume_boundary` rows. Each complete update is 16,384 decisions, so 104 updates are 1,703,936 new D2 decision transitions. The partial 105th collection (52 episodes) has no completed update.
- **Wall time per update:** median 16.913 s, mean 17.172 s, range 13.45–25.37 s (103 intervals, 12:14:45–12:44:14 UTC). The device probe measured MPS inference 1.803 s and PPO update 14.648 s per 16,384-transition buffer. Learner compute, mostly the update, dominates.
- **Per-update training-mean alive slope (OLS over 104 updates):** +4.86 ± 0.26 frames/update. First half: +6.54 ± 0.59. Second half: +4.12 ± 0.84. The deceleration is about 2.3 combined SE: real but modest, not flat.
- **Score slope:** +0.0495 ± 0.0028/update. Second half: +0.0478 ± 0.0091, so score shows no deceleration.
- **Training-mean alive frames by 8-update block:** 618, 663, 713, 817, 811, 857, 928, 964, 989, 965, 953, 1031, 1172. Score: 3.26 to 8.98.
- **Learner metrics:**
  - Entropy fell from 1.884 to 1.751 nats (first vs last 8 updates; ln 9 = 2.197), so the policy remains high-entropy.
  - Explained variance peaked at 0.813 and averaged 0.521 over the last 8 updates.
  - Approx KL rose from 0.0139 to 0.0295 (max 0.0312), with clip fraction 0.235 over the last 8 updates.
  - The KL early stop fired 7 times. All metrics were finite.
- **Completed episodes per update** fell from 99.9 to 56.6 (first vs last 8). Longer survival means fewer terminal death-penalty events per batch.

### Deterministic dev evaluation noise (`eval-parse.json`, `death-parse.json`)

- **Dev mean alive** at phases 0/16/32/48/64/80/96: 295.25, 756.66, 869.98, 855.89, 877.97, 939.61, 1148.78. Standard error of the 64-seed mean: 23, 59, 65, 62, 73, 79, 97 frames. Score SE: 0.27–1.05.
- **Per-seed alive frames barely correlate across consecutive checkpoints:** Pearson 0.032, 0.118, 0.168, 0.090, 0.079, −0.009. Per-seed outcomes are close to chaotic, so the phase 32–80 "plateau" lies within ±1–2 SE.
- **Argmax dev means track the contemporaneous stochastic training means.** These are different cohorts:

| Dev phase | Dev alive | Training-block alive |
|---|---|---|
| 16 | 757 | 713 (phases 16–23) |
| 32 | 870 | 811 |
| 48 | 856 | 928 |
| 64 | 878 | 989 |
| 80 | 940 | 953 |
| 96 | 1149 | 1031 |

### D2 entry: argmax versus stochastic at identical weights

The weights are byte-identical: all parameters of D1 `checkpoint-000009` equal D2 `checkpoint-000010`. Collection 48 was collected with those weights before any D2 gradient.

| Entry policy | Episodes | ≤200 alive | Median alive | Mean alive | Mean score | Died in 430–639 window |
|---|---|---|---|---|---|---|
| Argmax, 64 D seeds (`checkpoint-000010` dev rows) | 64 | **42** (all score 0, median 166) | 166 | 295.25 | 1.48 | 18 |
| Stochastic, first training episode per slot (collection 48) | 63 | **1** | 541 | 558.43 | 2.48 | 44 (57/63 with a pattern visible at death) |

- The first pattern cannot activate before 420 gameplay frames. The source has `INITIAL_PATTERN_DELAY_FRAMES = 420` at `crates/dodge-core/src/game.rs:25`, and the schedule at `game.rs:1700-1716` pauses its timer during freeze.
- So the argmax deaths at about 166 frames happen with no pattern-only inputs present. They come from base-dynamics shift under argmax extraction.
- For comparison, a random-init argmax policy at D1 died at about 204–208 frames (51/64). The ratio 166/204 ≈ 0.81 matches the D1→D2 speed change, 0.8→1.0 (`game.rs:2308-2313`). This is consistent with argmax failing to dodge the first enemy, not proof of it.
- Argmax fixed this by phase 16 (minimum alive 404).

### Where D2 deaths happen (`death-parse.json`)

The terminal diagnostics `admitted_rectangles` and `onscreen_warnings` are per-observation values at the final pre-reset observation (`env.rs:224-233`). They show that a pattern was present at death, not what caused the death.

| Window (alive frames) | D2 training deaths | Share | Pattern visible at death | D1 share (no patterns) |
|---|---|---|---|---|
| ≤200 | 32 | 0.4% | 0% | 0.1% |
| 201–429 | 520 | 6.6% | 20.8% | 14.3% |
| 430–639 (first pattern) | 3,567 | **45.1%** | **97.7%** | 15.2% |
| 640–1199 | 2,150 | 27.2% | 83.2% | 22.3% |
| ≥1200 | 1,646 | 20.8% | 81.5% | 48.2% |
| All | 7,915 | | **84.9%** | |

- Patterns are rescheduled only after at least 600 no-pattern, non-frozen frames (`game.rs:26`, `1711-1716`). So pattern-visible time is bounded well below 85% of frames, and patterns are over-represented at death.
- The per-update share of deaths in the first-pattern window fell from 0.686 to 0.303 (first vs last 8 updates), slope −0.00416 ± 0.00023/update. The policy is learning the first pattern.
- D1 training never saw a rectangle: 982 episodes, max admitted rectangles 0, pattern visible at death 0%.

### What D1 never trained (`checkpoint-introspection.json`)

These checks are CPU, weights-only, with no forward pass.

- **Type-embedding rows 7 and 8** (charging and moving pattern rectangles, `features.rs:294`) and **`global_projection` column 9** (`pattern_visible`, `features.rs:470`) changed by exactly **0.0** L2 from the pilot's initial checkpoint to D1 final. At D2 entry they were still at random init.
  - The row norms are 11.14 and 9.78, the same scale as the trained rows (10.6–12.7).
  - Every other type row (0–6) and every entity-projection column moved during D1.
- **During D2 (entry to phase 96)**, rows 7 and 8 moved 0.290 and 0.448, and column 9 moved 0.518. Rows 1–6 moved 0.16–0.49. D2 trained the new inputs.
- **Total parameter L2 change:** pilot init to D1 final 13.57; D2 entry to phase 96 17.05. D2 has already moved the weights further than pilot+D1 combined.

## What changes from D1 to D2 (source audit)

- **Dynamics** (`game.rs:2308-2353`, curves `game.rs:38-63`, ramp `game.rs:1683-1698`):

| Setting | D1 | D2 |
|---|---|---|
| Initial speed | 0.8 | 1.0 |
| `enemy_est` | 1.4 | 1.0 |
| Static/moving bounce caps | 0.8/1.05 | 0.65/0.9 |
| Per-score ramp, raw: speed | 131 | 452 (3.45×) |
| Per-score ramp, raw: enemy | 327 | 655 (2.0×) |
| Per-score ramp, raw: static/moving | 32/85 | 1,245/1,245 (39×/15×) |

  Every score event at D2, including each enemy destroyed by a powerup explosion (`game.rs:1210-1222`), ramps difficulty much faster. Score therefore costs future survival more at D2.
- **Content:** patterns on. The 39-entry catalog starts at 420 frames. It adds rect tokens of type 7 (charging, `pattern_type == 0`) and type 8 (moving), with `until_lethal` and `charging` values, on-screen warnings, and `global[9]` (`features.rs:240-305`, `470`). D1 enemy types are 1–3 and powerups are 4–6, so the same entity types appear at both difficulties.
- **Token counts:** D2 training max is 8 admitted enemies and 8 rectangles; D1 max is 8 and 0. There were no drops and no inverted boxes. Layout stays 81 tokens.
- **Initialization and optimizer:** exact D1-final model, Adam state, and RNG, already verified. Fresh envs, new run seed, cap 18,000.
- **Is D1 easy capped survival?** Largely yes.
  - The D1 dev cap is 2,000 frames: teacher 57/64 caps, heuristic 99/100.
  - Teacher D1 score is 12.11 against the heuristic's 17.89 on a different cohort.
  - D1 has no pattern and slower enemies. What can transfer is enemy and powerup avoidance until the first pattern, about 420–640 frames at D2. The stochastic entry result (median 541, 44/63 dying in the first-pattern window) is exactly that. Expecting D1 to transfer much further was not reasonable: D2's dominant hazard did not exist in D1, and its inputs were untrained.

## Reconciling the four prior explanations

| Explanation | Verdict | Evidence |
|---|---|---|
| Experience / distribution shift | **Supported** | The shift is pattern content plus faster dynamics. 85% of D2 deaths have a pattern visible, against 0% in D1. The new inputs were untrained at entry and are now training. Learning is steady at +4.86 alive and +0.0495 score per update. The "plateau" is within dev noise. |
| Stochastic vs argmax gap | **Supported at entry; not shown later** | Entry: 1/63 versus 42/64 died within 200 frames (different seeds, same weights). Later argmax dev means are within ±10% of contemporaneous training means, but those cohorts are confounded and need a paired test. Entropy of 1.75 nats keeps the risk open for an immutable argmax gate. |
| PPO / value-fit efficiency | **Plausible secondary contributor; unproven** | Explained variance fell from 0.81 to 0.52, KL doubled, and the alive slope fell from 6.5 to 4.1 (about 2.3 SE). Episodes per update fell 100→57, so fewer death events reach each batch. There is no instability, and value fit versus episode length was not separately tested. |
| Observation / timing / accounting defect | **No defect found** | See below. |

The audited paths showed no defect:
- **Collection and boundaries:** GAE bootstraps from the actual pre-reset final observation and uses zero on termination (`ppo.py:334-338`). The recurrence stops at both boundary types (`ppo.py:165-171`). Reset slots are audited (`ppo.py:340-362`).
- **Evaluation:** argmax over 64 independent B1 envs, under `model.eval()` with dropout 0 (`dev_eval.py:63-115`).
- **Featurizer and model:** type mapping (`features.rs:166-174`, `294`), raw-frame history and motion (`features.rs:216-305`), and the global-token readout (`teacher.py:172`) are as intended.
- **Episode accounting:** `checkpoint_resume_boundary` rows only record what a resume would abandon. The live env is not reset (`train_teacher.py:203-224`), and their 64-episode lists do not truncate training.
- **Unknown-motion counters** are expected first-sight counts and do not indicate a defect. D2 had 125,660 unknown-enemy samples out of 6,809,066 raw history samples (1.85%), 40,219 unknown-rectangle and 32,625 unknown-phase samples. Dropped and inverted counts were 0.
- **Efficiency note, not a correctness defect:** collection runs a second forward pass per step for `next_values` (`ppo.py:335-336`). That costs about 1.8 s of inference per buffer against a 14.6 s update.

## Observables never logged

- Per-step actions, logits, entropy, and top-1/top-2 margin per episode (only per-update aggregate entropy).
- Argmax-versus-sampled divergence.
- Killer entity or death cause. An enemy collision removes the enemy before `die()` (`game.rs:1168-1172`).
- The active pattern id or type at death, time since activation, and per-episode pattern exposure count.
- Freeze or size powerup state at death.
- Value predictions versus realized returns by episode length, and attention.
- Any diagnostics on dev rows (they carry only score, alive, and flags).
- Stochastic evaluation on D seeds.

This report invents none of these. The pattern-at-death numbers above are presence, not cause.

## Hypotheses (unverified)

- **H1.** Most remaining D2 deaths are pattern-rectangle collisions, the first pattern especially. Charging (type 7) and moving (type 8) patterns may differ.
- **H2.** A high-entropy policy, 1.75 nats, keeps argmax brittle in near-tie states. Later checkpoints may still lose performance under argmax on a paired basis.
- **H3.** The faster per-score difficulty ramp at D2 makes the learner trade score for survival. The marginal training ratio is 0.0102 score per extra alive frame, below the 0.0163 that both the gate (50/3060) and the heuristic (100.1/6114.6) imply.
- **H4.** Fewer terminal events per batch as survival grows slow the per-update gains.

## Projection: does more training suffice, and how much?

These are linear extrapolations from the observed slopes. They are unrun and uncertain, and if returns diminish they are optimistic.
- **Alive:** reaching 3,060 from the phase-96 dev mean of 1,149 at 4.86 (or 4.12) frames/update takes about 393 (464) more updates, roughly 6,750 (8,000) s.
- **Score:** reaching 50 from 8.91 at 0.0495/update takes about 830 more updates, roughly 14,300 s. **Score binds.** At the marginal ratio, alive 3,060 arrives at a score near 28.
- **From the eligible D1 final**, about 104 updates (about 1,790 s) must be relearned first. A gate-sized D2-r2 is therefore about 935 updates, roughly 16,100 s of updates plus about 58 evaluations at 8–25 s each, about 17,500 s or about 4.9 h.
- **Qualification is much further.** The D2 point floors are 200.2 score and 6,726 alive. These are a projection, not a plan.
- **Memory:** observed D2 peaks were RSS 0.95 GB and MPS 2.46 GB, so memory is not the constraint.

## Ranked recommendations

1. **First, an inference-only paired action-mode and death-cause diagnostic** (new authorization; diagnostic-only, can never qualify a run). Smallest falsifiable step.
   - **Frozen inputs:**
     - Current pinned 75-input source and installed wrapper, identity as in the D2 freeze.
     - Device MPS, matching the original evals, with CPU fallback as a separate label.
     - Checkpoints:

| Checkpoint | SHA256 |
|---|---|
| D1 `checkpoint-000009-candidate.pt` | `ce9c03c8…544f` |
| D2 `checkpoint-000010` | `33262cad…c64f` |
| D2 `checkpoint-000016` | `b988e9e0…76b6b` |
| D2 `checkpoint-000022` | `2d598e19…d4e8b6` |
| D2 `checkpoint-000023-periodic` (phase 104, never evaluated) | `22fa5976…b3bf` |

     The interrupted checkpoint is excluded.
   - **Seeds and settings:** the 64 registered D seeds `0xD0000000..0xD000003F` at D2, cap 18,000, K=4, patterns and powerups on. Do not touch B or E.
   - **Modes:**
     - (a) An argmax control that must reproduce the retained rows exactly for 000010, 000016, and 000022.
     - (b) Seeded stochastic sampling with 3 registered torch sampling seeds.
     - Totals: 5 checkpoints × 4 runs × 64 = 1,280 episodes, about 1.4M raw frames, estimated about 160 s at the observed 8.2 s per 73.6k frames.
     - Budget: 600 s wall, RSS < 6 GiB, MPS < 6 GiB under the existing cooperative guards. No gradients, no optimizer, no checkpoint writes.
   - **Log per step:** argmax action, sampled action, entropy, top-1 probability, and top-1/top-2 margin.
   - **Log at death:** classify from the terminal observation. A lethal type-7 or type-8 token with both signed gaps overlapping the player means a pattern death, recorded with its type. Otherwise record enemy or other, since the killing enemy is removed. Also record frames since a pattern first became visible.
   - **Outcomes:**
     - **Argmax control mismatch:** stop and diagnose evaluation determinism before anything else.
     - **(A)** At phases 96 and 104, |stochastic mean − argmax mean| ≤ 2 paired SE on both score and alive. Argmax is not the bottleneck, so proceed to recommendation 2.
     - **(B)** Stochastic beats argmax by > 2 SE on both metrics. Longer training alone is unlikely to pass an immutable argmax gate. Bring an explicit, separately reviewed entropy/temperature proposal (a learner-setting change) to the user. Do not bundle it with a budget change.
     - **Death mix:** if pattern deaths are ≥ 70%, direct D2 remains the right curriculum. If enemy deaths dominate after the first pattern, examine H3 (score-ramp trade-off) before extending.
2. **Then a new, separately registered D2-r2 stage.**
   - **Lineage:** start from the eligible D1 final `ce9c03c8…544f`, with a new identity, a new run seed distinct from `5562881586070242562`, a new terminal-budget anchor, and parent lease or receipt semantics as the protocol requires.
   - **Unchanged:** learner, source, device, architecture, reward, caps, gate, and evaluation cadence. Same-phase resume stays disabled, failed D2-r1 artifacts stay ineligible, and old metadata stays unedited.
   - **Budget:** size it from observed throughput, not 1,800 s:
     - About 17,500 s (≈4.9 h) is needed for the progress gate under linear score extrapolation.
     - Alternatively, a 7,200 s curve-extension stage. Predicted training-mean alive is about 2,300–2,600 and score about 20–23. It is expected not to pass the gate, but it measures whether the slope persists beyond 104 updates.
   - **Futility rule:** pre-register a tightening rule, never a relaxation. Example: at phase 400, stop for diagnosis if the 64-seed dev alive mean is below 1,700 and the training slope over phases 200–400 has a 95% upper bound below 2 frames/update.
   - **Warm start from D2-r1 is rejected:** it would need a protocol amendment admitting failed-run artifacts as parents, and only saves about 1,800 s.
3. **Rejected for now:**
   - **Additional D1:** it contains no pattern exposure, and its inputs for patterns stay untrained.
   - **A bridged curriculum,** such as D1 with patterns: an untested curriculum and protocol change. D2 itself is demonstrably learnable: first-pattern deaths fell from 69% to 30%.
   - **A source repair:** no defect was found. The `next_values` double forward is only an efficiency opportunity, and fixing it would need a new frozen source identity.
   - **Hyperparameter changes,** whether entropy, LR, batch, or minibatch, presented as causal tests.
   - **Relaxed caps or gates, reward or model changes,** and **reuse of D2-r1 checkpoints as eligible.**

## Remaining uncertainty

- **Linear projections are fragile.** The alive slope already decelerated by about 2.3 SE.
- **The entry action-mode comparison is unpaired:** training seeds versus D seeds. The 1/63 versus 42/64 contrast is large enough that cohort differences are implausible as the explanation, but they are not excluded.
- **Death cause is presence-based.** A pattern being visible at death does not show the pattern killed the player.
- **The dev noise floor is large:** SE is 60–100 frames and per-seed correlation is about 0.1, so 64-seed dev deltas under about 200 frames are not interpretable.
- **Phase-104 weights were never evaluated.**
