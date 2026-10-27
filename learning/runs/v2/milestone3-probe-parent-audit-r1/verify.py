"""Read-only independent audit of one retained device probe; no model execution."""
from __future__ import annotations

import collections
import hashlib
import json
import math
import pathlib
import subprocess
import sys
import time
import types
from datetime import datetime, timezone

import torch

torch.set_num_threads(1)
ROOT = pathlib.Path.cwd()
OUT = pathlib.Path(__file__).resolve().parent
EX = ROOT / "learning/runs/v2/milestone3-probe-execution-r1"
RUN = ROOT / "learning/runs/v2/milestone3-device-probe-r1"
OP = ROOT / "learning/runs/v2-orchestration"
INSPECTED = {}


def sha(path):
    path = pathlib.Path(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    INSPECTED[str(path.relative_to(ROOT))] = digest
    return digest


def read(path):
    sha(path)
    return json.loads(path.read_bytes())


def records(path):
    sha(path)
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def finite(value):
    if isinstance(value, float):
        assert math.isfinite(value)
    elif isinstance(value, dict):
        for x in value.values():
            finite(x)
    elif isinstance(value, (list, tuple)):
        for x in value:
            finite(x)


def inventory(directory):
    manifest = read(directory / "artifact-sha256.json")
    actual = {str(p.relative_to(directory)) for p in directory.rglob("*") if p.is_file()}
    assert actual == set(manifest) | {"artifact-sha256.json"}
    assert all(sha(directory / name) == digest for name, digest in manifest.items())
    return len(manifest)


started = time.monotonic()
start_utc = datetime.now(timezone.utc).isoformat()
plan_path = OP / "milestone3_device_probe_r1-plan.json"
plan = read(plan_path)
assert sha(plan_path) == "1348ba10f8e0f4ea05afde19babda635f758f094e742cb846f1d6e77e3d6c315"
identity = read(ROOT / plan["identity"])
config = read(ROOT / plan["config"])
assert sha(ROOT / plan["identity"]) == plan["identity_sha256"] == "82ad7e95ed3b1a780a826b44d603e2ef2cecc5c1e4057f6ceec4e0ebc3b92267"
assert sha(ROOT / plan["config"]) == plan["config_sha256"]
assert hashlib.sha256(json.dumps(config, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest() == plan["semantic_config_sha256"]
assert config["phase_settings"]["run_seed"] == 5562878279179977985
assert len(identity["sources"]) == 75
assert all(sha(ROOT / name) == digest for name, digest in identity["sources"].items())
execution_files, runner_files = inventory(EX), inventory(RUN)
command = read(EX / "command-terminal.json")
command_start = read(EX / "command-start.json")
execution = read(EX / "result.json")
rr = read(RUN / "run-result.json")
wr = read(RUN / "worker-result.json")
assert command["argv"] == command_start["argv"] == plan["argv"]
assert command["cwd"] == plan["cwd"] and command["environment_overrides"] == plan["environment"]
assert type(command["supervisor_exit_code"]) is int and command["supervisor_exit_code"] == 0
assert not command["timed_out"] and execution["command_launch_count"] == 1
assert rr["worker_exit_code"] == 0 and rr["status"] == wr["status"] == "passed"
assert rr["worker_result"] == wr and rr["run_id"] == plan["run_id"]
assert rr["phase"] == wr["phase"] == "probe"
assert rr["automatic_retries"] == 0 and not rr["limits_relaxed"] and not rr["B_opened"]
assert 0 <= rr["consumed_phase_wall_seconds"] == rr["elapsed_seconds"] <= 180
assert 0 <= wr["elapsed_seconds"] <= 180
for value in (rr, wr):
    assert value["identity_sha256"] == plan["identity_sha256"]
    assert value["config_sha256"] == plan["config_sha256"]
    finite(value)
assert read(RUN / "identity.json") == identity
assert read(RUN / "registered-config.json") == config
assert not list(RUN.glob("*failure*"))
assert wr["weights_discarded_from_training"] is True
assert execution["probe_weights_excluded_from_pilot_initialization"] is True
assert read(EX / "process-ownership-after.json")["remaining_owned"] == []
events = records(EX / "wrapper-events.jsonl")
kinds = collections.Counter(row["kind"] for row in events)
assert not any("signal" in row["kind"].lower() or "cleanup" in row["kind"].lower() for row in events)
ownership = read(EX / "worker-ownership-observed.json")
owned_pids = [command["supervisor_pid"], ownership["process"]["pid"]]
pid_status = []
for pid in owned_pids:
    result = subprocess.run(["ps", "-p", str(pid), "-o", "pid=,ppid=,pgid=,lstart=,command="], capture_output=True, text=True, timeout=5)
    pid_status.append({"pid": pid, "returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr})
    assert result.returncode == 1 and not result.stdout.strip()
peaks = {}
for filename in ("supervisor-resources.jsonl", "worker-resources.jsonl"):
    rows = records(RUN / filename)
    result = {"samples": len(rows)}
    for key in ("rss_bytes", "self_peak_rss_bytes", "worker_rss_bytes", "mps_driver_bytes"):
        result[key] = max(row.get(key, 0) for row in rows)
        assert result[key] <= 6442450944
    peaks[filename] = result
assert peaks["worker-resources.jsonl"]["rss_bytes"] == wr["maximum_observed_RSS_bytes"] == 1764065280
assert peaks["worker-resources.jsonl"]["mps_driver_bytes"] == wr["maximum_MPS_driver_bytes"] == 2348630016
assert peaks["supervisor-resources.jsonl"]["worker_rss_bytes"] == 1763983360
measurements = wr["measurements"]
assert [m["device"] for m in measurements] == ["cpu", "mps"]
for m in measurements:
    assert m["status"] == "completed" and m["optimizer_steps"] == 128
    assert m["metrics"]["transitions"] == 16384 and m["metrics"]["epochs_completed"] == 4
    assert m["metrics"]["optimizer_steps"] == 128 and m["metrics"]["finite"] is True
    assert m["metrics"]["actor_grad_norm"] > 0 and m["metrics"]["critic_grad_norm"] > 0
    assert not m["metrics"]["early_stop_kl"]
    assert m["inference_wall_seconds"] + m["update_wall_seconds"] == m["measured_inference_plus_update_seconds"]
assert min(measurements, key=lambda m: m["measured_inference_plus_update_seconds"])["device"] == wr["selected_device"] == "mps"
assert wr["devices_excluded_from_speed_selection_for_unequal_update_work"] == []

# The pickle contains a plain data record. A stub class permits CPU-only data
# inspection without importing the project package, native module or its code.
package = types.ModuleType("dodge_rl")
package.__path__ = []
module = types.ModuleType("dodge_rl.ppo")
module.RolloutBatch = type("RolloutBatch", (), {})
sys.modules["dodge_rl"] = package
sys.modules["dodge_rl.ppo"] = module
loaded = {}
for name in (wr["initial_checkpoint"], wr["frozen_rollout"], *[m["checkpoint"] for m in measurements]):
    sha(RUN / name)
    loaded[name] = torch.load(RUN / name, map_location="cpu", weights_only=False)
initial = loaded[wr["initial_checkpoint"]]
buffer = loaded[wr["frozen_rollout"]]
batch = buffer["batch"]
assert buffer["initial_checkpoint_sha256"] == wr["initial_checkpoint_sha256"] == sha(RUN / wr["initial_checkpoint"])
assert sha(RUN / wr["frozen_rollout"]) == wr["frozen_rollout_sha256"]
assert initial["tag"] == buffer["tag"] == "probe_diagnostic"
assert initial["identity"] == identity
assert batch.actions.shape == (256, 64)
tensor_shapes = {}
for name, value in vars(batch).items():
    assert isinstance(value, torch.Tensor) and value.device.type == "cpu"
    tensor_shapes[name] = {"shape": list(value.shape), "dtype": str(value.dtype)}
    if value.is_floating_point():
        assert torch.isfinite(value).all().item()
assert batch.global_feats.shape == (256, 64, 1, 14)
assert batch.entity_feats.shape == (256, 64, 80, 16)
assert batch.entity_mask.shape == batch.entity_types.shape == (256, 64, 80)
assert batch.entity_mask.dtype == batch.terminated.dtype == batch.truncated.dtype == torch.bool
assert not (batch.terminated & batch.truncated).any().item()
assert ((batch.actions >= 0) & (batch.actions < 9)).all().item()
assert ((batch.elapsed_raw_frames >= 1) & (batch.elapsed_raw_frames <= 4)).all().item()
assert torch.equal(batch.alive_raw_frames, batch.elapsed_raw_frames - batch.terminated.to(torch.int64))
raw_expected = batch.score_delta_raw_fixed.double() / 65536 + batch.alive_raw_frames.double() / 100 - 5 * batch.terminated
max_raw_error = (raw_expected - batch.raw_rewards.double()).abs().max().item()
assert max_raw_error <= 1e-5
assert torch.equal(batch.rewards, batch.raw_rewards * config["ppo"]["reward_scale"])
assert (batch.next_values[batch.terminated] == 0).all().item()
# Independently compute both recurrence and finite-horizon sums. This is a data
# arithmetic audit only; it invokes no project implementation or model.
r = batch.rewards.double()
v = batch.values.double()
nv = batch.next_values.double()
done = batch.terminated | batch.truncated
gamma = config["ppo"]["gamma"]
lam = config["ppo"]["gae_lambda"]
delta = r + gamma * nv * (~batch.terminated) - v
advantages = torch.empty_like(r)
carry = torch.zeros(64, dtype=torch.float64)
for step in range(255, -1, -1):
    carry = delta[step] + gamma * lam * (~done[step]) * carry
    advantages[step] = carry
sum_form = torch.zeros_like(r)
for start in range(256):
    weight = torch.ones(64, dtype=torch.float64)
    for stop in range(start, 256):
        sum_form[start] += weight * delta[stop]
        weight *= gamma * lam * (~done[stop])
gae_difference = (sum_form - advantages).abs().max().item()
assert gae_difference < 1e-12 and torch.isfinite(advantages).all().item()
updates = []
for measurement in measurements:
    state = loaded[measurement["checkpoint"]]
    assert state["tag"] == "probe_diagnostic" and state["identity"] == identity
    assert state["actual_measured_device"] == measurement["device"]
    assert state["update_progress"]["complete"] is True
    assert state["update_progress"]["optimizer_steps"] == 128
    steps = {float(item["step"]) for item in state["optimizer"]["state"].values()}
    assert steps == {128.0}
    changed = 0
    for name, tensor in state["model"].items():
        assert tensor.device.type == "cpu" and torch.isfinite(tensor).all().item()
        changed += int(not torch.equal(tensor, initial["model"][name]))
    assert changed > 0
    updates.append({"device": measurement["device"], "optimizer_state_entries": len(state["optimizer"]["state"]), "optimizer_step_values": sorted(steps), "changed_parameter_tensors": changed})
cpu = loaded[measurements[0]["checkpoint"]]
mps = loaded[measurements[1]["checkpoint"]]
assert torch.equal(cpu["rng"]["torch_cpu"], mps["rng"]["torch_cpu"])
max_final_parameter_delta = max((cpu["model"][n] - mps["model"][n]).abs().max().item() for n in cpu["model"])
episode_rows = records(RUN / "training-episodes.jsonl")
initial_rows = [r for r in episode_rows if r["kind"] == "initial"]
assert len(initial_rows) == 1
assert initial_rows[0]["batch_info"]["effective_excluded_seed_ranges"] == config["excluded_seed_ranges"]
seeds = []
def find_seeds(value):
    if isinstance(value, dict):
        if "actual_seed" in value:
            seed = value["actual_seed"]
            assert type(seed) is int and 0 <= seed < 2**32
            assert not any(a <= seed <= b for a, b in config["excluded_seed_ranges"])
            seeds.append(seed)
        for v in value.values():find_seeds(v)
    elif isinstance(value, list):
        for v in value:find_seeds(v)
find_seeds(episode_rows)
completed = [r["info"] for r in episode_rows if r["kind"] == "probe_completed"]
assert len(completed) == int(batch.terminated.sum() + batch.truncated.sum()) == 183
for info in completed:
    expected = info["score_raw_fixed"] / 65536 + info["alive_frames"] / 100 - 5 * info["terminated"]
    assert abs(expected - info["objective_return"]) <= 1e-9
    assert info["alive_frames"] == info["gameplay_frames"] - int(info["terminated"])
assert (RUN / "training-metrics.jsonl").read_bytes() == b""
sha(RUN / "training-metrics.jsonl")
assert all(sha(ROOT / name) == digest for name, digest in identity["sources"].items())
assert all(sha(ROOT / name) == digest for name, digest in list(INSPECTED.items()))
(OUT / "inspected-inputs.json").write_text(json.dumps(INSPECTED, indent=2, sort_keys=True) + "\n")
audit = {"status": "passed", "findings": [], "started_at_utc": start_utc,
    "finished_at_utc": datetime.now(timezone.utc).isoformat(), "elapsed_seconds": time.monotonic() - started,
    "scope": "read_only_receipts_source_and_CPU_tensor_deserialization;no_model_forward_optimizer_update_or_gameplay",
    "verified": {"execution_artifact_entries": execution_files, "runner_artifact_entries": runner_files,
        "current_source_pins": 75, "one_observed_command": True, "supervisor_exit_code": command["supervisor_exit_code"],
        "worker_exit_code": rr["worker_exit_code"], "source_pins_unchanged": True,
        "consumed_phase_wall_seconds": rr["consumed_phase_wall_seconds"], "outer_duration_seconds": command["duration_seconds"],
        "wrapper_event_kinds": dict(kinds), "resource_peaks": peaks, "owned_pid_inspection": pid_status,
        "selected_device": "mps", "measurements": measurements,
        "CPU_to_MPS_matched_work_ratio": measurements[0]["measured_inference_plus_update_seconds"] / measurements[1]["measured_inference_plus_update_seconds"],
        "tensor_shapes": tensor_shapes, "raw_reward_max_abs_error": max_raw_error,
        "GAE_recurrence_vs_independent_sum_max_abs_difference": gae_difference,
        "terminated": int(batch.terminated.sum()), "truncated": int(batch.truncated.sum()),
        "raw_frames": int(batch.elapsed_raw_frames.sum()), "alive_raw_frames": int(batch.alive_raw_frames.sum()),
        "completed_episode_reward_audits": len(completed), "logged_seed_occurrences": len(seeds), "unique_logged_seeds": len(set(seeds)),
        "updated_checkpoints": updates, "CPU_MPS_final_parameter_max_abs_difference": max_final_parameter_delta,
        "CPU_MPS_final_CPU_rng_equal": True, "probe_tags_only": True, "inspection_inputs_pinned": len(INSPECTED)},
    "limitations": ["Same starting weights are supported by initial checkpoint/buffer lineage and the reviewed load_state_dict path, not an independent execution replay.",
        "The CPU-only GAE audit verifies finite saved data and two independent arithmetic formulations; no stored learner GAE output exists to compare directly.",
        "Observed sampled RSS and MPS driver maxima are separate overlapping accounting categories; no unsampled hard memory ceiling is claimed.",
        "One frozen-buffer timing comparison does not establish closed-loop training throughput, teacher skill, score/survival qualification or future pilot initialization.",
        "No B/E evaluation or data use appeared in retained metadata; logged actual seeds are outside all three exclusion ranges."]}
(OUT / "audit.json").write_text(json.dumps(audit, indent=2, sort_keys=True, allow_nan=False) + "\n")
print(json.dumps({"status": audit["status"], "inputs": len(INSPECTED), "raw_reward_error": max_raw_error,
                  "GAE_error": gae_difference, "selected_device": "mps", "elapsed_seconds": audit["elapsed_seconds"]}))
