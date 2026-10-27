# BEST180 D2 branch preparation findings

## Frozen ancestry

- Restore parent: `D2-gradient-alignment-20261025-r2/checkpoint-000180-candidate.pt`, SHA-256 `105e0f7a83e154116bd9f0d5eaaf573a896886468c9038f548f5ce7e6377c7ea`.
- Parent audit: `d2-gradient-parent-terminal-audit-20261025-r2/parent-terminal-receipt.json`, SHA-256 `7968a62b6e601fab971e4145dbaebfa1995c8f696e6df442ab70fc0435b74903`.
- Runtime copied unchanged from `D2-gradient-capsule-parent-freeze-20261025-r5/own/runtime`; runner adapter copied from `D2-continuation180-parent-repair-20261025-r3`.
- Policy `user-best-checkpoint-policy-20261026-r1/policy.json` governs parent choice. The failed paired-inference harness does not gate training.

## Required branch design

- New run ID: `D2-best180-branch-luna-20261026-r1`.
- Phase updates 180 through 252; 72 new updates; fresh registered uint32 master seed, distinct from every prior D2 branch seed. Slot episode indices start at exact saved `next_episode_indices`; record all abandon/reset/complete events and raw-frame totals.
- Preserve PPO, reward, K=4, full attention, frozen native runtime, and current D2 reservation ranges. Use deterministic argmax on the same 64 D2 development seeds at entry and each 12 updates. Record mean alive raw frames, Q1/Q4 tail means, death counts, and score. Select by strict development mean improvement only after audit.
- Requested outer budget is 1800 seconds with 10 seconds reserved for cleanup; retain separate 6 GiB sampled RSS and MPS caps. Prior measured 72-update wall was 1169.719 seconds; preregister a smaller cap only if measured full-wall preflight cannot fit.
- Normal training completion cannot promote competence. D3/student/B/E and qualification remain out of scope.

## Stop conditions before registration

1. `ledgerstate.json` was not found in this checkout or searched T3 worktrees. No state-path authority is available to build a live lease guard or prove current lease absence from the file requested. User supplied current no-campaign/no-lease status; preserve as task context, not file evidence.
2. Owned adapter now registers/evaluates 180, 192, 204, 216, 228, 240, and 252, and validates each output. The 22 synthetic contract tests pass. The live registration/pin manifest still needs regeneration for these changed files.
3. Existing exact parent audit authorizes BEST180 for continuation; it does not provide automatic authority for future candidates. Register all seven checkpoints as complete-update candidates. Require parent audit of each exact candidate and paired evaluation before any candidate can replace BEST180. Do not label any candidate accepted or selected in this preparation.
4. Parent receipt records successful-lineage cumulative wall as 2952.324712417151 seconds. User-provided lineage figure 4122.0439 seconds differs. Resolve this against authoritative accounting before writing the new lineage baseline; never include failed/regressed 252 branch time.
5. Existing adapter registration has prior run ID, seed, output, 1600-second work budget, endpoint schedule, and lease identity. Do not reuse it. Source draft pins the lexical venv and resolved interpreter, current origin/HEAD, config hash, and copied runtime membership. Build the full fresh registration after lease-path authority and lineage reconciliation; refresh all changed-file/input pins then.

No campaign, lease, training environment, episodes, rollout, gradients, or optimizer steps were started here.
