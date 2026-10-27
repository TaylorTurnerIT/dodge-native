#!/usr/bin/env python3
"""Generate frozen M0 heuristic expectations; never execute a native episode."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
POLICY = "nearest_lethal_aabb_safe_powerup"
SOURCES = {
    2: ("learning/runs/v2/milestone0-campaign-r2/native-results/baselines/episodes.jsonl", "40b5a8a1614a304bfd041dcd6eedfd7e68262f60fbca5cf6acfc1ece9a2694b3"),
    3: ("learning/runs/v2/gate-baselines-r1/native-results/d3/episodes.jsonl", "cd0222856a3e56d3eb2b7ae89228314af5d35feefb1e28784aadfab3ad4f9801"),
}


def selected_rows(root: Path = ROOT) -> dict[int, list[dict]]:
    selected = {}
    for difficulty, (name, expected_hash) in SOURCES.items():
        raw = (root / name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected_hash:
            raise ValueError(f"Original baseline identity mismatch: {name}")
        rows = sorted((json.loads(line) for line in raw.splitlines() if line), key=lambda row: (row["policy"], row["episode_index"]))
        rows = [row for row in rows if row["policy"] == POLICY]
        if len(rows) != 1000:
            raise ValueError(f"Expected exactly 1000 heuristic rows at D{difficulty}")
        for index, row in enumerate(rows):
            if row["episode_index"] != index or row["seed"] != 0xB0000000 + index:
                raise ValueError("Noncanonical paired seed order")
            config = row["native_config"]
            if (config["difficulty"], config["patterns_enabled"], config["powerups_enabled"], config["theme_background_shadow"], config["initial_highscores_raw_fixed"]) != (difficulty, True, True, [12, 1], [0] * 12):
                raise ValueError("Baseline native configuration mismatch")
            if row["episode_status"] != "complete" or row["failure"] or row["run_deadline_truncation"] or row["startup_native_frames_excluded"] != 13:
                raise ValueError("Incomplete or incompatible baseline episode")
            if row["death"] == row["cap_truncation"] or not 0 < row["gameplay_native_frames"] <= 18000:
                raise ValueError("Invalid episode boundary")
        selected[difficulty] = rows
    return selected


def main() -> None:
    output = OUT / "qualification_expected.rs"
    receipt = OUT / "expected-generation.json"
    if output.exists() or receipt.exists():
        raise FileExistsError("Expected-table evidence already exists; no overwrite")
    selected = selected_rows()
    text = "// Generated from hash-pinned original M0 records. No native execution.\n"
    for difficulty, rows in selected.items():
        text += f"const EXPECTED_D{difficulty}: [Expected; 1000] = [\n"
        for row in rows:
            fields = [str(row["seed"]), str(row["scores"]["final_score_raw_fixed"]), str(row["gameplay_native_frames"]), str(row["raw_survival_frames"]), str(row["death"]).lower(), str(row["cap_truncation"]).lower(), str(row["final_state_hash"]), str(row["frame_event_counts_enemy_spawn_collision_death_pattern_active_terminal"][2])]
            text += "    Expected { seed: %s, score: %s, frames: %s, alive: %s, dead: %s, cap: %s, full_state_hash: %s, death_events: %s },\n" % tuple(fields)
        text += "];\n"
    output.write_text(text)
    receipt.write_text(json.dumps({"source_files": {name: sha for name, sha in SOURCES.values()}, "policy": POLICY, "rows_per_difficulty": {str(k): len(v) for k, v in selected.items()}, "generated_sha256": hashlib.sha256(output.read_bytes()).hexdigest(), "native_execution": False}, indent=2, sort_keys=True) + "\n")
    print(receipt.read_text())


if __name__ == "__main__":
    main()
