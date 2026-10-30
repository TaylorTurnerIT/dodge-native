# Review ideas and scaling plan, 2026-10-30

Source: an external review of the paper draft (`RL-Agent-Hyperparameter-and-Architecture-Optimization.md`, a Gemini chat export kept outside the repo, so its numbers come from the paper and are not re-verified here) plus the user's scaling hypothesis: the policy may simply need much more training on many more seeds. This document checks each idea against the repository, and lists the cheapest discriminating test for each. Nothing here authorizes training, seed use or promotion; every launch keeps its own registration, review, lease and user go-ahead.

Evidence base: checkpoint 420 death telemetry (`learning/reports/death-telemetry-fyou-patterns-20261029/`, DODGE-014, DODGE-015 pending), the research notebook (DODGE-001..013 as of `c2778d1`), `docs/v2-*`, `python/dodge_rl/`.

## Facts that change the picture

1. **The hand-written heuristic runs at 4-frame control, not 1-frame.** `docs/v2-baseline-campaign.md:21`: "Hold each policy action for at most four raw frames." It scores 6,115 mean alive frames (1,000 episodes, 15 capped) against 2,626 for checkpoint 420 with sampled actions at the same control rate (DODGE-012) and 4,387 at 1-frame. The cohorts are not paired, but the gap is large. The heuristic (`crates/dodge-rl-env/tests/support/m0_policy.rs`) simulates the player's inertia exactly, extrapolates every hazard linearly, looks 12 frames ahead over all 9 actions and keeps only actions that stay at least 4 px clear. It reads full game state, like the privileged teacher. So a 12-frame look-ahead with an exact player model beats the learned policy at its own control rate: the failure looks like short-horizon planning, not a missing 1-frame reflex.
2. **The whole training lineage is only a few compute-hours.** Production training ran at about 4k raw frames/s end to end (72 updates = 4.71M frames in 1,188 s, evaluations included). Checkpoint 420 is 420 updates x 16,384 decisions = 6.9M decisions = 27.5M raw frames, about 2 hours. The headless engine alone does about 14.5M raw frames/s (`docs/v2-foundation-progress.md`), roughly 3,500x faster than the training loop. Throughput is limited by the Python and model pipeline, not the game.
3. **The 64 and its neighbours are conservative operating choices, not derived values.** `docs/v2-m3-run-protocol.json` (registered 2026-10-24 before any probe): `training_batch_size` 64, `rollout_decisions` 256, minibatch 512 ("a conservative initial choice under the 6 GiB budget; the Opus proposal used 2,048. Neither has measured model-throughput evidence", `docs/v2-teacher-training-plan.md:37`), 1,800 s per stage, a hard UTC cutoff, 6 GiB RSS and MPS caps. Observed peaks were about 1 GB RSS and 2.4 GB MPS, so there is headroom under the stated cap.
4. **Seed reuse is real in the 420 lineage, at least in its Uniform #2 stage.** The base stream is unbounded (`dodge_slot_splitmix64_high32_reject_v1`, seeds from run seed, slot and episode index, about 2^32 values). But DODGE-010 trained all six models from one fixed 512-seed pool (256 historical early failures, 256 survivors), and DODGE-011 continued Uniform #2 to update 600 with an "unchanged training seed stream". To verify first: whether updates 324-600 sampled that 512-seed pool the whole way.
5. **Recent evidence does not support "same recipe, a bit more training".** DODGE-013 trained 11.8M frames per arm from 420: 4-frame training showed no clear Q1 gain over checkpoint 420 (1,625 vs 1,750), and 1-frame training regressed to 651. Checkpoint 600 had higher Mean but lower Q1 than 420 (DODGE-001). So extra updates at 64 envs and a 512-seed pool have plateaued or traded off. That is compatible with the scaling hypothesis only if the plateau comes from gradient noise, a small seed pool or short horizons, which is exactly what the tests below separate. The 1-frame regression also means the review's "fine-tune at K=1" has already been tried in one form (game-time-matched gamma and GAE, same reward); the review's version differs by also removing score from the reward.
6. **Death telemetry (DODGE-014/015 data):** enemy contact during patterns is the dominant failure; the policy changes its action at 76% of consecutive decisions (last-128 sample), turns toward the killer in the final 10-15 frames, and runs into already-filled rectangles while chased. fyou is not the cause.

## Priority order (expected immediate effect, weighed by confidence and cost)

Evidence tags: M measured here, L literature prior, R reasoned from our data, S speculative. Effect sizes are judgments except where tagged M; the order is a proposal to be revised as results arrive. Everything in Phases 1 and 2 needs at least two training seeds per arm and a fresh cohort of 1,024 or more seeds (the notebook puts the detectable difference at about 620 frames with 64 seeds and one training seed). Nothing launches without the user's go-ahead.

Phase 0, no training, hours (also tells us which later items to trust)
1. K at inference. Using K=1 already gives Q1 +934 and mean +1,761 frames [M, DODGE-012]. Add K=2 and K=3 zero-shot on the same 2,048 seeds to find the best rate. Controller adoption is the user's call.
2. Paired heuristic baseline at K=4 and K=1 on the same seeds [M after the run]. Sizes the gap to the best known controller (6,115 vs 4,434 mean) and gives a control variate for ranking.
3. Policy plus short-horizon shield: veto actions the exact player model predicts will collide within about 12 frames, otherwise follow the policy [R]. No training. If it closes much of the gap, the policy's weakness is short-horizon planning, and the shielded policy is also a stronger teacher for the vision student.
4. Counterfactual branching, DODGE-004 [R]. Shares the snapshot and rollout harness with item 3.
5. Argmax versus sampled per K, and checkpoint averaging of the saved 360 to 600 checkpoints [M for argmax at K=4: +275 Q1; L for averaging].
6. Seed audit and throughput profile (S0, S1). These gate scale: they say whether the 420 lineage reused a 512-seed pool and where the 3,500x slowdown versus the engine sits.

Phase 1, first training runs, cheap configuration changes
7. Gamma and lambda sweep (gamma 0.97 to 0.995, lambda 0.9 to 0.95) at K=4 and K=1 [L: the study's most important hyperparameter]. Highest value per cost among training changes, and it may explain DODGE-013's K=1 regression.
8. Fresh unbounded seed stream, larger batch, longer rollouts, learning rate retuned (S3), after the pipeline speedup (S2) [R, L]. Large effect if S0 shows pool reuse or gradient noise is the limit; effect unknown otherwise.
9. Imitation from the heuristic (behaviour cloning or DAgger on policy-visited states, then PPO fine-tuning) [R]. The target level is already demonstrated; main risk is capping near the heuristic until PPO moves past it.
10. K=2 and K=3 trained arms, K annealing 4 to 1, per-episode sampled K, from-scratch K=1 [S]. Order after item 7, because horizon length confounds K.

Phase 2, smaller or less certain, run as ablations once the base recipe moves
11. Planned learning-rate decay: adopt as the default inside Phase 1 runs rather than a separate experiment [L: small, "secondary"]. Compare schedule shapes only once.
12. Per-epoch advantage recomputation, logging KL early-stop frequency, value and observation normalisation, separate actor and critic encoders, lower or decayed entropy [L].
13. Survival-only reward [S]. The heuristic scores about 100 while surviving 6,115 frames, so scoring is not inherently fatal.
14. Input and architecture changes: closing speed and relative velocity, clearance raycasts, entity pooling into the heads, D4 symmetry (after the equivariance audit), more attention depth [S].
15. Segment carry-over (do not abandon live games), snapshot-prioritised replay [S].
16. Vision-student distillation, after a stronger teacher exists.

## K=1 track (the user's hypothesis about control rate)

Validation against the paper draft (`paper/main.tex` in the paper worktree): the review quoted the paper faithfully (4,400 vs 6,115 mean frames, 2,626 to 4,387 at K=1, 256 x 64 rollouts, minibatch 512, segment abandonment every 60 updates, constant learning rate 3e-5). The draft says the policy "was never trained at K=1"; that is out of date, because DODGE-013 did train from 420 at K=1 and regressed.

What the data show: with the same weights, K=1 inference gives a bell-shaped survival distribution (mean 4,434, median 4,346, 6% dead before 1,000 frames) while K=4 has an early-death shoulder (mean 3,342, median 3,101, 14% dead before 1,000), see `charts/chart10.png`. That is inference at a finer rate for a policy trained at K=4; it does not show K=1 training is better.

What DODGE-013 does and does not settle: one warm-started replica, 11.8M frames, game-time gamma and GAE, no KL, entropy, value-loss or advantage telemetry (its own note). It rules out "switch to K=1 and continue" as a free win. Still open: K=1 from scratch, K=1 with the scaling changes (large batch, fresh seed stream, longer rollouts so the credit horizon fits), K=2, and an instrumented diagnostic of why the warm start regressed (a 4x smaller per-decision reward and 4x more decisions per game-second change advantage scale, update cadence and KL budget even when gamma and lambda are matched). K=1 costs 5-6x more wall clock per game-second, so S2 (pipeline speed) gates any serious K=1 run. Self-imposed rule worth reconsidering with the user: one MPS campaign at a time.

### Which K, and how to train it

K=4 may be best only because it is the one value that was tried. A common reading of the pattern (K=4 trains well, K=1 acts better) is that coarse decisions make learning easier, with a shorter credit horizon and less per-decision noise, while fine decisions help execution. That is a hypothesis, not a result here. Cheap and expensive ways to test it:
- Inference only, no training: run checkpoint 420 at K=2 and K=3 on the same 2,048 fresh seeds as the existing K=1 and K=4 runs (paired contrasts). Shows whether the response to finer control is monotone. Needs AC power.
- K=2 and K=3 trained arms next to K=1 and K=4 (from scratch and from 420), game-time-matched gamma and GAE.
- K annealing 4 to 3 to 2 to 1 during training (DODGE-013 jumped straight from 4 to 1), or K sampled per episode so one network sees several rates; both are untried.

## Learning-rate schedule

Why the rate moved in steps: there is no scheduler in the code (`make_optimizer` in `train_teacher.py` is Adam with a fixed rate; the plan says "3e-4 constant"; `validate_config` requires the config to equal the registered default). Each change was a manual reaction to a plateau or endpoint regression, run as its own pinned, reviewed branch from a saved checkpoint through a resume-with-new-LR hook: 3e-4, then 1e-4 from retained 204 (mean +29.3%, Q1 -10.1%), then 3e-5 from 276. Each step is confounded with training seed and duration, and Adam moments carry over from the previous rate. One decay run (3e-5 to 1e-5, linear) was tried once: only an intermediate checkpoint won, the endpoint fell. So the schedule shape is genuinely untested, not tested and rejected. Literature prior (continuous-control benchmarks, not our game, so a prior and not proof): Andrychowicz et al. 2020, "What Matters in On-Policy RL" (arXiv 2006.05990), Sec. 3.7: linearly decaying the learning rate to 0 improved performance on 44 of 55 tasks, with small gains except about +15% on Ant, and they call it "of secondary importance"; the initial Adam learning rate has a "very strong" effect and 3e-4 is the safe default. Sec. 2 and 3.5: learning rate and minibatch size interact and must be tuned together, larger batches did not hurt sample complexity in their range, while many parallel environments (shorter experience chunks) hurt some tasks; they give no scaling rule. Engstrom et al. 2020, "Implementation Matters" (arXiv 2005.12729), lists Adam learning-rate annealing among the code-level optimizations that change PPO's reward landscape on Humanoid and Walker2d. Implication here: a planned decay is a mild, usually positive default, but the starting rate and the batch-size interaction matter more, and our staged drops to 3e-5 (10x below the 3e-4 default) were never compared with a planned schedule.

Plan: make the schedule part of the optimizer state (saved in checkpoints), then compare constant, warmup plus cosine to a floor, and KL-adaptive over at least two training seeds per arm, with learning rate rechecked whenever batch size changes.

## Literature checklist against our PPO setup

Source: Andrychowicz et al. 2020 (arXiv 2006.05990; five MuJoCo tasks, over 250,000 agents; read through a page summariser, so confirm any figure before citing it in a paper) and Engstrom et al. 2020 (arXiv 2005.12729). Continuous control with small MLPs, so a prior for us, not proof.

Already matches: PPO clip 0.2 (they suggest starting at 0.25); gradient clip 0.5; Adam with eps 1e-5 and initial rate 3e-4 (their safe default); MSE value loss with no value clipping (they found value clipping hurt at every threshold and Huber worse than MSE); per-minibatch advantage normalisation (little effect); actor final layer initialised with gain 0.01 (they found small last-layer initialisation a big win, about +66% on Humanoid).

Differs, each a cheap experiment:
- Policy and value networks: they found separate networks better on 4 of 5 tasks. Ours share one encoder (`teacher.py`); measured gradient alignment between actor and critic is near zero (cosine about 0.02), which weakens but does not settle the interference story.
- Discount: they call gamma the most important hyperparameter and start at 0.99. Ours is 0.995 per decision (half-life about 138 decisions, 550 frames at K=4) and was never swept; lambda 0.95 vs their 0.9. The heuristic needs only a 12-frame look-ahead. Link to K: at K=1 with game-time-matched gamma the credit horizon is 4x more decisions, so DODGE-013's regression may partly be a too-long horizon; sweep gamma and lambda at K=1 before concluding anything.
- Normalisation: they say always normalise observations and check value normalisation (crucial on two tasks, harmful on one). Ours has no running normalisation (hand-scaled features, fixed reward scale 0.1). Engstrom lists reward normalisation, Adam annealing and network initialisation as the optimisations that most reshape the PPO reward landscape.
- Epochs and advantages: they find multiple passes crucial and stale advantages harmful, recomputing advantages at the start of each pass. Ours computes GAE once per rollout (`ppo.py`) and runs four epochs with a 0.03 KL stop; how often the KL stop fires is worth logging.
- Parallel environments: more environments with shorter experience chunks hurt sample efficiency on some tasks; larger batches did not in their range. Argues for longer rollouts per environment in S3.
- Entropy bonus: none of the regularisers helped significantly in their continuous setting; ours is a constant 0.01 on a discrete policy, so test lower or decayed, not removal by assumption.
- Frame skip: improved 22 of 55 tasks ("try it"), which supports treating K as a tuned hyperparameter.
- Time-limit handling: no difference at 1,000-step limits; our cap is 18,000 frames, but capped games are rare (15 of 1,000 for the heuristic, none for the policy).

## Scaling track (the user's hypothesis)

Goal: find out whether more data, more diverse seeds and larger batches move the weak tail (Q1), and what limits throughput.

- **S0, seed audit (no compute).** Count unique training seeds and episodes in the 324-600 segments from `training.jsonl` and the seed-stream config. Report episodes per unique seed. Decision: if the 512-pool was used throughout, fresh-stream training is the first change to test, ahead of everything else.
- **S1, throughput profile (minutes).** Time one update split into: environment stepping, observation stacking and transfer, model inference on MPS, GAE, PPO epochs. Test 64, 128, 256, 512 envs with 4/8/12 threads and rollout lengths 256/512/1,024, plus CPU vs MPS inference. Output: frames/s per configuration and the real bottleneck. Expect the engine to be a small share; verify.
- **S2, pipeline fix (code).** Whatever S1 shows: batched inference, avoiding per-env Python loops, pinned buffers, vectorised rollout storage. Target at least 10x frames/s. Parity-test against the current loop on the same weights (same seeds give the same rollouts).
- **S3, scaled run from 420 (training, gated).** Fresh unbounded seed stream (no pool), 256 or more envs, rollout of 512 or more steps, minibatch 2,048 as the Opus proposal suggested, learning rate rechecked for batch size, game-time gamma and GAE unchanged. Compare against the DODGE-013 4-frame arm at equal frames first (isolates batch and seed diversity from length), then extend to 10x the frames. Primary metric Q1, with Mean, Q4 and milestone counts, on a fresh shared cohort.
- **S4, scaled run from scratch (training, gated).** Only after S3 shows direction, since a from-scratch run tests whether 420's basin is the limit. Run it at K=1 (and K=2) as well as K=4: from scratch is where K=1 has never been tried.

Prediction to register first: if gradient noise and seed reuse limit the policy, S3 improves Q1 at equal frames; if the limit is representation or horizon (fact 1), it will not.

## Idea ledger (every item in the review, with repo check)

Diagnoses:
- Inertia and 1-frame closed-loop damping explain K=1 over K=4: plausible, mechanism untested. Test: counterfactual branching (below). Telemetry shows heavy action switching, consistent with dithering.
- Score in the reward trains the policy to rush: unverified. Score comes from enemy deaths and pickups, not elapsed time (`docs/v2-performance-policy-2026-10-25.md`), and the heuristic scores about 100 while surviving 6,115 frames, so scoring is not inherently fatal. Test: survival-only reward arm.
- Segment boundaries censor late-game experience: real (each resume abandons the live games, journal showed 42,768 frames of 3.9M), small in count but biased to the longest games. Fix needs live-game snapshot carry-over; cheap to test only after S2.
- Pattern 3 vs pattern 4 (70% vs 40% lethal) means orientation overfit: pattern 3 and 4 have identical score gates (10-60) and are listed as sibling variants, so a gate confound is ruled out here. Not yet verified: that the rectangle layouts are exact transposes, or that the game dynamics are symmetric (spawn points, center box, pickups).
- Turning toward the killer because a wall zeroes the escape velocity: telemetry shows the turn; the wall mechanism is untested.

Inputs:
- D4 symmetry augmentation: needs an equivariance audit first (the playfield clamp is [2, 125], so the symmetry axis is 63.5 while the features centre at 64). Cleanest form is a per-episode wrapper that transforms observations and inverse-maps actions, which stays on-policy. Test: Rust equivariance check, then pattern 3 vs 4 gap.
- Relative velocity and closing speed: partly present already (signed gaps, enemy motion, time-to-contact `contact.frames`); explicit closing speed and relative-velocity vector are missing. New input columns can be zero-initialised so 420 warm-starts.
- 8-way clearance raycasts (wall or rectangle): absent; plausible for the wall-rectangle cul-de-sacs seen in patterns 3 and 39.
- Action and velocity history: velocity is already in the global token; previous actions are not.

Architecture:
- Heads read only the global token: confirmed (`teacher.py:174`). Adding masked max and mean pooling is cheap but changes head width, so warm start is partial.
- Separate actor and critic trunks or normalised value targets: gradient-alignment instrumentation already exists as unaccepted work (`docs/v2-long-D2-results-2026-10-25.md`); critic explained variance sits near 0.5.
- More attention depth or heads: from-scratch cost, test last.

Hyperparameters and training:
- Train at K=2 or K=1: partly answered by DODGE-013 (K=1 regressed). Untested: K=2.
- Gamma and GAE rescaling by control rate: already done in DODGE-013.
- Larger rollout and minibatch: folded into S3.
- EMA or checkpoint averaging: free to test offline now with the saved 360/420/480/540/600 checkpoints, no training.
- Entropy decay 0.01 to 0.001: untested; DODGE-015 will show how confident the policy is per decision.
- Never abandon in-flight episodes: see segment note above.

Curriculum and evaluation:
- Snapshot-based prioritised replay (restore about 120 frames before high-lethality patterns): static hard-seed priority failed (DODGE-010), but this is a different mechanism. It shares its machinery with the counterfactual branching harness, so build the snapshot-restore harness once.
- EMA plus stratified evaluation with the heuristic's survival as a control variate: analysis-only, cheap, reduces ranking noise. Needs the heuristic run on the same seeds.
- Vision student (4-frame pixel stack, KL plus value loss plus a spatial-threat auxiliary head): later stage, after a stronger teacher.

## Work order

Track A, no training, can start immediately (main agent owns the ledger and leases):
1. S0 seed audit and S1 throughput profile.
2. Counterfactual branching (DODGE-004): restore snapshots 60, 45, 30 and 15 frames before enemy-contact deaths; roll out the policy at K=4 and K=1, plus an oracle that tries each of the 9 actions for 12 frames. This separates reaction-delay failures from earlier commitment to doomed regions.
3. Paired heuristic baseline on the same fresh seeds at K=4, to put a number on the gap in fact 1, and to turn the heuristic into a stratification control variate.
4. Checkpoint averaging evaluation (offline).
5. Rust equivariance audit for D4 symmetry.

Track B, code changes (after Track A informs priorities): S2 pipeline speedups, wrapper-level D4 augmentation, extra input features, pooling heads, survival-only reward switch, snapshot carry-over across segments.

Track C, training (each needs registration, independent review, resource qualification and explicit user go-ahead): S3, then reward, symmetry, features, imitation from the heuristic.

Imitation from the heuristic is the idea the review did not raise: since a 12-frame look-ahead already beats the policy at 4-frame control, DAgger or behaviour cloning from it is a direct way to reach that level cheaply and then continue with PPO. Evaluate it as its own track after item 3 above confirms the gap.

## Limits of this document

All repository claims above were checked in the code or docs named; the 512-pool continuation (fact 4), transpose-exactness of patterns 3 and 4, and the training-loop bottleneck are explicitly unverified. The telemetry shows associations at death, not causes.
