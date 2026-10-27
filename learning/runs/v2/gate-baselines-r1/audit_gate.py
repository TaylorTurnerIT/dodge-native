"""Audit the exact registered D3 and D1 receipts; never execute native gameplay.

Episode checks are copied from frozen D2 auditor 4c8b9c93cd4ffdacdf1a28d70888db020dd77967d49c8aa6b81f3bd995c6291f.
Only configuration, three cap references, and category slot are parameterized.
Parser, identity checks and independent distribution functions are imported unchanged.
"""
from __future__ import annotations
import argparse
from collections import Counter
import datetime as dt
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[4]
EVIDENCE = Path(__file__).resolve().parent
ORIGINAL = ROOT / "learning/scripts/v2_audit_m0.py"
EXPECTED_AUDITOR_SHA = "4c8b9c93cd4ffdacdf1a28d70888db020dd77967d49c8aa6b81f3bd995c6291f"
assert hashlib.sha256(ORIGINAL.read_bytes()).hexdigest() == EXPECTED_AUDITOR_SHA
spec = importlib.util.spec_from_file_location("frozen_d2_auditor", ORIGINAL)
m0 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m0)
WORKTREE, HEAD, SCALE, EVENTS = m0.WORKTREE, m0.HEAD, m0.SCALE, m0.EVENTS
POLICIES, COUNT_SUMS = m0.POLICIES, m0.COUNT_SUMS
RUNS = {
    "d3": {"episodes": 1000, "difficulty": 3, "patterns": True, "cap": 18000, "seconds": 900,
           "slot": 8, "output": "target/v2-gate-d3-r1"},
    "d1": {"episodes": 100, "difficulty": 1, "patterns": False, "cap": 2000, "seconds": 120,
           "slot": 3, "output": "target/v2-curriculum-d1-r1"},
}
def command(name):
    r = RUNS[name]
    return [str(WORKTREE / "target/release/examples/m0_baseline"), "--action-repeat", "4",
            "--difficulty", str(r["difficulty"]), "--patterns", str(r["patterns"]).lower(),
            "--powerups", "true", "--episodes", str(r["episodes"]), "--max-frames", str(r["cap"]),
            "--max-seconds", str(r["seconds"]), "--output-dir", str(WORKTREE / r["output"])]
class Auditor(m0.Auditor):
    def __init__(self, name):
        super().__init__()
        self.name, self.run = name, RUNS[name]
        self.config = {"difficulty": self.run["difficulty"], "patterns_enabled": self.run["patterns"],
                       "powerups_enabled": True, "theme_background_shadow": [12, 1],
                       "initial_highscores_raw_fixed": [0] * 12}
        self.cap, self.slot = self.run["cap"], self.run["slot"]
    def manifest(self, directory, frozen):
        self.directory(directory)
        value = self.read(directory / "manifest.json")
        fields = {"schema_version": 2, "mode": "baseline", "native_config": self.config,
                  "action_repeat": 4, "startup_expected_native_frames_verified_per_instance": 13,
                  "baseline_seed_base": 0xB0000000, "episodes_per_policy": self.run["episodes"],
                  "max_raw_gameplay_frames": self.cap, "max_seconds": self.run["seconds"],
                  "all_baseline_seeds": list(range(0xB0000000, 0xB0000000 + self.run["episodes"])),
                  "command_argv": command(self.name)}
        for key, expected in fields.items():
            self.same(value[key], expected, "manifest " + key)
        self.identity(value["identity"], frozen)
        return value
    def episode(self, row: dict, policy: str, index: int) -> None:
        label = f"{policy}[{index}]"
        self.same(row["policy"], policy, label + " policy")
        self.same(row["episode_index"], index, label + " index")
        self.same(row["seed"], 0xB0000000 + index, label + " seed")
        self.same(row["native_config"], self.config, label + " configuration")
        self.same(row["episode_status"], "complete", label + " status")
        self.same(row["failure"], "", label + " failure")
        self.same(row["startup_native_frames_excluded"], 13, label + " startup")
        self.same(row["policy_rng_initial_state"], row["seed"] ^ 0xD1B54A32D192ED03, label + " private RNG")
        self.uint(row["final_state_hash"], label + " final state hash", 2**64 - 1)
        frames = self.uint(row["gameplay_native_frames"], label + " raw frames", self.cap)
        alive = self.uint(row["raw_survival_frames"], label + " alive frames", self.cap)
        self.require(frames > 0, label + " empty gameplay episode")
        dead, capped = row["death"], row["cap_truncation"]
        self.require(type(dead) is bool and type(capped) is bool and dead != capped, label + " death/cap exclusivity")
        self.same(row["run_deadline_truncation"], False, label + " deadline interruption")
        self.same(alive, frames - int(dead), label + " alive/death accounting")
        self.same(row["native_survival_frames_delta"], alive, label + " native survival delta")
        self.require(not capped or frames == self.cap, label + " cap frame count")
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
        self.same(scores["stored_highscore_category_slot_zero_based"], self.slot, label + " registered highscore category slot")
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

    def audit(self):
        self.same(m0.sha(m0.FROZEN / "manifest.json"), m0.FROZEN_SHA, "frozen review manifest")
        capsule = self.read(m0.FROZEN / "manifest.json")
        for relative, expected in capsule["files"].items():
            self.same(m0.sha(m0.FROZEN / relative), expected, "frozen capsule " + relative)
        repair = WORKTREE / "target/v2-m0-review-r2/final-manifest.json"
        self.same(m0.sha(repair), capsule["files"]["evidence/final-manifest.json"], "frozen repair manifest")
        frozen = self.read(repair)
        self.same(frozen["head"], HEAD, "frozen HEAD")
        self.same(frozen["executable_sha256"], "922485d26128dbdc4df0868a5df7d7e72bc8f4135addfd691a1e11484d785d39", "registered executable")
        self.same(len(frozen["new_source_and_docs_sha256"]), 5, "five frozen harness/doc hashes")
        for relative, expected in frozen["new_source_and_docs_sha256"].items():
            self.same(m0.sha(WORKTREE / relative), expected, "frozen harness/doc " + relative)
        self.same(subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=WORKTREE, text=True).strip(), HEAD, "current original HEAD")
        tracked = list(filter(None, subprocess.check_output(["git", "ls-files", "-z"], cwd=WORKTREE).decode().split("\0")))
        self.same(len(tracked), 33, "all 33 tracked paths")
        for relative in tracked:
            original = subprocess.check_output(["git", "show", f"{HEAD}:{relative}"], cwd=WORKTREE)
            self.require((WORKTREE / relative).read_bytes() == original, "tracked HEAD bytes " + relative)
        directory = WORKTREE / self.run["output"]
        manifest = self.manifest(directory, frozen)
        summary = self.read(directory / "summary.json")
        self.same(summary["status"], "complete", "summary status")
        self.same(summary["quantiles"], "median averages central pair; p10/p25/p75/p90 nearest-rank ceil(p*n)", "native quantile convention")
        self.same([x["policy"] for x in summary["policies"]], list(POLICIES), "policy order")
        rows = self.jsonl(directory / "episodes.jsonl")
        n = self.run["episodes"]
        self.same(len(rows), 3*n, "exact completed episode count")
        output = {}
        for position, policy in enumerate(POLICIES):
            group = rows[position*n:(position+1)*n]
            for index, row in enumerate(group):
                self.episode(row, policy, index)
                if not self.config["patterns_enabled"]:
                    self.same(row["counts"]["active_pattern_frames"], 0, "D1 patterns off")
                    self.same(row["counts"]["pattern_ids"], [], "D1 pattern IDs absent")
                    self.same(row["counts"]["max_active_pattern_rect_count"], 0, "D1 rectangles absent")
            actual = summary["policies"][position]
            expected = {"policy": policy, "episodes": n, "death_count": sum(x["death"] for x in group),
                        "cap_truncation_count": sum(x["cap_truncation"] for x in group),
                        "startup_native_frames": n*13}
            for key in ("gameplay_native_frames", "decision_steps"):
                expected[key] = sum(x[key] for x in group)
            for key in COUNT_SUMS:
                expected[key] = sum(x["counts"][key] for x in group)
            for family, cap in (("enemy",64),("rect",16)):
                expected[f"episodes_with_{family}_overflow"] = sum(x["counts"][f"{family}_overflow_frames_above_{cap}"]>0 for x in group)
            expected["pattern_ids"] = sorted({i for x in group for i in x["counts"]["pattern_ids"]})
            for key, val in expected.items():
                self.same(actual[key], val, policy + " summary " + key)
            selections = {
                "raw_score": [x["scores"]["final_score_raw"] for x in group],
                "display_score_ceil": [x["scores"]["final_score_display_ceil"] for x in group],
                "stored_highscore": [x["scores"]["stored_highscore"] for x in group],
                "raw_survival_frames": [x["raw_survival_frames"] for x in group],
                "survival_seconds_60hz": [x["raw_survival_frames"]/60 for x in group],
                "max_active_enemy_family_count": [x["counts"]["max_active_enemy_family_count"] for x in group],
                "max_active_pattern_rect_count": [x["counts"]["max_active_pattern_rect_count"] for x in group],
            }
            distributions = {k: m0.distribution(v) for k,v in selections.items()}
            self.same(set(actual), set(expected) | set(distributions), policy + " complete native summary fields")
            for key, values in distributions.items():
                self.same(sorted(actual[key]), sorted(values), policy + " distribution fields " + key)
                for metric, val in values.items():
                    self.close(actual[key][metric], val, policy + " distribution " + key + "." + metric)
            patterns = Counter()
            for row in group:
                patterns.update({x["id"]:x["frames"] for x in row["counts"]["pattern_frames"]})
            output[policy] = {**expected, **distributions,
                "cap_fraction": expected["cap_truncation_count"]/n,
                "pattern_frames": dict(sorted(patterns.items())),
                "frame_event_totals": [sum(x[EVENTS][i] for x in group) for i in range(5)],
                "death_event_multiplicity": dict(sorted(Counter(x[EVENTS][2] for x in group).items())),
                "raw_score_exceeds_stored_highscore_episodes": sum(x["scores"]["final_score_raw"]>x["scores"]["stored_highscore"] for x in group),
                "ragged_K_endings": sum(x["gameplay_native_frames"]%4 != 0 for x in group),
                "death_at_raw_cap": sum(x["death"] and x["gameplay_native_frames"]==self.cap for x in group),
                "actual_fixed_score_delta_sum": sum(x["score_delta_sum_raw_fixed"] for x in group),
                "shaped_return_sum": sum(x["score_survival_objective_return"] for x in group)}
        resources = self.read(EVIDENCE / f"{self.name}-receipt.json")
        self.same(resources["command"], command(self.name), "supervisor command")
        self.same(resources["cwd"], str(WORKTREE), "supervisor cwd")
        self.same(resources["exit_code"], 0, "native exit status")
        self.require("supervisor_failure" not in resources, "no supervisor failure")
        self.same(resources["native_wall_limit_seconds"], self.run["seconds"], "registered wall budget")
        self.same(resources["watchdog_grace_seconds"], 15, "watchdog grace")
        self.same(resources["rss_limit_bytes"], 6*1024**3, "RSS threshold")
        self.require(0 < resources["elapsed_seconds"] <= self.run["seconds"]+15, "supervisor wall bound")
        samples = self.jsonl(EVIDENCE / f"{self.name}-resources.jsonl")
        self.require(bool(samples), "resource samples present")
        self.require(all(type(x["rss_bytes"]) is int and 0<=x["rss_bytes"]<=6*1024**3 for x in samples), "observed RSS bound")
        self.require(all(a["elapsed_seconds"]<=b["elapsed_seconds"] for a,b in zip(samples,samples[1:])), "resource sample order")
        self.same(resources["peak_observed_rss_bytes"], max(x["rss_bytes"] for x in samples), "resource peak recomputation")
        gaps = [b["elapsed_seconds"]-a["elapsed_seconds"] for a,b in zip(samples,samples[1:])]
        self.require(all(0.9<=gap<=3 for gap in gaps), "one-second cooperative sampling cadence with scheduling tolerance")
        self.require(resources["elapsed_seconds"]-samples[-1]["elapsed_seconds"]<=3, "last resource sample near exit")
        return {"status": "registered_receipts_verified", "run": self.name, "registered_settings": self.run,
            "native_directory": str(directory), "native_manifest_sha256": m0.sha(directory/"manifest.json"),
            "policies": output, "completed_records": len(rows), "checks": self.checks,
            "resources": {"wall_seconds":resources["elapsed_seconds"], "peak_observed_rss_bytes":resources["peak_observed_rss_bytes"],
                "samples":len(samples), "maximum_sample_gap_seconds":max(gaps,default=0)},
            "source_event_semantics": {
                "multiple_death_events": "Allowed on a single terminal raw frame; collision_check can call die repeatedly.",
                "terminal_count": "Exactly one per terminated episode; zero on a live cap.",
                "death_penalty": "Minus five once per terminated episode; never per Death event.",
                "score_delta": "Read actual post-advance native score, including pickups after lethal collision; not reconstructed from Death/collision events."},
            "limitations": ["Receipt consistency and source identity; no independent collision replay or per-frame trace.",
                "Score/death-pickup checks use actual aggregate score deltas; individual lethal-frame pickups are not separately logged.",
                "Native occupancy is post-call sampled; observed capacity does not prove all future trajectories fit.",
                "RSS is cooperative one-second sampling, not a hard memory ceiling.",
                "Cap observations are censored; D1 shorter sanity is not gate qualification."]}
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--run", choices=RUNS, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args=parser.parse_args()
    auditor=Auditor(args.run)
    try:
        result=auditor.audit(); code=0
    except BaseException as error:
        result={"status":"failed", "run":args.run,"error":f"{type(error).__name__}: {error}","checks":auditor.checks}; code=1
    result.update(audited_at_utc=dt.datetime.now(dt.timezone.utc).isoformat(),
                  checker_sha256=m0.sha(Path(__file__)), frozen_D2_auditor_sha256=m0.sha(ORIGINAL),
                  artifact_sha256=auditor.artifacts)
    with args.output.open("x") as handle:
        json.dump(result,handle,indent=2,sort_keys=True,allow_nan=False); handle.write("\n")
    print(json.dumps({k:v for k,v in result.items() if k not in ("policies","artifact_sha256")},allow_nan=False),flush=True)
    return code
if __name__=="__main__":
    sys.exit(main())
