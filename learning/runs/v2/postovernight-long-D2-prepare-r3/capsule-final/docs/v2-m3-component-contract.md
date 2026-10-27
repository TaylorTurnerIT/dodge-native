# M3 implementation interfaces, revision 2

M2 was accepted on the pinned r2 campaign after independent native/build and Python-result audits. Acceptance is recorded in `learning/runs/v2-orchestration/milestone2-acceptance-r2.json`. This contract coordinates disjoint implementation work; it does not authorize training before integration tests and frozen review.

The [specification](SPEC_PRIVILEGED_VIT_RL.md), [registered teacher plan](v2-teacher-training-plan.md), and immutable [qualification definition](teacher-qualification-v2.json) govern behavior. No student code, imitation training, additional reward shaping, altered gate, or smaller teacher is included.

## Model interface

`python/dodge_rl/models/teacher.py` exports `OmniscientEntityTeacher` and `TeacherOutput`. Its constructor uses the registered defaults without required arguments.

`forward(global_feats, entity_feats, entity_types, entity_mask)` accepts tensors shaped `[B,1,14]`, `[B,80,16]`, `[B,80]`, and `[B,80]`. Floating inputs use float32, types use int64, and masks use bool with true meaning a valid entity. `TeacherOutput` exposes:

- `logits`: `[B,9]`.
- `values`: `[B]`, obtained by squeezing the critic's final singleton dimension.
- `latent`: `[B,128]`.
- `attentions`: a tuple containing two `[B,81,81]` attention tensors.

Preserve full self-attention: width 128, two pre-norm layers, four heads, FFN width 256 with GELU, zero dropout, LayerNorm epsilon `1e-5`, and final trunk LayerNorm. Global embedding is Linear(14,128) plus type-0 embedding; entities use a 16→128→128 GELU MLP plus their type embedding. There are no entity position embeddings. Token zero is never masked. Every custom layer explicitly requests averaged attention weights with `need_weights=True` and `average_attn_weights=True`.

Expose `actor_head` and `critic_head`, each Linear(128,128)→GELU→Linear. Initialize hidden head layers orthogonally with gain √2, final actor with 0.01, and final critic with 1.0. Keep default PyTorch trunk initialization. Supply a JSON-serializable architecture description for identity construction. Do not retain attention tensors across rollout transitions.

Tests cover default 81-token architecture, all-padding finite outputs, entity permutation and masked-padding invariance, zero padded-key attention, a meaningful valid-entity intervention, full entity-to-entity attention, actor/critic/trunk gradient routing, and fixed-input save/load equality. Synthetic CPU tests are permitted before the training review.

## PPO interfaces

`python/dodge_rl/ppo.py` exports `PPOConfig`, `RolloutBatch`, `RolloutCollection`, `compute_gae`, `collect_rollout`, and `ppo_update`.

`PPOConfig` contains the registered defaults: `gamma=.995`, `gae_lambda=.95`, `learning_rate=3e-4`, `adam_eps=1e-5`, `clip_coef=.2`, `vf_coef=.5`, `ent_coef=.01`, `max_grad_norm=.5`, `update_epochs=4`, `minibatch_size=512`, `target_kl=.03`, and `reward_scale=.1`. Record the exact value-loss formula; value clipping is disabled. Normalize advantages per minibatch. Use the nonnegative approximate KL estimator `mean(exp(logratio)-1-logratio)` and stop additional epochs when the registered epoch KL threshold is exceeded.

`RolloutBatch` contains the four observation tensors, `actions`, `old_log_probs`, `values`, scaled `rewards`, `next_values`, `terminated`, and `truncated`. Every collected batch also retains `score_delta_raw_fixed`, `alive_raw_frames`, and `elapsed_raw_frames` as int64 tensors, plus the actual environment `raw_rewards` as float32. These diagnostics are required for real collection/training and never become neural inputs. Synthetic updater fixtures may explicitly omit diagnostics when they are not testing collection. All tensors have leading `[T,N]` dimensions. Observation suffix dimensions match the model interface.

`compute_gae(rewards, values, next_values, terminated, truncated, gamma=.995, gae_lambda=.95)` returns `(advantages, returns)`. Its delta is `reward + gamma * next_value * (~terminated) - value`. Its recursive chain stops at either boundary. An alive truncation bootstraps from the actual final observation before reset. Death bootstraps from zero. The next episode's reset observation never supplies the previous episode's bootstrap.

`collect_rollout(model, env, rollout_steps, device, *, observation=None, config=None, check_guard=None)` returns `RolloutCollection` with `batch`, `observations` for the next action, `completed_episodes`, `reset_info`, and `batch_info`. The latter fields hold bounded diagnostic metadata, not neural features. Collection runs without gradients and samples actions using PyTorch RNG. Preserve actual Torch RNG state in checkpoints. Stream reset metadata after each bounded collection; the trainer separately logs initial episode metadata.

Use the existing public `VecDodgeEnv` API. Validate raw reward and completed-episode accounting against score delta, alive frames, and one termination penalty. Initialize cumulative episode counters from `env.episode_info()` at collection start, since episodes cross rollout boundaries; compare exact integer score/alive totals after each step and clear counters after explicit resets. Compare raw float32 step rewards with the integer-derived value at absolute tolerance `1e-5`; episode objective recomputation uses absolute tolerance `1e-9`. Scaled rewards are the float32 multiplication of the stored raw rewards by the fixed learner scale. Compute final-state values before explicit `reset_done`; use reset observations only for later actions. At a nonterminal rollout end, retain `V(obs_T)` as the last next value. Copy observation tensors so later environment calls cannot overwrite stored transitions.

`ppo_update(model, optimizer, batch, config, *, check_guard=None, progress=None)` returns JSON-compatible metrics. Include actual optimizer steps/epochs, loss components, entropy, approximate KL, clipping fraction, gradient norm, explained variance, and KL-stop status. Check finite losses and gradients before optimization. Report intended actor/critic gradient signals when available. Guard callbacks run before/after environment work and during minibatches so the supervisor can stop cooperatively. When supplied, mutate `progress` with zero-based epoch/minibatch, actual optimizer steps completed, and `in_update`/`complete` markers. Update the step counter immediately after `optimizer.step`, before another guard. An interrupted update retains this progress for an `interrupted_mid_update` checkpoint, which cannot be a transition parent or qualification candidate.

Tests use an independent small GAE reference with both boundaries, tagged final/reset observations, reward/death accounting, detached and independently owned rollout storage, finite frozen-buffer updates, and reproducible CPU fixed-buffer learner state. Tiny deterministic model/environment doubles are appropriate for alignment tests. No long training or device probe is part of component testing.

## Trainer and checkpoint boundary

Trainer implementation follows the read-only Opus review and parent source reconciliation recorded in `milestone3_component_trainer_opus_r1-result.json`. It owns separate `train_teacher.py`, `checkpoints.py`, `identity.py`, `supervision.py`, `dev_eval.py`, and separate tests. It must consume the interfaces above rather than edit model/PPO-owned source during parallel work. The preregistered [execution protocol](v2-m3-run-protocol.json) fixes seed namespaces, pilot statistics, development cadence, and stage transitions before the probe or training.

Before any real training, integrate all components, run meaningful tests, freeze every actual source/runtime/configuration input, and obtain independent read-only review. Only then run the registered ≤180-second device probe and separately identified ≤300-second D1 pilot. Probe weights are retained diagnostics and discarded from training. The pilot requires finite data, reward audits, intended gradients, and completed closed-loop development improvement before a longer stage. Do not infer training throughput from the M2 API benchmark.

Each later experiment has a parent-owned single lease, a full preflight budget plus 600-second receipt reserve before 13:00 UTC, a ≤1,800-second wall guard, and separate observed 6 GiB RSS and MPS-driver limits. Keep checkpoints on failures and timeout. The runner never owns the scheduler or parent ledger. Qualification B and replication E remain unopened; development uses only reserved D seeds and never gradients.

Checkpoint identities include actual neural sources, unchanged accepted native/build inputs and binary hash, architecture/features/reward/gate/config hashes, runtime versions, device/threads/chunks/batch, actual RNG states, optimizer state, counters, and per-slot next episode indices. Atomic new-path saves preserve originals. Same-run loading rejects identity mismatches. Explicit curriculum transitions permit only the registered stage/difficulty/pattern/seed-namespace changes and record immutable parent-checkpoint lineage. Initial resume is `fresh_env`: discard partial rollout state and construct new episodes at saved next episode indices. Exact live-environment continuation is not claimed.

The wrapper hard-codes only B exclusion. Every trainer constructor explicitly supplies the registered B/D/E tuple pairs, verifies their effective union and seed/exclusion version strings, and logs actual seeds. Explicit evaluation seeds intentionally bypass training exclusions, so the development entry point derives only `0xD0000000+i`, `0<=i<64`, and exposes no arbitrary seed input. Neither B nor E evaluation is implemented in this trainer.

Use 64 independent one-slot evaluation environments, each with one fixed D seed, and batch policy inference over the currently alive environments. Step only those live environments and remove each after its first termination/truncation. Never reset an evaluation environment. A single 64-slot `VecDodgeEnv` cannot support this pattern: its `step` rejects any already-ended slot. This adapts the review's proposed evaluation layout to the actual wrapper without changing Rust or adding filler episodes. Record the layout and shrinking policy batch in identity and test unequal episode lengths.

For live episode metadata, `bootstrap == !terminated`. For completed episodes only, that also equals `truncated && !terminated`. Do not apply the latter expression to alive, nonterminal steps. This qualifies the review's bootstrap assertion against `env.rs`.

Fresh-environment resume uses the wrapper's `next_episode_indices`, already defined as each current index plus one. Log every abandoned in-progress episode and its seed before replacing the environments. Pass the saved indices as `initial_episode_indices` and verify they are echoed. Reject missing/overflowed indices or a changed batch size. Checkpoint at rollout boundaries normally; partial collection/update failures retain clearly tagged diagnostics and cannot advance a stage.

Save CPU Torch RNG, Python `random`, any owned NumPy generator, and MPS RNG when MPS samples actions. Record the actual sampling backend. CPU fixed-buffer reproducibility is the tested claim; device equivalence and exact uninterrupted gameplay continuation are not claimed. Include the actual installed `.so` in the source/runtime inventory, exclude caches, and compare it to the M2-accepted extension hash before running.

Pilot before/after development evaluations use the same 64 D seeds, D1 flags, cap 2,000, and deterministic argmax. Both mean score and mean alive frames must strictly increase from fresh initial weights to the single pilot-end checkpoint, alongside the existing finite/reward/gradient requirements. There is no intermediate best-of selection or added sign-test condition. Reserve time for the final evaluation inside the 300-second budget using the fixed rule in the execution protocol.

Long stages evaluate at entry and after each 16 completed updates. End a stage immediately when a complete evaluation of the exact saved checkpoint passes the registered progress condition. Wall expiry never advances a stage. A successful pilot checkpoint may initialize D1 only through an explicit registered transition carrying learner, Adam, and RNG state; probe weights are always excluded. Phase-derived budget/mode changes are allowed only when they exactly match the immutable protocol row, never an arbitrary resource-limit increase.

No automated stage advance follows time expiry. D1/D2 development progress thresholds and B-opening conditions remain exactly those in the registered plan. Student work and visual distillation remain deferred.

## Ownership

- Model component: `python/dodge_rl/models/**`, `python/tests/test_teacher.py`, and its new run-owned evidence directory.
- PPO component: `python/dodge_rl/ppo.py`, `python/tests/test_ppo.py`, and its new run-owned evidence directory.
- Trainer component: separate trainer/checkpoint/identity/supervision files and tests, assigned after the Opus contract review.
- Parent: orchestration ledger, integration contract, project reports, acceptance, reviews, and campaign registration.

Do not modify Rust, installed extension, dependencies, historical learning code, prior receipts, another component's files, or shared package initialization without parent reconciliation.
