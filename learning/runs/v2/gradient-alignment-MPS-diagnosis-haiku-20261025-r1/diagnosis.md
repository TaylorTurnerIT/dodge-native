# Gradient alignment MPS diagnosis (read-only review)

Scope: static inspection of the FAILED prep `gradient-alignment-prepare-luna-20261025-r1` plus the parent runtime. No code, tests, training, or evaluation was run. No hypothesis below is proven unless marked as proven. Inputs and hashes are in `receipt.json`.

## Ranked findings

### 1. Real runs would fail on the output schema (proven by reading, high confidence)

`gradient_alignment.py:39-41` emits `None` for `cosine`, `norm_ratio_critic_over_actor`, and `zero_norm_reason` on ordinary nonzero groups. `zero_norm_reason` is `None` whenever the cosine is defined, so nearly every group carries a null. The parent runner `critic-diagnostic-runner-prepare-20261025-r3/runner.py:175-183` (`finite_tree`) rejects any `None` except under key `explained_variance`. If `finite_tree` walks the full metrics dict, which the user's brief says it does, every real run fails at the validation step even on CPU.

Fix: omit undefined keys instead of setting them to `None`, as the request asked. Add a test that asserts no `None` values appear in the summary.

### 2. MPS output is wrong in more ways than NaN (strong signal, cause not localized)

Compare `own/mps.log` against `own/parity.log` (CPU, same fixture, same seed, same 4 steps):

| Quantity | MPS (mps.log) | CPU (parity.log) |
|---|---|---|
| `global_preclip_norm` | 7.42808723 | 7.42808533 |
| `layers.0` actor_norm | NaN | 0.03477 |
| `layers.1` actor_norm | 0.0031855 | 0.0338575 (about 10.6x) |
| `remaining_shared_parameters` actor_norm | 0.0 | 0.006960 |
| `remaining_shared_parameters` weighted_critic_norm | 0.0 | 0.378334 |
| `embeddings_and_input_projections` actor/critic | NaN | finite |

Two points follow:

- The combined gradient check cannot catch this. The preclip norm (7.43) is dominated by head gradients. Trunk actor gradients are about 0.05 in norm, so an error of that size changes the total by roughly 0.0001, far below the observed agreement. Finite and matching combined norms do not validate the separately computed actor and critic probes.
- The `remaining` group shows exactly zero critic gradient on MPS but 0.378 on CPU. `final_norm` is shared by actor and critic, so zero there is suspicious. Coverage reports 33/33 non-None, so this is not `allow_unused` returning `None`, which `summarize` silently zero-fills.

Candidate causes, none proven:

- (a) Device-to-float64 conversion. `summarize` does `.to(device="cpu", dtype=torch.float64)` in one call on MPS tensors (`gradient_alignment.py:22-23`). A bad cast could produce NaN. It does not obviously explain finite but wrong values such as layers.1 at 10.6x and remaining at zero.
- (b) Separate `torch.autograd.grad` calls with `retain_graph=True` and `allow_unused=True` on MPS (`ppo.py:507-510`), with a second graph reused by `loss.backward()`. Multihead attention backward on MPS is a plausible place for wrong or zero values. This best fits the mixed pattern: NaN in some groups, wrong magnitude in others, zero in one.
- (c) The MPS run script is not in `own/tests`. `parity_fixture.py` calls `.cpu()` and compares enabled against disabled on CPU only. The MPS evidence therefore cannot be reproduced from the listed files.

Staged localization that discriminates (a) from (b):

1. Before `summarize`, check `isfinite` on each raw `ga[i]` and `gc[i]` on MPS, and record which parameters are NaN or zero.
2. Copy the same batch and model to CPU and compute the same two `autograd.grad` calls. Compare per parameter against MPS in float32 before any float64 cast.
3. Cast to CPU float32, check finiteness, then cast to CPU float64, check finiteness again. If NaN appears only after step 3, that is (a). If NaN or zeros are already present in step 1, that is (b) or an upstream MPS issue.
4. Add an identity check: `ga[i] + gc[i]` should equal the `.grad` of each shared parameter after `loss.backward()`, before clipping, on the same graph. This catches the case where the probe and the real backward diverge.

Do not claim a fix until step 2 agrees with CPU within float32 tolerance and the output is finite.

### 3. No finite guard in the probe path (high)

`summarize` has no `isfinite` check. NaN flows into the returned dict and only surfaces later when the runner rejects it, possibly after a full update. `ppo_update` checks finiteness for loss and gradients but not for `alignment_result`. Add a `_finite` check on the per-parameter tensors inside `summarize` (or immediately after it in `ppo_update`) so the failure is raised at the probe, with the parameter name.

### 4. Test coverage gaps (high)

- `test_gradient_alignment.py` covers only analytic cosine, ratio, zero-norm reason, and grouping for two `layers.*` parameters. It does not test `final_norm` (`remaining` group), `embeddings_and_input_projections`, the `None` omission, non-finite input rejection, or the `ga + gc == total grad` identity.
- `parity_fixture.py` asserts enabled equals disabled on CPU, which checks that the probe does not perturb training. It does not check CPU against MPS, does not check that the probe values are finite, and does not check values against an independent reference.
- Parity claims in `implementation-result.json` ("exact CPU/MPS parity") are not supported by the listed fixture. Only the enabled/disabled equality is tested.

### 5. Fixture shape is not production (medium)

`parity_fixture.py:11` draws `entity_types` from `randint(0, 9)`. Valid rows (mask True) can take type 0, which the production allowlist excludes (types 1..8 per `teacher.py` `architecture_description`, `entity_valid_types`). The teacher does not enforce this; the environment boundary does. Type 0 on valid rows therefore exercises `type_embedding[0]` gradients that production never produces. Use `randint(1, 9)` for valid rows.

The fixture is also small: 8 transitions, minibatch 4, `update_epochs=2`, `target_kl=100` (early stop disabled). It does not exercise the production 512 minibatch, epoch-end KL early stop, or 4 epochs. Note: the probe fires only on epoch 0, start 0, so a small fixture cannot show a problem that appears only on later minibatches.

Source-fixture validity note: `identity_types` 0 is accepted by the teacher but outside the production allowlist; this is "meaningful" only in that it changes which embedding rows get gradients. Low impact for the probe, but fix it.

### 6. RSS calculation is wrong on macOS (medium, measurement only)

`parity_fixture.py:36` multiplies `ru_maxrss` by 1024. On macOS `ru_maxrss` is already bytes. The logged `rss_max_bytes` 353395277824 is therefore 1024 times the true value: 353395277824 / 1024 = 345112576 bytes (about 329 MiB). Remove the `*1024`. RSS remains unmeasured in `benchmark.log` (`rss_bytes: null`), so the RSS cap is still untested.

### 7. Timing claim is not a per-update overhead (medium)

The 74% median (`0.2193` disabled vs `0.3823` enabled) is one synthetic 512-sample minibatch on CPU, three pairs, fixed order (disabled first in each pair), no warm-up. Disabled times drift from 0.277 to 0.199 to 0.219, and the tiny-minibatch run in `parity.log` shows enabled faster by 12%, so noise is at least tens of percent. Real overhead per update is one probe over total update work: `update_epochs` times minibatches per epoch, plus epoch KL passes. That denominator depends on rollout size T x N, which is not in the inputs. MPS timing was not measured (`benchmark.log` `mps_allocated: 0`), and per-group `.to(cpu)` syncs on MPS may add cost.

### 8. Undefined-value and zero-norm semantics (low)

- `norm_ratio_critic_over_actor` is `None` when the actor norm is zero, rather than omitted (see finding 1).
- When both norms are zero, `zero_norm_reason` reports `actor_gradient_zero`. That is consistent but undocumented; decide and test it.

## Parent-receipt check

`learning/runs/v2/d2-continuation-parent-terminal-audit-20261025-r1/parent-terminal-receipt.json` exists now, with SHA-256 `fce4262d97f4cca11d8c28dd68fe4a4ec8fa48ba747c393ab864a380f07f90a3`, matching the brief. The `implementation-result.json` limitation "receipt path absent" is a path-resolution error in the prep, not a lineage failure. The authority `learning/runs/v2/gradient-alignment-parent-prepare-20261025-r1/parent-plan.json` also exists (3009 bytes).

## Unchanged-input checks

- Teacher SHA-256 `e4d7f597...` matches `implementation-result.json` `unchanged_teacher_sha256`.
- Parent `ppo.py` (`abf25f32...`) differs from the prep `ppo.py` (`0230e6b2...`) only by the gradient-alignment flag, the probe block, and the metrics wiring (`diff` reviewed). The native `.so` was not hashed.

## What was not done

- No experiment, training, evaluation, or MPS run.
- No modification of any source, test, or log.
- `partial r2` not read.
- Accepted-performance context (132 updates, Q1 565.8125, Q4 2786.25, mean 1518.75 alive frames) noted; no real-training diagnostic data exists.

## Priority order for the Luna repair (recommendation)

1. Omit undefined keys; make `summarize` raise on non-finite input (findings 1, 3).
2. Localize the MPS divergence with the staged procedure in finding 2 before any further integration.
3. Add the identity test and the `final_norm` / embedding grouping tests; add a real MPS-vs-CPU script under `own/tests` so the provenance gap closes (findings 2c, 4).
4. Fix fixture types and RSS calculation (findings 5, 6).
5. Re-measure per-update overhead with rollout-sized inputs, randomized order, and warm-up, on the device actually used (finding 7).
