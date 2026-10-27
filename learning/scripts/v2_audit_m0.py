"""Independently audit the registered original-engine Dodge v2 M0 receipts.

This reads retained receipts and source identities; it does not run gameplay.
Full mode requires the finished 3,000-episode campaign and supervisor. The
explicit --profile-only mode makes no claim about baseline completion.
"""

from __future__ import annotations

import argparse
from collections import Counter
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
WORKTREE = Path("/Users/taylor/.t3/worktrees/dodge-native/t3-5d7162c0")
HEAD = "d7ad95127ad7529c5217a51ae9dc5cfedd3f2365"
FROZEN_SHA = "1178bf8236dbecb305a86053462609017d3e756a0f514e8bb913b2525af3b6b8"
FROZEN = ROOT / "learning/.cache/v2-m0-review-r2"
POLICIES = ("random", "neutral", "nearest_lethal_aabb_safe_powerup")
CONFIG = {"difficulty": 2, "patterns_enabled": True, "powerups_enabled": True,
          "theme_background_shadow": [12, 1], "initial_highscores_raw_fixed": [0] * 12}
SCALE = 65_536
EVENTS = "frame_event_counts_enemy_spawn_collision_death_pattern_active_terminal"
COUNT_SUMS = ("enemy_overflow_frames_above_64", "rect_overflow_frames_above_16",
              "enemy_excess_record_frames", "rect_excess_record_frames", "active_pattern_frames")


class AuditError(ValueError):
    """A receipt is missing, inconsistent, incomplete, or has changed identity."""


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reject_constant(value: str) -> None:
    raise AuditError(f"nonfinite JSON constant: {value}")


def unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise AuditError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def finite_tree(value: object) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise AuditError("nonfinite JSON number")
    if isinstance(value, dict):
        for child in value.values():
            finite_tree(child)
    elif isinstance(value, list):
        for child in value:
            finite_tree(child)


def parse(text: str) -> object:
    result = json.loads(text, parse_constant=reject_constant, object_pairs_hook=unique_object)
    finite_tree(result)
    return result


class Auditor:
    def __init__(self) -> None:
        self.checks = 0
        self.artifacts: dict[str, str] = {}

    def require(self, condition: bool, message: str) -> None:
        self.checks += 1
        if not condition:
            raise AuditError(message)

    def same(self, actual: object, expected: object, name: str) -> None:
        # bool is an int subclass in Python. Preserve JSON type distinctions.
        if isinstance(expected, (bool, int, str)):
            self.require(type(actual) is type(expected) and actual == expected, name)
        elif isinstance(expected, dict):
            self.require(isinstance(actual, dict) and actual.keys() == expected.keys(), name + " keys")
            for key, value in expected.items():
                self.same(actual[key], value, f"{name}.{key}")
        elif isinstance(expected, list):
            self.require(isinstance(actual, list) and len(actual) == len(expected), name + " length")
            for index, value in enumerate(expected):
                self.same(actual[index], value, f"{name}[{index}]")
        else:
            self.require(actual == expected, name)

    def close(self, actual: object, expected: float, name: str) -> None:
        self.require(type(actual) in (int, float) and math.isfinite(actual)
                     and math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-10), name)

    def uint(self, value: object, name: str, maximum: int | None = None) -> int:
        self.require(type(value) is int and value >= 0 and (maximum is None or value <= maximum), name)
        return value

    def read(self, path: Path) -> object:
        raw = path.read_bytes()
        self.artifacts[str(path)] = hashlib.sha256(raw).hexdigest()
        return parse(raw.decode("utf-8"))

    def jsonl(self, path: Path) -> list[dict]:
        raw = path.read_bytes()
        self.artifacts[str(path)] = hashlib.sha256(raw).hexdigest()
        self.require(raw.endswith(b"\n"), f"{path}: missing final newline")
        lines = raw.decode("utf-8").splitlines()
        self.require(all(lines), f"{path}: empty JSONL record")
        rows = [parse(line) for line in lines]
        self.require(all(isinstance(row, dict) for row in rows), f"{path}: non-object record")
        return rows

    def directory(self, directory: Path) -> None:
        self.require(not (directory / "failure.json").exists(), f"{directory}: native failure receipt exists")
        # Also reject nonfinite or malformed numbers in additional retained JSON.
        for path in sorted(directory.glob("*.json")):
            self.read(path)
        for path in sorted(directory.glob("*.jsonl")):
            self.jsonl(path)

    def identity(self, identity: dict, frozen: dict) -> None:
        self.same(identity["head"], HEAD, "identity HEAD")
        self.same(identity["worktree"], str(WORKTREE), "identity worktree")
        for key in ("tracked_engine_inputs_unchanged", "all_original_tracked_files_unchanged",
                    "compiled_harness_matches_disk", "release_profile"):
            self.same(identity[key], True, f"identity.{key}")
        self.same(identity["executable_sha256"], frozen["executable_sha256"], "frozen executable identity")
        executable = Path(identity["executable"])
        self.same(str(executable), frozen["executable"], "executable path")
        self.same(sha(executable), identity["executable_sha256"], "current executable identity")
        self.artifacts[str(executable)] = sha(executable)
        selected = subprocess.check_output(
            ["git", "ls-files", "-z", "--", "crates/dodge-core", "assets", "Cargo.toml",
             "Cargo.lock", ".cargo", "rust-toolchain.toml", "rustfmt.toml", "clippy.toml"], cwd=WORKTREE
        ).decode().split("\0")
        expected_paths = set(filter(None, selected)) | {
            path for path in frozen["new_source_and_docs_sha256"] if path.endswith(".rs")}
        records = identity["source_sha256"]
        self.require(len(records) == len(expected_paths), "source identity count")
        self.same(sorted(record["path"] for record in records), sorted(expected_paths), "source identity paths")
        for record in records:
            path = WORKTREE / record["path"]
            actual = sha(path)
            self.same(actual, record["sha256"], f"current source: {record['path']}")
            capsule_path = FROZEN / record["path"]
            if capsule_path.is_file():
                reviewed = sha(capsule_path)
            else:
                # The review capsule omitted some unchanged infrastructure
                # inputs. Their authoritative identity is the pinned Git blob,
                # not a missing-file exception or a relaxed provenance check.
                original = subprocess.check_output(["git", "show", f"{HEAD}:{record['path']}"], cwd=WORKTREE)
                reviewed = hashlib.sha256(original).hexdigest()
            self.same(actual, reviewed, f"reviewed source: {record['path']}")
            self.artifacts[str(path)] = actual

    def manifest(self, directory: Path, mode: str, frozen: dict) -> dict:
        self.directory(directory)
        manifest = self.read(directory / "manifest.json")
        self.same(manifest["schema_version"], 2, "manifest schema")
        self.same(manifest["mode"], mode, "manifest mode")
        self.same(manifest["native_config"], CONFIG, "manifest configuration")
        self.same(manifest["action_repeat"], 4, "manifest action repeat")
        self.same(manifest["startup_expected_native_frames_verified_per_instance"], 13, "manifest startup")
        self.same(manifest["baseline_seed_base"], 0xB0000000, "manifest seed base")
        self.same(manifest["episodes_per_policy"], 1000 if mode == "baseline" else 0, "manifest episode count")
        self.same(manifest["max_raw_gameplay_frames"], 18000 if mode == "baseline" else 2000, "manifest cap")
        self.same(manifest["max_seconds"], 3600 if mode == "baseline" else 60, "manifest global budget")
        seeds = list(range(0xB0000000, 0xB0000000 + (1000 if mode == "baseline" else 0)))
        self.same(manifest["all_baseline_seeds"], seeds, "manifest complete paired seed list")
        self.identity(manifest["identity"], frozen)
        argv = manifest["command_argv"]
        self.require(isinstance(argv, list) and len(argv) % 2 == 1, "manifest command argument shape")
        self.same(argv[0], frozen["executable"], "manifest executable argument")
        args = dict(zip(argv[1::2], argv[2::2]))
        self.require(len(args) * 2 + 1 == len(argv), "duplicate command option")
        expected = {"--action-repeat": "4", "--difficulty": "2", "--patterns": "true",
                    "--powerups": "true", "--max-seconds": "3600" if mode == "baseline" else "60",
                    "--output-dir": str(directory)}
        expected.update({"--episodes": "1000", "--max-frames": "18000"} if mode == "baseline"
                        else {"--benchmark-seconds": "10", "--threads": "4"})
        self.same(args, expected, "registered command arguments")
        return manifest

    def episode(self, row: dict, policy: str, index: int) -> None:
        label = f"{policy}[{index}]"
        self.same(row["policy"], policy, label + " policy")
        self.same(row["episode_index"], index, label + " index")
        self.same(row["seed"], 0xB0000000 + index, label + " seed")
        self.same(row["native_config"], CONFIG, label + " configuration")
        self.same(row["episode_status"], "complete", label + " status")
        self.same(row["failure"], "", label + " failure")
        self.same(row["startup_native_frames_excluded"], 13, label + " startup")
        self.same(row["policy_rng_initial_state"], row["seed"] ^ 0xD1B54A32D192ED03, label + " private RNG")
        self.uint(row["final_state_hash"], label + " final state hash", 2**64 - 1)
        frames = self.uint(row["gameplay_native_frames"], label + " raw frames", 18000)
        alive = self.uint(row["raw_survival_frames"], label + " alive frames", 18000)
        self.require(frames > 0, label + " empty gameplay episode")
        dead, capped = row["death"], row["cap_truncation"]
        self.require(type(dead) is bool and type(capped) is bool and dead != capped, label + " death/cap exclusivity")
        self.same(row["run_deadline_truncation"], False, label + " deadline interruption")
        self.same(alive, frames - int(dead), label + " alive/death accounting")
        self.same(row["native_survival_frames_delta"], alive, label + " native survival delta")
        self.require(not capped or frames == 18000, label + " cap frame count")
        self.same(row["decision_steps"], (frames + 3) // 4, label + " ragged K decision count")
        self.close(row["survival_seconds_60hz"], alive / 60, label + " survival seconds")
        self.close(row["legacy_native_reward_sum"], alive, label + " alive reward")
        scores = row["scores"]
        fixed = self.uint(scores["final_score_raw_fixed"], label + " fixed score", 2**31 - 1)
        self.require(fixed % 32768 == 0, label + " score half-point increments")
        self.same(row["score_delta_sum_raw_fixed"], fixed, label + " score delta sum")
        self.close(row["score_delta_sum"], fixed / SCALE, label + " score delta numeric")
        self.close(scores["final_score_raw"], fixed / SCALE, label + " raw numeric score")
        self.same(scores["final_score_display_ceil"], (fixed + SCALE - 1) // SCALE, label + " display ceil")
        self.same(scores["stored_highscore_category_slot_zero_based"], 4, label + " D2 category slot")
        stored = self.uint(scores["stored_highscore_raw_fixed"], label + " stored highscore", 2**31 - 1)
        self.require(stored % SCALE == 0, label + " stored highscore integral")
        self.close(scores["stored_highscore"], stored / SCALE, label + " stored numeric highscore")
        self.same(scores["new_highscore"], stored > 0, label + " new highscore flag")
        self.require(stored / SCALE <= scores["final_score_display_ceil"], label + " highscore cannot exceed final ceil")
        self.require(dead or stored == 0, label + " alive capped game has not saved a highscore")
        self.close(row["score_survival_objective_return"], fixed / SCALE + 0.01 * alive - 5 * dead,
                   label + " shaped return")
        events = row[EVENTS]
        self.require(isinstance(events, list) and len(events) == 5, label + " event vector")
        for number in events:
            self.uint(number, label + " event count")
        # The original collision loop can call die() for several colliding
        # enemies and then a rectangle in the same raw frame. Those are event
        # multiplicities, not multiple terminal frames or reward penalties.
        self.require((events[2] >= 1 if dead else events[2] == 0), label + " death events match termination")
        self.require(events[2] <= events[1] + 1, label + " death event source bound")
        self.same(events[4], int(dead), label + " terminal event count")
        counts = row["counts"]
        for key in ("max_active_enemy_family_count", "max_active_pattern_rect_count", *COUNT_SUMS):
            self.uint(counts[key], label + " " + key)
        self.require(counts["active_pattern_frames"] <= frames, label + " active pattern frame bound")
        self.same(events[3], counts["active_pattern_frames"], label + " pattern event accounting")
        ids = counts["pattern_ids"]
        self.same(ids, sorted(set(ids)), label + " unique sorted pattern IDs")
        for number in ids:
            self.require(type(number) is int and 1 <= number <= 255, label + " pattern ID range")
        pattern_frames = counts["pattern_frames"]
        self.same([value["id"] for value in pattern_frames], ids, label + " pattern frame IDs")
        for value in pattern_frames:
            self.require(type(value["frames"]) is int and value["frames"] > 0, label + " pattern frame count")
        self.same(sum(value["frames"] for value in pattern_frames), counts["active_pattern_frames"],
                  label + " per-pattern frame sum")
        for family, cap in (("enemy", 64), ("rect", 16)):
            maximum = counts["max_active_enemy_family_count" if family == "enemy" else "max_active_pattern_rect_count"]
            overflow = counts[f"{family}_overflow_frames_above_{cap}"]
            excess = counts[f"{family}_excess_record_frames"]
            self.require(overflow <= frames, label + " overflow frame bound")
            self.require((maximum > cap) == (overflow > 0), label + " maximum/overflow consistency")
            self.require(overflow <= excess <= overflow * max(0, maximum - cap), label + " excess record bounds")
        for key in ("construction_startup_seconds", "gameplay_seconds_including_policy_and_metrics"):
            self.require(type(row[key]) in (int, float) and row[key] >= 0, label + " timing")

    def baselines(self, directory: Path, frozen: dict) -> dict:
        self.manifest(directory, "baseline", frozen)
        summary = self.read(directory / "summary.json")
        self.same(summary["status"], "complete", "baseline summary status")
        rows = self.jsonl(directory / "episodes.jsonl")
        self.same(len(rows), 3000, "full campaign has exactly 3000 records")
        self.same([value["policy"] for value in summary["policies"]], list(POLICIES), "summary policy order")
        result = {}
        for position, policy in enumerate(POLICIES):
            group = rows[position * 1000:(position + 1) * 1000]
            for index, row in enumerate(group):
                self.episode(row, policy, index)
            actual = summary["policies"][position]
            expected = {"policy": policy, "episodes": 1000, "death_count": sum(row["death"] for row in group),
                        "cap_truncation_count": sum(row["cap_truncation"] for row in group)}
            for key in ("gameplay_native_frames", "decision_steps"):
                expected[key] = sum(row[key] for row in group)
            expected["startup_native_frames"] = 13000
            for key in COUNT_SUMS:
                expected[key] = sum(row["counts"][key] for row in group)
            for family, cap in (("enemy", 64), ("rect", 16)):
                expected[f"episodes_with_{family}_overflow"] = sum(row["counts"][f"{family}_overflow_frames_above_{cap}"] > 0 for row in group)
            expected["pattern_ids"] = sorted({number for row in group for number in row["counts"]["pattern_ids"]})
            for key, value in expected.items():
                self.same(actual[key], value, f"{policy} summary {key}")
            selections = {
                "raw_score": [row["scores"]["final_score_raw"] for row in group],
                "display_score_ceil": [row["scores"]["final_score_display_ceil"] for row in group],
                "stored_highscore": [row["scores"]["stored_highscore"] for row in group],
                "raw_survival_frames": [row["raw_survival_frames"] for row in group],
                "survival_seconds_60hz": [row["raw_survival_frames"] / 60 for row in group],
                "max_active_enemy_family_count": [row["counts"]["max_active_enemy_family_count"] for row in group],
                "max_active_pattern_rect_count": [row["counts"]["max_active_pattern_rect_count"] for row in group],
            }
            distributions = {key: distribution(values) for key, values in selections.items()}
            for key, values in distributions.items():
                self.same(sorted(actual[key]), sorted(values), f"{policy} {key} distribution keys")
                for metric, value in values.items():
                    self.close(actual[key][metric], value, f"{policy} {key}.{metric}")
            patterns = Counter()
            for row in group:
                patterns.update({value["id"]: value["frames"] for value in row["counts"]["pattern_frames"]})
            result[policy] = {**expected, **distributions, "cap_fraction": expected["cap_truncation_count"] / 1000,
                              "pattern_frames": dict(sorted(patterns.items())),
                              "frame_event_totals": [sum(row[EVENTS][index] for row in group) for index in range(5)],
                              "death_event_multiplicity": dict(sorted(Counter(row[EVENTS][2] for row in group).items())),
                              "score_exceeds_stored_highscore_episodes": sum(row["scores"]["final_score_raw"] > row["scores"]["stored_highscore"] for row in group)}
        return result

    def profile(self, directory: Path, frozen: dict) -> dict:
        self.manifest(directory, "benchmark", frozen)
        summary = self.read(directory / "summary.json")
        self.same(summary["status"], "complete", "profile complete")
        self.same(summary["native_config"], CONFIG, "profile configuration")
        self.same(summary["requested_total_wall_seconds"], 10, "registered profile duration")
        self.same(summary["nonoverlapping_phases"], True, "sequential profile phases")
        self.require(0 < summary["elapsed_total_wall_seconds"] <= 60, "profile total wall budget")
        result = {}
        for key, filename, threads in (("single_thread", "benchmark-single.json", 1), ("multi_thread", "benchmark-multi.json", 4)):
            phase = summary[key]
            self.same(phase, self.read(directory / filename), key + " standalone phase receipt")
            self.same(phase["status"], "complete", key + " status")
            self.same(phase["native_config"], CONFIG, key + " configuration")
            self.same(phase["threads"], threads, key + " thread count")
            self.same(phase["startup_frames_per_instance_verified"], 13, key + " startup count")
            self.require(threads <= summary["physical_cpu_count"] and threads <= summary["available_parallelism"], key + " hardware thread bound")
            workers = phase["workers"]
            self.same([worker["worker_id"] for worker in workers], list(range(threads)), key + " stable worker IDs")
            for worker in workers:
                label = f"{key}.worker{worker['worker_id']}"
                self.same(worker["failure"], "", label + " failure")
                for field in ("fresh_instances", "gameplay_native_frames", "alive_raw_frames", "decision_steps", "deaths", "episode_cap_truncations", "deadline_truncations"):
                    self.uint(worker[field], label + " " + field)
                n = worker["fresh_instances"]
                self.require(n > 0, label + " empty worker")
                seeds = [0xC0000000 + worker["worker_id"] + index * threads for index in range(n)]
                self.same(worker["all_seeds"], seeds, label + " strided seeds")
                self.same(worker["first_seed"], seeds[0], label + " first seed")
                self.same(worker["last_seed"], seeds[-1], label + " last seed")
                self.same(worker["startup_native_frames"], 13 * n, label + " startup frames")
                self.same(n, worker["deaths"] + worker["episode_cap_truncations"] + worker["deadline_truncations"], label + " every instance ended")
                self.require(worker["deadline_truncations"] <= 1, label + " at most one final deadline truncation")
                frames = worker["gameplay_native_frames"]
                self.same(frames - worker["deaths"], worker["alive_raw_frames"], label + " no post-death frames")
                self.require(worker["episode_cap_truncations"] * 2000 + worker["deaths"] <= frames <= n * 2000, label + " capped fresh instance frame bounds")
                decisions = worker["decision_steps"]
                self.require((frames + 3) // 4 <= decisions <= (frames + 3 * n) // 4, label + " ragged decision bounds")
                for field in ("construction_startup_seconds", "simulation_seconds_including_action_rng"):
                    self.require(type(worker[field]) in (int, float) and worker[field] >= 0, label + " timing")
            wall = phase["elapsed_wall_seconds_including_startups_and_thread_lifecycle"]
            simulation = sum(worker["simulation_seconds_including_action_rng"] for worker in workers)
            startup = sum(worker["construction_startup_seconds"] for worker in workers)
            self.require(wall > 0 and simulation > 0 and simulation + startup <= wall * threads + 1e-6, key + " worker time versus wall time")
            self.close(phase["simulation_worker_seconds_sum"], simulation, key + " simulation worker sum")
            self.close(phase["construction_startup_worker_seconds_sum"], startup, key + " startup worker sum")
            totals = {field: sum(worker[field] for worker in workers) for field in ("gameplay_native_frames", "startup_native_frames", "decision_steps")}
            for field, number in totals.items():
                self.same(phase[field], number, key + " total " + field)
            rates = {"gameplay_raw_frames_per_wall_second": totals["gameplay_native_frames"] / wall,
                     "all_native_frames_per_wall_second": (totals["gameplay_native_frames"] + totals["startup_native_frames"]) / wall,
                     "decision_steps_per_wall_second": totals["decision_steps"] / wall,
                     "gameplay_raw_frames_per_simulation_worker_second": totals["gameplay_native_frames"] / simulation,
                     "decision_steps_per_simulation_worker_second": totals["decision_steps"] / simulation}
            for field, value in rates.items():
                self.close(phase[field], value, key + " rate " + field)
            result[key] = {"threads": threads, "fresh_instances": sum(worker["fresh_instances"] for worker in workers),
                           **totals, **rates, "wall_seconds": wall, "simulation_worker_seconds_sum": simulation,
                           "deaths": sum(worker["deaths"] for worker in workers),
                           "cap_truncations": sum(worker["episode_cap_truncations"] for worker in workers),
                           "deadline_truncations": sum(worker["deadline_truncations"] for worker in workers)}
        self.require(sum(summary[key]["elapsed_wall_seconds_including_startups_and_thread_lifecycle"] for key in ("single_thread", "multi_thread")) <= summary["elapsed_total_wall_seconds"] + 1e-6, "phase walls fit sequential total")
        return result

    def supervisor(self, profile_only: bool) -> dict:
        folder = ROOT / "learning/runs/v2/milestone0-campaign-r2"
        supervisor = self.read(folder / "supervisor.json")
        if not profile_only:
            self.same(supervisor["status"], "native_experiments_complete_parent_audit_pending", "finished supervisor status")
        self.same(supervisor["head"], HEAD, "supervisor HEAD")
        self.same(supervisor["script_sha256"], sha(ROOT / "learning/scripts/v2_run_m0_campaign.py"), "supervisor script identity")
        self.same(supervisor["plan_sha256"], sha(ROOT / "docs/v2-baseline-campaign.md"), "registered plan identity")
        result = {}
        for name, seconds in (("profile", 60),) if profile_only else (("profile", 60), ("baselines", 3600)):
            phase = self.read(folder / f"{name}-receipt.json")
            self.same(phase["exit_code"], 0, name + " native process exit")
            self.require("supervisor_failure" not in phase, name + " no supervisor failure")
            self.same(phase["native_wall_limit_seconds"], seconds, name + " wall limit")
            self.same(phase["rss_limit_bytes"], 6 * 1024**3, name + " RSS limit")
            self.require(phase["elapsed_seconds"] <= seconds + 15, name + " watchdog bound")
            samples = self.jsonl(folder / f"{name}-resources.jsonl")
            self.require(bool(samples), name + " retained resource samples")
            self.require(all(type(sample["rss_bytes"]) is int and 0 <= sample["rss_bytes"] <= 6 * 1024**3 for sample in samples), name + " observed RSS threshold")
            self.require(all(a["elapsed_seconds"] <= b["elapsed_seconds"] for a, b in zip(samples, samples[1:])), name + " resource sample order")
            self.same(phase["peak_observed_rss_bytes"], max(sample["rss_bytes"] for sample in samples), name + " observed peak RSS")
            matches = [entry for entry in supervisor["phases"] if entry["name"] == name]
            self.require(len(matches) == 1, name + " supervisor phase membership")
            self.same(matches[0], phase, name + " supervisor phase receipt")
            result[name] = {"elapsed_seconds": phase["elapsed_seconds"], "peak_observed_rss_bytes": phase["peak_observed_rss_bytes"], "resource_samples": len(samples)}
        return result

    def run(self, profile_only: bool) -> dict:
        self.same(sha(FROZEN / "manifest.json"), FROZEN_SHA, "frozen review manifest identity")
        capsule = self.read(FROZEN / "manifest.json")
        for relative, expected in capsule["files"].items():
            self.same(sha(FROZEN / relative), expected, f"frozen capsule {relative}")
        repair_manifest = WORKTREE / "target/v2-m0-review-r2/final-manifest.json"
        self.same(sha(repair_manifest), capsule["files"]["evidence/final-manifest.json"], "reviewed repair manifest")
        frozen = self.read(repair_manifest)
        self.same(frozen["head"], HEAD, "repair HEAD")
        for relative, expected in frozen["new_source_and_docs_sha256"].items():
            self.same(sha(WORKTREE / relative), expected, f"frozen harness {relative}")
        self.same(subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=WORKTREE, text=True).strip(), HEAD, "current HEAD")
        tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=WORKTREE).decode().split("\0")
        tracked = list(filter(None, tracked))
        self.same(len(tracked), 33, "original tracked file count")
        for relative in tracked:
            original = subprocess.check_output(["git", "show", f"{HEAD}:{relative}"], cwd=WORKTREE)
            self.require((WORKTREE / relative).read_bytes() == original, f"original tracked file {relative}")
        profile = self.profile(WORKTREE / "target/v2-m0-profile-r2", frozen)
        baselines = None if profile_only else self.baselines(WORKTREE / "target/v2-m0-baselines-r2", frozen)
        resources = self.supervisor(profile_only)
        multiplicity = Counter()
        if baselines is not None:
            for policy in baselines.values():
                multiplicity.update(policy["death_event_multiplicity"])
        return {"status": "profile_only_verified_baseline_not_audited" if profile_only else "full_registered_campaign_receipts_verified",
                "profile": profile, "baselines": baselines, "resources": resources,
                "checks": self.checks,
                "native_event_semantics": {
                    "source": "d7ad951 crates/dodge-core/src/game.rs collision_check/collide_enemy, lines917-998",
                    "death_events": "May exceed one: multiple enemies and a rectangle can call die() on the same raw frame.",
                    "terminal_events": "Exactly one per terminated episode; zero for an alive cap truncation.",
                    "reward_penalty": "Subtract five once using bool death, regardless of Death-event multiplicity.",
                    "death_event_multiplicity_total": dict(sorted(multiplicity.items())),
                    "terminal_events_total": None if baselines is None else sum(value["death_count"] for value in baselines.values()),
                    "checker_correction": "Retained full-audit-r1.json records the invalid exactly-one-Death-event assumption; corrected against source without rerunning native experiments."},
                "limitations": ["Receipt consistency and pinned source review are not an independent replay of native simulation.",
                                "No per-frame state trace is retained; score/event checks do not reconstruct every collision.",
                                "Occupancy maxima are sampled after calls; observed absence of overflow does not establish every future configuration safe.",
                                "Cap-truncated score and survival remain censored; no cap or seed change is authorized by this audit.",
                                "Profile uses fresh short random episodes; rates do not establish mature-pattern, vectorized, or PPO throughput.",
                                "RSS is sampled native-process resident memory, not a proof of a hard memory ceiling."]}


def distribution(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    n = len(ordered)
    return {"mean": math.fsum(ordered) / n, "min": ordered[0], "max": ordered[-1],
            "median": statistics.median(ordered),
            **{f"p{percent}": ordered[(percent * n + 99) // 100 - 1] for percent in (10, 25, 75, 90)}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile-only", action="store_true")
    parser.add_argument("--output", type=Path, help="Write a new JSON file; existing files are refused")
    args = parser.parse_args()
    output = args.output.open("x") if args.output else None
    auditor = Auditor()
    try:
        report = auditor.run(args.profile_only)
        exit_code = 0
    except Exception as error:
        report = {"status": "failed", "error": f"{type(error).__name__}: {error}", "checks": auditor.checks,
                  "baseline_accepted": False, "profile_only_requested": args.profile_only}
        exit_code = 1
    report.update(audited_at_utc=dt.datetime.now(dt.timezone.utc).isoformat(),
                  script_sha256=sha(Path(__file__)), artifact_sha256=auditor.artifacts)
    serialized = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if output:
        with output:
            output.write(serialized)
    print(json.dumps({key: value for key, value in report.items() if key not in ("artifact_sha256", "profile", "baselines")}, allow_nan=False))
    if not output:
        print(serialized)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
