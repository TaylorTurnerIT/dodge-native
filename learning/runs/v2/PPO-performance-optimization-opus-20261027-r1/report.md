# Dodge PPO performance optimization: findings (Opus r1)

Scope: read-only review of the completed baseline source
(`learning/runs/v2/progressive1000-throughput-runtime-parent-20261027-r2/`) and the saved
telemetry from the control run
(`.../progressive1000-monitored-comparison-parent-20261027-r1/progressive1000-confirmed324-20261026-r1-replica-1-control_constant_3e-5/`).
I ran no training, evaluation, native environment, MPS work, or checkpoint loading. The only
code I ran is a CPU/stdlib host microbenchmark (`host_microbench.py`, results in
`host_microbench-result.json`).

**Evidence limit:** the GPU/MPS is shared with the le-caissa encoder training. I have no isolated
device timing, so every MPS-side speedup below is an **estimate**. None of them is causally
attributed.

Line numbers below refer to `runtime/dodge_rl/ppo.py` unless another file is named.

## What the telemetry shows (measured)

| Fact | Value | Source |
|---|---|---|
| Per update (mean) | 28.15 s = collection 5.15 + PPO 22.99 + rest <0.02 | timing-result.json |
| PPO spread across 60 updates | 21.45 / 23.02 / 24.47 s (min/med/max) | progress-reports.jsonl |
| 24-update probe, same source | PPO 16.40 s, collection 3.84 s | parent brief |
| Guard: total cost | 111,833 calls, 29.36 s, which is 0.26 ms/call or **0.49 s/update (1.7%)** | progress-reports guard_seconds |
| KL early stop | **never fired**: 4 epochs × 32 minibatches = 128 optimizer steps every update; max approx_kl 0.0071 vs target 0.03 | training-metrics.jsonl |
| Episode ends | 1,877 ends, **all terminated, 0 truncated**; only **11.5%** of 15,360 steps had any reset | training-events.jsonl |
| Host minibatch gather (CPU) | 9.3 ms/epoch, about 37 ms/update | microbench |
| Durable event emit + fsync | 0.027 ms/event, about 7 ms/update | microbench |
| deepcopy of 64 EpisodeInfo rows | 0.53 ms; about 2 per step, so about 0.27 s/update | microbench |
| Categorical validation, host only | 42.5 µs vs 26.6 µs unvalidated; log_prob bitwise equal | microbench |
| Checkpoint | 0.015 s mean | timing-result.json |

Conclusion: host-side Python, I/O, guard, gather and checkpoint costs total less than about 1 s/update.
Almost all of the time is device work plus forced CPU↔MPS synchronization. PPO takes about
180 ms per optimizer step including its KL share.

Sync count per update in the current code (counted from source):

- PPO steps: about 57/step × 128 = **about 7,300**. That is 41 per-parameter gradient finite checks
  (lines 526–528), 3 `_gradient_norm` `.item()` (411–415, 529–533), the clip nonfinite check
  (534), 6 metric `.item()` (550–555), 2 model-output finite checks (198–199), 2 Categorical
  validations (513–514), ratio and loss finite checks (516, 523).
- KL passes: about 6/chunk × 128 = **about 770** (lines 566–577).
- Collection: about 10/step × 256 = **about 2,560** (lines 311–316, 344–345).
- **Total: about 10,600 blocking syncs/update.** Each sync drains the MPS queue and stops CPU kernel
  launch from overlapping GPU execution. The cost per sync on this shared device is **unknown**.

## A. Operational changes (learning-identical; keep all invariants)

Priority follows expected value divided by risk.

### A1. Delete the per-parameter gradient finite loop: `ppo.py:526-528`

- **Why it is safe:** `clip_grad_norm_(..., error_if_nonfinite=True)` at line 534 already raises on a
  NaN or Inf total norm before `optimizer.step()`. Any nonfinite gradient element makes the total
  norm nonfinite, and gradient overflow raises in both versions. The set of aborting cases is the
  same, and no step happens in either version. Only the exception type and text change
  (`RuntimeError` instead of `FloatingPointError`).
- **Removes:** 41 syncs × 128 = **5,248 syncs/update** (about 49% of all syncs).
- **Expected speedup:** **estimated** 1–4 s/update (about 5–15% of PPO), assuming 0.2–0.7 ms of lost
  overlap per sync. The actual magnitude is unknown.
- **Learning and numerics:** bitwise identical weights, Adam state, RNG and metrics.
- **Verify:** `run_tests.py` (update any test that asserts the `"Nonfinite PPO gradient"` text).
  Run the A/B synthetic MPS bench described under "Smallest combined verification" below.

### A2. Use one host sync per optimizer step: `ppo.py:512-556`

Make three changes:

1. Build `Categorical(..., validate_args=False)` at lines 312, 513 and 572. Logits are already
   finite-checked at line 198, actions are range-checked at line 399, and samples are in range by
   construction.
2. Do not call `.item()` inside `_gradient_norm`. Return the device scalar, keep the same ops, and
   still compute it before the clip.
3. Call `clip_grad_norm_(..., error_if_nonfinite=False)`. Then, **before `optimizer.step()`**, do a
   single `torch.stack([isfinite flags for logits, values, ratio, loss, grad_norm] + [loss,
   policy_loss, value_loss, entropy, clip_fraction, grad_norm, actor, critic, trunk]).tolist()`.
   Raise on any false flag. The clip uses the same math with error checking off.

- **Removes:** about 15 more syncs/step, which takes a step from about 57 to 1 when combined with A1.
- **Expected speedup:** **estimated** 0.5–2 s/update on top of A1. The host-side Categorical saving
  alone is about 16 µs × 512 calls, roughly 8 ms (measured on CPU).
- **Learning and numerics:** identical. The same tensors are converted float32→float64 by `.tolist()`
  exactly as with `.item()`, and the `sums` accumulation order is unchanged. The nonfinite abort
  still happens before the step.
- **Verify:** the A/B MPS bench must assert `torch.equal` on every parameter, on the Adam state, and
  on the metrics dict (`==`).

### A3. Skip the redundant final-observation forward on steps with no reset: `ppo.py:343-347`

- **Why it is safe:** when no slot ended, `current = result["observations"]` (line 377). The
  next step's policy forward (line 311) runs the **identical input batch** through the identical
  eval-mode model. `next_values[step]` therefore equals `values[step+1]` exactly, provided MPS
  kernels are deterministic for identical inputs.
- **Change:** on steps where `ended` is empty and `step < rollout_steps - 1`, fill
  `next_values[step]` from `values[step+1]` once that value is computed. Keep the current forward
  on every step that has a reset, because there the batch composition differs. Also keep it on the
  last step, because PPO will change the weights before the next collection.
  - Terminated rows are already zeroed.
  - No truncations occurred in this run.
  - Sampling RNG order is untouched, because forwards draw no RNG.
- **Removes:** about 227 of 512 batch-64 forwards per update (88.5% of steps), plus about 3 syncs on each
  of those steps.
- **Expected speedup:** **estimated** 0.6–1.5 s/update of collection, out of 5.15 s.
- **Learning and numerics:** identical if MPS forward is deterministic. That condition must be
  proven, not assumed.
- **Verify:**
  1. Run a CPU fake-env test with `tests/fakes.py` that runs the old and new collectors on the same
     seed and asserts `torch.equal` for every `RolloutBatch` field.
  2. Run one MPS synthetic check: the same batch-64 input through two forwards, assert bitwise
     equality, repeated many times.
  3. Optionally add a debug flag that computes both values for one update and asserts equality.

### A4. Batch the syncs in the epoch-end KL pass: `ppo.py:566-578`

- **Change:**
  1. Append each chunk's `kl.sum()` and an `isfinite(kl).all()` flag to device lists.
  2. Do one `.tolist()` after the loop.
  3. Raise on any false flag.
  4. Compute `kl_total` with the same sequential Python float64 additions.
- **Effect:** the KL value and the stop decision stay bitwise identical. About 770 syncs drop to 4
  per update.
- **Expected speedup:** **estimated** 0.2–0.8 s/update.
- **Verify:** the same A/B bench; `epoch_approx_kls` must compare equal.
- **Not exact, so held for a decision:**
  - Enlarging KL chunks from 512 to 4096 cuts launches (estimated 1–2 s/update) but changes
    per-row GEMM rounding, so KL could differ at about 1e-7. A threshold flip is practically
    impossible at 0.0071 vs 0.03, but the result is not bitwise.
  - Skipping the KL pass after the *final* epoch does not affect learning, since nothing remains to
    stop. It saves about 1/16 of PPO compute (estimated 1–1.5 s/update), but it drops the logged
    `approx_kl` and the last `epoch_approx_kls` entry. That is a telemetry contract change.

### A5. Device contention (operational; not a code change)

The same source took a PPO mean of 16.40 s in the 24-update probe and 22.99 s in the 60-update
control, with collection at 3.84 s vs 5.15 s. Per-update PPO in the control was flat at 21.5–24.5 s.
Everything here is consistent with differing load from the shared le-caissa job, but the cause is
**unknown and not attributed**. If the difference is mainly contention, avoiding overlap is
possibly the largest single lever (up to about 7 s/update observed between runs). Confirming
that needs one isolated timing, which is the user's or parent's call.

## B. Not worth changing (measured as small)

- **Guard / ledger reread:** 0.49 s/update. The only remaining saving would come from relaxing
  the per-call exact read, which the contract forbids.
- **Host gather / H2D upload-once of the rollout:** the gather is 37 ms/update. Uploading the
  96.6 MB rollout to the device once would save little and add device memory. Low priority.
- **Per-step durable events:** about 7 ms/update of fsync. Keep them.
- **deepcopy and audits in collection:** about 0.3 s/update estimated from the microbench. They are
  not worth touching the audit contract.
- **Checkpoint saves:** 0.015 s mean. **GAE** and **`_validate_batch`:** milliseconds on CPU.

## C. Experiments only (change numerics or hyperparameters; need their own arm)

- **`need_weights=False` in `models/teacher.py:57-64`:** MHA switches to the SDPA path.
  `TeacherOutput.attentions` is not consumed anywhere in `runtime/dodge_rl` outside the teacher
  (grep). The change alters float rounding and the architecture-description field
  `need_weights: True`. **Estimated** to have the largest per-forward GPU gain (10–30% of model
  time; unknown on MPS).
- **bf16/fp16 autocast** and **`torch.compile`:** numerics change; unknown benefit on MPS.
- **`update_epochs` 4→3:** about −25% PPO time, but it changes learning. KL never approached
  target, so all 4 epochs always ran.
- **Minibatch 512→1024/2048:** fewer launches and optimizer steps; changes learning dynamics.

## Smallest combined verification

Before any training launch:

1. Run `run_tests.py`, plus a new CPU fake-env bitwise-equality test for A3.
2. Run a standalone MPS A/B bench. It uses a random-init teacher (fixed seed), a synthetic
   `RolloutBatch` with the real shapes (256×64), `ppo_update` old vs new, and interleaved
   repetitions (at least 3 each, because the device is shared).
   - Assert bitwise-equal parameters, Adam state, CPU and MPS RNG state, and metrics.
   - Report the median time per update.
   - It needs no env, no checkpoint and no lease. Its MPS use needs the parent's approval.
3. Only then, run one monitored training probe to measure the end-to-end effect.

**Combined estimate for A1–A4: about 2.5–8 s/update, roughly 9–28% of the 28.15 s baseline. This is
an estimate and is not verified.**
