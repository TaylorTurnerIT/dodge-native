"""One prospective normal D2 training iteration; no stage promotion.

Importing this module uses only the standard library. The parent supplies an
externally pinned registration and an isolated, fully pinned runtime package.
Historical validators and accepted checkpoint metadata remain unchanged.
"""
from __future__ import annotations

import argparse
from collections.abc import Mapping
import hashlib
import json
import math
import os
from pathlib import Path
import resource
import signal
import sys
import time
import traceback

PARENT_SHA = "105e0f7a83e154116bd9f0d5eaaf573a896886468c9038f548f5ce7e6377c7ea"
PARENT_REGISTRATION_SHA = "6f4adf808789655a663800a1e4a0613192d02b0c8287d121455ea748fe043916"
PARENT_RECEIPT_SHA = "7968a62b6e601fab971e4145dbaebfa1995c8f696e6df442ab70fc0435b74903"
PARENT_WALL_SECONDS = 2952.324712417151
PARENT_RECEIPT_SCHEMA = "d2_normal_training_parent_terminal_receipt_v1"
PARENT_RUNTIME_SHA = "2cf10e9f056f41b39dc17845192e9adf553a5f699546d4f5dcea764a23e36b31"
CONFIG_SHA = "2d8eb5626d0debdf5416d0b89610d78ddd56011c3238a82fec72efabe1bd7fe3"
ANCHOR_SHA = "4e9f12884712916e9eb957628b89b357784c79d0f1f6f8ab18e6047935197413"
VALIDATOR_SHA = "72c34ea7a3208f8ce1cba1cd144b3ba58bac7b246ce57610b70970355ac60c55"
ARCHIVE_SHA = "3b4b1e4f3337323de9938c0c86f158036d8dacc77acba645b3e150d9d2e765bd"
NEW_NATIVE_SHA = "022d41dde9bace0b4f4c4c06b9b4ed007bc2c60013cd98734086e587d7bb997e"
OLD_NATIVE_SHA = "967c7249acd52339d1818dcbe94e63ee734aea914c3497eb59a7e945a6e95583"
RANGES = [[0xB0000000, 0xB00003E7], [0xD0000000, 0xD000007F], [0xE0000000, 0xE00003E7]]
NEW_UPDATES = 72
PHASE_START = 180
PHASE_END = 252
PARENT_TOTAL_UPDATES = 228
EXPECTED_TOTAL = 300
LIMITS = {"max_updates": NEW_UPDATES, "eval_updates": [PHASE_START, PHASE_END], "work_seconds": 1600,
          "total_seconds": 1800, "RSS_bytes": 6442450944, "MPS_bytes": 6442450944,
          "retries": 0}
PPO = {"gamma": .995, "gae_lambda": .95, "learning_rate": .0003, "adam_eps": .00001,
       "clip_coef": .2, "vf_coef": .5, "ent_coef": .01, "max_grad_norm": .5,
       "update_epochs": 4, "minibatch_size": 512, "target_kl": .03, "reward_scale": .1}
RUN_ID = "D2-continuation-20261025-r2"
POLICY_SHA = "bfcbee1609cec0180495c957cf4b5e0b31356f395e2a706217cc9225647d23ae"
GATE_SHA = "11257111602f26e49fbc71afc6a51acb79434a3717bd8d6d36d1bbf87dfb8841"
INVENTORY_SHA = "2957832457c39751998012f4aeb4440f5d7570250ae9ab072ee10d86dd970ed6"
OLD_PPO_SHA = "abf25f327f9ff749a8a32de4edb07705f12ebcdc5cd0eba8775ad4f693eff1d5"
NEW_PPO_SHA = "b3cef91b1293056e9d1820a94fd5730accae4c5728d23566857a6c3a0e1eeac5"
NEW_ALIGNMENT_SHA = "cd7d16aebe9eed247b0a4747956d8106991b3637ab0b45118ea9e7ebc0c1e25f"
ALIGNMENT_MEANING = "measurement_only_CPU_shadow; one first existing minibatch per update; not native MPS gradients or a competence gate"


def need(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1048576), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    """New-path publication only; no replacing old receipts."""
    with Path(path).open("x") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def emit(stream, value):
    stream.write(json.dumps(value, sort_keys=True, allow_nan=False) + "\n")
    stream.flush()


def verify_pins(pins):
    need(isinstance(pins, dict) and bool(pins), "Missing input pins")
    for name, digest in pins.items():
        path = Path(name)
        need(path.is_absolute() and path.is_file() and len(digest) == 64,
             "Invalid pinned file: " + name)
        need(sha(path) == digest, "Pinned input changed: " + name)


def check_lease(reg):
    need(read(reg["state_path"]).get("active_long_campaign") == reg["expected_lease"],
         "Exact parent-owned diagnostic lease changed")


def check_import_cache(reg):
    prefix = reg["import_policy"]["pycache_prefix"]
    path = Path(prefix)
    need(path.is_absolute() and path.is_dir() and not any(path.iterdir()),
         "Registered bytecode prefix must be an empty absolute directory")
    need(os.environ.get("PYTHONPYCACHEPREFIX") == prefix
         and sys.pycache_prefix == prefix and sys.dont_write_bytecode,
         "Process bytecode policy differs from registration")


def validate_registration(reg):
    need(reg.get("schema") == "d2_training_v3_continuation_registration_v1", "Wrong continuation registration schema")
    need(reg.get("normal_training_iteration") is True and reg.get("training_eligible") is False,
         "Prospective continuation eligibility flags changed")
    need(reg["limits"] == LIMITS, "Registered continuation limits changed")
    need(reg["run_id"] == RUN_ID and reg["run_seed"] == 810631976, "Wrong continuation identity/seed")
    need(type(reg["run_seed"]) is int and 0 <= reg["run_seed"] <= 0xFFFFFFFF
         and not any(a <= reg["run_seed"] <= b for a, b in RANGES), "Invalid continuation master seed")
    need(reg["timing_policy"] == "launcher_monotonic_start_plus_registered_limits_v1", "Timing policy changed")
    for key in ("root", "output", "runtime_root", "interpreter", "runner_path", "launcher_path", "state_path", "config_path"):
        need(Path(reg[key]).is_absolute(), "Registration path must be absolute: " + key)
    need(Path(reg["cancel_path"]).is_absolute(), "Cancellation path must be absolute")
    root = Path(reg["root"])
    need(Path(reg["output"]).resolve() == (root / "learning/runs/v2" / RUN_ID).resolve(), "Continuation output path differs")
    need(reg["parent"].get("sha256") == PARENT_SHA and reg["parent"].get("registration_sha256") == PARENT_REGISTRATION_SHA,
         "Exact successful normal-D2 parent and registration required")
    need(Path(reg["parent"]["path"]).resolve() == (root / "learning/runs/v2/D2-gradient-alignment-20261025-r2/checkpoint-000180-candidate.pt").resolve(),
         "Parent candidate path substitution")
    need(reg["parent"].get("phase") == "D2" and reg["parent"].get("completed_updates") == PHASE_START,
         "Parent is not a complete normal D2 phase-180 candidate")
    receipt = reg["parent"].get("terminal_receipt_path")
    receipt_sha = reg["parent"].get("terminal_receipt_sha256")
    need(isinstance(receipt, str) and Path(receipt).is_absolute() and isinstance(receipt_sha, str) and len(receipt_sha) == 64,
         "Parent-authoritative terminal receipt path/digest required")
    need(receipt_sha == PARENT_RECEIPT_SHA, "Parent terminal receipt is not the externally pinned receipt")
    need(reg["config_sha256"] == CONFIG_SHA and reg["native"]["sha256"] == NEW_NATIVE_SHA
         and reg["native"]["old_sha256"] == OLD_NATIVE_SHA, "Frozen D2 runtime identity differs")
    need(Path(reg["native"]["path"]).resolve().parent == (Path(reg["runtime_root"]) / "dodge_rl").resolve(),
         "Native runtime path differs")
    need(reg["runtime_versions"].keys() == {"python", "torch", "numpy"}, "Runtime versions missing")
    need(reg["import_policy"].get("pycache_prefix") and Path(reg["import_policy"]["pycache_prefix"]).is_absolute(),
         "Absolute empty bytecode prefix required")
    need(isinstance(reg["expected_lease"], dict) and reg["expected_lease"].get("run_id") == RUN_ID
         and reg["expected_lease"].get("kind") == "D2_gradient_alignment"
         and reg["expected_lease"].get("authorization") == "user_continue_D2_training_v3"
         and reg["expected_lease"].get("parent_checkpoint_sha256") == PARENT_SHA,
         "Continuation lease authority differs")
    return reg


def validate_parent_checkpoint_for_restore(state, checkpoint_sha256=PARENT_SHA):
    """Validate the exact accepted provisional parent before any environment construction."""
    need(checkpoint_sha256 == PARENT_SHA, "Parent checkpoint digest authority differs")
    need(state.get("tag") == "candidate" and state.get("phase") == "D2"
         and state.get("identity", {}).get("phase") == "D2"
         and state.get("update_progress", {}).get("complete") is True
         and state.get("update_progress", {}).get("completed_updates") == PHASE_START
         and state.get("phase_update") == PHASE_START
         and state.get("training_eligible") is False and state.get("promoted") is False,
         "Not the exact complete provisional normal D2 candidate")
    need(state.get("registration_sha256") == PARENT_REGISTRATION_SHA
         and state.get("cumulative_counters", {}).get("updates") == PARENT_TOTAL_UPDATES
         and state.get("counters", {}).get("updates") == 48,
         "Accepted parent registration or cumulative/local update counts differ")
    need(state.get("identity", {}).get("run_id") == "D2-gradient-alignment-20261025-r2",
         "Parent checkpoint run identity differs")
    return state


def validate_parent_terminal_receipt(receipt, reg):
    """Require parent acceptance for exact successful normal phase-180 D2 candidate."""
    parent = reg["parent"]
    need(receipt.get("schema") == PARENT_RECEIPT_SCHEMA
         and receipt.get("status") == "accepted_completed_normal_training_iteration",
         "Parent terminal receipt is absent or unsuccessful")
    need(receipt.get("training_continuation_eligible") is True
         and receipt.get("stage_promotion_eligible") is False
         and receipt.get("competence_passed") is False
         and receipt.get("checkpoint_metadata_edited") is False,
         "Parent receipt does not authorize only provisional same-phase continuation")
    need(receipt.get("run_id") == "D2-gradient-alignment-20261025-r2" and receipt.get("phase") == "D2"
         and receipt.get("completed_phase_updates") == PHASE_START
         and receipt.get("completed_local_updates") == 48
         and receipt.get("raw_outer_exit") == 0 and receipt.get("raw_worker_exit") == 0
         and receipt.get("publication_failure_present") is False
         and receipt.get("cancellation_lineage") == [],
         "Parent receipt does not certify complete successful normal D2 execution")
    need(receipt.get("checkpoint_sha256") == PARENT_SHA
         and receipt.get("registration_sha256") == PARENT_REGISTRATION_SHA
         and receipt.get("inclusive_iteration_wall_seconds") == 729.7051892500604
         and receipt.get("cumulative_D2_inclusive_wall_seconds") == PARENT_WALL_SECONDS
         and receipt.get("cumulative_counters", {}).get("updates") == PARENT_TOTAL_UPDATES,
         "Parent receipt candidate, registration, wall, or cumulative counter binding differs")
    artifact_path = str((Path(reg["root"]) / "learning/runs/v2/D2-gradient-alignment-20261025-r2/checkpoint-000180-candidate.pt").resolve())
    need(receipt.get("checkpoint_path") == artifact_path
         and receipt.get("artifacts", {}).get(artifact_path) == PARENT_SHA,
         "Parent receipt artifact manifest does not bind exact candidate")
    return receipt


def validate_capsule_support(reg):
    required_support = {
        "v2-m3-run-protocol.json": "9e0d82028011f83e0cf6ddaef5f5e118591158d8a557f6698c82c150d5a69bab",
        "teacher-qualification-v2.json": "e091f8a2fad0a307d289a6d306112606b15df8f8aa0f3a75707ac7cfb2cee803",
        "v2-m3-component-contract.md": "a1051d82527a9aec1f7967ff8ab217c30263240e032991aeff7b993fd975ba47",
        "teacher-qualification-v3.json": "bfcbee1609cec0180495c957cf4b5e0b31356f395e2a706217cc9225647d23ae",
    }
    support = reg.get("capsule_support")
    need(isinstance(support, dict) and support == required_support,
         "Capsule support file set or exact registered hashes differ")
    for name, digest in required_support.items():
        support_path = Path(reg["runtime_root"]).parent / "docs" / name
        need(support_path.is_file() and sha(support_path) == digest,
             "Capsule support file missing or changed: " + name)
        need(reg["pins"].get(str(support_path)) == digest,
             "Capsule support file is not externally pinned: " + name)


def validate_runtime_continuity(reg):
    """Bind runtime root, exact parent member map, and current pins."""
    continuity = reg.get("runtime_continuity")
    need(isinstance(continuity, dict)
         and continuity.get("parent_runtime_sha256") == PARENT_RUNTIME_SHA
         and continuity.get("parent_registration_sha256") == PARENT_REGISTRATION_SHA
         and continuity.get("source_runtime_root") == str((Path(reg["root"]) / "learning/runs/v2/D2-gradient-capsule-parent-freeze-20261025-r5/own/runtime").resolve())
         and continuity.get("semantics") == "same_exact_runtime_member_paths_and_hashes;archival_baseline_to_shadow_review_is_ancestry_only"
         and reg.get("runtime_sha256") == PARENT_RUNTIME_SHA,
         "Exact accepted parent runtime continuity binding differs")
    old_root = Path(continuity["source_runtime_root"])
    new_root = Path(reg["runtime_root"])
    old_files = {p.relative_to(old_root).as_posix(): p for p in old_root.rglob("*")
                 if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"}
    new_files = {p.relative_to(new_root).as_posix(): p for p in new_root.rglob("*")
                 if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"}
    need(set(new_files) == set(old_files), "Same-runtime member path set differs")
    parent_member_hashes = continuity.get("member_sha256")
    need(isinstance(parent_member_hashes, dict) and set(parent_member_hashes) == set(old_files),
         "Accepted parent runtime member map differs")
    for relative, old_file in old_files.items():
        digest = sha(old_file)
        new_digest = sha(new_files[relative])
        need(digest == parent_member_hashes[relative] == new_digest,
             "Same-runtime member bytes differ: " + relative)
    package = Path(reg["runtime_root"]) / "dodge_rl"
    actual = {str(path.resolve()) for path in package.rglob("*") if path.is_file()
              and "__pycache__" not in path.parts and path.suffix != ".pyc"}
    need(actual and actual <= reg["pins"].keys(), "Unpinned isolated runtime member")
    return True


def load_registration(path, expected_sha):
    need(sha(path) == expected_sha, "External registration digest differs")
    reg = validate_registration(read(path))
    verify_pins(reg["pins"])
    parent = reg["parent"]
    critical = {reg["runner_path"], reg["launcher_path"], reg["interpreter"], reg["config_path"],
                parent["path"], parent["terminal_receipt_path"], reg["native"]["path"], reg["native"]["old_path"]}
    need(critical <= reg["pins"].keys(), "Critical continuation pins missing")
    need(reg["pins"][parent["path"]] == PARENT_SHA
         and reg["pins"][reg["config_path"]] == CONFIG_SHA
         and reg["pins"][reg["native"]["path"]] == NEW_NATIVE_SHA
         and reg["pins"][reg["native"]["old_path"]] == OLD_NATIVE_SHA,
         "Critical continuation pin binding differs")
    package = Path(reg["runtime_root"]) / "dodge_rl"
    actual = {str(path.resolve()) for path in package.rglob("*") if path.is_file()
              and "__pycache__" not in path.parts and path.suffix != ".pyc"}
    need(actual and actual <= reg["pins"].keys(), "Unpinned isolated runtime member")
    runtime_digest = hashlib.sha256(json.dumps(
        {name: reg["pins"][name] for name in sorted(actual)},
        sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    need(reg["runtime_sha256"] == runtime_digest, "Runtime manifest identity differs")
    validate_capsule_support(reg)
    validate_runtime_continuity(reg)
    need(reg["pins"].get(parent["path"]) == PARENT_SHA
         and reg["pins"].get(parent["terminal_receipt_path"]) == parent["terminal_receipt_sha256"],
         "Exact parent candidate/terminal receipt pins missing")
    need(sha(parent["terminal_receipt_path"]) == parent["terminal_receipt_sha256"], "Parent terminal receipt digest differs")
    validate_parent_terminal_receipt(read(parent["terminal_receipt_path"]), reg)
    root = Path(reg["root"])
    policy = root / "docs/teacher-qualification-v3.json"
    gate = Path(reg["runtime_root"]) / "dodge_rl/survival_gate.py"
    inventory_path = root / "learning/runs/v2/critic-diagnostic-parent-prepare-20261025-r1/dependency-inventory.json"
    need(reg["policy_sha256"] == POLICY_SHA and reg["pins"].get(str(policy)) == POLICY_SHA
         and reg["pins"].get(str(gate)) == GATE_SHA
         and reg["pins"].get(str(inventory_path)) == INVENTORY_SHA,
         "Policy, gate, or dependency inventory pin differs")
    inventory = read(inventory_path)
    need(all(reg["pins"].get(name) == item["sha256"] for name, item in inventory["pins"].items()),
         "Original interpreter/Torch/NumPy dependency pins missing")
    need(reg["pins"].get(reg["config_path"]) == CONFIG_SHA, "Frozen config pin differs")
    config = read(reg["config_path"])
    need(config["ppo"] == PPO and config["device"] == "mps" and config["batch_size"] == 64
         and config["rollout_steps"] == 256 and config["action_repeat"] == 4 and config["num_threads"] == 4
         and config["chunk_size"] == 8 and config["excluded_seed_ranges"] == RANGES,
         "Frozen learner/environment settings differ")
    check_import_cache(reg)
    check_lease(reg)
    need(sha(path) == expected_sha, "Registration changed during preflight")
    return reg, config


def continuation_cumulative_counters(parent_cumulative, local):
    """Compose local continuation work over accepted parent cumulative counters."""
    keys = ("updates", "optimizer_steps", "environment_decisions", "raw_frames")
    need(isinstance(parent_cumulative, dict) and isinstance(local, dict)
         and set(parent_cumulative) >= set(keys) and set(local) == set(keys),
         "Cumulative counter keys malformed")
    result = {}
    for key in keys:
        before, current = parent_cumulative[key], local[key]
        need(type(before) is int and before >= 0 and type(current) is int and current >= 0,
             "Cumulative counters must be nonnegative integers")
        result[key] = before + current
    return result

def finite_tree(value, key=""):
    if isinstance(value, dict):
        for name, item in value.items():
            finite_tree(item, name)
    elif isinstance(value, list):
        for item in value:
            finite_tree(item, key)
    elif value is None:
        need(key == "explained_variance", "Unexpected null metric")
    elif isinstance(value, float):
        need(math.isfinite(value), "Nonfinite metric")


def validate_gradient_alignment(diag):
    need(isinstance(diag, dict) and diag.get("backend") == "cpu_shadow"
         and diag.get("measures_live_MPS_gradients") is False
         and diag.get("snapshot") == "first_minibatch_pre_optimizer_step"
         and diag.get("probe_count") == 1 and diag.get("minibatch_count") == 512,
         "Gradient probe scope/labels differ")
    groups = diag.get("groups", {})
    need(all(name in groups for name in ("layers.0", "layers.1", "embeddings_and_input_projections", "final_norm")),
         "Gradient probe does not cover the full shared trunk")
    def check(moment):
        need(isinstance(moment, dict) and type(moment.get("defined")) is bool,
             "Gradient alignment moment schema differs")
        dot, actor, critic = moment.get("dot"), moment.get("actor_norm"), moment.get("weighted_critic_norm")
        need(all(type(v) in (int, float) and math.isfinite(v) for v in (dot, actor, critic))
             and actor >= 0 and critic >= 0, "Gradient alignment reductions are nonfinite or negative")
        defined = actor > 0 and critic > 0
        need(moment["defined"] is defined, "Gradient alignment defined flag differs")
        if defined:
            cosine, ratio = moment.get("cosine"), moment.get("norm_ratio_critic_over_actor")
            need(type(cosine) in (int, float) and math.isfinite(cosine) and -1.0000001 <= cosine <= 1.0000001
                 and type(ratio) in (int, float) and math.isfinite(ratio) and ratio > 0
                 and math.isclose(cosine, dot / (actor * critic), rel_tol=1e-9, abs_tol=1e-12)
                 and math.isclose(ratio, critic / actor, rel_tol=1e-9, abs_tol=1e-12),
                 "Gradient cosine or norm ratio identity differs")
        else:
            need("cosine" not in moment and "norm_ratio_critic_over_actor" not in moment,
                 "Undefined cosine or norm ratio must be omitted")
    check(diag)
    for moment in groups.values():
        check(moment)
    coverage = diag.get("coverage", {})
    need(type(coverage.get("parameters")) is int and coverage["parameters"] > 0
         and type(coverage.get("elements")) is int and coverage["elements"] > 0
         and coverage.get("actor_used") == coverage["parameters"]
         and coverage.get("critic_used") == coverage["parameters"],
         "Gradient probe parameter coverage incomplete")
    live = diag.get("live_preclip_grad_norm")
    clip = diag.get("live_clip_coefficient")
    need(type(live) in (int, float) and math.isfinite(live) and live >= 0
         and type(clip) in (int, float) and math.isfinite(clip)
         and math.isclose(clip, min(1.0, PPO["max_grad_norm"] / (live + 1e-6)), rel_tol=1e-9, abs_tol=1e-12),
         "Live preclip norm/clip coefficient identity differs")


def fingerprint(value):
    """Device-independent typed tree digest; does not consume RNG."""
    h = hashlib.sha256()
    def field(tag, payload=b""):
        tag = tag.encode("utf-8")
        h.update(len(tag).to_bytes(8, "big")); h.update(tag)
        h.update(len(payload).to_bytes(8, "big")); h.update(payload)
    def visit(v):
        if hasattr(v, "detach"):
            v = v.detach().cpu().contiguous().numpy()
        if hasattr(v, "dtype") and hasattr(v, "tobytes"):
            field("array", (str(v.dtype) + repr(tuple(v.shape))).encode())
            field("array-bytes", v.tobytes()); return
        if isinstance(v, Mapping):
            field("mapping", len(v).to_bytes(8, "big"))
            for k in sorted(v, key=lambda key: (type(key).__name__, repr(key))):
                field("entry")
                visit(k); visit(v[k])
            field("end-mapping")
        elif isinstance(v, list):
            field("list", len(v).to_bytes(8, "big"))
            for item in v:
                visit(item)
            field("end-list")
        elif isinstance(v, tuple):
            field("tuple", len(v).to_bytes(8, "big"))
            for item in v:
                visit(item)
            field("end-tuple")
        else:
            field("scalar:" + type(v).__module__ + "." + type(v).__qualname__, repr(v).encode())
    visit(value)
    return h.hexdigest()


def mismatch_paths(left, right, path="$", limit=128):
    """Return paths only; never serialize tensor, RNG, or scalar contents."""
    if fingerprint(left) == fingerprint(right):
        return []
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        if set(left) != set(right):
            return [path + ".<keys>"]
        found = []
        for key in sorted(left, key=lambda item: (type(item).__name__, repr(item))):
            found.extend(mismatch_paths(left[key], right[key], path + "." + str(key), limit))
            if len(found) >= limit:
                return found[:limit]
        return found or [path]
    if type(left) is not type(right):
        if hasattr(left, "detach") and hasattr(right, "detach"):
            try:
                if left.dtype != right.dtype: return [path + ".<dtype>"]
                if tuple(left.shape) != tuple(right.shape): return [path + ".<shape>"]
            except Exception:
                pass
        return [path + ".<type>"]
    if isinstance(left, (list, tuple)):
        if len(left) != len(right): return [path + ".<length>"]
        found = []
        for index, (a, b) in enumerate(zip(left, right)):
            found.extend(mismatch_paths(a, b, path + f"[{index}]", limit))
            if len(found) >= limit: return found[:limit]
        return found or [path]
    if hasattr(left, "detach") and hasattr(right, "detach"):
        if left.dtype != right.dtype: return [path + ".<dtype>"]
        if tuple(left.shape) != tuple(right.shape): return [path + ".<shape>"]
    return [path]


class Cancelled(BaseException):
    pass


class Guard:
    def __init__(self, reg, started, torch, stream, clock=time.monotonic):
        self.reg, self.started, self.torch, self.stream, self.clock = reg, started, torch, stream, clock
        self.last_lease = self.last_sample = -math.inf
        self.peak_rss = self.peak_mps = 0
        self.first_failure = None
        self.first_signal = None

    def signal(self, number, _frame):
        if self.first_signal is None:
            self.first_signal = number
            if self.first_failure is None:
                self.first_failure = {"monotonic": self.clock(), "kind": "cancelled", "signal": number}
            raise Cancelled("Cancellation signal " + str(number))

    def check(self, *, finalizing=False):
        now = self.clock()
        try:
            need(self.first_signal is None, "Cancellation latched")
            budget = LIMITS["total_seconds"] if finalizing else LIMITS["work_seconds"]
            need(0 <= now - self.started < budget, "Absolute iteration budget exhausted")
            need(not Path(self.reg["cancel_path"]).exists(), "Parent cancellation requested")
            if now - self.last_lease >= .15:
                check_lease(self.reg); self.last_lease = now
            if now - self.last_sample >= .05:
                rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                rss = int(rss if sys.platform == "darwin" else rss * 1024)
                mps = int(self.torch.mps.driver_allocated_memory())
                self.peak_rss, self.peak_mps = max(self.peak_rss, rss), max(self.peak_mps, mps)
                emit(self.stream, {"monotonic": now, "elapsed_seconds": now - self.started,
                                   "peak_rss_bytes": self.peak_rss, "mps_driver_bytes": mps})
                self.last_sample = now
                need(rss <= LIMITS["RSS_bytes"] and mps <= LIMITS["MPS_bytes"], "Resource cap exceeded")
        except BaseException as error:
            if self.first_failure is None:
                self.first_failure = {"monotonic": now, "error": repr(error)}
            raise


def performance(evaluation):
    rows = evaluation["rows"]
    need(evaluation["complete"] is True and len(rows) == 64, "Incomplete development evaluation")
    summary = {}
    for name in ("alive_frames", "score"):
        values = sorted(row[name] for row in rows)
        summary[name] = {"Q1": sum(values[:16]) / 16, "Q4": sum(values[-16:]) / 16,
                         "mean": sum(values) / 64}
    return summary


def valid_worker_result(value):
    return (value.get("status") == "completed" and value.get("updates") == NEW_UPDATES
            and value.get("evaluated_updates") == [PHASE_START, PHASE_END]
            and value.get("normal_training_iteration") is True and value.get("training_eligible") is False
            and value.get("promoted") is False and value.get("first_failure") is None
            and value.get("first_signal") is None and "error" not in value)



def ordered_episode_events(completed, resets, update):
    events = [(item["rollout_step"], 0, "completed", item) for item in completed]
    events += [(item["rollout_step"], 1, "reset", item) for item in resets]
    return [{"kind": kind, "phase_update": update, "info": item}
            for _, _, kind, item in sorted(events, key=lambda event: (event[0], event[1]))]


def validate_episode_journal(records, initial_indices):
    records = [row for row in records if row["kind"] != "abandoned_parent_episode"]
    need(records and records[0]["kind"] == "initial", "Initial episode state missing")
    current = {item["seed"]["slot"]: item["seed"]["episode"] for item in records[0]["info"]}
    need(len(initial_indices) == 64 and current == dict(enumerate(initial_indices)) and len(records[0]["info"]) == 64
         and records[0]["batch_info"]["next_episode_indices"] == [value + 1 for value in initial_indices],
         "Initial current/future continuation episode index contract differs")
    waiting = set()
    previous = (0, -1, -1)
    for row in records[1:]:
        kind, info, update = row["kind"], row["info"], row["phase_update"]
        need(kind in ("completed", "reset") and type(update) is int and PHASE_START < update <= PHASE_END,
             "Episode event update/kind differs")
        order = (update, info["rollout_step"], 0 if kind == "completed" else 1)
        need(order >= previous, "Episode events are not chronological")
        previous = order
        if kind == "completed":
            seed = info["seed"]; slot = seed["slot"]
            need(slot in current and slot not in waiting and seed["episode"] == current[slot],
                 "Completed episode replayed, skipped or lacks reset")
            waiting.add(slot)
        else:
            need(len(info["indices"]) == len(info["info"]) and bool(info["indices"]),
                 "Reset payload shape differs")
            for slot, state in zip(info["indices"], info["info"], strict=True):
                seed = state["seed"]
                need(slot in waiting and seed["slot"] == slot and seed["episode"] == current[slot] + 1,
                     "Reset episode replayed or skipped")
                current[slot] += 1
                waiting.remove(slot)
    need(not waiting, "Completed episodes lack final resets")
    return {"next_episode_indices": [current[slot] + 1 for slot in range(64)],
            "current_episode_indices": current, "records_checked": len(records)}


def worker(registration, registration_sha, started):
    reg, config = load_registration(registration, registration_sha)
    need(Path(reg["runner_path"]).resolve() == Path(__file__).resolve(), "Worker runner origin differs")
    need(Path(sys.executable).resolve() == Path(reg["interpreter"]).resolve(), "Interpreter origin differs")
    sys.path.insert(0, reg["runtime_root"])
    import numpy as np
    import torch
    import dodge_rl
    from dodge_rl import checkpoints as ckpt
    from dodge_rl.dev_eval import evaluate, validate_summary
    from dodge_rl.models.teacher import OmniscientEntityTeacher
    from dodge_rl.ppo import PPOConfig, collect_rollout, ppo_update
    from dodge_rl.survival_gate import progress_passed
    from dodge_rl.identity import identity_hash
    need(Path(dodge_rl.__file__).resolve() == (Path(reg["runtime_root"]) / "dodge_rl/__init__.py").resolve(),
         "Python package origin differs")
    need({"python": sys.version.split()[0], "torch": str(torch.__version__), "numpy": str(np.__version__)}
         == reg["runtime_versions"], "Runtime versions differ")
    out = Path(reg["output"])
    result = {"status": "failed", "normal_training_iteration": True, "training_eligible": False,
              "promoted": False, "updates": 0, "evaluated_updates": [], "first_failure": None}
    with (out / "resources.jsonl").open("x") as resources:
        guard = Guard(reg, started, torch, resources)
        previous = {n: signal.getsignal(n) for n in (signal.SIGINT, signal.SIGTERM)}
        for n in previous:
            signal.signal(n, guard.signal)
        try:
            guard.check()
            torch.set_num_threads(4)
            need(torch.backends.mps.is_available(), "MPS unavailable")
            parent = ckpt.load_checkpoint(Path(reg["parent"]["path"]), expected_sha256=PARENT_SHA)
            ckpt.require_complete_update(parent)
            validate_parent_checkpoint_for_restore(parent, PARENT_SHA)
            model = OmniscientEntityTeacher().to(device="mps", dtype=torch.float32)
            need(model.architecture_description() == parent["identity"]["architecture"], "Architecture changed")
            optimizer = torch.optim.Adam(model.parameters(), lr=PPO["learning_rate"], eps=PPO["adam_eps"])
            ckpt.restore_learner(parent, model, optimizer, "mps")
            restored = {"model": model.state_dict(), "Adam": optimizer.state_dict(),
                        "RNG": ckpt.capture_rng("mps")}
            expected = {"model": parent["model"], "Adam": parent["optimizer"], "RNG": parent["rng"]}
            equality = {name: fingerprint(restored[name]) == fingerprint(expected[name]) for name in restored}
            details = {name: {"matched": equality[name], "restored_sha256": fingerprint(restored[name]),
                              "expected_sha256": fingerprint(expected[name]),
                              "mismatch_paths": mismatch_paths(restored[name], expected[name])}
                       for name in restored}
            save(out / "entry-restoration.json", {"matched": equality, "components": details,
                  "before_environment_or_gradients": True, "parent_sha256": PARENT_SHA})
            need(all(equality.values()), "Parent model/Adam/RNG restoration differs")

            inherited = dict(parent["cumulative_counters"])
            initial_indices = list(parent["next_episode_indices"])
            need(len(initial_indices) == 64 and all(type(index) is int and index >= 0 for index in initial_indices),
                 "Parent next episode indices invalid")
            identity = {"version": "teacher_identity_v3", "run_id": reg["run_id"],
                        "phase": "D2", "phase_update_start": PHASE_START, "phase_update_end": PHASE_END, "run_seed": reg["run_seed"], "config": config,
                        "parent_checkpoint_sha256": PARENT_SHA,
                        "policy_sha256": POLICY_SHA, "registration_sha256": registration_sha,
                        "architecture": model.architecture_description()}
            env = dodge_rl.VecDodgeEnv(batch_size=64, action_repeat=4, difficulty=2,
                    patterns_enabled=True, powerups_enabled=True, raw_frame_cap=18000,
                    num_threads=4, chunk_size=8, render_pixels=False, auxiliary_targets=False,
                    run_seed=reg["run_seed"], initial_episode_indices=initial_indices,
                    excluded_seed_ranges=[tuple(v) for v in RANGES])
            observation, ppo = env.observations(), PPOConfig(**config["ppo"])
            counters = {"updates": 0, "optimizer_steps": 0, "environment_decisions": 0, "raw_frames": 0}
            progress = {"complete": True, "in_update": False, "completed_updates": 0}
            actor_gradient_seen = critic_gradient_seen = False
            with (out / "training-episodes.jsonl").open("x") as episodes, (out / "training-metrics.jsonl").open("x") as metrics:
                for abandoned in parent["abandoned_current_episodes"]:
                    emit(episodes, {"kind": "abandoned_parent_episode", "reason": "fresh_environment_at_saved_next_episode_index",
                                    "parent_checkpoint_sha256": PARENT_SHA, "info": abandoned})
                emit(episodes, {"kind": "initial", "info": env.episode_info(), "batch_info": env.batch_info()})

                def evaluate_at(phase_update):
                    local_update = phase_update - PHASE_START
                    guard.check()
                    before = {"model": fingerprint(model.state_dict()), "Adam": fingerprint(optimizer.state_dict()),
                              "RNG": fingerprint(ckpt.capture_rng("mps")),
                              "env": fingerprint([env.episode_info(), env.batch_info()])}
                    path = out / f"checkpoint-{phase_update:06d}-candidate.pt"
                    current_wall = time.monotonic() - started
                    next_indices, abandoned = ckpt.episode_resume_state(env, 64)
                    cumulative = continuation_cumulative_counters(inherited, counters)
                    state = {"version": "teacher_checkpoint_v1", "schema": "d2_training_v3_checkpoint_v1",
                             "resume_mode": "fresh_env", "tag": "candidate", "phase": "D2",
                             "eligibility_status": "provisional_pending_parent_terminal_receipt",
                             "training_eligible": False, "promoted": False, "parent_sha256": PARENT_SHA,
                             "identity": identity, "identity_sha256": identity_hash(identity),
                             "config_sha256": reg["config_sha256"], "policy_sha256": POLICY_SHA,
                             "native_sha256": reg["native"]["sha256"], "run_seed": reg["run_seed"],
                             "runtime_sha256": reg["runtime_sha256"],
                             "registration_sha256": registration_sha, "model": ckpt._cpu_copy(model.state_dict()),
                             "optimizer": ckpt._cpu_copy(optimizer.state_dict()), "rng": ckpt.capture_rng("mps"),
                             "counters": dict(counters), "inherited_counters": inherited,
                             "cumulative_counters": cumulative, "phase_update": phase_update,
                             "local_update": local_update, "parent_inclusive_wall_seconds": PARENT_WALL_SECONDS,
                             "current_iteration_wall_seconds": current_wall,
                             "cumulative_D2_inclusive_wall_seconds": PARENT_WALL_SECONDS + current_wall,
                             "update_progress": dict(progress), "next_episode_indices": next_indices,
                             "abandoned_current_episodes": abandoned, "parent_abandoned_current_episodes": parent["abandoned_current_episodes"],
                             "parent_run_id": "D2-gradient-alignment-20261025-r2",
                             "parent_registration_sha256": PARENT_REGISTRATION_SHA,
                             "parent_checkpoint_sha256": PARENT_SHA}
                    checkpoint_sha = ckpt.save_checkpoint(path, state)
                    with (out / f"development-{phase_update:06d}.jsonl").open("x") as stream:
                        evaluation = evaluate(model, "D2", "mps", check_guard=guard.check, episode_stream=stream)
                    validate_summary(evaluation)
                    after = {"model": fingerprint(model.state_dict()), "Adam": fingerprint(optimizer.state_dict()),
                             "RNG": fingerprint(ckpt.capture_rng("mps")),
                             "env": fingerprint([env.episode_info(), env.batch_info()])}
                    need(before == after, "Checkpoint/evaluation changed training state")
                    save(out / f"development-{phase_update:06d}.json", {"evaluation": evaluation, "phase_update": phase_update, "local_update": local_update,
                         "performance": performance(evaluation), "competence_passed":
                         progress_passed("D2", {"D2": evaluation}), "normal_training_iteration": True,
                         "checkpoint": path.name, "checkpoint_sha256": checkpoint_sha,
                         "training_state_unchanged": True, "training_eligible": False, "promoted": False})
                    save(Path(str(path) + ".json"), {"eligibility_status": "provisional_pending_parent_terminal_receipt", "training_eligible": False,
                                                    "promoted": False, "checkpoint_sha256": checkpoint_sha})
                    result["evaluated_updates"].append(phase_update)
                    print(json.dumps({"evaluation_update": phase_update, "local_update": local_update, "performance": performance(evaluation)}), flush=True)

                evaluate_at(PHASE_START)
                for update in range(1, NEW_UPDATES + 1):
                    guard.check()
                    collection = collect_rollout(model, env, 256, "mps", observation=observation,
                                                 config=ppo, check_guard=guard.check)
                    observation = collection.observations
                    phase_update = PHASE_START + update
                    for event in ordered_episode_events(collection.completed_episodes, collection.reset_info, phase_update):
                        emit(episodes, event)
                    value = ppo_update(model, optimizer, collection.batch, ppo, check_guard=guard.check,
                                       progress=progress, critic_diagnostics=True,
                                       gradient_alignment_diagnostics=True)
                    finite_tree(value)
                    diag = value["critic_diagnostics"]
                    need(diag["version"] == "same_batch_critic_diagnostics_v1", "Unknown diagnostic version")
                    validate_gradient_alignment(value["gradient_alignment_diagnostics"])
                    old_ev, direct_ev = value["explained_variance"], diag["pre_update"]["explained_variance"]
                    need((old_ev is None and direct_ev is None) or (old_ev is not None and direct_ev is not None
                         and math.isclose(old_ev, direct_ev, rel_tol=1e-6, abs_tol=1e-6)), "Direct/legacy EV mismatch")
                    progress["completed_updates"] = update
                    actor_gradient_seen |= value["actor_grad_norm"] > 0
                    critic_gradient_seen |= value["critic_grad_norm"] > 0
                    counters["updates"] = update
                    counters["optimizer_steps"] += value["optimizer_steps"]
                    counters["environment_decisions"] += collection.batch.actions.numel()
                    counters["raw_frames"] += int(collection.batch.elapsed_raw_frames.sum().item())
                    result["updates"] = update
                    emit(metrics, {"phase_update": phase_update, "local_update": update, "metrics": value, "counters": dict(counters),
                                   "update_progress": dict(progress), "elapsed_seconds": time.monotonic() - started})
                    if update == NEW_UPDATES:
                        evaluate_at(PHASE_END)
                    guard.check()
                need(actor_gradient_seen and critic_gradient_seen, "Nonzero actor/critic gradient evidence missing")
                guard.check()
                current_wall = time.monotonic() - started
                result.update(status="completed", counters=counters, phase_updates=[PHASE_START, PHASE_END],
                              work_elapsed_seconds=current_wall,
                              parent_inclusive_wall_seconds=PARENT_WALL_SECONDS,
                              current_iteration_wall_seconds=current_wall,
                              cumulative_D2_inclusive_wall_seconds=PARENT_WALL_SECONDS + current_wall,
                              inherited_counters=inherited,
                              cumulative_counters=continuation_cumulative_counters(inherited, counters),
                              final_resume_next_episode_indices=env.batch_info()["next_episode_indices"])
            guard.check(finalizing=True)
        except BaseException as error:
            result.update(error=repr(error), traceback=traceback.format_exc(), update_progress=locals().get("progress", {}),
                          first_failure=guard.first_failure or {"monotonic": time.monotonic(), "error": repr(error)},
                          first_signal=guard.first_signal)
        finally:
            try:
                guard.last_sample = -math.inf
                guard.check(finalizing=True)
                check_import_cache(reg)
            except BaseException as final_error:
                result.update(status="failed", finalization_error=repr(final_error))
            for number, handler in previous.items():
                signal.signal(number, handler)
            result.update(elapsed_seconds=time.monotonic() - started, peak_rss_bytes=guard.peak_rss,
                          peak_mps_driver_bytes=guard.peak_mps)
            save(out / "worker-result.json", result)
    return 0 if valid_worker_result(result) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--registration", required=True)
    parser.add_argument("--registration-sha256", required=True)
    parser.add_argument("--started", required=True, type=float)
    args = parser.parse_args()
    need(math.isfinite(args.started) and args.started <= time.monotonic(), "Invalid inherited start")
    raise SystemExit(worker(args.registration, args.registration_sha256, args.started))
