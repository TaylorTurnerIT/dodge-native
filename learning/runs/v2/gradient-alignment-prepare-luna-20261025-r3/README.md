# Isolated CPU-shadow gradient alignment preparation

This preparation adds opt-in `gradient_alignment_diagnostics` to the cloned PPO runtime. Default remains off. The probe snapshots a CPU copy of pre-step weights and the first selected minibatch in epoch zero, then runs actor and critic `autograd.grad` calls only on that separate CPU graph after the unchanged live optimizer step.

Output labels `backend: cpu_shadow`, `measures_live_MPS_gradients: false`, and `snapshot: first_minibatch_pre_optimizer_step`. It reports CPU float32 reference vectors reduced as CPU float64, global/per-layer dot, cosine, and norms, shared-parameter coverage, plus separately labeled live preclip norm and clip coefficient. Head parameters are excluded. Undefined cosine and ratios are omitted at zero norm. No optimizer step, projection, or causal claim is made.

## Evidence

- Analytic and baseline suite: 48 passed.
- CPU one-thread exact enabled/disabled model, Adam, RNG, metrics, batch, modes, and gradient buffers: pass; disabled repeat control exact.
- MPS four-thread: exact parity fails. Disabled repeat control also fails at `adam.state.6.exp_avg`, max absolute delta `1.1641532182693481e-10`; enabled comparison fails at the same tensor and delta. See `own/parity-final.log`. This remains a blocker; no tolerance was applied.
- Synthetic 512-sample, one-minibatch timing used one warmup pair and three fixed-order pairs per device. Mean added time: CPU 0.4837 s, MPS 0.2935 s. This is per probed minibatch, not a full PPO update overhead estimate.
- Peak RSS: CPU 1,456,275,456 bytes; MPS 1,650,245,632 bytes. MPS peak allocated 1,285,632 bytes; driver allocation 2,315,075,584 bytes. All below 6 GiB.
- Protected checkpoint, sidecar, parent receipt, and native extension hashes match their before hashes. No checkpoint was loaded or changed.

## Limits and remaining work

This is a CPU reference measurement, not native MPS gradient alignment. Exact MPS live trajectory parity is not established because the disabled baseline itself is nondeterministic at tiny scale. The measurement is not approved for training or integration until Haiku review and parent reconciliation. No real environment, rollout, campaign, registration, or launch was run.
