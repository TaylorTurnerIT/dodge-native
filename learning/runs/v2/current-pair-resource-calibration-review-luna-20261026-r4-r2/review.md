# Independent R4 calibration review

**Verdict: BLOCK calibration registration and probe authorization.** Two source findings remain. They affect this one-shot calibration only; they do not block actual training, whose priority stays with the parent.

## B-1 — P1: Spawn identity failure bypasses bounded cleanup

[launch_once.py](/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/learning/runs/v2/current-pair-resource-calibration-prepare-luna-20261026-r4/launch_once.py:231) spawns the probe and claims the marker before capturing its process identity. If `ps` fails, returns malformed identity output, or reports an unexpected PGID, the error branches call `process.communicate()` without a timeout or signal (lines 231–242). A hung child can outlive the 120-second outer bound, and cleanup evidence is not guaranteed. Bound every post-spawn failure, safely reap/terminate the owned child, and record cleanup evidence before re-freezing.

## B-2 — P1: MPS gate rejects any zero sample, including startup

[probe.py](/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/learning/runs/v2/current-pair-resource-calibration-prepare-luna-20261026-r4/probe.py:195) starts sampling and waits for the first sample before loading `best204` on MPS at line 219. The final predicate at lines 114–118 rejects every zero value. A valid zero startup sample followed by positive workload samples therefore rejects the completed run and consumes its one-shot marker. Keep samples present, numeric, finite, and nonnegative; require positive allocation during the representative workload. Add a mixed zero/positive control.

## Evidence and limits

All 58 SHA-256 file pins matched. Retained CPU evidence reports seven passing controls and strict CPU loads for `best204` and `latest252`; it reports zero MPS operations. The retained two-pass evaluator reproduction reports 272 guards, 128 synthetic rows, and 16 CPU forwards. This confirms guard accounting only. It does not establish MPS workload timing or hardware acceptance. No runtime probe or training operation was performed.

The R4 plan records the old R6 cache mtimes in UTC as `2026-10-26T03:16:57Z`. This review leaves historical files untouched and does not connect them to the separate resolved training-cache incident.
