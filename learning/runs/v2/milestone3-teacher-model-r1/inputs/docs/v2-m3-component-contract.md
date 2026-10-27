# M3 implementation interfaces, revision 1

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

`RolloutBatch` contains the four observation tensors, `actions`, `old_log_probs`, `values`, scaled `rewards`, `next_values`, `terminated`, and `truncated`. All tensors have leading `[T,N]` dimensions. Observation suffix dimensions match the model interface. Add explicit optional raw-reward diagnostics if needed, without adding neural inputs.

`compute_gae(rewards, values, next_values, terminated, truncated, gamma=.995, gae_lambda=.95)` returns `(advantages, returns)`. Its delta is `reward + gamma * next_value * (~terminated) - value`. Its recursive chain stops at either boundary. An alive truncation bootstraps from the actual final observation before reset. Death bootstraps from zero. The next episode's reset observation never supplies the previous episode's bootstrap.

`collect_rollout(model, env, rollout_steps, device, *, observation=None, config=None, check_guard=None)` returns `RolloutCollection` with `batch`, `observations` for the next action, `completed_episodes`, `reset_info`, and `batch_info`. The latter fields hold bounded diagnostic metadata, not neural features. Collection runs without gradients and samples actions using PyTorch RNG. Preserve actual Torch RNG state in checkpoints. Stream reset metadata after each bounded collection; the trainer separately logs initial episode metadata.

Use the existing public `VecDodgeEnv` API. Validate raw reward and completed-episode accounting against score delta, alive frames, and one termination penalty. Compute final-state values before explicit `reset_done`; use reset observations only for later actions. Preserve all mandatory B/D/E exclusions. Copy observation tensors so later environment calls cannot overwrite stored transitions.

`ppo_update(model, optimizer, batch, config, *, check_guard=None)` returns JSON-compatible metrics. Include actual optimizer steps/epochs, loss components, entropy, approximate KL, clipping fraction, gradient norm, explained variance, and KL-stop status. Check finite losses and gradients before optimization. Report intended actor/critic gradient signals when available. Guard callbacks run before/after environment work and during minibatches so the supervisor can stop cooperatively.

Tests use an independent small GAE reference with both boundaries, tagged final/reset observations, reward/death accounting, detached and independently owned rollout storage, finite frozen-buffer updates, and reproducible CPU fixed-buffer learner state. Tiny deterministic model/environment doubles are appropriate for alignment tests. No long training or device probe is part of component testing.

## Trainer and checkpoint boundary

Trainer implementation follows a read-only Opus review of this integration contract. It will own separate `train_teacher.py`, `checkpoints.py`, optional identity/supervision modules, and separate tests. It must consume the interfaces above rather than edit model/PPO-owned source during parallel work.

Before any real training, integrate all components, run meaningful tests, freeze every actual source/runtime/configuration input, and obtain independent read-only review. Only then run the registered ≤180-second device probe and separately identified ≤300-second D1 pilot. Probe weights are retained diagnostics and discarded from training. The pilot requires finite data, reward audits, intended gradients, and completed closed-loop development improvement before a longer stage. Do not infer training throughput from the M2 API benchmark.

Each later experiment has a parent-owned single lease, a full preflight budget plus 600-second receipt reserve before 13:00 UTC, a ≤1,800-second wall guard, and separate observed 6 GiB RSS and MPS-driver limits. Keep checkpoints on failures and timeout. The runner never owns the scheduler or parent ledger. Qualification B and replication E remain unopened; development uses only reserved D seeds and never gradients.

Checkpoint identities include actual neural sources, unchanged accepted native/build inputs and binary hash, architecture/features/reward/gate/config hashes, runtime versions, device/threads/chunks/batch, actual RNG states, optimizer state, counters, and per-slot next episode indices. Atomic new-path saves preserve originals. Same-run loading rejects identity mismatches. Explicit curriculum transitions permit only the registered stage/difficulty/pattern/seed-namespace changes and record immutable parent-checkpoint lineage. Initial resume is `fresh_env`: discard partial rollout state and construct new episodes at saved next episode indices. Exact live-environment continuation is not claimed.

No automated stage advance follows time expiry. D1/D2 development progress thresholds and B-opening conditions remain exactly those in the registered plan. Student work and visual distillation remain deferred.

## Ownership

- Model component: `python/dodge_rl/models/**`, `python/tests/test_teacher.py`, and its new run-owned evidence directory.
- PPO component: `python/dodge_rl/ppo.py`, `python/tests/test_ppo.py`, and its new run-owned evidence directory.
- Trainer component: separate trainer/checkpoint/identity/supervision files and tests, assigned after the Opus contract review.
- Parent: orchestration ledger, integration contract, project reports, acceptance, reviews, and campaign registration.

Do not modify Rust, installed extension, dependencies, historical learning code, prior receipts, another component's files, or shared package initialization without parent reconciliation.
