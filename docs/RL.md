# Reinforcement learning evidence

This page reports development evidence from local experiment archives. The archive paths below are not present in this branch or portable to other checkouts. It contains no held-out outcomes. Source references use paths relative to this checkout. Missing measurements remain marked as not measured. Reproduction commands are listed only when retained evidence provides them.

## Current candidates

| Category | Current best candidate | Selection criterion and limits |
|---|---|---|
| Non-learned search | DODGE-083 approximate independent-belief planner, with M0 continuation | Its paired capped mean survival exceeded M0 at each difficulty on the development cohort below. This is a small, censored comparison, not promotion or proof of a fair teacher. |
| Learned policy | Checkpoint 420 | Historical trained teacher baseline; current comparable evaluations against other learned candidates are incomplete. This is a provisional working choice, not promotion. |

M0 (`nearest_lethal_aabb_safe_powerup`) is the base heuristic. For each action it predicts player motion and extrapolates observed boxes. It prefers a safely reachable powerup; otherwise it maximizes collision-free time, nearest-threat clearance, then overall clearance. Ties follow stable action order. The search planner samples independent future geometry, evaluates root actions with M0 continuation, and ranks expected capped survival with M0 and leaf-agreement tie breaks. Its belief approximation uses privileged present and past state and is not an exact posterior.

## Planner evidence

DODGE-083 compared M0 with a four-sample independent-belief planner on 12 development seeds at each difficulty. The common cap was 18,000 frames. Game seeds were `1907, 2909, 3911, 4913, 5917, 6919, 7927, 8929, 9931, 10937, 11939, 12941`. The belief planner used privileged present and past inputs. Its independent-belief estimate is approximate, not an exact posterior or a validated fair teacher.

The following statistics were recomputed from the 36 raw JSONL outcome rows per condition. Q1 uses nearest-rank selection at rank ceil(0.25n). Median uses the middle value or the mean of the two middle values. Capped belief outcomes remain at 18,000 frames. We did not round values upward.

| Difficulty | Condition | n | Mean frames | Q1 | Median | Minimum | Deaths / capped | Leading recorded death causes |
|---:|---|---:|---:|---:|---:|---:|---:|---|
| 1 | M0 | 12 | 8,264.25 | 5,554 | 7,072.5 | 1,437 | 11 / 1 | static pattern 7; moving pattern 2 |
| 1 | Belief | 12 | 15,034 | 11,203 | 18,000 | 6,285 | 4 / 8 | static pattern 2; moving pattern 1; normal enemy 1 |
| 2 | M0 | 12 | 5,643 5/6 | 698 | 3,414.5 | 695 | 12 / 0 | kamikaze explosion 5; normal enemy 4 |
| 2 | Belief | 12 | 16,049 1/3 | 16,045 | 18,000 | 698 | 4 / 8 | moving pattern 2; static pattern 1; normal enemy 1 |
| 3 | M0 | 12 | 2,665.75 | 513 | 2,431 | 513 | 12 / 0 | normal enemy 7; static pattern 3 |
| 3 | Belief | 12 | 13,297 2/3 | 7,281 | 18,000 | 698 | 5 / 7 | moving pattern 3; normal enemy 2 |

Cause counts omit capped rows, whose cause is null. Other causes occurred in the raw rows. The per-difficulty mean paired gains reported by the retained summary are 6,770, 10,406, and 10,632 frames. These are restricted-survival comparisons at the shared cap, not uncapped death-time estimates. The summary reports 23 censored belief rows and one censored M0 row.

The retained DODGE-083 summary reports mean planning time near 39.2–39.5 ms per call on its recorded system. This cost is environment-specific. It does not establish in-game frame-time compliance. The belief planner overrode M0 on 0.15%, 0.49%, and 0.80% of decisions by difficulty; action ties exceeded 99.9% in every group.

DODGE-085 ran the belief planner to death or a one-million-frame cap, with a 4,500-decision guard per game. The retained raw outcomes include 36 rows, all terminal by death. The table uses the same quantile rules as above and reports alive frames. Death-frame counts in the verified summary are one frame higher.

| Difficulty | n | Mean frames | Q1 | Median | Minimum | Deaths / capped | Mean planning ms/call | Leading death causes |
|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 12 | 27,816 5/6 | 11,203 | 27,218 | 6,285 | 12 / 0 | 4.72 | moving pattern 6; kamikaze explosion 2; static pattern 2 |
| 2 | 12 | 29,518.25 | 16,045 | 27,370.5 | 698 | 12 / 0 | 5.12 | kamikaze explosion 4; moving pattern 3; kamikaze enemy 2; normal enemy 2 |
| 3 | 12 | 21,773 5/6 | 7,281 | 20,823 | 698 | 12 / 0 | 5.17 | normal enemy 6; moving pattern 4 |

DODGE-085 used the saved DODGE-083 belief decisions as a guard, not a matched M0 outcome arm. This table reports only the belief outcome; no paired M0 performance comparison is supported. DODGE-088 checked its play-only selector against the full evaluator on saved decisions, but generic pruning had no hits. DODGE-085 did not replay saved DODGE-083 histories. It guarded selected decisions and compared death time. The DODGE-083 rows lack per-frame actions and canonical state checkpoints. Exact continuation equivalence and causal attribution are unverified.

### Best-candidate status

The evidence below identifies candidates for follow-up. It does not select a validated best policy. DODGE-094 is a four-seed reused-development-seed comparison with a horizon confound. Its results are descriptive only.

| Candidate | Evidence | Development result | Cost / limitation | Status |
|---|---|---|---|---|
| Four-sample independent-belief planner | DODGE-083 and DODGE-085 | DODGE-083 had higher capped survival than M0 across all three difficulty means. DODGE-085 recorded the uncapped-to-death distributions above. | About 39.2–39.5 ms per call in DODGE-083; DODGE-085 mean planning cost ranged from 4.72 to 5.17 ms per call by difficulty. Uses privileged inputs and approximate belief. | Follow-up candidate; not a fair teacher or best-policy claim. |
| Selected-hold policy | DODGE-094 | Pooled mean 11,476.8 frames versus 11,094.8 for belief; 12 paired games per condition. Paired selected-action sequences matched in 2 of 12 cases. | Belief used a 52-frame action rollout; selected-hold used a 24-frame evaluation horizon. Mean planner cost was 149.204 ms/call versus 144.614 ms/call. | Inconclusive; horizon confound prevents attribution to hold selection. |

DODGE-095 is registered as a same-horizon, paired fresh-development comparison of belief and selected-hold policies. Its registration specifies 24-frame total evaluation horizons and staged execution gates. Results are not present in the reviewed registration evidence. Status: registered; outcomes unverified. No seed list, private execution details, or held-out data are included here.

### M0 reference behavior

M0 is the current planner baseline in DODGE-083. In the recorded selection path, an M0 value at maximum survival returns immediately before the safety tie-break. This behavior can preserve selected play under an M0-first cutoff, but it does not provide all nine exact action labels. A separate exact play-only selector preserves the full evaluator's M0 and tie-break rules.

## Colleague interface

The planner source exposes `Policy::new(kind: PolicyKind, seed: u32)`, `observe(&mut self, state: &FullState)` on every raw frame, and `action(&mut self, state: &FullState) -> Action`. The nine actions are neutral, left, right, up, down, up-left, up-right, down-left, and down-right. M0 uses full game state and prior observed geometry; it is deterministic for the same state history. Preserve game and policy seeds, the observation cadence, and action ordering when comparing implementations.

Use paired games on the same development seeds and game version, with the same frame cap and difficulty. Report game count, mean, Q1, median, minimum, censoring, death causes, and decision time separately for each difficulty. A complete evaluation invocation for the retained experiment has not been established. The core runner's command-file interface alone does not evaluate a heuristic.

The colleague's teacher must accept the state available at each decision and return an action in the nine-action space. Record the teacher identity, game seed, action cadence, and game version with each label. The collector must capture the corresponding pixels without placing privileged state in the student input. Use the parity-fixed build as the current game version. Do not mix game versions in a dataset.

## Vision student and checkpoint identity

The vision student interface uses four consecutive 128×128 frames of PICO-8 palette indices, with values 0–15, and nine action labels numbered 0–8. The dataset stores teacher labels, actions, native-frame indices, and gameplay-frame indices. The writer binds each episode to a canonical game identity and rejects mixed identities, duplicate seeds, invalid dimensions or labels, and non-consecutive indices. FullState teacher labels are training provenance; the student receives pixel frames only.

Checkpoint 420 is identified by SHA-256 `7e0de8640f1337261412d91cde6bc692772ff212fbd360f5aad415dc6bc7ed4b`. Its verified filename is `checkpoint-global-420.pt` under `learning/runs/v2/uniform2-recovery240-luna-20261028-r1/worker-output/` in sibling worktree `t3-c8044e79`. This identity does not establish compatibility with the pixel-only interface. The sibling README states that a four-frame pixel callback cannot directly supply the entity-feature inputs used by checkpoint 420. A reviewed adapter and exact runtime pins are required before evaluation.

The DAgger development collection used eight episodes per arm. Its reconciliation matched 24 shard files across three arms to their manifests. It confirms game identity hash `d0ec361be981365552896b96c8814920a246a548af263bcadbd36251406e74d2`. It proves direct child reaping and sampled process-group absence, but not descendant containment. The collection also recorded development survival, but those results use a separate protocol from the tables above.

A separate supervised recovery produced a student checkpoint and passed a one-frame collector inference check. Its gameplay performance under the common protocol is not measured. The scaled `frame_stack_leaky_relu` fit did not complete. Its terminal receipt reports `status: failed`, `stop_reason: monitor_received_SIGTERM`, and raw exit code `-15`. It is not a trained or usable checkpoint. No held-out evaluation result is included here.

## Evidence references and reproduction

DODGE-083 raw rows are in `../exp-branching-planner/learning/runs/branching-planner/matched-dodge083-independent-belief-r1/`. Its paired summary is `../exp-branching-planner/learning/runs/branching-planner/cadence-m4-tntech-prep-r1/source-reconstructed/learning/research/evidence/dodge083-paired-summary-r2.json`, SHA-256 `0a675bff177ed42b0ae3bd0d1780e2b1f3463707de64374eec987782faacf999`.

DODGE-085 raw rows, `verified-summary.json`, `manifest.json`, and `terminal.json` are in `../exp-branching-planner/learning/runs/branching-planner/taylor-uncapped-085-r2/`. The summary SHA-256 is `8040cbb2829677f1180f8d55d7e4a97e6be008e3c09b6c64a75d3e3bdf75ab0a`. The manifest SHA-256 is `a966e2626f510a35e850328272cb725cf22a0e586bfbc0d672d216f3e23d41eb`. The terminal receipt SHA-256 is `4aabac47f6b85fad65bc7296c6f89f38581507e7817be10927380db012e35910`.

The supervised value network from the pipeline proof is not promoted. Its comparable game performance is not measured here. Checkpoint 420 architecture details, training seeds and comparable per-difficulty survival remain unverified in this evidence snapshot. Its decision cost and Mac/Linux parity are not measured here. The student is not a qualified replacement for the teacher.

## Unresolved

The cadence sweep, warning-aware policy, and selected-hold follow-up remain unresolved. DODGE-094 is a small descriptive comparison with a 24 versus 52 frame horizon confound. DODGE-095 is registered; a completed result is unverified. Do not use these studies to select a winner.

The retained DODGE-083 aggregate command is unavailable in the reviewed files. DODGE-085's retained artifacts describe inputs and identities, but no safe, complete reproduction command is available here. To recompute the displayed quantiles from retained rows, run this command from the experiment checkout:

```sh
python3 - <<'PY'
import glob, json, math, statistics
for condition, pattern in [
    ("M0", "learning/runs/branching-planner/matched-dodge083-independent-belief-r1/m0-d*-s*.jsonl"),
    ("belief", "learning/runs/branching-planner/matched-dodge083-independent-belief-r1/belief-4-d*-s*.jsonl"),
    ("DODGE-085 belief", "learning/runs/branching-planner/taylor-uncapped-085-r2/results/*.jsonl"),
]:
    groups = {}
    for path in glob.glob(pattern):
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

This command recomputes outcome summaries only. It does not rerun games. A fresh game run requires matching source, binary, inputs, and receipts. No training, GPU, or cloud job was started for this documentation change.

DODGE-094's detailed private execution audit is not reproduced here. DODGE-095's registration is at `../exp-deep-plan-replan/learning/experiments/deep_plan_replan/dodge095-registration.json`; only its public design status and horizon correction are summarized above.
