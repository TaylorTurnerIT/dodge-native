# Critic same-batch diagnostic: registration design (r1)

Design only. Nothing was run, decoded, imported, or edited. Current best cohort (checkpoint-000050, 64 fixed D2 dev seeds, best-of-24, not held-out): survival **Q1=648.25, Q4=4508.8125, mean 2240 frames**; final old checkpoint mean 1654.546875. One-shot long D2 failed outer acceptance; all its weights stay training-ineligible.

## Chosen plan
One new isolated one-shot diagnostic run `critic-diagnostic-D2-20261025-r1`: start from the accepted D1 parent, run a fresh D2 phase for **at most 48 updates**, with same-batch critic instrumentation. Learner settings are those of the frozen D2 config, unchanged.

## Lineage (permitted)
- Parent: `learning/runs/v2/milestone3-D1-curriculum-r1/checkpoint-000009-candidate.pt`, sha256 `ce9c03c8…0544f` (verified by hash in this design).
- Anchor: `milestone3-D2-freeze-r1/accepted-parent-anchor.json` (sha `4e9f1288…7197413`): phase D1, run `v2-m3-D1-20261024-r1`, run_result `3475d2b8…aa18` (verified), supervisor_exit_code 0.
- Old terminal validation, unchanged: extract `frozen-source.tar.gz` (sha `3b4b1e4f…65bd`) to a task-owned dir. Run frozen `validate-transition.py` (sha `72c34ea7…0c55`) with the original venv and the **old** installed extension `967c7249…5583` against the parent. The output must equal the stored `transition-validation-receipt.json` result (exit 0, `certificate_passed`). Use a separate subprocess with no training. Current `identity.py` (`50775b2e…a053`) stays strict and is not used to bless the diagnostic.
- Diagnostic transfer binding, new and separate: a new schema `critic_diagnostic_registration_v1` with its own validator in the run dir. It binds the parent sha, frozen D2 config sha `2d8eb562…7fe3`, new runtime `022d41dd…997e`, the source tree hash, and the fresh seed. It restores exactly the components that the frozen D2 transition path restored from D1. The parent must read frozen `train_teacher.py`/`checkpoints.py` and record which of model/Adam/RNG that path restores, then copy that set exactly. Missing or ambiguous: blocker, do not guess. After load, re-hash state tensors and compare them to the parent's decoded values.

## Runtime / source binding
- Native: isolated `death-telemetry-parent-validation-20261025-r1/runtime/dodge_rl/_native.cpython-312-darwin.so` `022d41dd…997e` (wheel `43f110e3…5849`), put on the path for this run only. Do not install it. Old `967c…` stays untouched. This is a deliberate break from old identity, so the result is diagnostic-only and is not the old foundation or qualification.
- Python: diagnostic `ppo.py` from the implementation child after parent review. The full `python/dodge_rl/*.py`, runner, validator, and config tree is hashed before launch and after exit. Pre and post hashes must match. Any drift fails the run.
- Gate: future v3 survival predicates (`survival_gate.py` `11257111…41`, policy `bfcbee16…ae`) are reported only. They are not a pass criterion here and are not bound as qualification.

## Learner/caps (unchanged settings)
Use the frozen D2 config as is: lr 3e-4, Adam eps 1e-5, clip 0.2, epochs 4, target_kl 0.03, minibatch 512, rollout 256×64, K=4, γ 0.995, λ 0.95, vf 0.5, ent 0.01, grad-norm 0.5, reward_scale 0.1, mps float32, architecture and reward unchanged. Changes are limited to these fields:
- `run_seed`: a fresh u32 episode-stream contract, drawn from OS entropy at registration and recorded before launch. It excludes the B/D/E ranges `[2952790016,2952791015]`, `[3489660928,3489661055]`, `[3758096384,3758097383]` and the 64 fixed dev seeds.
- Caps: ≤48 updates, which is normal successful termination. 1800 s total wall, including preflight, evaluations, and receipts. RSS ≤6 GiB and MPS driver ≤6 GiB, checked separately. 0 retries. Use the existing cooperative guard semantics from `supervision.py`, plus the existing owned-pgid stop/reap. Add no new grace windows, watchdog, or IPC.
- Reference pace: the frozen D2 run did 104 phase updates in 1800.44 s, including evaluations. Estimate for this run: about 830 s of training plus 3×64 evaluations, so about 1000–1200 s. That leaves headroom below 1800 s. The diagnostic pass is one no-grad forward over 16384 transitions per update, a few percent extra.

## Metrics, raw per update (jsonl)
Pre-optimization, frozen batch (R = GAE return, V0 = rollout-time value):
- n, Var(R), mean(R), Var(V0), Cov(R,V0)
- residual r0 = R−V0: mean, Var, MSE. MSE = Var + mean² is checked numerically.
- EV0 recomputed. It must equal the logged EV within 1e-6, otherwise the instrumentation is wrong.
- Optional stratum count: transitions whose GAE window contains a terminal vs. none. Counts and moments only, not Monte Carlo targets.

After the last executed epoch (including a KL early stop): V1 = critic(same obs), computed with no_grad, chunked by 512, same device/dtype.
- r1 = R−V1: mean, Var, MSE; in-sample EV1
- ΔV = V1−V0: mean, RMS
- corr(ΔV, r0)
- non-finite counts, diagnostic seconds, peak memory

Out-of-sample signal: the next update's EV0 is the post-update critic on fresh data. Report the pair (EV1_t, EV0_{t+1}). No EV threshold (0.55 rejected), no target-variance proxy, no causal claim from grad norms. Grad norms are logged as before, not interpreted.

Evaluations: three evaluations on the 64 fixed D2 dev seeds: the parent at update 0, then updates 24 and 48. Each reports survival Q1/Q4/mean (frames), score, native first-fatal-contact death causes, and caps.

## Required implementation tests (child, before launch)
- Bitwise parameter, optimizer, and RNG equality with diagnostics on and off over ≥2 updates on a deterministic CPU fixture. This proves the diagnostic pass consumes no RNG and does not change train/eval mode or gradients.
- Moment identities on synthetic data.
- Recomputed EV0 matches the existing EV.

## Scope (candid)
- Covers early D2, updates 0–48 from D1 (first-20 EV mean was 0.597973). It **cannot** explain the late fall (last-20 EV mean 0.317240 near update 384). It validates the instrumentation and gives an early-regime decomposition baseline only.
- The cheaper, sharper late-regime check would be no-update, inference-only critic statistics on fresh rollouts from late long-D2 checkpoints. It is not chosen and not authorized. Those weights are ineligible under existing contracts, and the post-update arm would require optimizer steps on failed weights. It needs a separate explicit user grant scoped to "read-only decode + rollout, no optimizer step, outputs non-promotable".
- Answering the late question within permitted lineage needs a later, separately registered long run from D1 with this instrumentation.

## Outputs / failure / cleanup
- New dir `learning/runs/v2/critic-diagnostic-D2-20261025-r1/` only: registration, preflight receipts, pre/post hashes, metrics jsonl, evaluation jsonl, resources, terminal receipt.
- Checkpoints are named `diagnostic-*.pt` with a sidecar `{diagnostic_only:true, training_eligible:false, promotion:none}`. The distinct schema means old validators reject them as parents.
- Any preflight mismatch: status `blocked`, no launch. Any runtime cap or error: status `failed`, artifacts kept, pgid reaped, a no-orphan process inventory recorded, no retry. Success means 48 updates, 3 evaluations, and matching post hashes. Never automatic stage promotion, state/doc edits, B/D3/E, or student work.
