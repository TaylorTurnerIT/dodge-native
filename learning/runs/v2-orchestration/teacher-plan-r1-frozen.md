# Teacher PPO plan and qualification, revision 1

This plan reconciles the read-only Opus design review in `learning/runs/v2-orchestration/teacher_plan_opus_r1-result.json` with the supplied v2 architecture and measured baselines. It is registered before any v2 teacher training. The [machine-readable qualification definition](teacher-qualification-v1.json) is immutable for this overnight campaign. M3 implementation and training wait for complete M2 acceptance.

## Foundation prerequisites

M2 must pass Rust and Python episode, feature, ownership, reset, seed, hidden-state, thread/chunk, memory, and throughput checks. The 100,000-step memory campaign needs retained post-warmup samples; it cannot be replaced by one RSS value. Compare the exact frozen M0 policy through the wrapper against all 1,000 paired heuristic episodes at both D2 and D3 before the qualification gate. Initial smaller cross-checks support implementation but do not replace that final comparison. Any score, alive-frame, or terminal-reason mismatch stops qualification and requires diagnosis.

Training must exclude three fixed seed ranges before episode construction:

| Purpose | Inclusive range | Use |
| --- | --- | --- |
| Qualification B | `0xB0000000..0xB00003E7` | 1,000 paired episodes per difficulty |
| Development D | `0xD0000000..0xD000007F` | Fixed development episodes, never gradients |
| Reserved replication E | `0xE0000000..0xE00003E7` | Unopened until B passes |

The first 64 development seeds serve regular curriculum checks; the full set remains reserved. Extend the environment's configurable seed exclusions before the first PPO rollout, retaining the existing B-range default. This adds no neural feature and changes no gameplay. Record the exclusion list and stream version in run identity. Post-run seed-log intersection checks are an additional audit, not the primary contamination control. Do not use a contaminated run as qualification evidence.

## Fixed architecture and starting PPO configuration

Keep the required 81-token, width-128 teacher with two full self-attention pre-norm layers and four heads. The global token is never masked. Use the exact 14/16 feature layout, typed entity embedding, and two-layer GELU actor/critic heads. Custom MHA calls retain `need_weights=True`; attention matrices remain extractable but are not stored for every rollout transition.

Implementation defaults not otherwise fixed by the spec are FFN width 256 with GELU, LayerNorm epsilon `1e-5`, dropout zero, and a final trunk LayerNorm. Use default PyTorch trunk initialization and orthogonal head initialization: hidden gain √2, final actor gain 0.01, final critic gain 1.0. Final LayerNorm is a chosen default, not a universal requirement of pre-norm transformers. Model identity records every choice.

| Setting | Starting value |
| --- | --- |
| Environment batch × rollout | 64 × 256 decisions |
| Gamma / GAE lambda | 0.995 per decision / 0.95 |
| PPO epochs / minibatch | 4 / 512 transitions |
| Adam learning rate / epsilon | `3e-4` constant / `1e-5` |
| Policy clip / gradient norm cap | 0.2 / 0.5 |
| Value / entropy coefficient | 0.5 / 0.01 |
| Value clipping | disabled |
| Advantage normalization | per minibatch |
| Per-epoch approximate KL stop | above 0.03, logged |

Minibatch 512 is a conservative initial choice under the 6 GiB budget; the Opus proposal used 2,048. Neither has measured model-throughput evidence yet. Preserve the architecture rather than reducing its dimensions to fit a larger minibatch.

The environment always returns the specified unscaled reward. A fixed learner-side scale of 0.1 multiplies all reward terms equally; critic values and GAE use those scaled units. Keep raw score and unscaled episode-return audits separately. Record both reward definitions in identity. No running reward or observation normalization is used.

## Bounded progression

After M2 and model/PPO unit checks pass, run a device probe of at most 180 seconds on one frozen, real training-stream rollout. Compare completed end-to-end update/inference measurements on MPS and CPU with four threads; test eight CPU threads only if the same budget permits. Each device uses the same starting weights and data. Discard probe weights from training while retaining them and their logs as diagnostic artifacts. Select from completed measurements and freeze the device before the pilot. Partial or missing comparisons remain explicit; do not infer throughput from the engine microbenchmark.

Run a separately identified D1 pilot for at most 300 seconds. Require finite losses, the reward-identity audit, nonzero intended gradients, and closed-loop development improvement before a longer stage. Entropy and explained variance are diagnostic signals; a short pilot does not need a monotonic entropy decline to demonstrate learning. A failed pilot stops the sequence for diagnosis.

Each curriculum stage is a separate experiment of at most 1,800 seconds, including its development evaluations, with observed peak RSS below 6 GiB. Start it only when the full registered budget plus ten minutes fits before `2026-10-24T13:00:00Z`.

1. **D1:** patterns off, powerups on. Advance only when a completed 64-episode deterministic development evaluation at cap 2,000 has mean score at least 10 and mean alive frames at least 1,500. The shorter evaluation cap is separate from the training cap.
2. **D2:** patterns and powerups on. Advance only when a completed 64-episode development evaluation at cap 18,000 reaches mean score at least 50 and mean alive frames at least 3,060. These are progress thresholds, not qualification. Use both metrics rather than a noisy requirement that successive evaluations never decline.
3. **D3:** patterns and powerups on. Open the B qualification set only if the final checkpoint's D2 and D3 development point estimates both meet the qualification score/survival ratios.

Stage boundaries create fresh environments, drop partial rollouts, and stop GAE chains. Carry Adam state and the fixed learning rate through explicitly validated curriculum transitions. A stage ending without its progress evidence does not advance merely because time expired. Stop and investigate using the retained checkpoint.

No step or iteration budget is inferred from assumed SPS. The probe measures iteration cost; wall and resource guards remain authoritative. There is no promise of qualification overnight. The available time may yield only a learning D1 policy or partial D2 progress.

## Qualification fixed before teacher results

Use deterministic argmax and the final D3 checkpoint. Seeded stochastic evaluation is a separately labeled diagnostic, never an alternate route to passing. B is opened at most once this overnight campaign. Do not choose a checkpoint or action mode by its B score.

At both D2 and D3, evaluate all 1,000 B seeds with matching theme, K, cap, flags, startup convention, and actual score/alive accounting. Include capped episodes. Survival is the restricted mean of alive raw frames at the 18,000-gameplay-frame cap; no uncensored lifetime is inferred. Score is restricted to that same horizon.

| Required metric | Point ratio to heuristic | Bootstrap lower ratio |
| --- | ---: | ---: |
| Mean raw score | ≥2.00 | ≥1.50 |
| Restricted mean alive frames | ≥1.10 | >1.00 |

All four metric/difficulty combinations must pass. The point floors are D2 score 200.215 and alive frames 6,726.0523; D3 score 177.266 and alive frames 4,433.0418. Score lower bounds of at least two at both difficulties are a separately reported ambitious target. No score-rate requirement is implied: two score and survival lower bounds do not themselves bound their quotient.

Compute paired ratios of means using 10,000 percentile-bootstrap resamples, fixed NumPy PCG64 seed from the JSON definition, and the `linear` percentile method. Allocate family alpha 0.025 over four checks, giving lower percentile 0.625 for each. Percentile-bootstrap uncertainty remains approximate; this is not an exact finite-sample guarantee. Report medians, p90, caps, deaths, ragged K endings, display score, and confidence bounds alongside the pass/fail decision.

After a B pass, and only if the full replication budget plus ten minutes fits before cutoff, run the frozen teacher and unchanged heuristic once each on E at both difficulties. Report replication separately. Failure does not trigger reselection. If time prevents opening E, report that qualification has not been independently replicated. Gate/evaluation states never become optimization data or labels.

## PPO correctness and diagnostics

GAE must bootstrap from the actual pre-reset final observation for alive truncations and from zero for termination. Its recursive chain stops at either episode boundary. A reset observation is used for the next action, never for the preceding episode's bootstrap. Death on the cap frame remains termination. Audit unscaled episode rewards against actual score delta plus 0.01 times alive frames minus one death penalty, even when native Death events repeat on one frame.

Required tests cover a small independent GAE reference with both boundaries, tagged final/reset observation alignment, model permutation/padding invariance, zero-entity finite outputs, full 81×81 attention with zero padded-key weights, valid-entity intervention, and actor/critic gradient routing. CPU reproducibility and save/load equality are tested on fixed rollout buffers; they do not prove an unimplemented live-environment restoration path.

If learning stalls, use the cheapest discriminating check first: reward/done identities, one update on a frozen buffer, advantage/return consistency, then masking and gradient routing. Entropy collapse below 0.3 nats before D1 competence, or persistently nonpositive explained variance with no closed-loop improvement, triggers diagnosis. Explained variance alone is not proof that the actor cannot learn. Nonfinite model/loss data, resource limits, repeated KL spikes above 0.1 on three iterations, or wall/cutoff expiry stop the run and preserve evidence. No automatic identical retry or looser limit follows.

## Resources and checkpoint identity

Record native/Python RSS and its observed peak. Record MPS driver-allocated memory separately and apply an independent 6 GiB guard if used. Do not add these overlapping accounting categories and call the result RSS. All guards are cooperative; retain timestamps, sampling cadence, and limits.

Each checkpoint records model/optimizer and actual RNG states, stage/iteration/step counters, seed-stream counters/logs, full config and hash, architecture/layout/reward/feature versions, gate hash, wrapper binary hash, Rust source manifest, Python source inventory including untracked files, versions, device/thread/chunk/batch configuration, and lineage. Git HEAD and a tracked diff alone do not identify this uncommitted implementation.

Write checkpoints atomically to new run-owned paths and hash them into receipts. Preserve stage-end, periodic, and failure checkpoints. Same-run loading rejects identity mismatches. A separate curriculum-transition operation permits only the preregistered stage/difficulty/pattern/seed-namespace changes and records the parent checkpoint hash in a new manifest; it never rewrites the parent's metadata.

Initial resume mode is explicitly `fresh_env`: restore learner/optimizer/RNG state and seed-stream progress, discard partial rollouts, and start fresh episodes. Exact uninterrupted environment trajectory resume would also require wrapper/history state serialization and is not claimed. Fixed-buffer learner save/load tests remain meaningful. Old v1 checkpoints stay historical.

## Parent qualifications to Opus

The review was a static design pass, not runtime evidence. Parent keeps its full-attention architecture, bounded curriculum, paired gate, truncation tests, provenance, and failure-first diagnostics. Parent qualifies its post-run-only seed-collision proposal, additive RSS/MPS accounting, strict short-pilot entropy/variance requirements, implied score-rate claim, and ambiguous full-trajectory resume. Additional configurable seed reservations must be implemented and reviewed before training; no active wrapper source is changed by this document.
