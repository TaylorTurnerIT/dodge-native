# Frozen Milestone 0 campaign, revision 2

This plan is registered before the full campaign. It measures the original engine at `d7ad95127ad7529c5217a51ae9dc5cfedd3f2365`, using the repaired harness in `/Users/taylor/.t3/worktrees/dodge-native/t3-5d7162c0`. It does not use the modified headless implementation or historical policy results.

## Preconditions and identity

Parent verification matched all 33 original tracked files to HEAD, all five new source/document hashes, the release executable, and every artifact hash in `target/v2-m0-review-r2/final-manifest.json`. Native static reviews found no defects. Free Beam attempts stalled; fresh DeepSeek and MiMo attempts hit the confirmed OpenCode free usage limit. Their failures are retained in `learning/runs/v2-orchestration/opencode-quota-exhausted-20261024.json`. All exact owned attempts were cancelled. A fresh independent Codex audit reviewed the unchanged frozen capsule and found no blocking defect; parent reconciled that fallback before launch. Provider failure is not represented as a completed free-model audit.

Frozen review manifest SHA256: `1178bf8236dbecb305a86053462609017d3e756a0f514e8bb913b2525af3b6b8`.

Release executable SHA256: `922485d26128dbdc4df0868a5df7d7e72bc8f4135addfd691a1e11484d785d39`.

The retained repair checks report 44 original core tests and 18 harness tests, formatting, workspace/all-target Clippy, release build, and receipt audits. Its only runtime smoke is one episode per policy at D1 with patterns and powerups off. Those results do not establish full-campaign performance or capacities.

## Registered campaign

- Run exactly 1,000 episodes each for random, neutral, and the repaired AABB safe-powerup heuristic, in that order.
- Pair seeds `0xB0000000 + i`, `i = 0..999`, across policies. Reserve these seeds from training.
- Set difficulty 2, patterns on, powerups on, theme 12/1, and initially zero highscores.
- Construct a fresh game for every episode. Verify X plus twelve neutral startup frames; exclude startup from gameplay and survival.
- Hold each policy action for at most four raw frames; stop immediately on death.
- Cap episodes at 18,000 raw gameplay frames. Death takes precedence if it coincides with the cap. Report actual alive frames separately.
- Apply a 3,600-second global cooperative wall budget. No automatic retry, cap increase, seed replacement, or resume follows a failure.
- Use exclusive output directory `target/v2-m0-baselines-r2`. Preserve interrupted records, failures, and all earlier runs.

Run from the isolated worktree:

```sh
target/release/examples/m0_baseline --episodes 1000 --max-frames 18000 --action-repeat 4 --difficulty 2 --patterns true --powerups true --max-seconds 3600 --output-dir target/v2-m0-baselines-r2
```

Before launch, recheck frozen hashes and remaining overnight time. Launch only if the full wall budget plus ten minutes fits before `2026-10-24T13:00:00Z`. Keep at most one long training/evaluation campaign active. Preserve the command, timestamps, process identity, output, exit status, and observed resource samples.

`learning/scripts/v2_run_m0_campaign.py` supervises the two sequential experiments. It verifies the frozen source/executable, requires the explicit ledger review gate, creates exclusive evidence files, samples native RSS once per second against a cooperative 6 GiB threshold, and stops only its own new process group after a native deadline plus 15 seconds of grace. Its identity-only preflight passed before launch. Native partial receipts remain intact if the supervisor stops a process. This is a one-shot evaluation campaign, not PPO training.

## Audit and interpretation

Parse every JSON/JSONL record and require 3,000 completed episode records. Verify paired seed order, configuration, startup count, fixed-point score accounting, survival, death/cap exclusivity, aggregate counts, and source/executable identities. Recompute score and survival distributions from episode records before accepting summaries.

Report raw fixed-point score, numeric raw score, display/ceil score, and stored highscore independently. Report mean, median, p90, cap truncations, raw enemy-family and active-rectangle maxima, overflow counts, and observed active-pattern coverage. Native occupancy includes hidden control records; it is not the eventual model's admitted-token count. Post-frame samples do not prove within-call maxima.

Cap-truncated score and survival are censored. Report their fraction; do not silently raise the cap or describe the sample as uncensored. Any change requires a separate documented decision and new run identity. No observed absence of overflow proves all future configurations safe.

The original-engine throughput measurement is a separate short experiment after the review gate. Use `--benchmark-seconds 10` for ten seconds total: five seconds for the single-thread phase and the remaining time for the four-thread phase. Set D2/patterns/powerups on, K4, and a 60-second global wall budget. The harness rejects unsupported thread counts. Retain per-phase wall throughput, summed worker simulation time, seeds, startup frames, deaths, and cap/deadline truncations. Random short-episode throughput does not establish mature-pattern or PPO throughput.

Difficulty 3 gate baselines and difficulty 1 curriculum sanity remain separate later steps. Freeze teacher score/survival margins from measured evidence before teacher evaluation. The supplied two-times-score example is illustrative.
