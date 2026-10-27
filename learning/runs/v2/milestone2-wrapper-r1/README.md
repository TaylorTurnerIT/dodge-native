# M2 pure Rust vectorized environment, wrapper revision 1

The implementation is frozen for independent parent review before Python binding work. All source changes are confined to `crates/dodge-rl-env`, root workspace member registration, and `Cargo.lock`. Evidence is retained here. Accepted core and math sources, the promoted primitive fixture, and the frozen M0 policy remain byte-identical to the pinned inputs.

## Public Rust API

`VecDodgeEnv::new(EnvConfig) -> Result<VecDodgeEnv, EnvError>` constructs fresh games and completes bounded startup. Read initial owned data with `observations()`. Construction consumes episode zero; calling `reset_all()` starts the next episode.

- `step(&[i64]) -> Result<StepBatch, EnvError>` accepts exactly B IDs in `Action::ALL` order. It validates the complete request before mutation, executes up to K raw gameplay frames per slot, and returns final observations without an automatic reset.
- `reset_done(&[usize]) -> Result<ResetBatch, EnvError>` requires unique, in-range, ended slots and validates the complete request first. Returned rows follow the requested index order. An empty request returns an empty subset.
- `reset_all() -> Result<ResetBatch, EnvError>` starts fresh episodes for all slots. Only a successful full reset clears poison. Failed seed preflight mutates no slots; failed initialization after mutation retains partial state and consumes the attempted episode.
- `batch_info() -> BatchInfo` returns B, K, raw cap, thread/chunk configuration, curriculum flags, seed mode, motion/seed versions, fixed theme 12/1, and zero initial highscores. Callers should retain this metadata with a run.
- `episode_info()`, `is_poisoned()`, and `last_failures()` expose diagnostics after a failed parallel call. Observation data is unavailable while poisoned. An error does not imply rollback.

`EnvConfig` defaults: B=1, K=4, difficulty=2, patterns/powerups enabled, cap=18,000 raw gameplay frames, one pool thread, chunk size eight, no pixels or auxiliary targets, training run seed zero. B, cap, threads and chunk size must be positive; K must be 2..=4 and difficulty 1..=3. Values are rejected rather than clamped. Theme and initial highscores are fixed by construction. Startup is one X frame and neutral frames until alive Game, bounded at 64 and asserted to equal 13 for the accepted core. Startup frames do not consume the gameplay cap.

`SeedMode::Training { run_seed: u64 }` uses `dodge_slot_splitmix64_high32_reject_v1`; the exact wrapping tuple hash and upper-32-bit extraction are documented in `src/seed.rs`. Reserved M0 seeds `0xB0000000..=0xB00003E7` are rejected by deterministic counter rehash. Run, stable slot and episode determine the stream independently of Rayon scheduling. Hashing does not promise globally unique u32 outputs. `SeedMode::Evaluation { seeds_by_slot: Vec<Vec<u32>> }` supplies explicit slot/episode lists; exhaustion is an error and never falls back to the training generator. `SeedMetadata` returns actual seed, counter, stable slot, episode and evaluation marker.

`ObservationBatch` owns contiguous, row-major vectors. Its `indices` maps rows to stable slots:

- `global_feats`: f32 `[B,1,14]`.
- `entity_feats`: f32 `[B,80,16]`.
- `entity_types`: i64 `[B,80]`, valid types 1..=8, padding zero.
- `entity_mask`: bool `[B,80]`, true for valid rows. Enemy-family rows occupy 0..64; rectangle rows occupy 64..80.
- Optional `pixels`: u8 `[B,4,128,128]`, oldest to newest, palette indices 0..=15.
- Optional `auxiliary`: f32 `[B,5,16,16]`, channel order lethal_now, lethal_soon, enemy, powerup, player.

The 14/16 feature orders and normalizations match contract revision 2. Geometry uses the accepted literal collision and conservative admission helpers. Motion is current minus immediately preceding raw-frame geometry, retaining half-raw precision. Growth uses the same /4 normalization as center displacement. Unknown history yields zero deltas and separate counters. Stable serial equality/order matching prevents removal/index aliasing. Every executed raw frame updates history; every None-pattern gap clears rectangle history. No hidden targets, lives, sizes, shown flags, timers or serials enter neural arrays.

Admission uses only current footprints at observation boundaries. Coordinates remain unclipped. Borrowed currently drawn warnings can set the visible-pattern flag and lethal-soon target without admitting an offscreen rectangle. Enemy overflow keeps the first 64 by full-precision slab time then opaque serial, and reports drops. More than 16 admitted rectangles is an error that poisons a stepped batch. Auxiliary occupancy includes all admitted geometry, including enemy rows dropped from the token buffer. Inverted collision boxes retain their literal features, paint no occupancy, and increment diagnostics.

`StepBatch` returns f32 rewards, exact i64 fixed-score deltas, executed/alive raw-frame counts, separate terminated/truncated flags, and `EpisodeInfo`. Reward is score delta plus 0.01 per alive raw frame minus five once if terminated. Exact score/count fields and the cumulative f64 objective avoid treating summed f32 rewards as fixed-score identity. Death on the cap frame terminates without truncation; alive truncation bootstraps.

Pixels render only at the initial alive state and alive decision ends. Initial/reset stacks repeat the initial frame four times. A terminal call retains the prior stack, returns actual terminal features and auxiliary geometry, and marks `pixel_valid` and `pixel_aux_pair_valid` false. Alive truncation keeps valid current pixels. Pair validity is also false when either optional member is absent. Returned buffers can be mutated without changing the environment or earlier returns.

The crate links `dodge-core` and Rayon only. Its persistent pool processes stable-slot chunks; it does not use a simulation PRNG tied to an OS worker. The crate owns its lint table (`unsafe_code=allow`, `clippy::all=warn`); production contains no explicit unsafe code. Snapshot/FullState use and observer/error seams compile only under `cfg(test)`.

## Verification

Exact commands, source hashes, timestamps, limits, statuses and complete compiler/native logs are in `commands.jsonl`. Final Rust-source hashes match the successful receipts.

- Normal `cargo +1.97.1 test --locked -p dodge-rl-env -- --nocapture --test-threads=1`: 33 unit tests plus all 35 promoted primitive tests passed; the separate release replay was ignored in this ordinary invocation. The unit count includes eight tests from the unchanged frozen M0 helper.
- `cargo +1.97.1 fmt --all -- --check`: passed.
- `cargo +1.97.1 clippy --workspace --all-targets --all-features -- -D warnings`: passed.
- The one bounded release replay passed: ten original M0 seeds per policy, D2/K4/cap 18,000. Both paths use the exact frozen policy and observe every raw frame. All 69,326 raw frames matched full logical state except physical_screen. All 30 retained original fixed scores, alive counts, death/cap flags and final full-path state hashes matched exactly. Active-pattern coverage was 28,395 frames across 22 catalog IDs. These selected episodes all died; cap behavior is covered by ordinary crate fixtures. See `baseline-replay.json`.
- Supplemental public-API comparison: B=9, 300 decisions, 10,750 raw frames per batch, thread/chunk pairs 1/1 and 4/3. Owned observations, pixels, auxiliary arrays, metadata and 43 explicit ended-slot resets matched. Sixteen seed vectors also matched an independent Python implementation of the documented hash. See `trajectory.json`. This is a correctness check, not a throughput measurement.

Fixtures cover feature orders/types/padding, half-raw growth, stable identities through earlier removal/new birth, powerup size jumps, raw cadence/activation gaps, unknown/charging/fading/full phases, hidden-field invariance, renderer/admission boundary examples, warnings and shadows, overflow selection/error, death with positive score in both pickup orders, repeated same-frame deaths, ragged cap/death batches, request validation without mutation, fresh/reset history, terminal stacks, buffer ownership, poison recovery, and canonical-state thread/chunk invariance.

Three compiler/check attempts failed during implementation: an unstable Option helper, unused test support before the replay was added, and a test-observer type-complexity lint. Their raw logs remain. The supplemental native probe passed on its sole execution; its first result parser assumed the wrong numbered filename. That checker error was repaired by parsing the retained receipt with `--parse-only`, without rerunning simulation. See `failure-ledger.json`.

## Boundaries and integration notes

No PyO3, Python binding, GIL release, NumPy transfer, model, PPO or student work is included. `ObservationBatch` provides owned Rust storage for the later binding. Validate copying Python action IDs before GIL release, conversion into owned arrays, retained-array independence, and the required 100,000-step post-warmup memory check in that stage. No memory, leak, allocation, PPO performance or throughput claim follows from these checks. Snapshot recovery curriculum remains absent.

The prior 86-test core receipt is separate evidence and was not rerun here. Current work checked the accepted seven core hashes and ran workspace Clippy, while executing wrapper/math tests and the new full/vectorized replay. External Pemsa runtime remains unrun. Conservative footprints do not prove general pixel observability; slab/charge forecasts remain estimates. Final capacities retain the parent-accepted D2 decision, with runtime guards; these tests do not prove every future trajectory fits.

No provider retry, nested agent, commit, PR, deployment or external message was made. The parent long-campaign lease was clear before replay; that state is retained. Source and artifacts are ready for independent parent review, not represented as parent acceptance.
