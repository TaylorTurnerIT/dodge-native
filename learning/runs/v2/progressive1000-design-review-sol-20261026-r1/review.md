# Source-only design review

**Result: changes required before implementation freeze.** Four P1 experiment-definition blockers; three P2 pilot/registration items. The cumulative-prefix approach is feasible in principle. It does not establish the weak-early-practice hypothesis or runtime qualification.

All seven entries in the design source manifest match current bytes. Checkpoint324 hashes to `c10d90ec0e67503afef8f4d90c4968581d430ef2065117a75e81c445a04c8ddc`; acceptance hashes to `3e84979c4c8da76d0f98666a23f90eb15c1e813ca5edf1001e19daebaf4d5bbd`. The acceptance receipt records phase324/cumulative372 and no training launch authority. Exact hashes for the three design artifacts and every source/support artifact used are in [receipt.json](receipt.json).

## Findings

Paths below use `design/` for `learning/runs/v2/progressive1000-curriculum-design-luna-20261026-r1/` and `runtime/` for `learning/runs/v2/D2-gradient-capsule-parent-freeze-20261025-r5/own/runtime/dodge_rl/`.

### F1 — P1: Equal optimizer steps conflict with unchanged PPO KL stopping

**Path/line:** `design/plan.md:12`; `design/experiment.json:27,75`; `runtime/ppo.py:60,70,470,475,521,565,567`.  
**Trigger:** The two arms cross target_kl=0.03 after different epochs.  
**Consequence:** Equal 60-update, 256-decision rollouts do not guarantee equal Adam steps. Enforcing the stated equality would require an unregistered PPO change, topping up, or stopping one arm.  
**Required resolution:** Keep the inherited KL rule; define equality as rollout transitions and identical PPO settings/maximum optimization budget, and report actual epochs/Adam steps. If exact Adam-step equality is essential, specify and review a separate matched protocol before implementation.

### F2 — P1: Stage/window state machine has multiple valid interpretations

**Path/line:** `design/experiment.json:40,41,44,47,49,53`; `runtime/ppo.py:340,349`.  
**Trigger:** Simultaneous completions straddle a 100-episode window or promotion; old-horizon episodes remain active; two passing windows arrive before update ten.  
**Consequence:** Completion order, entry reset, and exposure-clock choices change promotions and the training distribution despite identical seeds.  
**Required resolution:** Specify stable (learner update, rollout decision, slot) ordering, atomic completion-batch processing, one promotion boundary, stage-generation eligibility, and reset of episode/window/streak/update counters on entry. Freeze in-flight assignments. Define whether pre-minimum windows qualify, whether later failures erase eligibility, and exactly when the tenth completed stage update counts; no double-charging an update to stages.

### F3 — P1: 70/30 assignment does not yet define section exposure

**Path/line:** `design/experiment.json:36,39,40,52,53`.  
**Trigger:** Implementations interpret 'episode slots' as fixed vector occupancy, reset-event quotas, or Bernoulli episode draws; earlier horizons need rounding.  
**Consequence:** Each interpretation changes experienced frames and mastery arrival. Normal-start H episodes also practice every earlier section; 70% current episodes is neither 70% current-section frames nor guaranteed exposure beyond H-1000.  
**Required resolution:** Choose one explicit assignment algorithm, balancing scope, rounding/remainder order, RNG/hash, and stage-entry behavior. Use scheduler randomness independent of policy/minibatch RNG. Declare this a cumulative-prefix curriculum, not isolated section starts; log actual raw frames, reaches, and survival through each 1000-frame interval. Retain the proposed 90%, 200 episodes, 10 updates and 70/30 only as unapproved design choices, not user requirements.

### F4 — P1: Full-run regression, endpoint selection, and required death metrics are unspecified

**Path/line:** `design/experiment.json:64,67,69,70,71`; `design/plan.md:20`.  
**Trigger:** Choosing a checkpoint or replica after inspecting the fresh cohort, pooling away a lower-tail regression, or implementing only the listed metrics.  
**Consequence:** The cohort becomes selection data; a curriculum can improve capped training mastery while regressing complete runs. The requested death-cause comparison is absent from the required metric list.  
**Required resolution:** Predeclare endpoint/cadence and per-replica plus paired aggregation; minimal pilot uses every terminal update-60 replica without best-of-stage/replica selection. Compare both arms and checkpoint324 on the same new normal-start cohort with cutoffs disabled, fixed action selection/backend, milestone rates, Worst/Q1/Mean/Q4/Best and death causes/caps/unknown/unavailable counts. Define survival as alive_frames (fatal frame excluded), quartile size/rounding and milestone ties. Any later candidate selection needs separate fresh confirmation and a parent-defined regression/acceptance rule; do not invent a mastery threshold.

### F5 — P2: The 60-update pilot cannot cover the entire 18-stage program

**Path/line:** `design/experiment.json:24,37,41,48,50`.  
**Trigger:** At least ten non-overlapping learner updates are required per mastered stage.  
**Consequence:** Even perfect success can master at most six stages and enter 7000 at the end, with no remaining training. Exposing 18000 requires at least 170 prior-stage updates; mastering all stages requires at least 180, before episode-count constraints.  
**Required resolution:** Explicitly label 60 updates per replica a bounded early-stage pilot; clarify global budget versus per-stage timeout, and record stages reached/mastered and untested stages. This is a limit, not permission to increase the cap.

### F6 — P2: Training equality and total resource ceilings need separate semantics

**Path/line:** `design/experiment.json:23,24,27,28,31,67`; `design/plan.md:12,20`.  
**Trigger:** One arm hits a raw-frame/wall cap first, or evaluation/baseline/checkpoint overhead is charged inconsistently.  
**Consequence:** Pairs may have unequal completed decisions or silently different total cost. The unspecified evaluation count/cadence prevents a complete resource bound.  
**Required resolution:** Pin batch size, six-run execution/concurrency plan, evaluation count/cadence, and train/eval/aggregate wall, raw-frame, memory and cleanup budgets. Count every startup (13 frames/reset), reset, initial construction, discarded work and evaluation. Define fail-closed partial-pair reporting without top-ups. At inherited batch64, each replica plans 983040 transitions and at most 7680 Adam steps; six replicas plan 5898240 transitions. Actual steps may be lower under KL stopping.

### F7 — P2: Five named exclusions are not a complete freshness or replica contract

**Path/line:** `design/experiment.json:25,26,40,67,68`; `crates/dodge-rl-env/src/seed.rs:75,89,115,136`; `runtime/checkpoints.py:138,142`.  
**Trigger:** A 'fresh' evaluation seed appeared in historical training, discarded later updates, probes/benchmarks or other consumed cohorts; replicas share restored RNG without a declared fork.  
**Consequence:** Disjointness from B/E/D128/D100/D200 alone does not prove held-out freshness or independent replicas. Matching run_seed does not mean both arms consume identical episode counts, because cutoffs reset sooner.  
**Required resolution:** Make the ancestry audit cover all observed/consumed seed sets, including discarded branches, and reserve the new cohort against future training in both arms before construction. Preserve B/E unopened, D100 opened and D200 consumed. Pin model/Adam restoration and replica-specific paired policy/minibatch RNG forks, run_seed/slot/episode offsets and collision handling. Treat pairing as matched streams and report actual consumed seeds/exposure; exact seed manifests may remain parent-owned registration work.

## Minimal correct implementation boundary

- Create a successor-owned copy of the accepted runtime/build inputs. Both arms must use the **same new native binary, Python runtime, model, PPO, evaluator, dependencies and configuration**, differing only in enabled curriculum assignment/cutoff. Plan line12 already requires source equality for control reuse; preserve that requirement. A current-tree native rebuild only for curriculum would confound cutoff with native drift. Hashing current Rust and the accepted binary does not prove their build correspondence.
- Keep normal starts and replayed prefixes. Native history updates on every executed raw frame (`env.rs:225-226`); a timer edit cannot construct the engine RNG/objects/history. No later-start optimization is needed. Preserve checkpoint324's model and Adam state; explicitly define paired replica RNG forks. Keep LR `3e-5`, reward, GAE, 256-decision buffers and KL control isolated from the LR study.
- The missing operation is real: `env.rs:483-484` rejects active-slot reset, and `python.rs:323-355` exposes no practice truncation. Add a validated native active-slot truncation operation plus a thin successor adapter/collector scheduler. All proposed H are divisible by K=4 and episodes start at frame0, so marking a still-alive slot **after its exact H-reaching step** is sufficient if alignment is asserted. Reject unsupported misalignment, or stop inside the raw-frame loop for a general horizon API. Do not change only Python flags or use `reset_all`.
- Validate the whole cutoff request before mutation. Mark only alive, non-ended, exactly-at-H selected slots; preserve final observation/history/reward/counts/seed index, and synchronize step masks, episode metadata and bootstrap before collector audit/storage. Keep true death ahead of cutoff, including death on frame H. H=18000 already uses ordinary alive-cap truncation; avoid a second cutoff.
- Frozen GAE already uses `1-terminated` for bootstrap and `1-(terminated|truncated)` for recurrence (`ppo.py:162-170`). Preserve final-value-before-reset ordering (`334-360`), then reset selected ended slots once and increment each episode index once. No GAE rewrite or new reward is justified.
- Successor identity/registration plumbing is necessary: frozen `identity.py:88-91,115-133` enforces old config/native pins. Copy and bind new pins explicitly; do not weaken or edit frozen validators. Existing expanded evaluator also pins runtime members (`expanded_eval.py:392-395`); adapt only a successor and retain complete normal-start row validation.

## Required later CPU/native tests — not run here

1. **Native boundary and parity:** disabled-cutoff successor versus accepted native on identical seeds/actions; selected-slot H=1000/2000 and ordinary18000 exactness, observations/history and reward/count conservation. Cover death at H-1/H/H+1, one death penalty, first death cause, and no simulation beyond an alive cutoff. Test ragged boundaries only if the API supports them.
2. **Reset/API:** mixed death/cutoff/continuing slots; no continuing-slot mutation, whole-request rejection for duplicate/out-of-range/wrong-frame/ended indices, poison/overflow handling, owned final buffers, subset reset ordering and one seed-index increment. Repeat across thread/chunk layouts.
3. **CPU collector/GAE:** independent scalar oracle for death/no bootstrap and alive cutoff/final-state bootstrap; tagged pre-reset observation; no next-episode leakage; boundaries at rollout decision256 and spanning rollouts; unchanged reward/raw audits and no abandoned/filler samples.
4. **Scheduler:** 89/90/91 successes per100, 199/200 episodes, exposure updates9/10, pass/fail/pass windows, stage-entry counter reset, old in-flight episodes, simultaneous completion ordering and exactly one promotion. Check deterministic quota/rounding and RNG isolation, fixed global60 stop, no budget extension.
5. **Experiment/evaluation:** matched full config/runtime diff with only curriculum fields differing; unchanged Adam/LR/KL accounting; exhaustive seed-union rejection before construction; cutoffs disabled in all fresh full runs; fatal-frame milestone ties, exact quarter means, death/cap count conservation, per-replica pairing and predetermined endpoint selection. Verify incomplete-resource outcomes cannot become passing comparisons.

Existing source tests provide useful patterns (`python/tests/test_ppo.py:49-83,199-209,425-437`; `crates/dodge-rl-env/src/tests.rs:620-669`; `python/tests/test_env.py:248-339`). Their presence is not execution evidence.

## Evidence limits and ownership

Only stdlib file reading/hashing, JSON inspection and Python AST parsing were performed with `python3 -B -S`, plus text searches. No project module, Torch, NumPy or native extension was imported; checkpoint and binary were hashed only. No model/environment construction, deserialization, MPS, training, evaluation, build or tests occurred. No subdelegation. Only this new review directory was created.

This review verifies the supplied checkpoint/receipt bytes and visible source contracts, not the full ancestry/seed audit, successor build parity, resource calibration, statistical acceptance or runtime qualification. Exact seed values, ceilings and registration IDs can remain unresolved at design stage; F1–F4 define behavior and must be resolved before implementation freeze. Proposed mastery numbers remain unapproved.
