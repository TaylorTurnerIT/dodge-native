# Reinforcement learning evidence

This page reports development evidence only. It contains no held-out outcomes. Committed, sanitized summaries in `docs/evidence/` support retained numeric claims. Raw data remains in external artifacts and is not portable with this checkout.

## Current candidates

| Category | Current best candidate | Selection criterion and limits |
|---|---|---|
| Non-learned search | DODGE-083 approximate independent-belief planner, with M0 continuation | Its paired capped mean survival exceeded M0 at each difficulty on the development cohort below. This is a small, censored comparison, not promotion or proof of a fair teacher. |
| Learned policy | No best ML model established | No learned candidate has comparable results on the same development seeds, difficulties, and frame cap. Checkpoint 420 remains a historical baseline only. |

M0 (`nearest_lethal_aabb_safe_powerup`) is the base heuristic. For each action, it predicts player motion and extrapolates observed boxes. It prefers a safely reachable powerup. Otherwise, it maximizes collision-free time, nearest-threat clearance, and overall clearance. Ties follow stable action order.

The search planner samples independent future geometry, evaluates root actions with M0 continuation, and ranks expected capped survival. It uses M0 and leaf agreement as tie breaks. Its belief approximation uses privileged present and past state. It is not an exact posterior.

## Planner evidence

DODGE-083 compared M0 with the independent-belief planner on 12 development seeds at each difficulty. The shared cap was 18,000 frames. The game seeds were `1907, 2909, 3911, 4913, 5917, 6919, 7927, 8929, 9931, 10937, 11939, 12941`. The planner used privileged present and past inputs. Its independent-belief estimate is approximate, not an exact posterior or validated fair teacher.

The table reports alive frames. Q1 uses nearest-rank selection at `ceil(0.25n)`. Median uses the middle value or the mean of the two middle values. Capped belief outcomes remain at 18,000 frames. The evidence summary recomputes each statistic from the individual development rows.

| Difficulty | Condition | n | Mean frames | Q1 | Median | Minimum | Deaths / capped | Leading recorded death causes |
|---:|---|---:|---:|---:|---:|---:|---:|---|
| 1 | M0 | 12 | 8,264.25 | 5,554 | 7,072.5 | 1,437 | 11 / 1 | static pattern 7; moving pattern 2 |
| 1 | Belief | 12 | 15,034 | 11,203 | 18,000 | 6,285 | 4 / 8 | static pattern 2; moving pattern 1; normal enemy 1 |
| 2 | M0 | 12 | 5,643 5/6 | 698 | 3,414.5 | 695 | 12 / 0 | kamikaze explosion 5; normal enemy 4 |
| 2 | Belief | 12 | 16,049 1/3 | 16,045 | 18,000 | 698 | 4 / 8 | moving pattern 2; static pattern 1; normal enemy 1 |
| 3 | M0 | 12 | 2,665.75 | 513 | 2,431 | 513 | 12 / 0 | normal enemy 7; static pattern 3 |
| 3 | Belief | 12 | 13,297 2/3 | 7,281 | 18,000 | 698 | 5 / 7 | moving pattern 3; normal enemy 2 |

Cause counts omit capped rows, whose cause is null. Other causes occurred. The mean paired gains were 6,769.75, 10,405.5, and 10,631 11/12 frames by difficulty. These are restricted-survival comparisons, not uncapped death-time estimates. There were 23 censored belief rows and one censored M0 row.

Mean planning cost was 39.2–39.5 ms per call on the recorded system. This cost is environment-specific. It does not establish in-game frame-time compliance. The planner overrode M0 on 0.15%, 0.49%, and 0.80% of decisions by difficulty. Action ties exceeded 99.9% in every group.

DODGE-085 ran the belief planner to death under a one-million-frame cap, with a 4,500-decision guard per game. All 36 development outcomes ended by death. The table reports alive frames. Verified death-frame counts are one frame higher.

| Difficulty | n | Mean frames | Q1 | Median | Minimum | Deaths / capped | Mean planning ms/call | Leading death causes |
|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 12 | 27,816 5/6 | 11,203 | 27,218 | 6,285 | 12 / 0 | 4.72 | moving pattern 6; kamikaze explosion 2; static pattern 2 |
| 2 | 12 | 29,518.25 | 16,045 | 27,370.5 | 698 | 12 / 0 | 5.12 | kamikaze explosion 4; moving pattern 3; kamikaze enemy 2; normal enemy 2 |
| 3 | 12 | 21,773 5/6 | 7,281 | 20,823 | 698 | 12 / 0 | 5.17 | normal enemy 6; moving pattern 4 |

DODGE-085 used saved DODGE-083 belief decisions as a guard, not as a matched M0 outcome arm. It supports no paired M0 comparison. DODGE-083 rows lack per-frame actions and canonical state checkpoints. Exact continuation equivalence and causal attribution are unverified.

DODGE-088 checked its play-only selector against the full evaluator on saved decisions. No portable, reviewed summary is retained here, so this page reports no DODGE-088 numeric result or speed claim.

The DODGE-083 and DODGE-085 tables use [DODGE-083 evidence](evidence/dodge083-development.json), SHA-256 `2498a8ae5b990bb47c925fdf28c1fb330d871ce253541716fe74a2906904775b`, and [DODGE-085 evidence](evidence/dodge085-uncapped-development.json), SHA-256 `e896ee69c6a3a3c79648e1ead33aed0101ca298124faf33f7de81b40259abe72`. The DODGE-085 summary pins its binary (`8a7bf2ce37d25f834ad688710b46cd51b2f34d4cabd2818d2cab56f461dc1afe`), manifest (`a966e2626f510a35e850328272cb725cf22a0e586bfbc0d672d216f3e23d41eb`), verified summary (`8040cbb2829677f1180f8d55d7e4a97e6be008e3c09b6c64a75d3e3bdf75ab0a`), and terminal receipt (`4aabac47f6b85fad65bc7296c6f89f38581507e7817be10927380db012e35910`). The exact development rows are in `../exp-branching-planner/learning/runs/branching-planner/taylor-uncapped-085-r2/results/`. The row index [dodge085-row-files.json](evidence/dodge085-row-files.json), SHA-256 `0388f5187714348ccd7ecfa71ceb11bf376388be7a76eda53c316a3333edd120`, lists each exact relative path and row-file SHA-256. Raw inputs remain external.

### Best-candidate status

DODGE-094 provides a small, descriptive four-seed comparison across three difficulties. The sanitized [DODGE-094 summary](evidence/dodge094-four-seed-development.json), SHA-256 `06a87c85a20a3253dc04ba78a090784f1fd858aee1ce892386a4602a16f4c3ea`, retains the pooled and per-difficulty statistics. The source document and exact external summary paths are named there with SHA-256 hashes. The Linux binary hash is `8375179f8145f705173e03a3f3deb00c625cac34930a9def5bad756daef99731`; its source archive hash is `d8396b814107c3b693843a60993462d748ccc6eaccc47c0be0240e46dbfa582c`.

| Condition | Games | Mean frames | Q1 | Median | Minimum | Frame-cap games | Mean score | ms/game frame | ms/planner call |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Belief | 12 | 11,094.83 | 2,561.33 | 11,733 | 699 | 4 | 217.75 | 36.156 | 144.614 |
| Hold-policy | 12 | 11,476.83 | 2,577 | 12,880.5 | 699 | 5 | 208.50 | 37.270 | 149.204 |

| Difficulty | Condition | Games | Mean frames | Q1 | Median | Minimum | Capped |
|---:|---|---:|---:|---:|---:|---:|---:|
| 1 | Belief | 4 | 9,103 | 6,286 | 8,932 | 6,286 | 0 |
| 1 | Hold-policy | 4 | 12,686.25 | 6,984 | 12,880.5 | 6,984 | 1 |
| 2 | Belief | 4 | 13,186.25 | 699 | 17,023 | 699 | 2 |
| 2 | Hold-policy | 4 | 10,986.25 | 699 | 12,623 | 699 | 2 |
| 3 | Belief | 4 | 10,995.25 | 699 | 12,641 | 699 | 2 |
| 3 | Hold-policy | 4 | 10,758 | 699 | 12,166.5 | 699 | 2 |

Each difficulty-condition group has four games. DODGE-094 is not a winner result: paired selected-action sequences matched in 2 of 12 cases, and the hold-policy route selected 4-frame holds 34,388 times, 12-frame holds 13 times, and one 24-frame hold. The hold-policy evaluation horizon is 24 frames; belief uses a 52-frame action rollout. This horizon confound prevents attribution to hold selection alone. The four seeds are reused development inputs.

DODGE-095 remains unresolved. Cadence, warning-aware planning, and selected-hold behavior remain unresolved as research questions. No DODGE-095 outcome table or numeric claim is retained here. DODGE-094 does not resolve those questions.

## Learned candidates

Checkpoint 420 is a historical trained teacher baseline. Its checkpoint SHA-256 is `7e0de8640f1337261412d91cde6bc692772ff212fbd360f5aad415dc6bc7ed4b`.

The inspected native evaluation script accepts entity-line model JSON files and does not load checkpoint 420. No comparable learned candidate was runnable through that inspected interface. This does not establish that a compatible loader is impossible generally.

The supervised value network from the pipeline proof is not promoted. The student’s game performance under the shared protocol is not measured. No learned policy has established comparable survival, decision cost, or Mac/Linux parity.

Checkpoint 420 uses entity features. Its exact configuration, training data, training seeds, and decision cost are not measured here. Evaluation on the shared development protocol and Mac/Linux parity are not established.

The scaled `frame_stack_leaky_relu` fit failed and did not yield a usable checkpoint. Its external terminal receipt has SHA-256 `dc28e64e00996254fb04db0c405f7278f2f4051c2d5be1809be65ab4f15ea742`. The vision student remains a retained research candidate, not a selected policy. Its gameplay performance under the shared protocol is unverified. The verified collector records one 128 by 128 indexed frame before each labeled action. Acting receives a four-frame stack of 128 by 128 indexed frames, oldest to newest. Pixel indices use the 16-value PICO-8 palette. The stack zero-pads at startup and resets at each episode. Each episode record carries schema identifiers, cartridge SHA-256, seed, partition, labeler identifier, core schema version, startup count, and native/gameplay frame indices. Each sample stores pixels, the privileged label, and the action from the same pre-action state; the runtime receives only pixels. The exact collector contract is external artifact `exp-vision-student-heuristic/docs/vision-student-foundation.md`, SHA-256 `76c9ee3d590c296fef49456eee63b1bfc33a424892ccb45c0677d0ee1d91dc1a`. The pixel dataset contract source hash is `167b8d159b14f88ebb7a6792702817445436a9c1c95bb3e6a8aeadcf14721025`. The exact schema data file path is not retained in this checkout. The parity-fixed game identity reported by the pipeline diagnostic is `d0ec361be981365552896b96c8814920a246a548af263bcadbd36251406e74d2`.

Mac/Linux parity for the planner, M0, and learned candidates is not established by the summaries in this document.

| Learned candidate | Status | Specific blocker |
|---|---|---|
| Checkpoint 420 | NOT RUN | Torch checkpoint requires entity-transformer inputs and a compatible current-game loader. The inspected runner accepts linear entity-line JSON; no bridge or matched parity-fixed source and binary pins are retained. |
| Vision student | NOT RUN | Pixel checkpoint is not accepted by the inspected entity-lines runner. No reviewed pixel-policy game adapter, exact checkpoint/source pins, or shared-protocol startup and terminal receipts are retained. |
| Entity-lines arms | NOT RUN | Runner supports six JSON arms, but candidate model JSON files, copy report, dataset metadata, exact source pins, and bounded evaluation config are absent. |
| Supervised value network | NOT RUN | No reviewed game-action adapter or shared-protocol game evaluation record is retained. |

The learned-model evaluation is **NOT RUN**. In the inspected safe sources, no reviewed loader or adapter was found for the checkpoint interfaces. This finding is limited to those inspected sources and does not mean such an adapter is impossible generally. The entity-lines model is interface-compatible, but its required model files, copy report, dataset metadata, exact source pins, and bounded configuration are missing. The [learned-candidate evaluation record](evidence/learned-candidate-evaluation.json), SHA-256 `cfdb8dcfe857fb698594c3fe4721a3f993cc526a1577b8ee928fe5a2d6c2d0ea`, records the inspected source hashes and limits. The external M3 component contract artifact is `exp-vision-student-heuristic/docs/v2-m3-component-contract.md`, SHA-256 `a1051d82527a9aec1f7967ff8ab217c30263240e032991aeff7b993fd975ba47`. No game evaluation or training job was started for this documentation change.

## M0 and colleague interface

The planner source exposes `Policy::new(kind: PolicyKind, seed: u32)`, `observe(&mut self, state: &FullState)` on every raw frame, and `action(&mut self, state: &FullState) -> Action`. The nine actions are neutral, left, right, up, down, up-left, up-right, down-left, and down-right. M0 (`nearest_lethal_aabb_safe_powerup`) uses full game state and previously observed geometry. It is deterministic for the same state history. Preserve game and policy seeds, observation cadence, and action ordering when comparing implementations.

The teacher must accept state available at each decision and return one of the nine actions. The collector must capture corresponding pixels without exposing privileged state to the student. Use the parity-fixed build as the current game version. Do not mix game versions in a dataset.

Use paired games on the same development seeds, game version, frame cap, and difficulty. Report game count, mean, Q1, median, minimum, censoring, death causes, and decision time separately for each difficulty. A complete evaluation invocation for the retained planner experiment is not established. The core runner’s command-file interface alone does not evaluate a heuristic.

## Evidence and limits

The evidence files under `docs/evidence/` are small, portable summaries. They contain development results, source paths, and SHA-256 hashes. They contain no raw archives or held-out outcomes. Recompute checks use only the exact development-row patterns named in those summaries.

From the experiment checkout, the following command reads only the explicitly listed development filenames. It does not scan other rows or rerun games. The list is limited to the DODGE-083 cohort.

```sh
python3 - <<'PY'
import json, math, statistics
seeds = [1907, 2909, 3911, 4913, 5917, 6919, 7927, 8929, 9931, 10937, 11939, 12941]
root = "learning/runs/branching-planner/matched-dodge083-independent-belief-r1"
files = [("M0", [f"{root}/m0-d{d}-s{s}.jsonl" for d in (1,2,3) for s in seeds])]
files += [("belief", [f"{root}/belief-4-d{d}-s{s}.jsonl" for d in (1,2,3) for s in seeds])]
for condition, paths in files:
    groups = {}
    for path in paths:
        with open(path) as stream:
            row = json.loads(stream.readline())
        groups.setdefault(row["difficulty"], []).append(row["alive_frames"])
    for difficulty, values in sorted(groups.items()):
        values.sort()
        q1 = values[math.ceil(0.25 * len(values)) - 1]
        print(condition, difficulty, len(values), sum(values) / len(values), q1,
              statistics.median(values), values[0])
PY
```

This command recomputes outcome summaries only. It does not reproduce a game run. A fresh run requires matching source, binary, inputs, and receipts.

The learned-candidate record is [here](evidence/learned-candidate-evaluation.json). Its runner source hash is `7f40e2f8e5544712a75478be7ff50d182177f61ad6827302650a065178b92d4e`; the pixel dataset contract and student model source hashes are `167b8d159b14f88ebb7a6792702817445436a9c1c95bb3e6a8aeadcf14721025` and `b1d442c5517155a3941f925799b6b8818e931f2ba9f6f9c9000150f4b255e799`. The vision pipeline report is external artifact `exp-vision-student-heuristic/docs/vision-pipeline-debug-parity-report-20261104.md`; its SHA-256 is `47951b4c4a36a1655b9f46e80ce0bee61ae90d94a63b9df43b03734053cb3d57`.

The following DODGE-085 command reads exactly 36 listed development row filenames from the external experiment checkout. It recomputes frame summaries, death causes, and mean planner call time. The row index above pins each input file hash. This command does not rerun games.

```sh
python3 - <<'PY'
import json, math, statistics
from collections import Counter
from pathlib import Path
root = Path("learning/runs/branching-planner/taylor-uncapped-085-r2/results")
seeds = [1907, 2909, 3911, 4913, 5917, 6919, 7927, 8929, 9931, 10937, 11939, 12941]
for difficulty in (1, 2, 3):
    rows = []
    for seed in seeds:
        path = root / f"belief-uncapped-d{difficulty}-s{seed}.jsonl"
        with path.open() as stream:
            rows.append(json.loads(stream.readline()))
    values = sorted(row["alive_frames"] for row in rows)
    q1 = values[math.ceil(0.25 * len(values)) - 1]
    causes = Counter(row["death_cause"] for row in rows if row["dead"])
    capped = sum(not row["dead"] for row in rows)
    mean_ms_per_call = sum(row["planning_ns_per_call"] for row in rows) / len(rows) / 1_000_000
    print(difficulty, len(values), sum(values) / len(values), q1,
          statistics.median(values), values[0], capped, causes, mean_ms_per_call)
PY
```

DODGE-083 and DODGE-085 report different protocols. DODGE-083 uses a shared frame cap and supports paired comparison with M0. DODGE-085 runs the planner to death and supports no paired M0 comparison. Neither establishes a fair teacher or a best ML model.

The learned-candidate record is a committed summary. Its source data remains external. Internal registration steps are not part of this public report.
