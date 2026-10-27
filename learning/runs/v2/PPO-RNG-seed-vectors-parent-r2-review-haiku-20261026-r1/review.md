# PPO RNG seed vectors parent r2: source-only review

Reviewer: Haiku 5.5 review sub-agent. Scope: static source review only.
Owned output: this directory. No edits outside it.

## Verdict

No blocking findings in the r2 artifacts for the arithmetic, domain separation, uint32 bounds, or receipt/metadata consistency that were checked.

Three findings should be resolved before any reseed helper or runner binding is written: F1 (reseed order), F2 (LR origin wording), F3 (master-seed provenance). Remaining findings are low severity.

## Scope and limits

- No Python import or execution of `stdlibderive.py`. The parent's `controls.log` (`OK: committed seed-vectors file matches stdlib derivation`) is parent-reported and was not re-run here.
- Spot-checked token digests with `shasum` (not reviewed code). Did not independently recompute the SplitMix env seeds (no execution; no shell 64-bit XOR/unsigned shift).
- Rust formula is read from source. No binary binding is established.
- The torch seeding claim is read from the vendored `python/.venv/.../torch/random.py`. Pinned torch version not separately confirmed.
- No CPU or MPS RNG, no native build, no checkpoint load, no training, no lease or marker access.

## Verified (no finding)

1. Hashes of reviewed files match the receipt `files` block: `stdlibderive.py` 5cb2bb8c…, `seed-vectors.json` 00880af0…, `controls.log` c663962a…. `receipt.json` is the review target and is not self-hashed.
2. Predecessor manifest hashes match the predecessor files: `report.md` 6faaa142…, `inventory.json` 80690d87…, `seed-vectors.json` bcafb9f9…, `stdlibderive.py` bbe6ff0f….
3. Parent receipt sha256 is `cb3645899b5cb660d26d44645e00b3f53c5d0c8341b645b3b78af6b651d8b016`. `next_episode_indices` (receipt line 210) equals the 64 hardcoded `PARENT_NEXT_EPISODE_INDICES` in `stdlibderive.py:74-83` exactly (0 positional diffs). Predecessor list differs in 53 positions, matching the parent's claim.
4. Constructor seeds in `receipt.json:10-12` equal `seed-vectors.json` constructor values for replicas 1-3 (3917617846, 926977497, 16489749). All are in [1, 2^32-1].
5. Token arithmetic spot-check, replica 1, attempt 0. Message `D2-LAYERB-RNG-VECTOR-V1|study=expanded-D2-training-replication-layerb-20261026-r1|replica=1|stream=<name>|attempt=0`:
   - `constructor_init_seed`: digest prefix `e9821ab6…` = 3917617846 (matches).
   - `numpy_global_seed`: digest prefix `a5c394be…` = 2781058238 (matches).
   - `torch_cpu_global_seed`: digest prefix `c652f032f981e1d1`; masked to 2^63-1 gives `4652f032f981e1d1` = 5067376632470299089 (matches).
   Domain separation includes stream name and replica, so streams are distinct in token space.
6. Env derivation matches the Rust source by reading. `stdlibderive.py:144-153` (mix, base, counter, upper 32 bits) equals `crates/dodge-rl-env/src/seed.rs:77-82` (`base` and `to_be_bytes()[0..4]`) and the `reject_ranges` loop. Mix constants and rotation match. Slot and episode offsets match.
7. Reserved ranges match the protocol. `docs/v2-m3-run-protocol.json:108-` lists B, D128, E (3 ranges); stdlib adds D1_new and D2_new, as the docstring states. Mandatory B in Rust (`seed.rs:4`) equals stdlib B.
8. Stream ownership, as read from pinned and current source:
   - MPS: `ppo.py:312` `policy.sample()`, the only action draw.
   - CPU: `ppo.py:472` (current) / `474` (pinned) `torch.randperm(count, device="cpu")` once per epoch; `models/teacher.py:109` orthogonal init.
   - Dropout is 0.0 (`models/teacher.py:46,198`).
   - `random` and `np.random` are only seeded, read, and restored (`train_teacher.py:69-70`, `checkpoints.py:24-35`). No draws.
   - `restore_rng` fails closed on backend mismatch (`checkpoints.py:33`).
   - `make_state` passes no NumPy generator (`checkpoints.py:78`), so the "no owned NumPy generator" claim holds.
   - Rust env has no RNG crate use in `dodge-rl-env` beyond SplitMix (`seed.rs`).
9. Pinned runtime hashes: `seed.rs`, `dodge-core/src/rng.rs`, `checkpoints.py`, `train_teacher.py`, `models/teacher.py` match inventory pins. `ppo.py` differs (pinned `b3cef91b…`, current `abf25f32…`). RNG-relevant lines have the same content, shifted by 1-2 lines (see F5).
10. Bounds: `validate()` and `STREAM_BOUNDS` match the field rule text. `numpy_global_seed` 0..2^32-1; `constructor_init_seed` 1..2^32-1. Derivation widths (4 vs 8 bytes) match `stdlibderive.py:117`.

## Findings

### F1 (medium): CPU-then-MPS reseed order is absent; silent MPS overwrite if reversed

- Where: `PPO-RNG-stream-inventory-deepseek-free-20261026-r1/report.md:9` (reseed order) and `seed-vectors.json` `controls_pending_runtime` (lines 487-493).
- Fact: pinned torch `torch/random.py:62-72` `_manual_seed_impl` calls `torch.mps.manual_seed(seed)` as well as CPU. So `torch.manual_seed(torch_cpu_global_seed)` overwrites MPS. `torch.mps.manual_seed(action_sampler_torch_mps_seed)` must run after it.
- Trigger: a future reseed helper calls `torch.mps.manual_seed` first, then `torch.manual_seed`. Or it calls `torch.manual_seed` after the MPS seed.
- Consequence: `action_sampler_torch_mps_seed` silently becomes `torch_cpu_global_seed` on MPS. Vectors still pass bounds. `controls_pending_runtime` captures fingerprints but states no expected post-reseed MPS value, so it would not catch this.
- Fix: state the order (CPU, then MPS) in `report.md:9`. Add an expected post-reseed MPS state fingerprint, or a read-back assertion, to `controls_pending_runtime`.

### F2 (low): "396-origin controller" misstates the LR schedule origin

- Where: `report.md:9`.
- Fact: receipt `origin_cumulative_update` is 372 (`retained-best-candidate-receipt.json:179,322,335`). Decoded helper `ORIGIN_CUMULATIVE_UPDATE = 372`. 396 is `actual_cumulative_updates` (receipt lines 16, 42; inventory `parent_context`).
- Consequence: a runner author who follows the text and sets origin 396 shifts the LR schedule by 24 updates. The helper hardcodes 372, so literal wiring would not do this, but the text misleads.
- Fix: change to "372-origin schedule, applied at actual cumulative update 396".

### F3 (low/medium): Master-seed provenance inconsistent in the parent receipt; rejection list incomplete

- Where: parent receipt `retained-best-candidate-receipt.json:145` (`identity.config.phase_settings.run_seed` = 5562881586070242562) versus lines 194 and 308 (`run_seed` = 4200000001). `stdlibderive.py:68` `PRIOR_MASTER_SEEDS` omits 5562881586070242562.
- Fact: 5562881586070242562 appears in earlier D2 artifacts (`learning/runs/v2/milestone3-D2-execution-r1/*`, `D2-retained276-lr3em5-prepare-luna-20261026-r2/registration.json`, `postovernight-long-D2-campaign-r2/long-identity.json`). `identity.py:216` requires `seed_mode.run_seed == config.phase_settings.run_seed`, so the receipt's two values cannot both be live for the accepted run.
- Current status: none of the three derived `env_master_seed` values equals 5562881586070242562 (6341453824149129831, 12312454464013200898, 12504964076835590278). No collision now.
- Trigger: the same master seed is reused later, or the parent's env actually used 5562881586070242562.
- Consequence: episode seeds repeat an earlier campaign with no rejection.
- Fix: add 5562881586070242562 to `PRIOR_MASTER_SEEDS`. Record which master seed the accepted 348 episodes used, and why the config block differs.

### F4 (low): Env control has no counters and is computed under an uninstalled union

- Where: `stdlibderive.py:182-200`; `seed-vectors.json` `env_control` blocks.
- Fact: env control uses the 5-range union (B, D128, E, D1_new, D2_new). Installed runtime union is B, D128, E (receipt `excluded_seed_ranges` lines 123-131). Counters are not recorded.
- Consequence: runtime and control agree unless a candidate in D1_new or D2_new precedes the selected one. Per-candidate chance is about (1024+2048)/2^32, roughly 1e-6. The mismatch cannot be checked from the artifact as written.
- Fix: record per-slot counters. Recompute against the installed union at launch.

### F5 (low): Citation drift in report

- `report.md:5` cites `ppo.py 474` for randperm. That is the pinned copy; the current `python/dodge_rl/ppo.py` line is 472. The report does not say which copy.
- `report.md:7` cites `seed.rs 122-123` for the SplitMix base. Base is `seed.rs:77`. Lines 122-123 are inside `seed_for`.
- Fix: cite pinned path plus hash, or update lines to current.

### F6 (low): Silent constructor-seed default at the binding point

- Where: `python/dodge_rl/train_teacher.py:448`, `seed_initialization(config["phase_settings"].get("initialization_seed", 0))`.
- Trigger: a runner omits `initialization_seed`. The default 0 is legal for `np.random.seed` but outside the constructor bound (1..2^32-1) in `stdlibderive.py:91`.
- Consequence: all arms silently use seed 0 for constructor init.
- Fix: the binding must assert the key is present and equals the vector constructor value. Do not rely on the default.

### F7 (informational): Master seed checked against episode-seed reserved ranges

- Where: `stdlibderive.py:127` applies `in_reserved` to `env_master_seed`. Reserved ranges are episode-seed (32-bit) space (`seed.rs`, `env_actual_seed`). Rust's master-seed space is u64 with no such exclusion.
- Consequence: harmless over-restriction. The rationale in the docstring (lines 19-20) is slightly wrong.

## Hashes reviewed

| File | sha256 |
|---|---|
| `PPO-RNG-seed-vectors-parent-20261026-r2/stdlibderive.py` | 5cb2bb8c0031c3a39703348dcefbb8edb38d0adbcc5afbc77a3b0923e3f869e0 |
| `PPO-RNG-seed-vectors-parent-20261026-r2/seed-vectors.json` | 00880af03f64aace8507295bf6a44587a6f34a1dee082609194a201d22dc3767 |
| `PPO-RNG-seed-vectors-parent-20261026-r2/receipt.json` | ffb53bfd66abeb33a01430daa3e9e34585c88ab0c3b305dc022973df0cb9c51d |
| `PPO-RNG-seed-vectors-parent-20261026-r2/controls.log` | c663962a92627605aa4df802bd19d1f06e6e543e9b38130fdc7ae9fcdd223ae4 |
| `PPO-RNG-stream-inventory-deepseek-free-20261026-r1/report.md` | 6faaa14226a3979b8c03bcdd915d3e9769ea57ce0b1c0ff13e9310dcb3df05d1 |
| `PPO-RNG-stream-inventory-deepseek-free-20261026-r1/inventory.json` | 80690d878bb29a32866a29ebce03751f0dcb6837f773820e13ef74fc5a2dae2c |
| `PPO-RNG-stream-inventory-deepseek-free-20261026-r1/seed-vectors.json` | bcafb9f932ca2b63b5c6189f2a7d07b1c4c360c70afc519906ba4bf2258342b5 |
| `PPO-RNG-stream-inventory-deepseek-free-20261026-r1/stdlibderive.py` | bbe6ff0f002ba8f007c5c23abb4edf2c3d56ccbc835ccc43acda3452f773fe01 |
| `PPO-RNG-stream-inventory-deepseek-free-20261026-r1/manifest.json` | (not hashed; its listed hashes match the four files above) |
| `D2-retained324-linear-parent-terminal-audit-20261026-r1/retained-best-candidate-receipt.json` | cb3645899b5cb660d26d44645e00b3f53c5d0c8341b645b3b78af6b651d8b016 |
| `crates/dodge-rl-env/src/seed.rs` | 239cb9d88a61fff7d63c3c13c80e4552caafe814729160f8fb2948d3c1498832 |
| `crates/dodge-core/src/rng.rs` | 6e5bfcf9d241332fcae2357f5dd420829ed8e8d19330803a5062c817a771b050 |
| `python/dodge_rl/ppo.py` (current) | abf25f327f9ff749a8a32de4edb07705f12ebcdc5cd0eba8775ad4f693eff1d5 |
| `learning/runs/v2/D2-gradient-capsule-parent-freeze-20261025-r5/own/runtime/dodge_rl/ppo.py` (pinned) | b3cef91b1293056e9d1820a94fd5730accae4c5728d23566857a6c3a0e1eeac5 |
| `python/dodge_rl/checkpoints.py` | 807141943a742c6e9fdd34274c191b3c318134cc7fb0c1c6256874cadee1cbc3 |
| `python/dodge_rl/train_teacher.py` | 1d134bfb221ff52139e1243c9e4f9c3063432942a3274c567b71db4d7669c0cf |
| `python/dodge_rl/models/teacher.py` | e4d7f597a2824c2b0d4ba261dddc9d7d1ee1d5592c2fc966a44c54b5ec417e35 |
| `python/.venv/lib/python3.12/site-packages/torch/random.py` | 0b2bd65c8fdf324e00ed2c64e7b06ca5d5ff96053001055c86352c0b3668d0be |
| `docs/v2-m3-run-protocol.json` | 9e0d82028011f83e0cf6ddaef5f5e118591158d8a557f6698c82c150d5a69bab |

## Authority

Source review only. This review grants no seed reservation, no launch authority, and no training authority. The vectors remain proposed.
