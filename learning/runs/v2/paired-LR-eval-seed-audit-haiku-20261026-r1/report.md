# Upper D64 seed audit for the paired LR endpoint (read-only)

Run: `paired-LR-eval-seed-audit-haiku-20261026-r1`. Source and metadata audit only. No environment, evaluation, training, MPS, checkpoint load, seed reservation, lease, or state change. No sealed B/E or D3 scores, results, or student artifacts were read. No manifest is frozen here.

## Verdict

The upper pool `0xD0000040`–`0xD000007F` (decimal `3489660992`–`3489661055`, 64 seeds) cannot honestly be called "previously untouched independent held-out" yet. It can be called:

- Not a seed of any episode record in the accessible artifacts scanned (see scope below).
- Training-excluded by protocol (`docs/v2-m3-run-protocol.json` `training_excluded_ranges`, `python/dodge_rl/ppo.py` `_RESERVED_RANGES`).
- Not in the dev-64 selection set and not in the sealed B/E blocks.
- Registered in the qualification metadata as role `development` with `episodes_available: 128` (`docs/teacher-qualification-v2.json` `seed_ranges`; same in v1). The whole D block is a development-namespace block, not a sealed reserve.

Partial absence in scans is not proof of non-use. There is no seed ledger in the repo, and `dev_eval` never assigns the upper 64 to any run. The parent must decide whether this label is acceptable, or freeze a different manifest.

## Evidence inspected

Protocol and qualification metadata (read as text, hashes below):

- `docs/v2-m3-run-protocol.json`: `development.seed_start` = 3489660928; `development.episodes` = 64; `training_excluded_ranges` = `[2952790016, 2952791015]`, `[3489660928, 3489661055]`, `[3758096384, 3758097383]`; `qualification_B_opened` = false; `student_work` = false.
- `docs/teacher-qualification-v2.json` (`seed_ranges`): qualification `2952790016`–`2952791015` (1000 per difficulty); development `3489660928`–`3489661055` (`episodes_available` 128); reserved_replication `3758096384`–`3758097383` (1000).
- `docs/teacher-qualification-v1.json`: same development block (128).
- `docs/teacher-qualification-v3.json`: survival-only policy; states that existing `dev_eval.py` and `identity.py` stay tied to the retained v2 protocol.
- Arithmetic: `0xB0000000`=2952790016, `0xB00003E7`=2952791015, `0xD0000000`=3489660928, `0xD000007F`=3489661055, `0xE0000000`=3758096384, `0xE00003E7`=3758097383. The qualification (B), development (D), and replication (E) blocks do not overlap each other. The upper 64 sits inside the D block and outside the dev-64 (`0xD0000000`–`0xD000003F`).

Source:

- `python/dodge_rl/dev_eval.py`: `development_seeds()` (64 seeds from `seed_start`); `require_development_seed` (rejects any other seed); `development_environment_config` (`raw_frame_cap` 2000 for D1, else 18000; `action_repeat` 4; `patterns_enabled` = difficulty != 1; `powerups_enabled` True; `excluded_seed_ranges` from protocol); `summarize` (`len(rows)==64` and `seed` list equal to `development_seeds()`; frame bounds `alive<=gameplay<=cap`; `terminated XOR truncated`; death-cause check; score identity; returns mean score, mean alive frames, raw frames, deaths, death-cause counts, caps); `evaluate` (deterministic argmax over `development_seeds()`, asserts `actual_seed == development_seeds()[index]`). It does not compute Q1/Q4.
- `python/dodge_rl/ppo.py`: `_RESERVED_RANGES` = B, D (`0xD0000000`–`0xD000007F`), E. `_audit_episode` and `collect_rollout` enforce this on the training stream.
- `crates/dodge-rl-env/src/seed.rs`: `MANDATORY_SEED_RANGE` = B only. Exclusions are applied to training seed draws (`training_seed_normalized`). `SeedMode::Evaluation` uses the explicit `seeds_by_slot` list with no exclusion check. So an explicit upper-D evaluation seed is accepted by the environment; the Python dev guard is the only block.
- `crates/dodge-rl-env/src/seed_reservation_tests.rs`: exclusion tests for D and E edges.
- `learning/runs/v2/latest-best-paired-eval-prepare-luna-20261026-r6/paired_eval.py`: `SEEDS = range(3489660928, 3489660992)` (dev-64 hardcoded); `_tail_means` (bottom-16 / top-16 / all-64 arithmetic means, requires 64 values) — usable Q1/Q4 reference.

Prior design and control:

- `learning/runs/v2/D2-retained324-paired-LR-study-design-haiku-20261026-r1/` (`plan.json`, `design.md`, `input-hashes.json`): design only; marks upper pool as "candidate, pending parent freeze".
- `learning/runs/v2/D2-retained324-continuation-prepare-luna-20261026-r2/registration.json`: hash matches `44ac8185…4c` (not opened beyond hash).
- `learning/runs/v2/D2-retained324-continuation-20261026-r1/`: control with `checkpoint-000384-candidate.pt`, `development-000324..384.json(l)`, `training-episodes.jsonl`. Dev files are on dev seeds only (see below).

Artifact scans (read-only scripts in `scripts/`):

1. `scripts/exact_upper_scan.py` over all of `learning/` (text extensions: json, jsonl, py, md, txt, log, patch, toml, yaml, rs; files ≤5 MB). It searched for decimal 10-digit tokens in `[3489660992, 3489661054]` and hex tokens `0xD0000040`–`0xD000007E`. Output: `exact-upper-scan-learning.tsv` (539 lines, only files with hits). Hits found, all non-episode:
   - Exclusive range stop `range(3489660928, 3489660992)` in dev-only sources (`negative-controls-source-*`, `long_d2.py`, `postflight-adaptation.json`, `paired_eval.py`), 445 lines.
   - Test parametrize `0xD0000040` as a rejected negative (`python/tests/test_teacher_runner.py:143` and copies), plus audit one-liners `range(0xD0000000,0xD0000040)`.
   - No decimal or hex token inside `[3489660993, 3489661054]` in any file.
   - Config range ends `3489661055` / `0xD000007F` are excluded from the search by design (they are range ends).
2. Big files (>5 MB, json/jsonl/log/csv/tsv) grepped separately for the same token patterns: 0 hits.
3. `scripts/seed_summary.py`: per-file seed range class for 438 development/evaluation/episode files: 435 entirely in dev-64 (`0xD0000000`–`0xD000003F`); 3 with other ranges: `postovernight-action-mode-campaign-r1/evaluations.jsonl` (contains a non-seed int `64` plus dev seeds), `milestone0-campaign-r2/native-results/baselines/episodes.jsonl` (B range, see flag below), `gate-baselines-r1/native-results/d1/episodes.jsonl` (B range, see flag below). Table: `dev-eval-seed-classes.tsv`.
4. `scripts/training_block_count.py`: seed values in training-episode logs for `D2-retained324-continuation`, `D2-retained300-continuation`, `D2-retained276-lr3em5`, `milestone3-D2-curriculum-r1`, `postovernight-long-D2-campaign-r2`, `D2-retained204-lr1e4`: 0 seeds in D-upper, D-dev, B, or E blocks (≈83k seed integers in total; ≈22.5k distinct in the largest file alone).
5. Source/protocol/tests tree (`python/`, `docs/`, `reports/`, `research_notes/`, `native/`, `crates/`): same token grep, only the `test_teacher_runner.py` negative-test literal.

Limits of the scans (what they do not prove):

- Not scanned: `.pt` (1880 files, checkpoint binaries), `.bin`/`.npz`, and 197 text files whose path matched the name skip (`sealed`, `qualif`, `student`, `D3`, `-B-`/`-E-`/`/B/`/`/E/`, and third-party `.venv` files). Among those are `*-sealed.log` files (e.g., `D2-retained276-lr3em5-prepare-luna-20261026-r2/attempts/*-sealed.log`). I did not open them. Whether they contain upper-D seeds is unverified.
- Seeds stored only in binary form, or in formats not matched by the regex, would be missed.
- No ledger of evaluated seeds exists in the repo to check against.

## Flags for parent (not resolved here)

1. `milestone0-campaign-r2/native-results/baselines/episodes.jsonl` (mtime 2026-10-24 01:16) has SHA-256 `40b5a8a1…694b3`, which equals `teacher-qualification-v2.json` `baselines.D2.episodes_sha256`. Its seed fields cover the whole B qualification block (`2952790016`–`2952791015`, 1000 distinct). `gate-baselines-r1/native-results/d1/episodes.jsonl` (01:41) has 100 distinct B-block seeds. I read seed fields only, no scores. This means the registered qualification D2 baseline episodes exist on disk. That conflicts with the protocol's `qualification_B_opened: false` and the D2/D3 "not opened" status recorded in the design inputs, unless the protocol flag refers to something narrower. Parent must reconcile before any use of B-range language. I did not check the D3 baseline hash (`cd0222…f801`) against any file.
2. `dev_eval.summarize` and `evaluate` are hard-wired to dev-64. Any upper-D eval needs a new helper, not a parameter flip.
3. `dev_eval` never computes Q1/Q4 or per-episode audit fields for the new contract; `paired_eval._tail_means` is the nearest reference.

## Recommendation

Option A (use the upper 64): acceptable only if the parent accepts the label "unselected development-namespace block, artifact-scan clean, training-excluded". Do not call it sealed or independent. Parent should record the scan command hashes (below) and do a ledger check if one exists.

Option B (fresh manifest): requires a new protocol seed-exclusion version, because the Rust env excludes by ranges, not single seeds. Draw a registered seeded manifest from u32 minus the union of B, D, E, dev-64, all observed training/eval seeds (tens of thousands distinct across the logs above), and any `sealed`-named logs' seeds (not verified). Freeze the manifest hash before eval. Add the manifest block as a training exclusion in the new version, otherwise future training can draw those seeds. This is heavier and is parent-owned.

Recommend option A with the stated label, unless the parent finds a ledger or flag 1 changes the picture.

## Helper and registration contract (for a future independent eval; not written here)

- New module, not a change to `dev_eval.py`. Reuse `death_fields`, `DEATH_CAUSES`, `DEATH_CAUSE_UNAVAILABLE`, and the evaluate loop structure.
- Inputs: checkpoint path and SHA-256; manifest path and SHA-256 (64 seeds, sorted, order fixed); stage `D2`; `raw_frame_cap` 18000; `action_repeat` 4; `patterns_enabled` true; `powerups_enabled` true; deterministic argmax; `batch_size` 1 per seed; `SeedMode::Evaluation` with the manifest.
- Guard: replace `require_development_seed` with a manifest-membership check and a check that the manifest is not in the dev-64 or any reserved block except the one named in the registration.
- Keep these audits: action mode (argmax, `gradients` false, `environment_layout` as dev); 18000 cap (`cap` check in summarize, `truncated` counted separately); 64 episodes; Q1 and Q4 as arithmetic means of bottom/top 16 with fractional frame means; death-cause counts and survival by cause, unknown and truncations separate; raw-frame bounds and `terminated XOR truncated`; score identity; `startup_frames == 13`; `seed.evaluation` flag and `actual_seed` equal to the manifest entry.
- Output: per-episode rows (`episode_index`, `seed`, frames, terminated, truncated, cause, score_raw_fixed), summary, and a manifest-check record. Scores are diagnostic only.
- Comparison: per-seed `linear − constant` alive-frame difference on identical seeds; mean and bootstrap interval with the RNG seed fixed before launch; reports one training pair only.
- Endpoint: local update 384 (cumulative 432) for both arms; no checkpoint selection on the held-out pool.
- Claim limit: a win does not isolate schedule shape from lower mean LR (2e-5). One training pair: no replicate variance.

## Hashes

Full SHA-256 values for all inputs and this run's outputs are in `evidence.json`. Key values:

| Artifact | SHA-256 |
|---|---|
| `docs/v2-m3-run-protocol.json` | `9e0d82028011f83e0cf6ddaef5f5e118591158d8a557f6698c82c150d5a69bab` |
| `docs/teacher-qualification-v1.json` | `120fbb085235f4be2b88c18f2b8ae57cd520718e2f19333fbdac3a2bbd564634` |
| `docs/teacher-qualification-v2.json` | `e091f8a2fad0a307d289a6d306112606b15df8f8aa0f3a75707ac7cfb2cee803` |
| `docs/teacher-qualification-v3.json` | `bfcbee1609cec0180495c957cf4b5e0b31356f395e2a706217cc9225647d23ae` |
| `python/dodge_rl/dev_eval.py` | `eecf71936f10938169c0283ed1bb0717b87e46da7ee4ac8636a20d366df3753b` |
| `python/dodge_rl/ppo.py` | `abf25f327f9ff749a8a32de4edb07705f12ebcdc5cd0eba8775ad4f693eff1d5` |
| `python/dodge_rl/identity.py` | `50775b2e7c30e53757dd3134d11613f716733cee8e6a96cc18b62e8ff2a4a053` |
| `crates/dodge-rl-env/src/seed.rs` | `239cb9d88a61fff7d63c3c13c80e4552caafe814729160f8fb2948d3c1498832` |
| `learning/runs/v2/latest-best-paired-eval-prepare-luna-20261026-r6/paired_eval.py` | `51b78e6e74dcbaf3d9b04302d6f9ea1e37ea92779e9d237c48dd03ec77946475` |
| `D2-retained324-paired-LR-study-design-haiku-20261026-r1/plan.json` | `7781a5f79f96e55af55b0b1aa1f8c8df7a9fd19dc967c3613e1abbb034bf242c` |
| `D2-retained324-continuation-prepare-luna-20261026-r2/registration.json` | `44ac8185b24de2d98cc1c870191f18be47734b5cc11c7c6ff91b9feacb34cd5a` (matches proposal) |
| `milestone0-campaign-r2/native-results/baselines/episodes.jsonl` | `40b5a8a1614a304bfd041dcd6eedfd7e68262f60fbca5cf6acfc1ece9a2694b3` (equals qualification v2 D2 baseline `episodes_sha256`) |
| `exact-upper-scan-learning.tsv` (this run) | `451b3004d6a3b9eac380f574afd8a96734df33c51d75c9a95405c5ba24550d0b` |
| `dev-eval-seed-classes.tsv` (this run) | `1aa09a32d1a5484be544d16f8087b1a0eede61c03c5fdca266cbf19b9f62e257` |
| `scripts/exact_upper_scan.py` (this run) | `a8c7818ac891f61921578106a9217a4dd886869001655a732fdd275cfb658e69` |
