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

## K=1 track (the user's hypothesis about control rate)

Validation against the paper draft (`paper/main.tex` in the paper worktree): the review quoted the paper faithfully (4,400 vs 6,115 mean frames, 2,626 to 4,387 at K=1, 256 x 64 rollouts, minibatch 512, segment abandonment every 60 updates, constant learning rate 3e-5). The draft says the policy "was never trained at K=1"; that is out of date, because DODGE-013 did train from 420 at K=1 and regressed.

What the data show: with the same weights, K=1 inference gives a bell-shaped survival distribution (mean 4,434, median 4,346, 6% dead before 1,000 frames) while K=4 has an early-death shoulder (mean 3,342, median 3,101, 14% dead before 1,000), see `charts/chart10.png`. That is inference at a finer rate for a policy trained at K=4; it does not show K=1 training is better.

What DODGE-013 does and does not settle: one warm-started replica, 11.8M frames, game-time gamma and GAE, no KL, entropy, value-loss or advantage telemetry (its own note). It rules out "switch to K=1 and continue" as a free win. Still open: K=1 from scratch, K=1 with the scaling changes (large batch, fresh seed stream, longer rollouts so the credit horizon fits), K=2, and an instrumented diagnostic of why the warm start regressed (a 4x smaller per-decision reward and 4x more decisions per game-second change advantage scale, update cadence and KL budget even when gamma and lambda are matched). K=1 costs 5-6x more wall clock per game-second, so S2 (pipeline speed) gates any serious K=1 run. Self-imposed rule worth reconsidering with the user: one MPS campaign at a time.

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
