"""Strict identity and schedule contract for retained324 linear-LR registration."""
from __future__ import annotations

from pathlib import Path

SCHEMA = "d2_retained324_linear_lr_registration_v1"
RUN_ID = "D2-retained324-linear-lr-20261026-r1"
ROOT = Path("/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79")
OUTPUT = ROOT / "learning/runs/v2" / RUN_ID
PHASE_START = 324
PHASE_END = 384
PARENT_TOTAL_UPDATES = 372
TOTAL_UPDATES = 432
RUN_SEED = 4200000001
SCHEDULE_SPEC_SHA256 = "7ceed85c5dc277602f2f51937b4ac003e2013e2689341a963ce5d82d5b64c9e4"
HELPER_SHA256 = "ef81e87580c39e6f733098a5c228e4660af03e7fccddcc06044e9d3612bce079"


def need(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_identity(registration: dict) -> dict:
    need(isinstance(registration, dict) and registration.get("schema") == SCHEMA,
         "Wrong registration schema")
    need(registration.get("run_id") == RUN_ID, "Wrong registration run identity")
    root = Path(registration.get("root", "")).resolve()
    output = Path(registration.get("output", "")).resolve()
    need(root == ROOT.resolve() and output == root / "learning/runs/v2" / RUN_ID,
         "Unsafe registration output identity")
    need(registration.get("run_seed") == RUN_SEED, "Paired master seed differs")
    need((registration.get("phase_start"), registration.get("phase_end"),
          registration.get("parent_total_updates"), registration.get("expected_total_updates"))
         == (PHASE_START, PHASE_END, PARENT_TOTAL_UPDATES, TOTAL_UPDATES),
         "Scheduled treatment update horizon differs")
    need(registration.get("new_updates") == 60
         and registration.get("evaluation_updates") == [324, 336, 348, 360, 372, 384],
         "Scheduled treatment update/evaluation contract differs")
    schedule = registration.get("lr_schedule")
    need(isinstance(schedule, dict), "Linear LR schedule contract is missing")
    need(schedule.get("origin_cumulative_update") == 372
         and schedule.get("horizon_updates") == 60
         and schedule.get("start_lr") == 3e-5 and schedule.get("end_lr") == 1e-5
         and schedule.get("application") == "after_rollout_before_ppo_update"
         and schedule.get("group_lr_log") == "per_optimizer_group_per_update",
         "Linear LR schedule contract differs")
    need(schedule.get("spec_sha256") == SCHEDULE_SPEC_SHA256
         and schedule.get("helper_sha256") == HELPER_SHA256,
         "Linear LR schedule source/spec digest differs")
    need(registration.get("training_eligible") is False
         and registration.get("promoted") is False
         and registration.get("normal_training_iteration") is True,
         "Registration grants continuation or promotion authority")
    need(schedule.get("spec_sha256") == SCHEDULE_SPEC_SHA256, "Schedule spec digest differs")
    need(registration.get("limits", {}).get("planned_seconds") == 1750
         and registration["limits"].get("work_seconds") == 1790
         and registration["limits"].get("total_seconds") == 1800
         and registration["limits"].get("cleanup_seconds") == 10
         and registration["limits"].get("RSS_bytes") == 6442450944
         and registration["limits"].get("MPS_bytes") == 6442450944,
         "Registered resource limits differ")
    need(registration.get("ppo") == {"gamma": .995, "gae_lambda": .95, "learning_rate": 3e-5,
         "adam_eps": .00001, "clip_coef": .2, "vf_coef": .5, "ent_coef": .01,
         "max_grad_norm": .5, "update_epochs": 4, "minibatch_size": 512,
         "target_kl": .03, "reward_scale": .1}, "PPO settings differ")
    for key in ("runner_path", "launcher_path", "parent_adapter_path", "registration_schema_path", "lr_schedule_path"):
        need(Path(registration.get(key, "")).is_absolute(), "Missing absolute source path: " + key)
    pins = registration.get("pins", {})
    for path_key, digest_key in (("runner_path", "runner_sha256"), ("launcher_path", "launcher_sha256"),
                                 ("parent_adapter_path", "parent_adapter_sha256"),
                                 ("registration_schema_path", "registration_schema_sha256"),
                                 ("lr_schedule_path", "lr_schedule_sha256")):
        need(registration[path_key] in pins and pins[registration[path_key]] == registration.get(digest_key),
             "Required executable source pin missing: " + path_key)
    return registration
