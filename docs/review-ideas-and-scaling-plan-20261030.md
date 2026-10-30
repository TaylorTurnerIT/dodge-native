# Review ideas and scaling plan, 2026-10-30

Source: an external review of the paper draft (`RL-Agent-Hyperparameter-and-Architecture-Optimization.md`, a Gemini chat export kept outside the repo, so its numbers come from the paper and are not re-verified here) plus the user's scaling hypothesis: the policy may simply need much more training on many more seeds. This document checks each idea against the repository, and lists the cheapest discriminating test for each. Nothing here authorizes training, seed use or promotion; every launch keeps its own registration, review, lease and user go-ahead.

Local planning copy of the death-telemetry handoff at commit `0775cafc59bcb6c793c6269604b49b7dda3c55a2`. The other worktree remains read-only. Local S0 findings and the control-rate and schedule proposals below supersede the corresponding unverified claims; the full review idea ledger is retained. No launch is authorized.

Evidence base: checkpoint 420 death telemetry (`learning/reports/death-telemetry-fyou-patterns-20261029/`, DODGE-014, DODGE-015 pending), the research notebook (DODGE-001..013 as of `c2778d1`), `docs/v2-*`, `python/dodge_rl/`.

## Goal and the clairvoyance rule (P6)

Build the strongest teacher whose decisions and targets depend only on information a vision student could infer from its declared short, causal frame/action history. No true future, hidden timers, environment RNG, seed identities, pattern IDs/catalogs or offscreen hidden geometry may enter actor/critic inputs, action masks, imitation/DAgger labels or auxiliary targets. New geometry/rays/grids/closing speed come only from admitted entities and measured motion. While value distillation is planned, the critic keeps the actor's information boundary, including with separate encoders. Snapshot/RNG storage for exact continuation is opaque to decision and labeling code.

**Observability audit:** DODGE-045 rechecked all three source pins from DODGE-033 and the FullState heuristic's production action path. The richer-information mismatch remains: complete enemy/rectangle lists, analytic enemy motion, raw `sh`/index-bound history and explicit pattern23 metadata exceed the four teacher arrays. Player position/velocity/size and global speed/freeze are already admitted; that does not license other FullState fields. The AABB branch does not itself draw native RNG or roll out the actual engine future, but it still fails the equal-input gate. Keep it only as a disclosed reference. A shield, labeler or imitation expert needs a separately implemented and reviewed pure admitted-input predictor. The prior audit's suggestion that privileged-label distillation could be proposed separately is **superseded by this goal**, without editing that historical audit.

DODGE-004 branches and nine-action engine oracles remain diagnostics only. Their action choices, future returns, masks and value estimates must never become training labels, targets or reward-shaping signals. Hindsight may select a registered snapshot start state; it does not authorize hindsight action supervision. Separate artifact schemas and label-loader provenance checks must enforce this boundary. The existing tensor allowlist is necessary, not proof of exact recoverability from a particular pixel stack: align measured-motion cadence/history and audit new channels before claiming student observability.

**Standing teacher metrics:** add clean, epsilon0.01, epsilon0.05, one-raw-frame delay and four-raw-frame delay panels. Epsilon replaces a policy decision with a uniform draw over nine actions, including the original; log realized action changes. Delay uses a causal FIFO action queue, holds the last applied action until due, starts neutral and clears at episode boundaries. Delay is in raw frames, not decisions; it needs a qualified raw-frame executor. Epsilon is per decision, so K1/K4 are not equal perturbation doses per game-second. Keep policy and executor RNG streams separate, domain-separated by game seed/decision/condition; neither reads native RNG. Zero-noise/delay-zero must preserve the registered clean controller. Count new clean games rather than pairing a new sampler with incompatible cached controls. Apply executor perturbations after any shield; delay queues the selected request. Never re-mask a corrupted executor action or expose future noise to the teacher.

Report Worst/Q1/Mean/Q4/Best, alive-frame milestones and early deaths for each condition, with paired noise-minus-clean contrasts and 2,000 shared-game-seed bootstrap draws. Sort each condition independently for marginal Q1/Q4. Report intended policy, post-shield selected and actually executed action switches separately, with within-episode denominators and per1,000-frame rates; preserve prior action across rollouts and exclude resets/initialization. These are standing endpoint/entry/monitor/final panels; optimizer telemetry stays per update. Noise is a proxy for imperfect execution, not a substitute for evaluating a real student's state distribution.

**Entropy and distillation:** retain the controlled entropy-schedule comparison. Alongside clean/noisy survival and switching, log teacher and post-shield target entropy, H/log9, maximum probability, top-two gap and effective support, stating which distribution would be distilled. Compare on a fixed admitted-state bank as well as each policy's own occupancy. Low entropy can discard useful soft alternatives; near-uniform labels can be uninformative. Neither entropy nor low jitter establishes calibration or distillation quality. Temperature/smoothing changes are separate interventions; never sharpen targets with a true-future oracle.

The [P6 proposal](../learning/runs/v2/teacher-observability-parent-20261030-r6/teacher-metrics-proposal-v6.json) adds explicit **unapproved** evaluation supplements, leaving old P4/P5 artifacts unchanged:

|Supplement|Counted workload|Additional ceiling|
|---|---|---:|
|A9 pilot,420 at K1/K4|5 conditions ×1,024 consumed seeds ×2 rates =10,240 new games, including clean controls|3h9m|
|Entry robustness panel|4 perturbations ×256 fixed subset seeds ×5 models =5,120 extra games|2h6m|
|Six long monitoring panels|4 perturbations ×256 seeds ×4 models ×6 looks =24,576 extra games|6h18m|
|Final robustness panel|4 perturbations ×512 seeds ×7 models =14,336 extra games|4h12m|

If approved and feasible, A9 raises the Phase0 ceiling from7h35m to10h44m. Monitoring/final supplements raise the long-run ceiling from28h50m to39h20m; entry remains separate (16h24m if all four qualification trajectories are missing;10h18m if only controls are missing). All are ceilings, not throughput forecasts. Noise panels use predetermined subsets of each clean stage cohort; recompute clean subset statistics for paired contrasts. No additional distinct seeds beyond the P5 request, and none opened/reserved now. The256-game monitoring tails have only64 samples each and remain diagnostic. Clean P5 progress/stop rules stand; no posthoc noise-based selection gate or mid-run schedule change. Source review, exact-once/lease/resource gates and Taylor's explicit go-ahead remain required. DODGE-046 holds predictions; no performance or distillation result is claimed.

## More information for the teacher: spatial grid and derived geometry (P7)

**Proposal only: no architecture implementation, data collection, fitting or launch.** DODGE-047 scopes cost; DODGE-048 registers the supervised proxy. Another CNN's reported benefit remains unverified. Recommend a pooled CNN residual first, then grid-token attention if useful; keep the entity-only control. The [cost scope](../learning/runs/v2/spatial-teacher-proposal-parent-20261030-r7/spatial-cost-scope.json) and [proxy proposal](../learning/runs/v2/spatial-teacher-proposal-parent-20261030-r7/imitation-proxy-proposal.json) specify counts, gates and limitations.

**Raster reuse needs an information audit.** Existing `features.rs:337–354,372–402` paints visible warning segments and *all* admitted enemy geometry before the64-token cap. Warning positions are absent from the four arrays; the visible-pattern scalar cannot reconstruct them. Thus feeding the existing auxiliary target tensor directly would add information relative to checkpoint420's capped entity input. That may be a legitimate later visible-information intervention, but it would confound the primary representation comparison and still need student-observability review.

For the primary comparison, reuse canonical raster geometry/conventions and rebuild a deterministic grid from the **same sanitized four arrays** every arm receives. Canonical16×16 cells cover8×8 world pixels, distinct from the planned student's8×8 grid of16-pixel patches. Proposed eight channels: current lethal occupancy; an explicitly versioned observed12-frame lethality estimate; enemy-body occupancy; powerups; player; mean measured enemy-family dx/dy; and enemy-family coverage count/64. Preserve literal signed geometry, half-open/point/inverted-box rules and the existing unknown-motion ambiguity. Do not import full-list geometry, analytic velocities or hidden history-valid flags. Overlapping velocity averages can cancel; empty grid cells mean no represented occupancy, not certified safety. The12-frame channel is an estimate from exposed `until_lethal`, not a true-future target or exact copy of native warning/charging semantics. Float-array decoding cannot promise fixed-point boundary identity.

Walls, clearance rays and free-space maps can be later deterministic channels from admitted geometry/public physics. No hidden timers, RNG, pattern IDs, future spawns or offscreen hidden boxes. The primary grid adds spatial structure, not new information. A later same-C capped-grid versus full-visible-grid contrast can isolate extra visible warnings/overflow entities; it needs its own renderer/provenance audit, dataset/labeler contract and counted budget. Give representation-comparison controls the same reviewed information. Critic input follows actor input while value distillation remains planned.

**Source-derived costs.** The current teacher is81 tokens, width128, two4-head layers and FFN256: **321,290 parameters** by source arithmetic, not a model-instantiation measurement. Proposed frontend: padded3×3 convolutions8→32→32→64, final stride2, GELU, no BatchNorm, yielding8×8×64.

|Option|Added / total parameters|Approximate core MAC ratio|Use|
|---|---:|---:|---|
|Entity-only E|0 /321,290|1.00×|Matched control|
|CNN, global pool→128|38,401 /359,691 (+12.0%)|1.17×|Cheapest; loses coarse layout|
|CNN C,2×2 pool→128|62,977 /384,267 (+19.6%)|1.17×|Recommended primary; retains four spatial regions|
|Grid tokens P,64 tokens plus two gated cross-attention blocks|171,522 /492,812 (+53.4%)|1.68×|Retains8×8 layout without changing legacy self-attention domain|
|CNN, flatten8×8×64→128|554,497 /875,787 (+172.6%)|1.19×|Defer; the projection is not a40k branch|

MAC ratios count declared convolution/linear/attention cores, excluding other operations, backward, rasterization and software overhead; they are **not measured latency or memory ratios**. The upstream≈40k estimate is reasonable only with global pooling. Appending64 tokens increases the quadratic attention term3.20×; appending256 gives17.31×. Those are not whole-model speed ratios. A warm-start dual legacy/augmented-pass blend would cost roughly3.17×/6.97× baseline core MACs respectively. A gated cross-attention residual avoids that duplicate legacy pass, at the parameter cost shown above.

**Checkpoint420 compatibility requires a real residual gate.** C adds `g * CNN(grid)` after the unchanged legacy final normalization and before original actor/value heads. P uses separate query/grid normalization and zero-gated cross-attention residuals, leaving81-token legacy self-attention intact; fixed2D positions belong only to grid tokens. Initialize branch weights nonzero and only gates zero. Zero embeddings appended to self-attention still change its softmax denominator. Zeroing both gate and branch output can prevent the gate opening; first-step branch gradients being zero while the gate learns is expected. Preserve constructor RNG isolation and require initial logits **and values**, hidden-state invariance and serialization parity before any execution. Proxy arms use fresh Adam; later PPO continuation needs a reviewed name-based mapping of legacy Adam state plus new-parameter state, never positional copying or an old-capsule edit.

A float32 eight-channel grid is8KiB/state. Saving it for64 envs×256 steps adds128MiB;512×1,024 adds4GiB, alongside about2.88GiB of existing arrays before model overhead. Derive grids on minibatches from stored source arrays rather than duplicating a full rollout grid. Raster/transfer/backward cost and6GiB RSS/MPS feasibility remain unmeasured; S1/S2 and separate resource qualification gate PPO use.

**Supervised imitation proxy, after observable-expert qualification.** FullState AABB remains ineligible. First review a stateless12-frame predictor using only the four arrays/public physics, then separately approve its bounded evaluation against420:128 consumed telemetry seeds×2 controllers at K4 =256 games. Labels come only from its deterministic chosen action and frozen tie-breaking. A weak expert limits interpretation; do not silently tune it or substitute engine-oracle labels.

Freeze a bank from512 consumed training-pool seeds, with one sampled420 and one observable-expert episode per seed at K4:1,024 games. Split by seed384/64/64 into train/validation/test, keeping both behavior episodes together. Select up to32 decision states/game by deterministic uniform reservoir independent of labels/future outcomes: at most32,768 states. Use identical original arrays, labels, minibatch order and episode-balanced weights in all architectures; derive grids on demand.420 historically trained on this pool, so this is a supervised split, not unseen-game generalization. No new cohort opens.

Fit E/C/P with **two independent fit seeds each**, six warm-start fits from the same420 weights. Fresh Adam1e-4, eps1e-5, batch512, gradient clip0.5; hard expert-action cross entropy only, critic head frozen, no PPO/value/auxiliary loss. Cap at20 epochs or2,000 steps, whichever first; fit exposure and validation-selection rule match across arms. Report held-out seed-grouped CE/NLL, agreement/macro-F1/class balance versus majority baseline, loss versus examples/time, parameter counts and measured resource/component costs when approved. Keep terminal and validation-selected weights; test/survival cannot select an endpoint and then serve as confirmation. Hard-label fit success does not qualify the resulting soft teacher. Encoder updates can change values despite the frozen critic head; this proxy supplies no qualified value-distillation targets.

Follow with6 fixed selected endpoints plus420 and the observable expert, each on1,024 consumed telemetry seeds at K1 and K4:16,384 clean games. P6 standing epsilon/delay/switch/soft-label metrics add16,384 games on fixed256-seed subsets, paired against matching clean subset rows. This is exposed development evidence; it neither proves better PPO learning nor satisfies the independent full-send entry gate. Before attributing gains to spatial bias, separately approve matched entity-only latent-MLP capacity controls (+62,837/+171,548 parameters, two fit seeds each). Scratch architecture tests remain a later separate comparison.

|Proposed packet|Hard ceiling, not forecast|
|---|---:|
|Observable-expert qualification|15m work +2m receipts =17m|
|Dataset/labels:1,024 games, at most32,768 states|1h work +3m receipts =1h3m|
|Six supervised fits|6×(20m+2m) =2h12m|
|Clean follow-up:16,384 games, four shards|4×(1h+3m) =4h12m|
|Core proxy total|7h44m|
|Standing-noise supplement|4h12m; total11h56m|
|Optional four capacity-control fits + clean follow-up|3h34m extra;5h40m including their noise supplement|

These are additional proposals, not amendments granting B5/A1 execution. Require a full-path forecast with20% margin plus I/O inside each cap, source review, exact-once/lease/seed gates and explicit approval. First approval would cover **source-only implementation**, not games/fits/PPO. No implementation occurred here; no lease/marker/seed disposition, model loading or labels. Predictions remain in DODGE-047/048; performance remains unobserved.

## Facts that change the picture

1. **The hand-written heuristic runs at 4-frame control, not 1-frame.** `docs/v2-baseline-campaign.md:21`: "Hold each policy action for at most four raw frames." It scores 6,115 mean alive frames (1,000 episodes, 15 capped) against 2,626 for checkpoint 420 with sampled actions at the same control rate (DODGE-012) and 4,387 at 1-frame. The cohorts are not paired, but the gap is large. The heuristic (`crates/dodge-rl-env/tests/support/m0_policy.rs`) simulates the player's inertia exactly, extrapolates every hazard linearly, looks 12 frames ahead over all 9 actions and keeps only actions that stay at least 4 px clear. It reads FullState, while the teacher receives capped, derived allowlisted arrays; DODGE-033 found that these are not information-equivalent. So a 12-frame look-ahead with an exact player model beats the learned policy at its own control rate: this motivates a planning intervention, but the unpaired cohorts and information mismatch prevent a planning-only explanation.
2. **The whole training lineage is only a few compute-hours.** Production training ran at about 4k raw frames/s end to end (72 updates = 4.71M frames in 1,188 s, evaluations included). S0 corrected the numbering: checkpoint420 is continuation420, cumulative852. About27.5M raw frames covers those420 continuation updates only, not the full selected ancestry or discarded campaign compute. A complete ancestral compute total remains to be reconciled. The headless engine alone does about 14.5M raw frames/s (`docs/v2-foundation-progress.md`), roughly 3,500x faster than the training loop. The benchmark gap motivates S1; different engine-only and PPO workloads do not by themselves locate the bottleneck.
3. **The 64 and its neighbours are conservative operating choices, not derived values.** `docs/v2-m3-run-protocol.json` (registered 2026-10-24 before any probe): `training_batch_size` 64, `rollout_decisions` 256, minibatch 512 ("a conservative initial choice under the 6 GiB budget; the Opus proposal used 2,048. Neither has measured model-throughput evidence", `docs/v2-teacher-training-plan.md:37`), 1,800 s per stage, a hard UTC cutoff, 6 GiB RSS and MPS caps. Early-stage observed peaks were about1GB RSS and2.4GB MPS; DODGE-013 later reached5.52GiB RSS. Headroom cannot be assumed for scaled rollouts under the unchanged6GiB limits.
4. **Seed reuse is real in the 420 lineage, at least in its Uniform #2 stage.** The base stream is unbounded (`dodge_slot_splitmix64_high32_reject_v1`, seeds from run seed, slot and episode index, about 2^32 values). But DODGE-010 trained all six models from one fixed 512-seed pool (256 historical early failures, 256 survivors), and DODGE-011 continued Uniform #2 to update 600 with an "unchanged training seed stream". S0 now confirms the same512 pool throughout retained Uniform2 producer60 plus continuation600:18,550 starts and17,846 completed episodes,36.23 starts per unique seed. Constructor starts were derived from the pinned stream; resets and completions were journaled. Independent review matched every per-seed count. This establishes reuse, not its causal effect on learning.
5. **Recent evidence does not support "same recipe, a bit more training".** DODGE-013 trained 11.8M frames per arm from 420: 4-frame training showed no clear Q1 gain over checkpoint 420 (1,625 vs 1,750), and 1-frame training regressed to 651. Checkpoint 600 had higher Mean but lower Q1 than 420 (DODGE-001). So extra updates at 64 envs and a 512-seed pool have plateaued or traded off. That is compatible with the scaling hypothesis only if the plateau comes from gradient noise, a small seed pool or short horizons, which is exactly what the tests below separate. The 1-frame regression also means the review's "fine-tune at K=1" has already been tried in one form (game-time-matched gamma and GAE, same reward); the review's version differs by also removing score from the reward.
6. **Death telemetry (DODGE-014/015 data):** enemy contact during patterns is the dominant failure; the policy changes its action at 76% of consecutive decisions (last-128 sample), turns toward the killer in the final 10-15 frames, and runs into already-filled rectangles while chased. fyou is not the cause.

## Priority order (expected immediate effect, weighed by confidence and cost)

Evidence tags: M measured here, L literature prior, R reasoned from our data, S speculative. Effect sizes are judgments except where tagged M; the order is a proposal to be revised as results arrive. Everything in Phases 1 and 2 needs at least two training seeds per arm and a fresh cohort of 1,024 or more seeds (the notebook puts the detectable difference at about 620 frames with 64 seeds and one training seed). Nothing launches without the user's go-ahead.

Phase 0, no training, hours (also tells us which later items to trust)
1. K at inference. Using K=1 already gives Q1 +934 and mean +1,761 frames [M, DODGE-012]. Add K=2 and K=3 zero-shot on the same 2,048 seeds to find the best rate. Controller adoption is the user's call.
2. Paired heuristic baseline at K=4 and K=1 on the same seeds [M after the run]. Sizes the gap to the best known controller (6,115 vs 4,434 mean) and gives a control variate for ranking.
3. Policy plus short-horizon shield [R]: veto logits using a12-raw-frame observed-motion model driven only by the teacher arrays and public physics; no FullState, RNG or true-future access. DODGE-033 blocks treating the original FullState heuristic as equal-input. A gain would support the intervention, not prove the network lacks planning or authorize a stronger teacher.
4. Counterfactual branching, DODGE-004 [R]. Diagnostic only: exact simulator/RNG restoration can inspect a true12-frame future. It shares capture/rollout infrastructure with item3 but never supplies future state to the deployable shield.
5. Argmax versus sampled per K, and checkpoint averaging of the saved 360 to 600 checkpoints [M for argmax at K=4: +275 Q1; L for averaging].
6. Seed audit and throughput profile (S0, S1). These gate scale: they say whether the 420 lineage reused a 512-seed pool and where the 3,500x slowdown versus the engine sits.

Phase 1, first training runs, cheap configuration changes
7. Gamma and lambda sweep (gamma 0.97 to 0.995, lambda 0.9 to 0.95) at K=4 and K=1 [L: the study's most important hyperparameter]. Highest value per cost among training changes, and it may explain DODGE-013's K=1 regression.
8. Fresh unbounded seed stream, larger batch, longer rollouts, learning rate retuned (S3), after the pipeline speedup (S2) [R, L]. Large effect if S0 shows pool reuse or gradient noise is the limit; effect unknown otherwise.
9. Imitation (behaviour cloning or DAgger on policy-visited states, then PPO fine-tuning) [R], gated on an evaluated expert using teacher observations. The original richer-state heuristic does not pass that gate. Privileged-label distillation is a separate possible proposal; historical heuristic performance is not an attainable guarantee.
10. K=2 and K=3 trained arms, K annealing 4 to 1, per-episode sampled K, from-scratch K=1 [S]. Order after item 7, because horizon length confounds K.

Phase 2, smaller or less certain, run as ablations once the base recipe moves
11. Learning-rate schedules [L prior; not adopted by default]: compare constant, warmup+cosine to a floor, and KL-adaptive within the registered S3/S4 matrix, with at least two training seeds per cell. Freeze the comparison once; do not use endpoint disappointments to change its schedule.
12. Per-epoch advantage recomputation, logging KL early-stop frequency, value and observation normalisation, separate actor and critic encoders, lower or decayed entropy [L].
13. Survival-only reward [S]. The heuristic scores about 100 while surviving 6,115 frames, so scoring is not inherently fatal.
14. Input and architecture changes: closing speed and relative velocity, clearance raycasts, entity pooling into the heads, D4 symmetry (after the equivariance audit), more attention depth [S].
15. Segment carry-over (do not abandon live games), snapshot-prioritised replay [S].
16. Vision-student distillation, after a stronger teacher exists.

## Local priority reconciliation and concrete approval packets

The upstream ranking is an expected-value judgment, not measured effect sizes. Keep all16 ideas. The local evidence changes dependencies and claims:

1. **S0 is done:** fixed512 reuse is confirmed; do not rerun it. **S1 comes first operationally**, despite its low position in the value ranking, because the first startup attempt failed and still holds its exact lease. There is no measured S1 bottleneck yet. A1 preserves the reviewed successor protocol rather than silently retrying the failed capsule.
2. **The heuristic gap remains unpaired and information-confounded.** DODGE-033's completed static audit found complete-list/analytic-motion/raw-history access absent from the teacher arrays. Global player state and global speed/freeze are available, so the mismatch is not simply “all physics hidden.” Unknown motion is metadata-only; a zero motion feature does not certify a stationary hazard. This does not measure how often the mismatch matters. Evaluate the original heuristic as a richer-information reference, not an equal-input teacher.
3. **The deployable shield and diagnostic oracle must stay distinct.** The shield receives only the four allowlisted neural arrays. Exact native future/RNG is confined to DODGE-004. Imitation waits for an evaluated observable expert; the original FullState code does not pass that gate.
4. **Logging moves ahead of training.** Accepted DODGE-013 flags show0/361 early stops and four epochs throughout; this weakens a “lost epochs” explanation, not the need for numerical KL/value/advantage telemetry. The instrumented diagnostic is a prerequisite, not an additional performance intervention mixed into every arm.
5. **Do not adopt LR decay by default.** That priority-list suggestion conflicts with the requested controlled schedule comparison and the absence of a clean local test. Use a locked common schedule for cheap recipe screens, then complete the registered constant/cosine/KL-adaptive matrix without silently dropping its controls.
6. **Long-run monitoring is development, not unread confirmation.** Once a rotating cohort affects stopping or selection, call it exposed development data. Reserve independent final confirmation after weights are locked. Hard wall/resource limits always stop a run, even if it is still learning. Current recovery snapshots do not yet restore live simulators; carry-over qualification gates the long run.

All following times are **proposed hard ceilings, not runtime forecasts**. The20% margin plus IO forecast gate must fit new runtime packets before full work. Prefixes use fixed registered seeds/settings and count toward the packet; no score-driven resizing, extra seeds, retry or deadline extension. A1 retains its existing reviewed2400s work/2520s total protocol. Separate6GiB RSS/MPS limits and the one-campaign rule remain unchanged. Nothing here reserves seeds, releases the held lease, consumes a marker or authorizes execution.

### Phase0: no retained training updates

| Packet | Workload | Existing game seeds | Work + receipts | Total ceiling |
|---|---|---:|---:|---:|
|A1|S1-r2:16 disposable update cells; discard all weights|512|40m + 2m|42m|
|A2|420 K2/K3 × sampled/argmax:8,192 games;256 fixed-prefix K1/K4 parity games|2048|1h + 3m|1h3m|
|A3|Original AABB heuristic K4/K1:4,096 games; cached420 controls|2048|30m + 2m|32m|
|A4|Observation-only shield K1/K4 × sampled/argmax:8,192 games|2048|2h + 3m|2h3m|
|A5|12 factual replays;4 offsets ×8 continuation RNGs ×3 controllers =1,152 branches of≤512 frames;432 oracle probes of12 frames|12|20m + 2m|22m|
|A6|4 non420 constituents + equal5-checkpoint average × K1/K4 sampled ×1,024 =10,240 new games;420 cached; selector contrasts use A2/cached groups|1024|1h30m + 3m|1h33m|
|A7|16 synthetic fixtures ×8 D4 symmetries ×9 actions ×64 raw steps; no normal-start evaluation games|0|15m + 2m|17m|
|A8|S2:baseline/optimized ×4 K ×3 disposable updates,64envs and1,536raw frames/env; discard all learned state|512|1h + 3m|1h3m|

The Phase0 runtime-packet ceiling sums to **7h35m**; it is not a promise of elapsed completion. Static observability audit DODGE-033 is already complete and adds no game/model launch. A2–A5 use the consumed telemetry range3657433088..3657435135; A6 uses its first1,024 seeds in ascending order. No new cohort is needed for these packets. A1/A8 reuse only the consumed512 training pool. All games retain the18,000-raw-frame cap.

A2's256-game prefix is a limited replay gate, not universal parity proof. Reuse the exact native/model/loop pins supported by the existing2,048-game D8 parity receipt; a materially changed capsule requires a separately specified full parity qualification. Do not expand the approved game count silently.

For A5, select the first12 eligible sampled-K4 normal/kamikaze-body contact deaths in ascending seed order with at least60 alive frames. Preserve those cases even if replay fails; no replacement seeds. Validate seeded replay against saved outcomes/action history, then validate restored full simulator/RNG/history/controller/held-action state against the newly captured factual reference. Do not claim an old canonical state hash exists if it was never recorded. K4 resumes its remaining held action and original decision schedule; K1 can act immediately. The12-frame nine-action oracle is explicitly privileged, caches its432 deterministic probes, then follows K4. The total raw-frame upper bound including12 complete prefixes is811,008.

### Shield contract before A4

Use a pure function of `global_feats`, `entity_feats`, `entity_types`, `entity_mask` and registered public physics constants; no `FullState`, native object, RNG, pattern table, hidden serial or diagnostic metadata. Predict a constant candidate action for12 raw frames, checking current plus predicted geometry, and replan at each actual K. Extrapolate only exposed motion/extent/lethality estimates. Unknown/omitted hazards and action changes make this an approximate veto, not a safety guarantee.

Argmax chooses the largest original logit among model-admissible actions; sampling uses the masked categorical distribution with one original sampler draw. If all actions pass, logits and RNG consumption must match the unshielded policy exactly. If none pass, use the original unshielded selector and log an empty-mask fallback; never resample until an action passes. Freeze the clearance rule and numerical convention before qualification. Log veto/override/empty-mask frequencies, switch rate and posthoc contact outcomes. A surviving shielded trajectory would support the intervention, not prove the policy lacks planning or automatically qualify a new teacher.

### Phase1/2: conditional training reservations, not launch-ready registrations

“Two training seeds” means two independent training-randomness vectors **per arm**, not two game seeds. Fresh stream game-seed counts depend on episode completion and must be logged; no pool or cohort is opened now. Each efficacy packet below requests a **new stage-specific1,024-seed development cohort**, common sampled K1 primary, and all endpoints plus420. Up to4 models form a shard of≤4,096 games with1h work +3m receipts. New packet cohorts cannot be reused adaptively for later selection. If a control is genuinely identical and preregistered for reuse, its duplicate training can be avoided; the table budgets all controls conservatively.

| Packet | Ordered comparison | Training trajectories × raw frames each | Training ceiling | Evaluation games / ceiling |
|---|---|---:|---:|---:|
|B0|Instrumented warm-start diagnostic before horizon tuning|4 × 1,179,648|1h33m|0 / 0|
|B1|Gamma/lambda horizon screen at K1/K4|26 × 2,359,296|28h18m|27,648 / 7h21m|
|B2|K4 pool-versus-fresh seed contrast|4 × 11,796,480|12h12m|5,120 / 2h6m|
|B3|S3 longer-rollout versus more-env allocation|12 × 2,359,296|18h36m|13,312 / 4h12m|
|B4|S3 constant-LR K1/K4 scaled baseline cells|4 × 11,796,480|12h12m|5,120 / 2h6m|
|B5|Observable-expert imitation versus matched PPO|4 × 2,359,296|6h12m|5,120 / 2h6m|
|B6|S3 constant-LR K2/K3 trained cells|4 × 11,796,480|12h12m|5,120 / 2h6m|
|B7|Annealed K and per-episode sampled K versus fixed K|6 × 11,796,480|18h18m|7,168 / 2h6m|
|B8|S4 constant-LR scratch K1/K2/K3/K4 cells|8 × 11,796,480|24h24m|9,216 / 3h9m|
|C1|Complete three-schedule fixed-K matrix, both initializations|32 × 11,796,480|97h36m|50,176 / 13h39m|
|C2|Per-epoch GAE refresh at K1/K4|8 × 2,359,296|12h24m|9,216 / 3h9m|
|C3|Observation/value normalization2x2 at K1/K4|16 × 2,359,296|24h48m|17,408 / 5h15m|
|C4|Shared/separate actor-critic encoders at K1/K4|8 × 2,359,296|12h24m|9,216 / 3h9m|
|C5|Three entropy recipes at K1/K4|12 × 2,359,296|18h36m|13,312 / 4h12m|
|C6|Original versus survival-only reward at K1/K4|8 × 2,359,296|12h24m|9,216 / 3h9m|
|C7|Single-change inputs/heads/D4/depth versus base|14 × 2,359,296|21h42m|15,360 / 4h12m|
|C8|Complete live-state carry-over qualification:64 disposable updates on existing512pool; no retained weights|0 retained|1h3m|0 efficacy games|
|C9|Ordinary versus snapshot-prioritized state starts|4 × 2,359,296|6h12m|5,120 / 2h6m|
|C10|Vision student supervision variants, last|4 × 11,796,480|32h12m|5,120 / 2h6m|

B0 is a4-trajectory short instrumented diagnostic with no efficacy evaluation and no new evaluation cohort. B1 is13 horizon cells ×2 training seeds; its training work caps are90m per K1 trajectory and30m per K4 trajectory, plus3m receipts each. B2–B8 follow the priority sequence: seed diversity and rollout allocation/scaling, observable imitation, then trained K2/K3/dynamic K and scratch. B5 is blocked until an observable expert is evaluated; at most512 demonstration games on the consumed training pool and30m demonstration work are a separate proposed prefix. That gate may defer imitation without replacing it by unapproved privileged labels or blocking unrelated approved work.

B4/B6 provide8 warm-start constant-LR trajectories and B8 provides8 scratch constant-LR trajectories. C1 adds the32 remaining cosine/KL-adaptive trajectories, preserving the requested **48-trajectory fixed-K/schedule matrix**. C1's fresh comparison evaluates all48 endpoints plus420 on1,024 new seeds,50,176 games across13 shards; earlier exposed packet cohorts are not its confirmation. An11.8M-frame scratch screen need not beat420, whose ancestry is much longer; it is not a fair basis for declaring from-scratch learning exhausted.

C2–C6 implement the priority-list item12 diagnostics/ablations and item13 reward contrast, with K1/K4 and two training seeds per condition. C7 has seven single-change conditions at a locked primary K:base,relative/closing velocity,clearance rays,action history,pooled heads,D4 augmentation,extra depth. D4 remains blocked if A7 does not validate the intended symmetry. C8 validates exact live-state recovery before C9 snapshot priority and before the long run. C10 is a last-stage **budget reservation only**: student data/model/source/resource specifications are absent, so it is not an approval-ready training request. No checklist group is a Cartesian multiplier on every other group.

Only A1 currently has a reviewed concrete launch package. The other rows are explicit seed/workload/budget proposals; they still need frozen source, real resource forecasts, registration and review before their separate launch approval. The immediate ready approval scope is **audited disposition of failed S1-r1, release only its exact lease, and exactly one A1/S1-r2 attempt under its unchanged42-minute total cap**. Approving that scope does not approve A2–C10, any new cohort or any training.

### Conditional long-run envelope (P4 sketch, superseded by P5 below)

G1 proposes one locked recipe with two training seeds, at most117,964,800 raw frames per trajectory,9h training work +10m receipts per trajectory. At most six development looks request1,024 new seeds each (6,144 total); a separate2,048-seed final confirmation remains unopened until endpoints are fixed. Each look evaluates the two models and420:18,432 development games in total plus6,144 final games. Proposed evaluation ceiling is8h work +24m receipts, making a **26h44m combined envelope**. These are ceilings awaiting measured feasibility, not an indefinite permission to continue learning.

Entry needs a prospectively frozen recipe and gains on Q1 and Mean on independent≥1,024-seed data across at least two training replicas, with game-seed and training-replica uncertainty kept separate. From-scratch extension needs its own justified entry decision rather than a naive comparison to420 at much less ancestral exposure. Predeclare progress/plateau criteria, maximum length, LR/entropy schedule horizon, checkpoint retention and collapse guards. Stop after three registered development looks without improvement under the frozen criterion, or earlier at a resource/wall/finiteness failure. Rotating monitoring cohorts are exposed development once used for stopping; they are not the independent final confirmation. No automatic extension or resume follows a stop, and full simulator/wrapper/learner carry-over must first pass C8.

The detailed machine-readable workload, per-trajectory caps and predictions are in `learning/runs/v2/priority-runlist-parent-20261030-r4/priority-run-list-v4.json`.


### Gate for the long run: P5 design and readiness

Taylor's intended sequence is Phase0/1 tuning, a prospectively qualified winning recipe, then a bounded long run while held-out performance improves. DODGE-043 records the source-only readiness audit; DODGE-044 preserves predictions for the long run. Its results remain unobserved. The [P5 protocol](../learning/runs/v2/long-run-readiness-parent-20261030-r5/long-run-protocol-v5.json) replaces only P4's G1 sketch; other priority packets and their budgets stand. No launch, cohort opening, lease disposition or promotion is authorized.

**Entry is a recipe comparison, not a comparison to an old endpoint.** Freeze the candidate and current-recipe controls before opening a fresh1,024-seed entry cohort. Require two independent training-randomness vectors per recipe, matched initialization and equal actual raw-frame exposure. A warm-start recipe uses matching warm-start controls; scratch uses matching scratch controls.420 is context, not an equal-exposure control. Model-only tuning endpoints cannot recover their missing live games: reproduce qualifying endpoints with full-state checkpoints if needed, rather than resetting environments and claiming continuity.

Proposed entry test: each training-replica pair has positive marginal-Q1 and Mean differences, and the average pair contrast has a shared-game-seed bootstrap lower95% bound above0 for both. Sort each model separately for Q1; never average paired per-game deltas to estimate a marginal tail. Use2,000 shared-seed draws, resampling each seed across every model and replica together. This is conditional game-seed uncertainty, not a training-population interval from n=2. Lock all comparisons, controller and seed vectors before execution; entry data become exposed development once used to select a recipe.

**Schedules and clocks.** Carry the winning Phase1 LR/entropy algorithm and state into a separately registered long phase. Do not choose cosine by assumption: constant, warmup+cosine-to-floor and KL-adaptive remain the requested comparison. Before approval, freeze exact starting/peak/floor rates, warmup and maximum horizon, or adaptive target/deadband/multipliers; also freeze entropy coefficients, gamma/lambda, K, N/T and minibatch. Use actual gameplay frames as the schedule clock, retaining startup frames and policy decisions separately. Define an explicit schedule transition from entry, never an accidental warmup restart. Changes to batch size require another LR qualification. No manual mid-run drops or automatic extension beyond the approved maximum.

**Long-run exposure and monitoring.** Two independent qualified entry states receive at most117,964,800 additional raw frames each. Keep every completed-update checkpoint. Six nominal barriers are19,660,800;39,321,600;58,982,400;78,643,200;98,304,000;117,964,800 additional frames. Reach barriers at completed updates without resetting live slots. Retain whole closing vector steps and optimize valid partial rollouts; freeze actual overshoot and between-replica frame-gap ceilings with the chosen N/K before launch. Unequal or budget-truncated exposures cannot masquerade as the full equal-frame result.

At each barrier, evaluate current2 and incumbent2 on the **same fresh1,024-seed cohort**, under fixed sampled K1 control. Initialization sets incumbents to frozen entry states. This costs4,096 games/look,24,576 total. Re-evaluating incumbents on the new cohort prevents changes in cohort difficulty from looking like learning. Report each replica's Worst/Q1/Mean/Q4/Best, counts reaching1,000/3,000/6,000/12,000/18,000 frames, early deaths, actual exposure and frame-gap. Plot current policies and incumbents separately: a rising best-so-far curve is not continued learning. Any deployment-controller or noise-robustness evaluation needs its own explicit packet and budget; controller choice cannot change after seeing long-run looks.

Joint progress requires both replicas' point Q1 and Mean gains against their incumbents, plus positive aggregate bootstrap lower95% bounds for both metrics. Update both incumbents only on joint progress; otherwise keep them. Three valid accepted looks without joint progress stop for plateau. Missing/failed evaluation receipts are incidents, not patience ticks and not grounds for a replacement cohort. The intervals are nominal development intervals used by a fixed stopping rule, not repeated independent confirmation. Proposed held-out collapse stops when each replica's Q1 and Mean contrast against its current incumbent has upper95% below0. A separate frozen-entry comparison during every look would require extra models and budget; it is not hidden inside this four-model design.

**Final confirmation.** Lock latest valid terminal raw2, rolling last5 averaged2, frozen entry2 and420 before opening2,048 new seeds:7 models,14,336 games. Primary comparison is latest raw versus frozen entry; averages versus raw are secondary. Report each training replica separately. Never substitute the best development checkpoint silently or promote a checkpoint. If fewer than five completed long updates exist, average the available complete updates and state the window. A failed mid-update endpoint is ineligible. Fresh final data support fixed-endpoint claims conditional on these trajectories, not certainty over training seeds or uncorrected secondary comparisons.

|Packet|Maximum work + receipts|Evaluation games|Status|
|---|---:|---:|---|
|Entry qualification, all four training trajectories missing|4×(3h+3m), plus2×(1h+3m) evaluation =14h18m|5,120|Additional to long run|
|Entry, only two matched controls missing|2×(3h+3m), plus2×(1h+3m) =8h12m|5,120|Candidate states must already qualify|
|Long training, two replicas|2×(9h+10m) =18h20m|0|Includes import/restore/update/checkpoint I/O|
|Six monitoring looks|6×(1h+3m) =6h18m|24,576|Four models/look|
|Final confirmation, four shards|4×(1h+3m) =4h12m|14,336|Seven models on2,048 seeds|
|**Long-run total, excluding entry**|**28h50m**|**38,912**|Ceiling, not forecast|

This requests9,216 distinct evaluation seeds:entry1,024 + monitoring6,144 + final2,048. None are reserved or opened now. Before training, register exclusion ranges for all future looks/final without opening their games. Exclude D7/D8/D9, consumed death-telemetry seeds, historical held-out allocations and every new evaluation range from training. Use a non-pool training stream with logged per-replica collision rejection and exhaustion failure; the finite u32 seed space cannot supply infinitely many unique seeds. Paired replicas may share a registered training-game sequence, with independent training randomness. No adaptive reuse of evaluation cohorts for later selection.

**Health and durability.** Log numerical epoch/final KL, threshold hits and stops before the maximum epoch, epochs/Adam steps, weighted entropy/value loss/clip fraction, EV and its definedness/target variance, raw GAE moments per refresh, reward/return/value scale, within-episode switch numerators/denominators, LR/entropy state, frame/seed counters, timings and memory every update. Preserve EV=null for a correctly identified near-zero target variance. Switching state carries across rollout boundaries; resets do not count as switches. Every committed complete update, including a valid final partial rollout, must have exactly one durable telemetry row.

Nonfinite data, invalid counters/distributions, missing telemetry, state/lease drift, power/resource violations and torn writes are immediate incidents. Proposed additional boundary stop: final full-rollout KL>0.15 for three consecutive completed updates; qualify and freeze this threshold before approval. Low entropy, negative EV or large value loss alone are warnings, not proof of collapse. Keep PPO's separately registered epoch stop independent. Hard wall,6GiB RSS and6GiB MPS driver limits, plus AC power guard, always win. Budget-limited completion is not plateau. A mid-update hard stop preserves partial failure and held lease; it cannot invent a completed endpoint.

Full-state checkpoints must include model/Adam, all RNGs, LR/entropy schedules, normalizers, each simulator/core RNG, feature History, cached observations, seed indices/collision set, current K/held-action phase, prior-action telemetry state, frame/cumulative-wall clocks, incumbent/patience state, averaging queue, source/runtime/parent/previous-checkpoint hashes. Publish state and telemetry through a durable no-replace commit manifest. Restore only a complete boundary with parent-owned cumulative time accounting. Atomic file publication alone is insufficient. Keep all raw checkpoints and last5 arithmetic model-weight averages; never average Adam. Changed normalization bases need a valid common-basis transform or must block averaging.

Full-state restore preserves live games **at the committed boundary**. A power failure can lose uncommitted work after that boundary; disclose it and preserve first failure. Normal preapproved phase handoffs and recovery after failure are distinct. No automatic recovery, marker reuse or retry follows a crash. Interleave serial replicas/evaluation only through reviewed, uniquely claimed child phases. Evaluate in a separate process and prove no mutation of training model/Adam/RNG/env/history/module flags. The existing one-MPS-job rule stays. A two-job contention/resource qualification could be proposed to Taylor separately; spare compute does not itself relax per-process or aggregate limits.

**Current blockers, source-only findings:**

|Source|Finding|Required before long launch|
|---|---|---|
|`checkpoints.py:57–80,120`|Explicit fresh-env resume abandons live games; Adam/global RNG are present.|Full native/wrapper/learner restore and next-step parity.|
|Formal `worker.py:372–425`|Recovery explicitly lacks full environment state; final model/Adam checkpoint lacks complete runtime/RNG state.|Every-update full-state commit, not metadata-only recovery.|
|`train_teacher.py:74–89`; frozen `curriculum.py:449–452`|Fixed LR and disabled same-phase restart; curriculum scheduler is not an LR scheduler.|New schedule-aware successor and parent cumulative-budget protocol.|
|`ppo.py:448–565`; formal `worker.py:122–138`|PPO computes KL/entropy/value/EV/clip metrics; formal journal drops numerical values.|Persist metrics with correct definitions, raw GAE and switch state.|
|DODGE-022 adapter|Synthetic-only preparation; lacks EV/clip fields and requires one GAE call.|New telemetry capsule, real passive parity and any per-epoch refresh contract.|
|Formal `worker.py:427–451`; `dev_eval.py:110–169`|Terminal evaluation reseeds global RNG; base evaluator reuses64 argmax seeds.|Isolated sampled-controller rotating-cohort evaluator and strict parent acceptance.|
|Native seed stream and resource guards|Exclusions/guards reusable; uniqueness, new shapes, disk/I/O and aggregate peaks unqualified.|S1/S2, full-state C8, resource/disk/AC qualification and20%-margin forecast.|

The [source-pinned audit](../learning/runs/v2/long-run-readiness-parent-20261030-r5/readiness-audit.json) contains exact references and limits. Qualification must measure snapshot size/write time, maximum update count, disk reserve, aggregate observer/child RSS and MPS peaks; project the entire approved path with20% margin inside the ceilings. If infeasible, redesign before approval. No old guard or frozen capsule changes. The failed S1-r1 exact lease remains held; S1-r2 still awaits explicit successor/failure-disposition authorization.324 remains the official parent.

## K=1 track (the user's hypothesis about control rate)

Validation against the paper draft (`paper/main.tex` in the paper worktree): the review quoted the paper faithfully (4,400 vs 6,115 mean frames, 2,626 to 4,387 at K=1, 256 x 64 rollouts, minibatch 512, segment abandonment every 60 updates, constant learning rate 3e-5). The draft says the policy "was never trained at K=1"; that is out of date, because DODGE-013 did train from 420 at K=1 and regressed.

What the data show: with the same weights, K=1 inference gives a bell-shaped survival distribution (mean 4,434, median 4,346, 6% dead before 1,000 frames) while K=4 has an early-death shoulder (mean 3,342, median 3,101, 14% dead before 1,000), see `charts/chart10.png`. That is inference at a finer rate for a policy trained at K=4; it does not show K=1 training is better.

What DODGE-013 does and does not settle: one warm-started replica, 11.8M frames, game-time gamma and GAE, no KL, entropy, value-loss or advantage telemetry (its own note). It rules out "switch to K=1 and continue" as a free win. Still open: K=1 from scratch, K=1 with the scaling changes (large batch, fresh seed stream, longer rollouts so the credit horizon fits), K=2, and an instrumented diagnostic of why the warm start regressed (a 4x smaller per-decision reward and 4x more decisions per game-second change advantage scale, update cadence and KL budget even when gamma and lambda are matched). K=1 requires four times as many decisions as K=4 at equal raw-game exposure. Wall-clock scaling must be measured rather than assumed to be4x or5-6x. S2 pipeline and memory qualification gate the expanded K=1/2/3/4 matrix. The one-MPS-campaign rule remains in force; a possible relaxation is a question for Taylor below.

### Which K, and how to train it

K=4 dominates the historical training lineage; K=1 has one warm-start trial, while K=2 and K=3 remain untested training rates. A common reading of the pattern (K=4 trains well, K=1 acts better) is that coarse decisions make learning easier, with a shorter credit horizon and less per-decision noise, while fine decisions help execution. That is a hypothesis, not a result here. Cheap and expensive ways to test it:
- Inference only, no training: run checkpoint 420 at K=2 and K=3 on the same2,048 already-consumed death-telemetry seeds3657433088..3657435135 as the existing K=1 and K=4 runs (paired contrasts; no new cohort). Shows whether the response to finer control is monotone. Needs AC power.
- K=2 and K=3 trained arms next to K=1 and K=4 (from scratch and from 420), game-time-matched gamma and GAE.
- K annealing 4 to 3 to 2 to 1 during training (DODGE-013 jumped straight from 4 to 1), or K sampled per episode so one network sees several rates; both are untried.

The first step is DODGE-025: evaluate frozen420 at K=2/K=3 before training either rate. Reuse the recorded consumed telemetry cohort, matching argmax and sampled groups separately, controller seed(s), cap, dtype and normal-start settings to their existing K=1/K=4 baselines. Require replay parity before interpreting a new native capsule. Report full survival summaries, the below1,000-frame death fraction and paired seed-cluster contrasts; do not combine different action-selection groups. These seeds are exposed diagnostics, not fresh confirmation. Zero-shot results cannot establish the best training K or automatically remove any fixed-K trained arm. No evaluation is launched by this plan.

The fixed trained matrix keeps **K=1/2/3/4** in both warm-start S3 and scratch S4. DODGE-026 preserves two additional options as separate experiments, not defaults:

- **Annealing4 to3 to2 to1:** preregister phase fractions on the actual raw-frame clock. Change K at a safe recorded collection boundary, retaining live simulator state and wrapper history rather than restarting episodes. Record requested and realized switch boundaries. Discounts and credit assignment must use the transition's actual duration; the current fixed-K capsule is not an implementation of this option.
- **Per-episode sampled K:** preregister the distribution over1/2/3/4, draw K at episode start and keep it for that episode. Episode-uniform sampling is not raw-frame-uniform exposure. Mixed-K vector stepping, per-transition gamma/GAE, value bootstrapping and actual frame accounting need new tests. Decide whether K is visible to the policy/critic; adding a K input is an explicit architecture ablation, not an invisible part of the experiment.

Keep both options behind S2 speed/memory qualification and separate registration, review and Taylor approval. DODGE-022's two-arm telemetry contract stays intact; four-rate or mixed-rate runs need a successor telemetry contract and coverage tests. No old K validator, frozen source, runtime or resource bound is changed.

### Local diagnostic successor: DODGE-022

DODGE-013 is one warm-started paired trajectory, not a rejection of K=1 training. Its saved update rows omit the numerical optimization diagnostics needed to explain its regression. Do not fabricate those missing values or alter its frozen source, runtime, receipts or checkpoints.

The successor must emit one durable telemetry row for **every completed update of both K=1 and K=4 arms**, including valid partial closing updates. A missing required row fails the successor audit. Required measurements:

- Full-rollout epoch-end approximate KL for every completed PPO epoch, final KL, configured KL threshold, early-stop flag, epochs and Adam steps completed. Do not compare KL by update index alone when raw-frame exposure differs.
- PPO minibatch/sample-weighted entropy and unweighted value MSE as actually computed by the loss. Label the latter `0.5 * mean((V - GAE_return)^2)` before `vf_coef`. Keep entropy and value-loss reduction definitions identical across arms.
- Advantage mean, population standard deviation, RMS, extrema and count **before per-minibatch normalization**, plus GAE-return and rollout-value scales. Log raw reward and learner reward scale, score/alive/death components and actual gameplay frames. A smaller alive bonus per K=1 decision does not imply every reward component is exactly four times smaller.
- Action switches and eligible adjacent-action comparisons, their ratio, and switches per1,000 actual gameplay frames. Compare only consecutive decisions in the same slot and episode; exclude reset/startup boundaries. Carry the last action across rollout boundaries for live episodes. An action switch is descriptive, not proof of dithering.
- K, learning rate, gamma, lambda, environment count, rollout decisions, effective and microbatch sizes, raw-frame and decision counters, guard peaks, and time. Preserve model/Adam restore binding and both arms' identities.

The implementation adapter and synthetic integration tests live in `learning/runs/v2/control-frequency-diagnostic-parent-20261030-r1/`. They instrument an existing prepared update; they do not construct games, choose seeds, acquire leases or authorize training. A real successor runner must freeze and review this integration, verify metric parity, register its bounded work and receive Taylor's go-ahead. K=2 and K=3 also need a separately tested capsule: the current root native config allows2..4, while the frozen DODGE-013 PPO/adapter explicitly allow1 or4. Neither interface should be silently relaxed.

Compare diagnostic trajectories at matched raw-frame boundaries and report both decision-weighted and exposure-normalized counters. Keep the original recipe fixed initially; any reward, entropy, learning-rate or horizon ablation becomes a separately registered contrast. Numerical telemetry can expose a failure mode, but causal attribution needs an intervention.

### S3/S4 control-rate matrix and credit horizon

S3 keeps K=1, K=2, K=3 and K=4 warm starts from420. S4 explicitly adds **all four from-scratch arms**, rather than treating scratch K=1 as a fallback only after it has already failed warm-start tuning. S4 still waits for S3 evidence and an explicit budget/launch decision. Use at least two independent training replicas per arm; three are preferred if Taylor accepts the measured cost. Shared initialization within each scratch replica controls initial weights; it does not turn the trained policies into one statistical replicate.

Match game-time discounts with `gamma_K = 0.995^(K/4)` and `lambda_K = 0.95^(K/4)`:

| K | gamma per decision | lambda per decision | Proposed rollout decisions per env | Raw-frame coverage | Proposed effective minibatch |
|---|---:|---:|---:|---:|---:|
|1|0.9987476493904754|0.9872585449014338|3,072|3,072|6,144|
|2|0.9974968671630001|0.9746794344808963|1,536|3,072|3,072|
|3|0.9962476513534098|0.9622606002309622|1,024|3,072|2,048|
|4|0.995|0.95|768|3,072|1,536|

These are candidates for resource qualification, not frozen launch settings. This revised grid supersedes the earlier2,048-frame candidate:3,072 raw frames per rollout and6,144 raw frames per macro-batch divide exactly by K=1/2/3/4, and every effective minibatch is a multiple of512. It changes the earlier K=4 macro-batch candidate from2,048 to1,536 decisions, so LR/batch calibration must be redone rather than silently reusing its LR. At a common env count, inverse-K rollout and macro-batch sizing match nominal updates and Adam steps per raw frame while K=1 processes four times as many decisions. Keep microbatches within measured memory limits and recheck learning rate with batch size; do not assume a square-root scaling rule. Log actual partial vector steps and preregister a feasible frame-matching tolerance for the new env count; the old DODGE-013 limits stay unchanged.

The matched discount half-life is553.13 raw frames. The `(gamma*lambda)` eligibility weight falls to1% after327.15 raw frames for every K, so3,072-frame rollouts comfortably contain that GAE horizon. They still leave2.13% of the infinite discounted tail beyond the boundary: correct final-observation value bootstrapping is essential. This is not a claim of a3,072-frame hard planning horizon. Test alternate gamma/lambda separately if the instrumented diagnostic points to excess variance or overly long credit assignment.

Memory is a gate, not a footnote. The current allowlisted observation tensors use5,896 bytes per transition. At256 envs, a K=1 rollout of2,048 decisions needs2.88GiB for observations alone; the revised3,072-step candidate needs4.32GiB;4,096 decisions need5.76GiB before action/reward storage, optimizer, attention, validation copies and native state. The latter cannot fit the existing6GiB RSS cap unchanged. Longer histories require qualified storage changes, reduced env count or an explicitly approved new resource budget; they are not enabled by assuming spare compute.

S3 first separates K=4 pool-versus-fresh seeds at the same recipe. A subsequent fresh-stream K=1/K=2/K=3/K=4 matrix tests control rate under the qualified larger batch and horizon. S4 repeats the rate matrix from scratch. Equal-frame screens precede any separately approved10x-frame extension. Record decisions, wall time and resource cost as well as frames; equal exposure is not equal compute.

Use a common sampled inference controller for the primary training comparison, proposed K=1, so changing both training and evaluation K cannot masquerade as a learning gain. Native-rate K=1/K=2/K=3/K=4 deployment comparisons and the early-death fraction below1,000 frames are secondary. Report Worst/Q1/Mean/Q4/Best, milestones and paired game-seed uncertainty, plus separate training-replica uncertainty. Use marginal Q1 differences with each distribution sorted separately. The14%-versus6% telemetry shoulder is a lead from its specific inference groups, not a measured benefit of K=1 training or proof of a Gaussian survival distribution.

### S2 speed gate and MPS concurrency question

Before a large K=1/2/3/4 run, S1 must measure the bottleneck and S2 must demonstrate faster end-to-end collection/update throughput with rollout/gradient parity and separate6GiB RSS/MPS bounds. The10x S2 speedup is a target, not a condition already met. Qualify each proposed K, env count and rollout length; compute training/evaluation/IO forecasts from those measurements with explicit margin. If a proposed run does not fit its approved budget, reduce its planned workload or seek approval before launch.

**Question for Taylor:** should we prepare a bounded qualification for up to **two concurrent MPS campaigns**, rather than retaining one as a permanent policy? Recommendation: consider two only after measuring contention. Compare matched solo and concurrent jobs for aggregate games/frames per second, per-job slowdown, timing tails and failure handling. Keep independent exact-once claims and receipts, a parent lease describing all approved workers, and no automatic promotion or retry. Admit concurrent work only if it improves useful aggregate throughput within an explicitly approved aggregate RSS/MPS envelope. Separate per-process6GiB caps are not an aggregate memory budget on unified-memory hardware. Decide the aggregate cap and fairness bound with Taylor before that qualification. Until explicit approval and successful qualification, **one MPS campaign remains the rule**. Spare compute alone does not establish that shared MPS execution is faster.

## Learning-rate schedule

Why the rate moved in steps: there is no scheduler in the code (`make_optimizer` in `train_teacher.py` is Adam with a fixed rate; the plan says "3e-4 constant"; `validate_config` requires the config to equal the registered default). Each change was a manual reaction to a plateau or endpoint regression, run as its own pinned, reviewed branch from a saved checkpoint through a resume-with-new-LR hook: 3e-4, then 1e-4 from retained 204 (mean +29.3%, Q1 -10.1%), then 3e-5 from 276. Each step is confounded with training seed and duration, and Adam moments carry over from the previous rate. One decay run (3e-5 to 1e-5, linear) was tried once: only an intermediate checkpoint won, the endpoint fell. So the schedule shape is genuinely untested, not tested and rejected. Literature prior (continuous-control benchmarks, not our game, so a prior and not proof): Andrychowicz et al. 2020, "What Matters in On-Policy RL" (arXiv 2006.05990), Sec. 3.7: linearly decaying the learning rate to 0 improved performance on 44 of 55 tasks, with small gains except about +15% on Ant, and they call it "of secondary importance"; the initial Adam learning rate has a "very strong" effect and 3e-4 is the safe default. Sec. 2 and 3.5: learning rate and minibatch size interact and must be tuned together, larger batches did not hurt sample complexity in their range, while many parallel environments (shorter experience chunks) hurt some tasks; they give no scaling rule. Engstrom et al. 2020, "Implementation Matters" (arXiv 2005.12729), lists Adam learning-rate annealing among the code-level optimizations that change PPO's reward landscape on Humanoid and Walker2d. Implication here: a planned decay is a mild, usually positive default, but the starting rate and the batch-size interaction matter more, and our staged drops to 3e-5 (10x below the 3e-4 default) were never compared with a planned schedule.

Plan: make the schedule part of the optimizer state (saved in checkpoints), then compare constant, warmup plus cosine to a floor, and KL-adaptive over at least two training seeds per arm, with learning rate rechecked whenever batch size changes.

### Controlled schedule comparison: DODGE-027 within S3/S4

The base runner's fixed Adam LR and historical manual branch changes explain the jarring steps; they do not compare schedules. Keep the three schedule arms explicit:

1. **Constant:** hold a calibrated positive starting LR throughout the registered raw-frame budget.
2. **Warmup plus cosine to a positive floor:** preregister starting LR, peak LR, floor, warmup fraction and total frame budget. Use actual collected gameplay frames as the schedule clock, not decisions, minibatches or update labels. Warm up linearly, then use `floor + 0.5*(peak-floor)*(1 + cos(pi*progress))`, where post-warmup `progress=(frames-warmup_frames)/(budget_frames-warmup_frames)` is clamped to[0,1]. Warm-start and scratch starting rates need separate calibration. Do not assume the old3e-5 warm-start rate is suitable from scratch.
3. **KL-adaptive:** preregister a target KL, deadband, LR multiplier and positive floor/ceiling. For example, lower LR when the completed update's full-rollout final KL exceeds the upper deadband, increase it below the lower deadband, and otherwise hold it. Freeze exact numbers before launch. Update only after a completed update using training telemetry, never evaluation performance. Keep the independently registered PPO KL-stop rule unchanged; adaptive LR cannot relax it, and a nonfinite metric is a failure rather than a reason to retry.

Use the same source, reward, stream recipe, exposure budget, PPO epochs, KL-stop rule and batching within each schedule comparison. Match initialization and nominal training RNG streams within a replica; trajectories can diverge because collection is on-policy. Recheck starting LR whenever effective batch or rollout sizing changes; no linear or square-root LR scaling rule is presumed. Every `(S3 or S4, fixed K, schedule)` cell needs **at least two independent training seeds**, with three preferred if measured budgets permit. The full minimal matrix is2 initializations ×4 fixed K values ×3 schedules ×2 replicas = **48 trajectories**:24 warm starts and24 scratch runs, before dynamic-K extras. This is a design-size target awaiting S1/S2 forecasts and explicit approval, not48 authorized launches. Any staged subset or selection rule must be declared prospectively; do not silently replace the requested schedule comparison by a chosen default.

Save scheduler **algorithm/version, all parameters, frame-budget/phase origin, actual frames consumed, completed-update count, per-group current/next LR, and KL-adaptation state** beside the exact model, Adam and RNG state in every checkpoint. Restore and validate them as one identity-bound learner state. Require a checkpoint round-trip test that produces the same next LR and Adam update as an uninterrupted synthetic trajectory. A new segment must not restart warmup, reset the cosine clock or erase adaptive history; any deliberate new phase is separately registered. A schedule-capable successor must replace the fixed-LR contract with registered schedule validation; do not disable an old guard or patch a frozen runtime. These requirements do not claim full simulator restoration or authorize automatic resume.

Log per-update current/next LR, schedule progress, KL/deadband decision and effective batch alongside DODGE-022 diagnostics. Compare fixed endpoints at equal raw frames using common evaluation controllers and the registered Q1 contrasts; report variability across training replicas separately from paired game-seed uncertainty. A later10x-frame extension must declare its schedule horizon before launch instead of opportunistically restarting decay.

## Literature checklist against our PPO setup

Source: Andrychowicz et al. 2020 (arXiv 2006.05990; five MuJoCo tasks, over 250,000 agents; read through a page summariser, so confirm any figure before citing it in a paper) and Engstrom et al. 2020 (arXiv 2005.12729). Continuous control with small MLPs, so a prior for us, not proof.

Use [Andrychowicz et al.](https://arxiv.org/abs/2006.05990) and [Engstrom et al.](https://arxiv.org/abs/2005.12729) as an implementation/ablation checklist, not a recipe proven for this discrete transformer policy. Exact task counts and quoted effect sizes in the handoff have not been independently checked against the papers in this planning pass. The proposals below are grounded in the local code; their predictions remain unobserved.

Already matches: PPO clip 0.2 (they suggest starting at 0.25); gradient clip 0.5; Adam with eps 1e-5 and initial rate 3e-4 (their safe default); MSE value loss with no value clipping (they found value clipping hurt at every threshold and Huber worse than MSE); per-minibatch advantage normalisation (little effect); actor final layer initialised with gain 0.01 (they found small last-layer initialisation a big win, about +66% on Humanoid).

Differs, each a cheap experiment:
- Policy and value networks: they found separate networks better on 4 of 5 tasks. Ours share one encoder (`teacher.py`); measured gradient alignment between actor and critic is near zero (cosine about 0.02), which weakens but does not settle the interference story.
- Discount: they call gamma the most important hyperparameter and start at 0.99. Ours is 0.995 per decision (half-life about 138 decisions, 550 frames at K=4) and was never swept; lambda 0.95 vs their 0.9. The heuristic needs only a 12-frame look-ahead. Link to K: at K=1 with game-time-matched gamma the credit horizon is 4x more decisions, so DODGE-013's regression may partly be a too-long horizon; sweep gamma and lambda at K=1 before concluding anything.
- Normalisation: they say always normalise observations and check value normalisation (crucial on two tasks, harmful on one). Ours has no running normalisation (hand-scaled features, fixed reward scale 0.1). Engstrom lists reward normalisation, Adam annealing and network initialisation as the optimisations that most reshape the PPO reward landscape.
- Epochs and advantages: they find multiple passes crucial and stale advantages harmful, recomputing advantages at the start of each pass. Ours computes GAE once per rollout (`ppo.py`) and runs four epochs with a 0.03 KL stop; how often the KL stop fires is worth logging.
- Parallel environments: more environments with shorter experience chunks hurt sample efficiency on some tasks; larger batches did not in their range. Argues for longer rollouts per environment in S3.
- Entropy bonus: none of the regularisers helped significantly in their continuous setting; ours is a constant 0.01 on a discrete policy, so test lower or decayed, not removal by assumption.
- Frame skip: improved 22 of 55 tasks ("try it"), which supports treating K as a tuned hyperparameter.
- Time-limit handling: no difference at 1,000-step limits; our cap is 18,000 frames, but capped games are rare (15 of 1,000 for the heuristic, none for the policy).

### Registered checklist experiments and predictions

**DODGE-028: discount/GAE sweep first, especially at K=1.** Candidate direct per-decision grid: gamma `{0.97,0.99,0.995}` × lambda `{0.90,0.95}`, initially at K=1 and K=4 from420. Retain the original matched-horizon K=1 anchor `(gamma=0.995^(1/4), lambda=0.95^(1/4))` as a separate control: it lies outside this direct grid. K=4's original `(0.995,0.95)` is already one grid cell. This makes13 distinct cells and at least26 trajectories with two training seeds each, not26 authorized launches. Hold reward, LR schedule, batching, rollout allocation and raw-frame exposure fixed within each contrast. Freeze actual budgets and seed vectors only after the existing gates.

Units matter: a reference K=4 gamma grid transformed by `gamma_K=gamma_4^(K/4)` is a **matched-game-time** sweep. Applying0.97–0.995 directly at K=1 is a deliberately **shorter-horizon intervention**, not matched game time. At K=1, those gamma endpoints give discount half-lives22.76–138.28 raw frames, versus553.13 for the original matched anchor. Log both decision and raw-frame discount/GAE decay horizons. Prediction: shorter traces may reduce advantage noise or critic instability; they may instead discard useful delayed credit. Gamma changes the discounted objective, so reduced variance or KL is not itself a survival win. A12-frame oracle horizon does not establish the right training discount.

**DODGE-029: separate actor/critic encoders.** Compare the shared encoder with genuinely disjoint actor and critic encoders, retaining reward, horizon, schedule and exposure. For warm starts, specify cloned weights and a versioned Adam-state mapping, then verify initial actor logits and values; copied shared Adam history is not evidence of a clean scratch intervention. Analyze scratch and warm-start contrasts separately. Report parameter count, FLOPs, wall time and memory: separation is not free. Prediction: it may improve fitting or reduce interference, but the reported near-zero gradient alignment weakens a simple interference explanation. If it helps, add a parameter/compute-matched shared control before attributing the gain specifically to separation. Use at least two training seeds per cell.

**DODGE-030: observation and value normalization as a2×2 ablation.** Compare current fixed scaling, running observation normalization only, value normalization only, and both. Existing transformer LayerNorm, hand-scaled features and fixed reward scale0.1 are already present; they are not running input/target normalization. Estimate statistics only from allowed training data; freeze them during evaluation and save their counts/means/variances in checkpoints. Normalize only registered continuous feature columns, excluding padding and invalid entities; preserve type IDs, masks and binary semantics. Keep final-observation bootstrapping correct.

For value normalization, specify target standardization with affine value-output compensation, retain predictions/GAE in original learner-reward units, and declare any optimizer-state rescaling and critic-loss weighting. Report normalized training loss and original-unit value errors separately. Validate continuity when statistics change. Warm-start observation statistics can shift the policy without a gradient step: require initial parity, log the KL due to a statistics-only update, or treat a non-preserving initialization as a separate intervention. Prediction: normalization may stabilize scales, but statistics drift or altered actor/value balance may hurt. Keep observation and value effects distinguishable and use at least two training seeds per cell; do not assume both are beneficial.

**DODGE-031: per-epoch advantage refresh and measured KL-stop frequency.** Compare the current single frozen GAE calculation with recomputing advantages **and returns** from the current critic before each PPO epoch. Keep sampled actions and rollout behavior log-probabilities fixed. Refresh matching current-state and next-state values; preserve pre-reset final observations for time-limit truncations and the final rollout boundary. Do not combine fresh values with stale next-values. Keep per-minibatch advantage normalization, the four-epoch maximum and the full-rollout epoch-end `KL > 0.03` stop unchanged. An advantage-only refresh with frozen critic targets is an optional separate ablation, not silently the same treatment.

Log raw advantage/return moments per refresh epoch, GAE call count, numerical KL by epoch, the early-stop flag, epochs/Adam steps, and aggregate rates with explicit denominators. Distinguish threshold hits from stops **before** the maximum epoch; an epoch4 hit avoids no epochs. Count incomplete/failed updates separately rather than treating them as non-stops. DODGE-022's current telemetry contract deliberately expects one GAE call per update, so this experiment needs a separately reviewed multi-epoch contract; do not edit that frozen source to accept extra calls. Prediction: fresh targets may improve updates or add noise and inference cost without improving Q1.

A retrospective read of the accepted DODGE-013 update rows found **0/181 K=4 and0/180 K=1 early-stop flags; all361 updates completed four epochs**. Therefore lost PPO epochs do not explain that run's regression. Missing numerical KL/entropy/value/advantage diagnostics still prevent a mechanism claim. This is a saved-receipt finding, not a new run; evidence is in `learning/runs/v2/ppo-literature-checklist-parent-20261030-r3/DODGE013-retrospective-KL-stop-counts.json`.

**DODGE-032: longer per-env histories versus more envs at fixed batch.** Compare `(N,raw frames per env)` candidates `(128,6144)`, `(256,3072)`, `(512,1536)`, each786,432 nominal raw frames per update. Convert per-env frame coverage to rollout decisions using K. Within a fixed K, hold total batch, effective minibatch, optimizer cadence, reward, discounts, LR schedule and total training exposure fixed. This compares N/T allocation, not an isolated horizon-only change. Prediction: longer chunks may reduce frequent bootstrap boundaries or retain useful within-env experience, while more envs may improve diversity or utilization. Report Q1/sample efficiency separately from throughput. Use at least two training seeds per cell.

All three allocations have the same observation-tensor count at a fixed K. At K=1 that is about4.32GiB before attention, optimizer and other storage, so a different N alone does not solve the6GiB memory problem. S2 must qualify storage and every proposed shape; the longer-rollout option cannot be replaced by simply increasing env count.

These five checklist groups are staged controlled ablations, not a full Cartesian product with the48-trajectory K/schedule proposal. Prioritize the instrumented warm-start diagnostic and horizon screen, then isolate encoder/normalizer/advantage changes and rollout allocation with matched controls. Any shared control must be preregistered as identical; do not reuse a result whose recipe or seed stream differs. Findings can inform a prospectively locked S3/S4 recipe, but exploratory selection requires separate validation before a population claim. Nothing here opens a cohort, overrides the held S1 lease, relaxes memory/concurrency limits, or authorizes a launch.

## Scaling track (the user's hypothesis)

Goal: find out whether more data, more diverse seeds and larger batches move the weak tail (Q1), and what limits throughput.

- **S0, seed audit (no compute).** Count unique training seeds and episodes in the 324-600 segments from `training.jsonl` and the seed-stream config. Report episodes per unique seed. Decision: if the 512-pool was used throughout, fresh-stream training is the first change to test, ahead of everything else.
- **S1, throughput profile (minutes).** Time one update split into: environment stepping, observation stacking and transfer, model inference on MPS, GAE, PPO epochs. Test 64, 128, 256, 512 envs with 4/8/12 threads and rollout lengths 256/512/1,024, plus CPU vs MPS inference. Output: frames/s per configuration and the real bottleneck. Expect the engine to be a small share; verify.
- **S2, pipeline fix (code).** Whatever S1 shows: batched inference, avoiding per-env Python loops, pinned buffers, vectorised rollout storage. Target at least 10x frames/s. Parity-test against the current loop on the same weights (same seeds give the same rollouts).
- **S3, scaled run from 420 (training, gated; K=1/K=2/K=3/K=4 are explicit arms).** Fresh unbounded seed stream (no pool), 256 or more envs, rollout of 512 or more steps, effective minibatch chosen on a grid divisible across all four K values (revised candidate below), learning rate rechecked for batch size, game-time gamma and GAE unchanged. Use a prospective matched K=4 pool-versus-fresh comparison to isolate seed diversity, then a fresh-stream K=1/K=2/K=3/K=4 matrix with matched game-time rollout coverage and nominal optimizer cadence. DODGE-013 is historical context, not a causal control for multiple pipeline, batch and seed changes. Compare equal frames first; any10x extension needs its own budget and approval. Primary metric Q1, with Mean, Q4 and milestone counts, on a fresh shared cohort.
- **S4, scaled run from scratch (training, gated).** Only after S3 shows direction, since a from-scratch run tests whether 420's basin is the limit. Run explicit K=1/K=2/K=3/K=4 scratch arms, crossed with the three registered LR schedules; from-scratch K=1 remains untested.

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
- Treat K as a hyperparameter: zero-shot K=2/K=3 first, then fixed K=1/K=2/K=3/K=4 trained arms, plus separately registered annealing and per-episode sampled-K options. DODGE-013 covers only one warm-start K=1 comparison.
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
1. S0 seed audit and S1 throughput profile. Extend inference-only Track A with DODGE-025 K=2/K=3 zero-shot before any trained-rate comparison; reuse the consumed telemetry cohort and require explicit evaluation go-ahead.
2. Counterfactual branching (DODGE-004): restore snapshots 60, 45, 30 and 15 frames before enemy-contact deaths; roll out the policy at K=4 and K=1, plus an oracle that tries each of the 9 actions for 12 frames. This separates reaction-delay failures from earlier commitment to doomed regions.
3. Paired heuristic baseline on the same fresh seeds at K=4, to put a number on the gap in fact 1, and to turn the heuristic into a stratification control variate.
4. Checkpoint averaging evaluation (offline).
5. Rust equivariance audit for D4 symmetry.

Track B, code changes (after Track A informs priorities): S2 pipeline speedups, wrapper-level D4 augmentation, extra input features, pooling heads, survival-only reward switch, snapshot carry-over across segments.

Track C, training (each needs registration, independent review, resource qualification and explicit user go-ahead): S3, then reward, symmetry, features, imitation from the heuristic.

Imitation from the heuristic is the idea the review did not raise: since a 12-frame look-ahead already beats the policy at 4-frame control, DAgger or behaviour cloning from it is a direct way to reach that level cheaply and then continue with PPO. Evaluate it as its own track after item 3 above confirms the gap.

## Limits of this document

The512-pool continuation is now independently verified by S0. Transpose-exactness of patterns3 and4 and the training-loop bottleneck remain unverified. S1-r1 failed before Torch import; corrected S1-r2 is source-reviewed but awaits explicit successor/failed-lease-disposition approval. The telemetry shows associations at death, not causes.
