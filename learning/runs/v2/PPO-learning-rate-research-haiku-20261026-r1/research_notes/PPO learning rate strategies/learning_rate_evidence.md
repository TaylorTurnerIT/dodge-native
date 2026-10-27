# PPO learning rate strategies: evidence notes

Research date: 2026-10-26. Scope: PPO learning-rate (LR) stability, empirical sensitivity, schedules, and adaptation, with implications for the Dodge D2 continuation branch (fixed Adam LR 3e-5 from accepted checkpoint `checkpoint-000324-candidate.pt`).

Source list, retrieval status, and local copies: `sources.json` in this directory. Text extraction for the three papers used `pypdf` on the downloaded PDFs (copies in `raw/`). Implementation files are raw GitHub `main`/`master` branch files, not pinned commits. Any claim marked **[snippet]** comes from a search-result snippet only, not a read page. Any claim marked **[summary]** comes from WebFetch's model-summarized output, not byte-verified text.

## 1. PPO update stability: LR interactions, clipping, KL stop, and causal attribution

### Takeaway
PPO's clipped objective does not enforce a hard trust region, and its step size depends on the optimizer (Adam state, LR, minibatch size, epochs), not just on the surrogate. A change in LR therefore cannot be attributed to a causal regression without holding the other update knobs fixed and measuring the realized KL and clip fraction.

### Cited Findings
- The clipped surrogate `L_CLIP = E[min(r_t A_t, clip(r_t, 1-ε, 1+ε) A_t)]` "removes the incentive for moving r_t outside of the interval [1-ε, 1+ε]"; it is a pessimistic bound on the unclipped objective, and the paper does not describe it as a hard constraint. — [Schulman 2017, §3, arXiv:1707.06347](https://arxiv.org/pdf/1707.06347) (text extracted, `raw/schulman2017.txt`).
- Engstrom et al. measured on Humanoid-v2: "the PPO variants' maximum ratios consistently violate the ratio 'trust region'", while "both PPO and PPO-M constraint the KL well (compared to the TRPO bound of 0.07)"; they conclude TRPO enforces a mean-KL trust region, while PPO's clipping is an approximation. — [Engstrom 2020, Fig. 2 caption and §4 "Trust regions in TRPO and PPO", arXiv:2005.12729](https://arxiv.org/pdf/2005.12729) (`raw/engstrom2020.txt`).
- Engstrom et al. give the PPO gradient for a single state-action pair as nonzero only when the ratio is inside `[1-ε, 1+ε]` or the clipped term is not active, so ratios can move outside the band; this is the mechanism for the violations above. — [Engstrom 2020, §4, arXiv:2005.12729](https://arxiv.org/pdf/2005.12729).
- Engstrom et al. state the dependence of PPO on optimizer properties "contributes to the brittleness of the algorithm to hyperparameters such as learning rate and momentum." — [Engstrom 2020, §4, arXiv:2005.12729](https://arxiv.org/pdf/2005.12729).
- Andrychowicz et al.: "many choices may have strong interactions with other related choices, for example the learning rate and the minibatch size. This means that such choices need to be tuned together and experiments where only a single choice is varied but interacting choices are kept fixed may be misleading." — [Andrychowicz 2020/2021, §2 study design, arXiv:2006.05990](https://arxiv.org/pdf/2006.05990) (`raw/andrychowicz2020.txt`).
- Andrychowicz et al. include Adam LR (C24) in every choice group because "we suspect that it may interact with many other choices." — same source.
- Local code (`D2-gradient-capsule-parent-freeze-20261025-r5/own/runtime/dodge_rl/ppo.py`, read by grep and line ranges): the policy loss is `max(unclipped, clipped)` with `clip_coef` 0.2 (line ~502-504), value clipping is off (`value_clipping: False`), gradients are clipped at 0.5 before `optimizer.step()` (~519-521), and `approximate_kl` is `mean(exp(logratio) - 1 - logratio)` (line ~98). KL stop is computed at epoch end over the full frozen rollout, and it breaks additional epochs only (lines ~548-571): `if epoch_kl > config.target_kl: early_stop = True; break`.
- Local code: `optimizer.param_groups` must own every trainable parameter exactly once (line ~446-448). Optimizer restore is `optimizer.load_state_dict(state["optimizer"])` plus RNG restore (`checkpoints.py` `restore_learner`, lines 138-142). A grep for `scheduler|anneal|lr_schedule` in `ppo.py` and `checkpoints.py` returns no matches (no LR schedule in the D2 runtime); the header docstring states there is no value clipping, running normalization, or auxiliary policy target (line 6).
- Local config (from task packet, not re-derived from source): 64 envs, 256 rollout steps (16384 decisions/update), 4 epochs, minibatch 512 (32 minibatches × 4 epochs = 128 optimizer steps/update), Adam eps 1e-5, γ 0.995, λ 0.95, clip 0.2, vf coef 0.5, entropy 0.01, max grad norm 0.5, target KL 0.03, reward scale 0.1, action repeat 4.
- Reward and advantage normalization: CleanRL's continuous PPO has `norm_adv: bool = True` (argument default; line 63 of `cleanrl_ppo_continuous.py`). Engstrom et al. list reward scaling (divide by rolling discounted-return std, no mean subtraction) as a code-level optimization ablated in Fig. 1. — [Engstrom 2020 §3 items 2, Fig. 1](https://arxiv.org/pdf/2005.12729).

### Inferences
- Because the clip band is not a hard bound, the realized update size is set by LR × gradient × (number of optimizer steps), so LR, minibatch count, and epochs are not separable as causal knobs. Any comparison of two LRs must match minibatch size, epochs, and optimizer-step count, and must log the realized KL.
- The local `target_kl` stop is epoch-end, full-rollout, so it can only skip later epochs, not individual minibatch steps. Its effect depends on how far KL moves in epoch 1; with 4 epochs and 32 minibatches, a too-large LR can overshoot within an epoch before the stop triggers. Logging per-epoch KL (already in `epoch_approx_kls`) gives the evidence needed.
- Adam normalizes per-parameter gradient scale, so raising or lowering LR changes the step size directly, and the Adam moment state (`exp_avg`, `exp_avg_sq`, step count) restored from a checkpoint affects the first updates after resume. Andrychowicz et al. and Engstrom et al. both keep Adam (with LR tuned) as the baseline; no source here studies Adam-state reset effects in PPO specifically.
- A regression (or improvement) observed at an LR change plus continuation cannot be attributed to the LR alone when training seed, optimizer state, training-data count, and evaluation endpoint all differ.

### Gaps
- No primary source found that quantifies the Adam-moment-restore effect on PPO after resume. Not searched further.
- No source tested actor vs critic vs shared optimizer LR in PPO. Local note: teacher is shared-trunk; the prior first-minibatch shadow measurements in the packet are not reproduced here.

## 2. Empirical LR sensitivity: what the three core papers actually show

### Takeaway
All three papers report that LR matters strongly. The claims about annealing are narrower: Engstrom et al. find LR annealing is among the optimizations that mattered on two MuJoCo tasks under their grid; Andrychowicz et al. find linear decay gives small gains (secondary). Neither supports annealing as universally best.

### Cited Findings
- **Schulman 2017 (PPO), §6 and Appendix A.** Hyperparameter tables: MuJoCo 1M-step benchmark uses a fixed Adam stepsize `3×10⁻⁴`, 10 epochs, minibatch 64, horizon 2048, γ 0.99, λ 0.95 (Table 3). Roboschool uses "Adam stepsize was adjusted based on the target value of the KL divergence" (Table 4). Atari uses `2.5×10⁻⁴×α` and clip `0.1×α`, where "α is linearly annealed from 1 to 0 over the course of learning" (Table 5). — [Schulman 2017, Appendix A, arXiv:1707.06347](https://arxiv.org/pdf/1707.06347).
- **Schulman 2017, Table 1 (continuous, 7 envs, 3 seeds, 21 runs per setting).** Normalized scores: no clip/penalty −0.39; clip ε=0.1 0.76; clip ε=0.2 0.82; clip ε=0.3 0.70; adaptive KL d_targ 0.003 0.68, 0.01 0.74, 0.03 0.71; fixed KL β 0.3–10 0.62–0.72. The paper states "the KL penalty performed worse than the clipped surrogate objective." — [Schulman 2017, §6.1 Table 1, arXiv:1707.06347](https://arxiv.org/pdf/1707.06347).
- **Engstrom 2020, Fig. 1 (Humanoid-v2 and Walker2d-v2, 24 optimization configurations, 5 seeds, LR grid, best LR per configuration).** "reward normalization, Adam annealing, and network initialization each significantly impact the rewards landscape with respect to hyperparameters, and were necessary for attaining the highest PPO reward within the tested hyperparameter grid." — [Engstrom 2020, Fig. 1 caption, arXiv:2005.12729](https://arxiv.org/pdf/2005.12729).
- **Engstrom 2020, §3 item 4.** "Adam learning rate annealing: Depending on the task, the implementation sometimes anneals the learning rate of Adam... for optimization." — same source.
- **Engstrom 2020, footnote 5.** They add a "KL decay ... inapplicable to PPO but meant to serve as the analog of Adam learning rate annealing" for TRPO+. — same source.
- **Engstrom 2020, Appendix A.1.** LR schedule is one of the grid dimensions for PPO-M and PPO; the code-level optimizations were "taken from the OpenAI baselines repository." — same source.
- **Andrychowicz et al. §3.7 (optimizers).** "the learning rate influences the performance very strongly ... with the default value of 0.0003 for Adam (C24) performing well on all tasks." On linear decay to 0: "increases the performance on 4 out of 5 tasks but the gains are very small apart from Ant, where it leads to 15% higher scores." Recommendation: "Use Adam ... and a tuned learning rate (0.0003 is a safe default). Linearly decaying the learning rate may slightly improve performance but is of secondary importance." — [Andrychowicz 2020, §3.7, arXiv:2006.05990](https://arxiv.org/pdf/2006.05990).
- **Andrychowicz et al. scope.** Five Gym continuous-control tasks (Hopper-v1, Walker2d-v1, HalfCheetah-v1, Ant-v1, Humanoid-v1); "train over 250'000 agents"; baseline "scaled up to 256 parallel environments." — [Andrychowicz 2020, Abstract and §2, arXiv:2006.05990](https://arxiv.org/pdf/2006.05990).
- **Andrychowicz ICLR 2021 title.** The arXiv v1 extracted here is titled "What Matters In On-Policy Reinforcement Learning?"; the ICLR 2021 version is "What Matters for On-Policy Deep Actor-Critic Methods? A Large-Scale Study." **[snippet]** from [iclr.cc poster 2527](https://iclr.cc/virtual/2021/poster/2527) and [Google Research pub50213](https://research.google/pubs/pub50213/). The ICLR version was not read, so any changed numbers there are unchecked.
- **Schulman 2017 and Engstrom 2020 differ on what matters.** Schulman's ablation found clipping ε and penalty choice matter (Table 1); Engstrom's Fig. 1 attributes large effects to annealing among four code-level optimizations (on two tasks, with a per-config LR tuned). These are different scopes; do not merge them.

### Inferences
- Literature supports "LR matters, tune it jointly with minibatch and epochs" (Andrychowicz §2, Engstrom §4) and "PPO's published results depend on implementation details including annealing" (Engstrom Fig. 1, limited scope).
- Literature does not support "linear annealing is the best schedule." Andrychowicz reports small gains and calls it secondary. Schulman's MuJoCo table uses fixed LR.
- Schulman's Atari table also anneals the clip coefficient (`0.1×α`). A schedule change in our D2 lineage may therefore alter the trust-region width as well, unless clip is held fixed deliberately.

### Gaps
- Engstrom et al.'s exact per-task LR grids and the annealing-on/off effect size per task were not extracted beyond Fig. 1's qualitative statement; the appendix tables were not read in depth.
- Andrychowicz et al.'s Fig. 65 (linear decay effect per env) and Fig. 69 (LR sensitivity) were referenced by figure number only, not read as images.

## 3. Scheduled LR: schedule forms, denominators, floors, and checkpoint behavior

### Takeaway
Two reference implementations use different progress denominators: CleanRL (per PPO iteration, decays to 0 at the last iteration) and SB3 (per environment timestep, updated before each `train()` call, default `learning_rate` `3e-4`). Neither handles resume explicitly for our custom checkpoint format. Our continuation must store the schedule's progress counter in the checkpoint and re-apply LR after `optimizer.load_state_dict`, because that call overwrites the saved param-group LR.

### Cited Findings
- **CleanRL `ppo_continuous_action.py` (master branch, unpinned).** `learning_rate: float = 3e-4` (line 47); `anneal_lr: bool = True` (line 53), help "Toggle learning rate annealing for policy and value networks"; `num_iterations = total_timesteps // batch_size` (line 148); `optimizer = optim.Adam(agent.parameters(), lr=args.learning_rate, eps=1e-5)` (line 183). Schedule at the start of each iteration: `frac = 1.0 - (iteration - 1.0) / args.num_iterations; lrnow = frac * args.learning_rate; optimizer.param_groups[0]["lr"] = lrnow` (lines 201-205). So iteration 1 uses `lr₀`, the last iteration uses `lr₀ × 1/num_iterations`, and the floor is not 0 but `lr₀/N`. — [CleanRL ppo_continuous_action.py, GitHub master](https://raw.githubusercontent.com/vwxyzjn/cleanrl/master/cleanrl/ppo_continuous_action.py) (`raw/cleanrl_ppo_continuous.py`).
- **CleanRL `target_kl`.** Default `None` (line 75). Early stop after each epoch: `if args.target_kl is not None and approx_kl > args.target_kl: break` (lines 307-308). `approx_kl` is the value from the most recent minibatch in that epoch, not a full-rollout mean. Unlike our local epoch-end check, this is a minibatch-sampled KL.
- **CleanRL logging.** `writer.add_scalar("charts/learning_rate", optimizer.param_groups[0]["lr"], global_step)` (line 315) logs the realized LR each iteration; `clipfracs` and `approx_kl` are logged (lines 319-321).
- **SB3 `PPO.__init__` default.** `learning_rate: float | Schedule = 3e-4` (line 84 of `ppo/ppo.py`, master). — [SB3 ppo.py, GitHub master](https://raw.githubusercontent.com/DLR-RM/stable-baselines3/master/stable_baselines3/ppo/ppo.py) (`raw/sb3_ppo.py`).
- **SB3 progress and update timing.** `_update_current_progress_remaining(num_timesteps, total_timesteps)` sets `progress = 1.0 - num_timesteps / total_timesteps` (base_class.py lines 278-285). The learn loop calls it after `collect_rollouts` and before `self.train()` (on_policy_algorithm.py lines 323-330). So the LR used in the first `train()` call already reflects the rollout just collected. `train()` calls `self._update_learning_rate(self.policy.optimizer)` (ppo.py line 191), which sets every optimizer's param-group LR from `self.lr_schedule(self._current_progress_remaining)` (base_class.py lines 287-301). Denominator: environment timesteps (transitions counted by `num_timesteps`), not PPO updates and not wall time. — [SB3 base_class.py, on_policy_algorithm.py, GitHub master](https://raw.githubusercontent.com/DLR-RM/stable-baselines3/master/stable_baselines3/common/base_class.py) (`raw/base_class.py`, `raw/on_policy_algorithm.py`).
- **SB3 schedule helpers.** **[summary]** From WebFetch of `common/utils.py` on master: `LinearSchedule(start, end, end_fraction)` returns `start` at progress 1, and `end` once `(1 - progress_remaining) > end_fraction`; in between it is linear `start + (1-progress)*(end-start)/end_fraction`. `progress_remaining` runs 1→0. `constant_fn`, `get_schedule_fn`, and `get_linear_fn` are deprecated; `ConstantSchedule` and `FloatSchedule` are current. The summary did not return line numbers; verify before reuse. — [SB3 utils.py, GitHub master](https://raw.githubusercontent.com/DLR-RM/stable-baselines3/master/stable_baselines3/common/utils.py) (WebFetch-summarized, not saved).
- **SB3 KL early stop.** `if self.target_kl is not None and approx_kl_div > 1.5 * self.target_kl: continue_training = False; break` (ppo.py line ~267). `approx_kl_div = mean((exp(log_ratio) - 1) - log_ratio)` per minibatch. Note the 1.5× factor, which differs from CleanRL's 1.0× and from our 1.0× local epoch check. — [SB3 ppo.py, GitHub master](https://raw.githubusercontent.com/DLR-RM/stable-baselines3/master/stable_baselines3/ppo/ppo.py).
- **PyTorch `Optimizer.load_state_dict` overwrites group hyperparameters.** `update_group(group, new_group)` returns the saved group dict with `params` reattached (`torch/optim/optimizer.py` ~lines 1049-1058 on `main`). So LR saved in the checkpoint replaces the LR set by the constructor or by a scheduler on the new process. — [PyTorch optimizer.py, GitHub main](https://raw.githubusercontent.com/pytorch/pytorch/main/torch/optim/optimizer.py) (`raw/torch_optimizer.py`).
- **Local restore path (confirmed in code).** `checkpoints.py` `restore_learner` calls `model.load_state_dict(strict=True)`, then `optimizer.load_state_dict(state["optimizer"])`, then `restore_rng` (lines 138-142). Nothing re-applies a schedule after load. The D2 runner asserts saved and effective LR equal `3e-5` (`assert_saved_optimizer_lr`, `assert_effective_lr`), so any schedule added later must be re-applied after restore and the assertion updated.
- **Local prep state.** Frozen continuation prep (`D2-retained324-continuation-prepare-luna-20261026-r1/`) uses `LEARNING_RATE = 3e-5` and `validate.py` checks `group['lr']==3e-5` with "same_LR_no_override". No scheduler or LR-schedule key appears in its runner, adapter, or registration files (grep for `sched|anneal|lr_|learning_rate|kl_threshold|cosine|warmup`: only constant `LEARNING_RATE`). Not edited.
- **Local progress/horizon.** The audit report (`D2-retained300-parent-terminal-audit-20261026-r1/report.md`) gives observed outer duration 1137.0s for the 60-update continuation (≈19 s/update) and total completed cost 9758.4s. The selected 324 checkpoint is local 24 / cumulative 372; the endpoint 360 (local 60 / cumulative 408) is discarded.

### Inferences
- A schedule is a function of an explicit counter. For our runs the natural counter is the **update index since the frozen parent**, not wall time and not environment transitions. CleanRL-style `frac = 1 - (u-1)/U` or SB3-style progress both work if `U` and the counter are fixed in the registration.
- On resume (for example, after a partial run), the counter must be stored in the checkpoint and read back. Because `load_state_dict` overwrites LR, the code should set `param_group["lr"]` from the counter after load, or store the schedule state and verify it. Do not reset the counter to 0 at each 60-update campaign, since that restarts the schedule and makes arms non-comparable.
- Keep the model weights, Adam moments (`exp_avg`, `exp_avg_sq`, step), and RNG state exactly as restored; only the LR value changes. Adam's internal state is not reset by an LR change.
- SB3's "progress already decayed before first train" behavior is a design choice in their code. For our arms, define the schedule explicitly: which update gets which LR, and whether update 1 of the continuation uses `lr_start`.

### Gaps
- Pinned commit SHAs for CleanRL and SB3 are not known; the files are from `main`/`master` at fetch time. Record exact commits before citing externally.
- Not verified: whether SB3's `save()` persists `num_timesteps` and `_current_progress_remaining` (the `save()` body at base_class.py line ~819 was not printed).
- Cosine, warmup, and step/plateau schedules have no PPO-specific primary evidence in this research. See Q4.

## 4. Adaptive LR: observed-KL adaptation vs PPO adaptive KL penalty vs target-KL early stop

### Takeaway
Three different mechanisms are often confused. (a) **Adaptive KL penalty** (Schulman 2017 §4) adapts the coefficient β on a KL penalty term in the objective; it does not change the optimizer LR. (b) **Target-KL early stop** (CleanRL, SB3, local D2) stops further epochs when KL exceeds a threshold; it does not change LR. (c) **KL-driven LR adaptation** (rsl_rl, rl-games) changes the optimizer LR each update or epoch from observed KL. Only (c) is an LR schedule, and no primary source found compares it to a fixed LR in PPO.

### Cited Findings
- **Adaptive KL penalty (PPO paper §4).** Objective `L^KLPEN = E[r_t Â_t − β KL[π_old, π]]`; after each update with `d = E[KL]`: if `d < d_targ/1.5` then `β ← β/2`; if `d > 1.5 d_targ` then `β ← 2β`. "The parameters 1.5 and 2 above are chosen heuristically." — [Schulman 2017 §4, arXiv:1707.06347](https://arxiv.org/pdf/1707.06347). Table 1 shows adaptive KL (d_targ 0.003/0.01/0.03: 0.68/0.74/0.71) below clipping ε=0.2 (0.82). — same.
- **Adaptive LR in PPO's own Roboschool experiments (Schulman 2017 Table 4).** "Adam stepsize was adjusted based on the target value of the KL divergence." The paper does not give the adaptation rule for Roboschool; the rule in §4 is for β, and footnote 3 points to an adaptive-stepsize baseline implementation for vanilla policy gradient (`berkeleydeeprlcourse` hw4). — [Schulman 2017, Table 4 and footnote 3, arXiv:1707.06347](https://arxiv.org/pdf/1707.06347). This is the only primary PPO-paper source found where the LR itself was KL-adapted.
- **rsl_rl (`algorithms/ppo.py`, main branch).** Defaults `schedule="adaptive"`, `desired_kl=0.01`, `learning_rate=0.001` (lines 52-57). Inside the update loop, `kl_mean` is computed between old and new distribution parameters; if `kl_mean > 2×desired_kl`, `lr = max(1e-5, lr/1.5)`; if `kl_mean < desired_kl/2` and `kl_mean > 0`, `lr = min(1e-2, lr×1.5)`; the new LR is written to all param groups (lines 241-266). On load, `self.learning_rate = self.optimizer.param_groups[0]["lr"]` (line 406). — [rsl_rl ppo.py, GitHub main](https://raw.githubusercontent.com/leggedrobotics/rsl_rl/main/rsl_rl/algorithms/ppo.py) (`raw/rslrl_onpolicy_runner.py`). Note: the adaptation is inside the minibatch-level block by indentation; verify against the file before reuse.
- **rl-games `AdaptiveScheduler` (`common/schedulers.py`, master).** Default `kl_threshold=0.008`, `min_lr=1e-6`, `max_lr=1e-3`, `lr_multiplier=1.5` (lines 19-25). Rule: if `kl > 2×threshold` then `lr = max(lr/multiplier, min_lr)`; if `kl < 0.5×threshold` then `lr = min(lr×multiplier, max_lr)`; otherwise unchanged (lines 27-33). Called once per epoch with the average epoch KL (`a2c_common.py` ~line 1439, `self.scheduler.update(..., av_kls.item())`). A class default and a warning string in `a2c_common.py` (lines 357-358) disagree about the default max LR (1e-3 vs 1e-2 prior); the config value governs when provided. — [rl-games schedulers.py, GitHub master](https://raw.githubusercontent.com/Denys88/rl_games/master/rl_games/common/schedulers.py) (`raw/rlgames_schedulers.py`); [a2c_common.py](https://raw.githubusercontent.com/Denys88/rl_games/master/rl_games/common/a2c_common.py) (`raw/rlgames_a2c_common.py`).
- **rl-games `kl_schedule_source`.** `rlgames_ppo.py` lines 44-45 and 256-305: the KL used by the scheduler is either the reference-policy KL (`reference`) or a post-optimizer-step KL (`optimizer_step`); the latter is disallowed for RNN policies. The code comment states the post-step KL "responds to the step just taken." — [rl-games a2c_continuous.py, GitHub master](https://raw.githubusercontent.com/Denys88/rl_games/master/rl_games/algos_torch/a2c_continuous.py) (`raw/rlgames_ppo.py`; the local filename is the copy as downloaded).
- **rl-games linear schedule.** `LinearScheduler(start_lr, min_lr=1e-6, max_steps=1000000, use_epochs=True)`, `lr = min + (start-min)×mul` (`schedulers.py` lines 36-55). Epoch/frame counting per `use_epochs` flag.
- **Local D2 code.** No adaptive LR. The only KL-dependent behavior is the epoch-end target-KL stop with threshold 0.03, which skips remaining epochs but does not change LR (`ppo.py` lines ~565-567).

### Inferences
- The rsl_rl and rl-games rules are heuristic step-size controllers, not PPO-paper results. Their thresholds (`desired_kl` 0.01 in rsl_rl; `kl_threshold` 0.008 in rl-games) are library defaults; no source here tests them against fixed-LR baselines in controlled ablation.
- Our `target_kl=0.03` is 3–4× the library adaptive targets. Under an rsl_rl-style rule with `desired_kl=0.03`, LR would drop only when KL exceeds 0.06 and rise when KL is below 0.015. This is a computed consequence, not a validated recommendation.
- Adaptive LR confounds itself with the KL stop: when LR falls, KL falls, so the controller and the stop interact. Log both.

### Gaps
- No comparative evidence found for KL-driven LR adaptation vs fixed LR on PPO in continuous or game-like tasks. The Schulman Table 4 mention lacks an ablation.
- rsl_rl "adaptive" rule: the minibatch-vs-epoch placement was inferred from indentation, not confirmed by reading the full `update` function.

### Support summary (what the sources actually back)
- **Cosine decay:** no PPO-specific primary source found. One **[snippet]** search (non-RL schedules) suggested warmup and cosine help in supervised and LM training; not read, not used as PPO evidence.
- **Warmup:** no PPO-specific primary source found. Same caveat.
- **Linear decay:** supported as a weak secondary effect (Andrychowicz §3.7; Atari table in Schulman; CleanRL default on) — not as best.
- **KL-adaptive LR:** Schulman Table 4 (no ablation) and implementation code (rsl_rl, rl-games). No controlled comparison found.
- **Adaptive KL penalty:** tested by Schulman (Table 1), but it underperformed clipping in that setting.

## 5. Recommended controlled experiments for D2

### Takeaway
Run one schedule arm against a constant 3e-5 control from the same accepted checkpoint, with matched seeds and identical optimizer and minibatch settings. Preregister the endpoint and metric. Do not change minibatch size, epochs, clip, or target KL in the same experiment. The literature supports linear decay as a small effect, so the proposed 3e-5→1e-5 is a project hypothesis, not an established optimum.

### Ranked experiments

**E1 (first): constant LR control, same parent.** Arm C: parent `checkpoint-000324-candidate.pt` (sha256 `ac10d90ec...` per packet; receipt `retained-best-candidate-receipt.json` sha `76cb1573...`), Adam LR 3e-5 fixed, eps 1e-5, 60 updates, training seed fixed per arm.

**E2 (second): linear decay from the same parent.** Arm L: same parent, same seed, same 60 updates, Adam LR `lr(u) = 3e-5 − 2e-5 × (u−1)/59` for update `u = 1..60` (so `lr(1)=3e-5`, `lr(60)=1e-5`; floor = `1e-5` reached at the final update, not after it). Denominator: **update count** (PPO iteration), not transitions and not wall time. This is the project hypothesis, not a published optimum; Andrychowicz's linear decay went to 0 and gained little.
- Setting: set LR at the start of each update from the counter, before rollout; do not change within update.
- Counter: store `local_update` in the checkpoint; on resume, recompute LR from the counter after `optimizer.load_state_dict`.

**E3 (only if E1/E2 are interpretable): KL-adaptive LR.** rsl_rl-style rule with `desired_kl = 0.03` (matching `target_kl`), bounds `[1e-5, 3e-5]` (start at 3e-5), factor 1.5, applied once per update on realized epoch-mean KL. Hypothesis only.

**E4 (not recommended now): cosine or warmup.** No PPO evidence; warmup adds an extra variable (initial LR) and cosine adds curvature. Defer.

Do not run E1–E4 combined. Do not compare against the old 300-continuation branch (different seed, different LR history) as a causal control.

### Matched design details
- **Seeds:** same training seed per matched pair (use the frozen continuation seed for each arm, for example `4200000001` in `D2-retained324-continuation-prepare-luna-20261026-r1/build.py`). Replicate across at least 3 training seeds if budget allows; the single-seed result is not a causal estimate.
- **Endpoint:** fixed at local update 60 for both arms (cumulative update index fixed by the registration). Do not select the best retained checkpoint on the same 64 dev games.
- **Primary metric (preregistered):** mean survival frames on an independent evaluation set, with Q1 and Q4 reported. Choose the held-out seed set before launch; the existing 64 dev seeds are used for selection and must not be the sole evidence.
- **Secondary:** death-cause counts, per-update KL, clip fraction, entropy, grad norm, explained variance.
- **Budget:** observed 60-update window ≈ 1137 s (report.md). Task policy: 1790 s work window, one MPS experiment at a time, no seed replacement or cap increase. Therefore E1 and E2 at 3 seeds each is ~6 windows (each ~1137 s) and cannot fit one 1790 s window; the parent must decide sequencing. This is a constraint, not a result.

### Telemetry required per update (and per epoch)
- Realized LR read back from `optimizer.param_groups[0]["lr"]` at the start of each update and after each optimizer step (confirm no override by `load_state_dict`).
- Optimizer steps executed; epochs completed; early-stop flag (existing `early_stop_kl`).
- Per-epoch approximate KL (existing `epoch_approx_kls`) and mean full-rollout KL; max per-minibatch KL if feasible.
- Clip fraction (existing `clip_fraction`, per minibatch and mean).
- Entropy, policy loss, value loss, explained variance (existing).
- Pre-clip gradient norm (existing `grad_norm`; log mean and max).
- Survival: dev Q1, Q4, mean frames (existing dev evaluation), and independent eval counterparts.
- Optional (hypothesis): weight-delta norm `||θ_new − θ_old||` per update, to compare step size across arms independent of KL.

### Thresholds grounded in our budget or sources
- `target_kl = 0.03` (existing). Log how often early stop fires; if it fires in most epochs of an arm, the LR effect is capped by KL, not LR. No threshold beyond this is literature-backed.
- Library adaptive thresholds: rsl_rl `desired_kl = 0.01`; rl-games `kl_threshold = 0.008`. Useful only as a range check; not validated for Dodge.
- Schulman Table 1 `d_targ` values 0.003/0.01/0.03 gave similar scores (0.68/0.74/0.71), so the choice is not sensitive in that setting, but that is not Dodge evidence.
- Andrychowicz Fig. 65 linear-decay gain: small (4/5 tasks, "very small" except Ant 15%). Use this to size expectations, not to set a threshold.
- The reported prior runs in D2 had a 3e-4→1e-4→3e-5 sequence confounded with seeds and durations; they are not controls.

### Limitations
- All literature is on different environments (Gym MuJoCo, Atari, Roboschool, Isaac/legged). Dodge's objective (survival, continuous action, 64 envs, action repeat 4) is not represented.
- Andrychowicz baseline uses 256 envs, which differs from our 64.
- Schulman Table 3 uses minibatch 64; our minibatch is 512. Interactions with LR (their §2) mean the MuJoCo numbers do not transfer directly.
- Nothing here measures whether our current LR of 3e-5 is above or below the optimum; the literature default 3e-4 and our 3e-5 differ by 10×.
- Teacher-critic interference and first-minibatch shadow measurements are from the packet; not re-derived.
- Source code checked is `main`/`master` at fetch time, not pinned.

## Sources and retrieval
See `sources.json`. Unreachable or unverified items (ICLR 2021 full text, SB3 `utils.py` raw lines, CleanRL and SB3 pinned commits, PyTorch Adam docs text, and the cosine/warmup search results) are marked in that file and are not used as sole support for any claim above.
