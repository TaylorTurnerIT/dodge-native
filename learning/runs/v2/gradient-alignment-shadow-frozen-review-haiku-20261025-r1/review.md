# Frozen review: gradient-alignment CPU-shadow probe (r3 source)

Scope: read-only review of the frozen source at `learning/runs/v2/gradient-alignment-prepare-luna-20261025-r3/own/runtime/dodge_rl/{ppo.py,gradient_alignment.py}` and the parent evidence in `learning/runs/v2/gradient-alignment-parent-prepare-20261025-r1/`. No source, test, training, eval, or rollout was run or edited. The adapter partial output was not read.

## Verdict

No blocking findings. The helper is a correct CPU reference of the live PPO objective decomposition, the pre-step snapshot boundary is correct, the probe does not alter live state, and the flag defaults off. Two evidence gaps and several scope limits must be carried into any interpretation of results.

## Hash verification

- `ppo.py` SHA-256 `b3cef91b…0c1e25f`: matches the frozen value.
- `gradient_alignment.py` SHA-256 `cd7d16ae…c1e25f`: matches the frozen value.
- Original base `critic-diagnostic-parent-prepare-20261025-r1/runtime/dodge_rl/ppo.py` SHA-256 `abf25f32…eff1d5`: matches.

## Checks performed

1. Objective equivalence. Live `loss = policy_loss + vf_coef*value_loss - ent_coef*entropy` (`ppo.py:507`). Shadow actor objective `policy_loss - ent_coef*entropy` and critic objective `vf_coef*value_loss` (`gradient_alignment.py:81-82`) sum to the same loss. Policy clipping, value loss `0.5*mean((v-R)^2)`, and entropy are formula-identical (`ppo.py:499-506` vs `gradient_alignment.py:74-80`). Advantage normalization is applied before the snapshot (`ppo.py:484-486` before `:487-495`), so the shadow uses the same normalized advantages as live.
2. Pre-step boundary. The snapshot (`ppo.py:488-495`) is taken after batch selection and before `optimizer.zero_grad` (`:496`), forward, and `backward`. The deep copy of the model therefore holds pre-step weights. Epoch 0, minibatch 0 only.
3. Train mode. `model.train()` is set at `ppo.py:468` before the snapshot, so `copy.deepcopy` carries train mode into the shadow. The teacher uses `dropout=0.0` (`models/teacher.py:46,198`) and has no BatchNorm, so the shadow forward draws no RNG. The shadow never calls the optimizer.
4. RNG and aliasing. `torch.randperm` (`ppo.py:474`) runs before the snapshot. The snapshot uses `.clone()` on every stored tensor (`ppo.py:491-495`), so no shadow tensor aliases a live buffer. `check.py:67` also asserts `data_ptr` differs.
5. Gradient coverage. Shared set = all trainable params not under `actor_head.`/`critic_head.` (`gradient_alignment.py:71-72`). Heads are excluded by name, and the live `trunk_parameters` (`ppo.py:460`) uses the same head set via ids. `allow_unused=True` returns `None`, which `summarize` handles as zero and counts in `coverage`. Layer groups follow `layers.N`, with embedding, final_norm, and remaining buckets.
6. Serialization. Cosine and norm ratio are Python floats, omitted when a norm is zero. Non-finite values raise (`gradient_alignment.py:27-30,51-52`). All keys are strings and counts are ints, so the result is JSON-serializable.
7. Live clip coefficient. `live_clip_coefficient = min(1, max_grad_norm/(preclip+1e-6))` matches `clip_grad_norm_`, and `grad_norm` is the pre-clip return value (`ppo.py:519`).
8. Parent evidence. `pointwise-invariance/result.json` shows CPU and MPS exact same-run invariance (model, Adam, grads, RNG, modes, batch) and a detected negative control. `check.py` tests state equality around capture and probe. `tests-parent-r3.log` shows 48 passed. The MPS repeat failure at `Adam exp_avg` (delta 1.16e-10) is disclosed, and the parent does not claim bitwise trajectory parity.

## Findings

### F1 (medium, evidence gap): no test ties the shadow reference to the live gradient on the real teacher

- Path: `own/tests/test_gradient_alignment.py:49-56`. The "combined identity" test uses a scalar toy `x.square().sum()` and `3*x`, not the teacher model.
- Parity fixture (`own/tests/parity_fixture.py:149-150`) checks only `live_clip_coefficient` against `live_preclip_grad_norm`. Nothing compares `actor+critic` shadow vectors to live gradients for the same weights and batch.
- Trigger: the objective decomposition is correct on paper but never executed against the teacher's actual loss.
- Consequence: a sign, scale, or head-exclusion error in the shadow would produce plausible-looking cosines with no failing test.
- Recommended before interpreting any result (not a blocker for the flag-off code): on the teacher, CPU, same pre-step weights and batch, assert `||ga+gc||` over shared params equals the CPU autograd gradient of the live `loss` restricted to shared params (atol around 1e-6). Optionally record `trunk_grad_norm` from the same step (`ppo.py:517`) and compare it to `||ga+gc||` as a sanity check. The MPS-vs-CPU gap is float reduction noise and should be small, but it is not a gate.

### F2 (low-medium, comparability): live and shadow norms cover different parameter sets

- Path: `ppo.py:519,528-529` vs `gradient_alignment.py:71-72`. `live_preclip_grad_norm` and `live_clip_coefficient` use all trainable parameters, including both heads. Shadow vectors and norms are trunk-only.
- Trigger: a reader compares `live_preclip_grad_norm` to `actor_norm` or `weighted_critic_norm`.
- Consequence: an apples-to-oranges comparison. The fields are named separately, and `parameter_count` is in metadata, but the docstring and `interpretation` string do not say "trunk only".
- Fix: state trunk-only scope in the `interpretation` string, and optionally add `live_trunk_grad_norm` to `alignment_result` (`ppo.py:528`).

### F3 (low, operational): diagnostic exception aborts the update after the live step

- Path: `ppo.py:522-527`. The shadow runs after `optimizer.step()`. A `FloatingPointError` from `summarize` or a shape mismatch propagates and ends the update with the optimizer already stepped.
- Also: `check_guard` is not polled during `measure_cpu_shadow` (roughly 0.3-0.5 s of CPU work per the parent benchmark), so cancellation latency rises by that amount.
- Default is off, so no effect on current runs. Note it before enabling in any campaign.

### F4 (low, wording): "near-zero is orthogonal" overstates

- Path: `gradient_alignment.py:63`. A near-zero raw-gradient cosine at one pre-step point on one minibatch is not orthogonality of updates. Adam's per-parameter preconditioning changes the update geometry, and the claim covers one point in training. Suggest: "near-zero cosine at this point" and drop "orthogonal" from the interpretation string.

## Scientific scope (honest statement)

- The probe measures CPU float32 reference gradients of the same loss at pre-step weights, on one minibatch (512 samples) at epoch 0 of each update. It does not measure native MPS gradients, the Adam-preconditioned update, or the realized post-step effect.
- It is one sample per update, and only the first update is included unless the run continues. It does not establish a trajectory, a causal harm, or gradient interference during training.
- Cosine on the trunk excludes heads, so head-level conflict is not measured.
- The parent's exact same-run state invariance shows the probe does not mutate live state. It does not show the probe is noise-free relative to the live run, and MPS run-to-run is not bitwise reproducible.
- The benchmark timings are synthetic (one minibatch, 3 pairs) and are not a production overhead estimate.

## Requested items, mapped

- Actor/critic objective equivalence: correct by reading; not executed on the teacher (F1).
- Pre-step boundary: correct.
- RNG or storage aliasing writes: none found.
- Gradient coverage: correct; coverage counters present.
- Serialization: correct.
- Pointwise proof adequacy: adequate for the stated claim (no live-state mutation, same-run). Not adequate as a trajectory or gradient-accuracy claim, which the parent does not make.

## Recommendation

The code can stay in the frozen state. Before the 48-update continuation is treated as evidence about orthogonality, add the teacher-level CPU identity check (F1) and state trunk-only scope (F2). Do not interpret results beyond the scope above.
