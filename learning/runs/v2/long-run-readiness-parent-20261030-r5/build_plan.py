"""Reproduce source-only readiness findings and budget arithmetic; never import RL code."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
FORMAL = "learning/runs/v2/one-frame-training-comparison-luna-20261029-r2"
RUNTIME = "learning/runs/v2/one-frame-training-comparison-luna-20261029-r1/runtime-clean-r2/dodge_rl"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def finding(identifier, status, source, lines, observation, requirement):
    return dict(id=identifier, status=status, source=source, lines=lines,
                source_sha256=sha(ROOT / source), observation=observation,
                successor_requirement=requirement)


findings = [
    finding("live_state", "blocker", "python/dodge_rl/checkpoints.py", [57, 80, 120],
            "Checkpoint v1 records abandoned live episodes and accepts only fresh_env resume; Adam and global RNG are present.",
            "Versioned full VecEnv/core RNG/feature History/adapter/cached-observation/action-phase serialization and exact continuation qualification."),
    finding("formal_recovery", "blocker", FORMAL + "/worker.py", [372, 390, 407, 414],
            "Recovery stores model/Adam/RNG plus episode metadata, explicitly no full environment state or automatic resume. Final checkpoint omits runtime/RNG state.",
            "Every completed update must commit full state and a durable journal anchor; old artifacts cannot reconstruct lost live games."),
    finding("checkpoint_atomicity", "reusable_component_not_full_protocol", "python/dodge_rl/checkpoints.py", [84, 109],
            "Existing atomic no-replace publication fsyncs file/directory and preserves failed partials; no atomic state-plus-journal transaction here.",
            "Qualify a crash-consistent manifest commit over state, telemetry, schedule and cumulative wall accounting; preserve torn writes as incidents."),
    finding("native_boundary", "blocker", "crates/dodge-rl-env/src/python.rs", [266, 380],
            "Python VecDodgeEnv exposes step/reset/observation/metadata APIs, not full-wrapper snapshot/restore.",
            "Core snapshot alone is insufficient: include per-slot feature history, indices, pending resets and held-action phase; no reset at monitoring barriers."),
    finding("learning_rate", "blocker", "python/dodge_rl/train_teacher.py", [74, 89],
            "make_optimizer constructs fixed-LR Adam; same-phase restart is explicitly disabled without parent cumulative-budget authority.",
            "Separately reviewed scheduler-aware successor and parent budget/phase protocol; do not weaken old guards or infer retry authority."),
    finding("fixed_lr_guard", "blocker", RUNTIME + "/curriculum.py", [449, 452],
            "Actual formal PreparedUpdates validates constant Adam LR/epsilon. Its scheduler_reference is a curriculum assignment scheduler, not an LR scheduler.",
            "Validate registered LR/entropy schedule state each update and restore, preserving epsilon and independent PPO stop controls."),
    finding("metric_computation", "reusable_with_limits", "python/dodge_rl/ppo.py", [448, 460, 532, 553, 565],
            "PPO computes epoch/final KL, entropy, value loss, explained variance, clip fraction and gradients. EV is undefined for near-zero target variance; GAE runs once.",
            "Persist original definitions and null/definedness. Log raw pre-normalization advantage scale and switches; do not claim PPO lacks existing metrics."),
    finding("metric_retention", "blocker", FORMAL + "/worker.py", [122, 138],
            "Formal journal keeps counts/epochs/early-stop booleans but discards numerical KL/entropy/value/EV/clip metrics.",
            "Exactly one complete identity-bound telemetry row per committed update, including valid closing partials, with counters and weighted denominators."),
    finding("telemetry_successor", "incomplete_source_preparation", "learning/runs/v2/control-frequency-diagnostic-parent-20261030-r1/update_telemetry.py", [194, 294],
            "Synthetic-tested adapter logs KL/entropy/value/GAE moments/switches, but omits EV/clip fraction and expects one GAE call.",
            "New capsule adds EV/clip fields, schedule/frame clocks and optional per-epoch refresh contract; qualify against real PPO and passive parity."),
    finding("evaluation_rng", "blocker_for_midrun_reuse", FORMAL + "/worker.py", [427, 451],
            "Terminal evaluator loads a separate model but reseeds Python/NumPy/Torch/MPS global RNG. This is valid terminal evaluation, not isolated training interleaving.",
            "Dedicated evaluation process plus full training suspension/checkpoint; prove no training RNG/model/Adam/env/history/module-flag mutation."),
    finding("evaluation_cohort", "blocker_for_long_monitor", "python/dodge_rl/dev_eval.py", [110, 169],
            "Base evaluator reuses 64 development seeds and argmax actions; restoring model.train flag does not implement rotating1024-seed sampled-K1 monitoring.",
            "Registered disjoint cohorts, fixed common controller, exact counts and strict terminal acceptance before reading outcomes."),
    finding("training_stream", "needs_successor_registration", "crates/dodge-rl-env/src/seed.rs", [50, 89],
            "Native tuple-hash stream supports exclusions but finite u32 seeds can collide; formal campaign used the fixed pool.",
            "Fresh non-pool stream excludes all historic/held-out allocations, deduplicates training starts within each replica, logs rejections/indices, fails on exhaustion; paired replicas may share their registered training seed sequence."),
    finding("resource_guard", "reusable_not_requalified", FORMAL + "/worker.py", [36, 61],
            "Existing worker guards work time, lease and RSS/MPS independently; larger batches, two replicas and full snapshots were not qualified by this run.",
            "Keep6GiB separate ceilings and one MPS job; qualify aggregate observer/child RSS, MPS peaks, I/O, disk reserve, AC guard and full budget forecast."),
]
save("readiness-audit.json", dict(schema="dodge_long_run_source_readiness_v5", record="DODGE-043",
     status="source_audit_complete_runtime_not_qualified", findings=findings,
     scope="Read-only source and accepted receipts only; no model load, games, optimizer steps, imports of RL code or launches.",
     readiness="blocked_pending_successor_implementation_review_qualification_and_user_approval"))

entry = dict(training_replicas_per_recipe=2, candidate_trajectories=2, control_trajectories=2,
             raw_frames_per_trajectory=11796480, fresh_game_seeds=1024, models=5, games=5120,
             training_work_seconds_per_trajectory=10800, training_receipt_seconds_per_trajectory=180,
             eval_shards=2, eval_work_seconds_per_shard=3600, eval_receipt_seconds_per_shard=180,
             all_four_missing_ceiling_seconds=4 * 10980 + 2 * 3780,
             only_two_controls_missing_ceiling_seconds=2 * 10980 + 2 * 3780,
             rule="Both paired training replicas: positive marginal-Q1 and Mean contrasts against prospective matched current-recipe controls; aggregate paired-game-seed bootstrap lower95>0 for both metrics.",
             bootstrap_draws=2000, uncertainty="Conditional game-seed uncertainty; n=2 training replicas is not a population confidence interval.",
             exposure="Same initialization and total ancestral/additional exposure;420 is context only. Model-only historical endpoints require reproduction with full-state checkpoints if selected for continuation.")
monitor = dict(looks=6, fresh_game_seeds_per_look=1024, models_per_look=4, games_per_look=4096,
               total_games=24576, eval_shards=6, eval_work_seconds_per_shard=3600,
               eval_receipt_seconds_per_shard=180, total_ceiling_seconds=22680,
               nominal_raw_frame_barriers=[19660800 * i for i in range(1, 7)],
               models="current2 plus incumbent2, all on this look's same fresh cohort; do not compare metrics from different cohorts as progress",
               acceptance="Read outcomes only after each strict evaluation-parent terminal acceptance; no replacement cohort after failure.",
               joint_progress="Each replica has positive Q1 and Mean differences; aggregate paired bootstrap lower95>0 on both. Update both incumbents together; reset patience.",
               plateau="Stop after3 valid audited looks without joint progress. Missing/failed look is an incident, not a patience tick.",
               collapse="Stop if each replica has paired-bootstrap upper95<0 for both Q1 and Mean versus that look's incumbents. Frozen-entry collapse checks require an additional approved evaluation packet.",
               inference_controller="sampled K1 fixed throughout; other deployment controllers need separate registration/budget",
               bootstrap_draws=2000, bootstrap_seed_rule="202610300510 + look_index_1_based",
               sequential_inference="Nominal development intervals guide prespecified stopping only; not multiplicity-adjusted confirmation or causal training-seed inference.")
final = dict(fresh_game_seeds=2048, models=7, games=14336, eval_shards=4,
             eval_work_seconds_per_shard=3600, eval_receipt_seconds_per_shard=180,
             total_ceiling_seconds=15120,
             models_description="latest valid terminal raw2, last5 averaged2, frozen entry2,420",
             endpoint_lock="Lock latest complete terminal raw endpoints and averaging window before opening games; no best-checkpoint substitution.",
             contrasts="Primary latest-raw minus frozen-entry marginal-Q1/Mean; secondary averaged-minus-raw and each-versus420; both training replicas reported separately.",
             bootstrap_draws=2000, bootstrap_seed=202610300599,
             early_stop="If fewer than5 completed long updates, use all available completed updates and label window length; missing valid terminal endpoints is an incident.",
             claims="Independent confirmation of fixed endpoints conditional on two trajectories; secondary contrasts descriptive, no automatic adoption/promotion.")
plan = dict(schema="dodge_bounded_long_run_design_v5", record="DODGE-044", launch_authority=False,
            status="proposal_only_not_launch_ready", supersedes="Only P4 conditional G1 long-run sketch; all Phase0/1/2 packets unchanged.",
            entry=entry, monitoring=monitor, final_confirmation=final,
            training=dict(replicas=2, additional_raw_frames_per_replica=117964800,
                          work_seconds_per_replica=32400, receipt_seconds_per_replica=600,
                          total_ceiling_seconds=66000,
                          per_update_checkpoint=True, retain_every_checkpoint=True,
                          limits=dict(rss_bytes=6 * 2**30, mps_driver_bytes=6 * 2**30, AC_only=True,
                                      concurrent_MPS_jobs=1),
                          wall_accounting="Sum all approved child-phase wall times including import, collection, PPO, checkpoint I/O and suspension/restore; monitoring has separate bounded packets. No counter resets across phases.",
                          frame_accounting="Actual gameplay/alive/startup counters separate; keep whole closing vector step and optimize valid final partial; exact overshoot/frame-gap caps frozen with N,K before launch.",
                          target_gate="Need measured full-path forecast including I/O and20% margin within each cap. If unmet, redesign before approval; never silently extend.",
                          schedule="Carry the selected Phase1 LR/entropy algorithms and state; freeze all parameters, frame origin, maximum horizon and extension behavior before launch. Constant, cosine and KL-adaptive stay alternatives until tested; no manual rate drops.",
                          continuation="Full-state qualifying entry checkpoints required; inherited training exposure and any schedule phase transition explicit. Never resume model-only420 as if live games were preserved."),
            seeds=dict(new_evaluation_seeds_requested=9216, reserved_now=0, cohorts_opened_now=0,
                       allocation="Entry1024 +6 development cohorts of1024 +final2048, mutually disjoint. Before training, reserve exclusion ranges without opening evaluation games; final outcomes remain unread until endpoint lock.",
                       training="Fresh non-pool stream with exclusion union, per-replica collision rejection and exhausted-space failure. Finite u32 space is not infinite unique seeds. Exclude D7/D8/D9, consumed telemetry and all prior held-out allocations; never adaptively recycle development cohorts."),
            telemetry=dict(required=["epoch/final KL", "target KL", "threshold hits and stops before max epoch",
                                     "epochs and Adam steps", "entropy with sample weights", "value_loss with original units",
                                     "EV plus target variance and definedness", "clip fraction", "raw GAE mean/std/RMS/extrema/count per refresh",
                                     "reward/return/value scale", "switch numerator/within-episode denominator/rate per1000 frames",
                                     "LR/entropy schedule and normalizer state", "actual frames/decisions/episodes/unique seeds",
                                     "component time/RSS/MPS/checkpoint I/O and size"],
                           parity="One durable complete row for every committed complete update including closing partial. Carry previous action across rollouts; exclude episode resets. EV null is valid only with its variance/definedness reason."),
            health=dict(immediate_incident=["nonfinite/invalid distribution or metric", "missing telemetry or wrong counters",
                                            "source/state/lease drift", "power/resource violation", "torn checkpoint or missing receipt"],
                        proposed_KL_stop="final full-rollout approximate KL>0.15 for3 consecutive completed updates stops at boundary; freeze/qualify threshold after tuning, before long launch.",
                        warnings_only="Low entropy, negative/undefined EV and large value loss alone do not prove collapse; report alongside survival. PPO four-epoch0.03 KL stop remains independently registered unless an approved recipe changes it.",
                        precedence="Hard wall/resource/AC/finiteness guards override all learning rules. Budget-limited completion is not scientific plateau. Mid-update interruption remains first partial failure, no eligible complete endpoint from that update."),
            checkpoint=dict(state=["model", "Adam", "Python/NumPy/Torch CPU/MPS and owned-generator RNGs",
                                   "LR/entropy schedule", "normalizer statistics", "every simulator slot and core RNG",
                                   "feature History and cached observations", "episode/seed indices and collision set",
                                   "current K and held-action phase", "previous action for switch metrics",
                                   "frame and cumulative wall clocks", "monitor/incumbent/patience state",
                                   "last5 averaging queue", "source/runtime/parent/previous-checkpoint hashes"],
                            commit="No mid-update restore. Fsync state+telemetry then publish no-replace hash-bound commit manifest; directory fsync. Restore only a fully committed boundary through separately authorized phase child. Preserve first partial failure.",
                            averaging="Keep every raw checkpoint plus rolling arithmetic average of last5 complete model states, no Adam averaging. Normalization must share a compatible basis or averaging is blocked.",
                            failure_limit="Crash may lose uncommitted post-checkpoint work; never claim zero lost updates or silently replay consumed work. Recovery requires new explicit authority and cumulative-budget accounting."),
            prerequisites=["Accepted S1 measurements and S2 throughput/memory parity", "prospective recipe-entry qualification",
                           "full simulator/wrapper/learner round-trip and next-step parity for K1/2/3/4",
                           "real telemetry parity and scheduler next-Adam-update parity", "isolated evaluation and durable child-phase lifecycle",
                           "checkpoint throughput/disk reserve qualification and aggregate resource forecast",
                           "concrete recipe/init/N/T/minibatch/gamma/lambda/K/schedule/seed vectors/hard bounds and independent reviews",
                           "exact lease availability/disposition and Taylor explicit launch approval"],
            concurrency_question="Should a separately registered two-job contention/resource qualification be proposed? One MPS campaign remains the rule until Taylor explicitly changes it; prefer serial full-state phase handoffs first.",
            official_parent=324, promotion=False, performance_result=None)
plan["combined_long_run_ceiling_seconds"] = 66000 + 22680 + 15120
assert plan["combined_long_run_ceiling_seconds"] == 103800
assert entry["all_four_missing_ceiling_seconds"] == 51480
assert entry["only_two_controls_missing_ceiling_seconds"] == 29520
assert monitor["looks"] * monitor["games_per_look"] == monitor["total_games"]
assert final["models"] * final["fresh_game_seeds"] == final["games"]
assert 1024 + 6 * 1024 + 2048 == plan["seeds"]["new_evaluation_seeds_requested"]
save("long-run-protocol-v5.json", plan)

protected_paths = [
    "learning/runs/v2-orchestration/state.json",
    "learning/runs/v2/track-a-review-scaling-parent-20261030-r1/S1-first-failure.json",
    "learning/runs/v2/track-a-review-scaling-parent-20261030-r1/S1-launch.claimed",
    "learning/runs/v2/priority-runlist-parent-20261030-r4/priority-run-list-v4.json",
    "learning/runs/v2/priority-runlist-parent-20261030-r4/approval-run-list.html",
    "learning/runs/v2/one-frame-training-comparison-parent-20261029-r2/operator-handoff.json",
    FORMAL + "/registration-formal-final-r5.json",
]
if not (OUT / "protected-before.json").exists():
    save("protected-before.json", {path: sha(ROOT / path) for path in protected_paths})
print(json.dumps(dict(findings=len(findings), long_run_ceiling_seconds=103800,
                      all_missing_entry_ceiling_seconds=51480, games=24576 + 14336,
                      runtime_launches=0, new_seed_cohorts=0)))
