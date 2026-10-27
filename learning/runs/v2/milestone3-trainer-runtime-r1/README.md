# M3 trainer runtime component

Five new modules implement semantic identities, immutable checkpoints, resource/lease supervision, development evaluation, and explicit teacher experiments. The parent must integrate and independently review these exact sources before any real probe or training.

Final validation: **64 synthetic CPU/read-only identity tests pass** under the target venv with `-B -W error` and four CPU threads. Prior successful 53/61-test runs remain. Attempt 4 retained 62 passes and two failed newly added controller fixtures: those fixtures omitted normal Experiment attributes. Attempt 5 initializes those attributes; production source and assertions were unchanged for that correction.

No environment was constructed or stepped by this task. No real-rollout optimizer update, MPS computation, device probe, pilot, stage, B/E evaluation, or dependency install ran. CPU learner/RNG round-trip tests use a tiny synthetic linear model. Resource/MPS/process tests use mocks. CLI config/freeze preparation succeeded against the actual installed runtime and accepted native pins; its candidate identity is not training authorization.

## CLI preparation and execution

Use the configured `python/.venv/bin/python -B -m dodge_rl.train_teacher` prefix. Output parent directories must already exist.

1. `config --phase probe --device cpu --output NEW_CONFIG.json`
2. `freeze --config NEW_CONFIG.json --output NEW_IDENTITY.json`
3. Parent independently reviews and registers `active_long_campaign` in the existing ledger with `run_id`, raw identity-document SHA256, raw config-document SHA256, `kind="M3_teacher"`, and `authorization="frozen_reviewed_M3_teacher"`.
4. `probe --config NEW_CONFIG.json --identity NEW_IDENTITY.json --run-id RUN_ID --run-dir NEW_RUN_DIRECTORY`
5. Parent selects a completed comparable probe measurement, creates a fresh `config --phase pilot --device SELECTED_DEVICE`, freezes/reviews/registers that identity, then invokes `pilot` with the same execution arguments.
6. After a successful pilot certificate, `config --phase D1 --device SELECTED_DEVICE --parent-checkpoint PILOT_CANDIDATE.pt --output NEW_CONFIG.json`, freeze/register, then `stage --stage D1 --parent-checkpoint PILOT_CANDIDATE.pt` with the execution arguments. D1→D2→D3 follows only successful hash-bound progress certificates.

A same-phase fresh-environment continuation uses `--resume-checkpoint CHECKPOINT.pt` and the exact original semantic config/identity. Consumed logical-phase wall time is stored in checkpoint context and deducted; expired phases cannot restart their full budget. Current episodes are abandoned and logged, next indices are current+1, and batch size must match. Root still owns the decision to authorize any continuation after diagnosis; there is no automatic retry.

Config seed namespaces are u64 values larger than JavaScript's exact-integer range. Keep CLI-generated JSON bytes intact; do not parse and reserialize them through floating-point JavaScript numbers.

## Boundaries

- The runtime never writes the parent ledger or scheduler. Parent orchestration owns phase order and device selection. Root must issue each reviewed lease explicitly; the CLI never invokes the next phase automatically.
- Probe measures completed inference and PPO updates on the same initial weights and real frozen rollout. Collection wall time is separate. Only measurements with matching optimizer-step/epoch work participate in speed selection; unequal work is retained and excluded. This is not a claimed closed-loop training SPS measurement.
- Development uses only the first 64 fixed D seeds, in independent B1 native environments with batched policy inference over live slots. Ended environments are never stepped/reset and no filler episodes run.
- Checkpoints publish by atomic non-overwriting hard link after data fsync, then directory fsync. Failed temporary files remain as owned `.partial` evidence. Candidate/transition loading anchors exact parsed bytes and rejects altered identities or invalid progression certificates. Interrupted updates cannot advance.
- Guards are cooperative, with separate RSS and MPS-driver samples plus external worker RSS/wall checks. They do not prove unsampled memory stayed below a hard OS ceiling. Forced process termination can prevent a final checkpoint; prior checkpoints and streamed successful native boundaries remain.
- Source/native pin preservation is verified against accepted M2 and published model/PPO manifests. No claim is made that this task captured a complete pre-edit checkout snapshot.
- No end-to-end real trainer process has run. Whole-runtime integration/frozen code review, actual device compatibility/performance, and empirical pilot learning remain pending.
