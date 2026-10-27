# M2 PyO3 binding and seed reservations, revision 1

Implementation is complete in the shared checkout and ready for independent parent audit. This is not full M2 acceptance. The long memory/throughput campaign and full 1,000 paired heuristic episodes at each of D2 and D3 were not run here. No teacher, student, checkpoint, provider retry, child agent, commit, PR, deployment, or external message was created.

## Source and binary identity

`input-manifest.json` and `inputs.tar.gz` freeze the accepted inputs before source edits. The acceptance receipt matches `38dd2aadf8d6a78e5e9511957157356baea125dcb69e2e9293de3ccbb7648319`. Accepted `features.rs` remains `78d72ee29fdcf2c0828e26d0a4265b50809f4c9899183332a4c48fb326dc006c`; original `src/tests.rs` remains `832d091b775af081e6501973572ead94b27c1bd519ad0199ba75bdece63e8379`.

`owned-source-manifest.json`, `source-manifest.json`, `source-final.tar.gz`, and `owned-changes.patch` identify final sources, including untracked files. The patch compares against this task's input freeze, not Git HEAD. The final archive includes frozen core, geometry, raster, feature, original test/fixture, authority-document, and wrapper-README inputs. `frozen-input-audit.json` verifies unchanged unowned source inputs. Only the orchestration ledger changed externally during work; this task never edited it.

The installed extension is `python/dodge_rl/_native.cpython-312-darwin.so`, imported from the shared checkout through the existing isolated `python/.venv`. Its SHA256 is `967c7249acd52339d1818dcbe94e63ee734aea914c3497eb59a7e945a6e95583`. `binary/` archives that exact file. The wheel in `wheels/` contains byte-identical extension bytes. `installed-identity.json` records absolute import paths, interpreter, package metadata, wheel hashes, Rust toolchain, and lock hash. `rust-locked-packages.json` and `dependency-tree-final.log` retain resolved dependencies. The environment's only engine dependency is `dodge-core`; it does not link the viewer.

The local interpreter is CPython 3.12.15, with NumPy 2.5.4, Torch 2.14.1, pytest 9.1.1, and maturin 1.15.0. Rust is 1.97.1; the binding uses PyO3 0.27.2 and Rust numpy 0.27.1. Torch was not used for model work. `Cargo.lock` SHA256 is `71f583c7fd42558fa9c87e26cf010f40fff131aedf70a0405be21dcb09aa7219`.

## Packaging and API integration

The Rust library name remains `dodge_rl_env`, with `rlib` and `cdylib` outputs. Default Rust features do not include Python. The optional `python` feature adds PyO3/numpy; `extension-module` adds Python support plus PyO3's extension-module linking mode. The crate retains its own lint table.

The mixed Python project lives in `python/pyproject.toml`, exports native module `dodge_rl._native`, and re-exports `dodge_rl.VecDodgeEnv`. Run maturin from `python/` so it discovers that configuration:

```sh
cd /Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/python
VIRTUAL_ENV="$PWD/.venv" PYO3_PYTHON="$PWD/.venv/bin/python" \
  .venv/bin/maturin develop --release --uv --locked
PYO3_PYTHON="$PWD/.venv/bin/python" \
  .venv/bin/maturin build --release --locked \
  --out ../learning/runs/v2/milestone2-binding-r1/wheels
```

Exact executed commands, working directories, source hashes, exit codes, timing, and full output appear in `commands.jsonl` and the associated logs. Installation used only the existing `python/.venv`.

The constructor and all eight requested methods follow the fixed Python API. Observations are flat dictionaries, while step and reset dictionaries contain observations plus their requested scalar arrays and episode information. Reset subsets preserve caller order, including correctly shaped empty arrays. Diagnostics and seeds remain metadata and are never appended to neural features.

Actions accept exactly one-dimensional NumPy `int64` arrays, including strided arrays, or lists/tuples of Python integers. Bool, floats, wrong shapes/dtypes, invalid IDs, and overflowing integers fail visibly. Python sequences of NumPy scalar integers are not accepted; use an `int64` array. Reset indices use the same strict input policy. Complete requests are copied and validated before any slot mutates. Validation errors map to `ValueError` or input conversion errors; poison, seed exhaustion, counter exhaustion, and native/contract failures map to `RuntimeError`. No error path implicitly resets an episode.

Numeric outputs have independent Rust allocations retained by NumPy base owners (`PySliceContainer`). `OWNDATA=False` is expected for these transferred allocations and is not the ownership proof. Tests retain and mutate old arrays across observations, step, reset, and environment destruction, compare fresh engine output against a separate environment, and check `np.shares_memory`.

`batch_info()` exposes all constructor configuration, schema/reward/admission/motion/seed versions, fixed theme and initial highscores, explicit evaluation lists or full-width run seed, caller-provided additional exclusions, normalized effective exclusions, initial episode indices, and next episode indices. `excluded_seed_ranges` and `effective_excluded_seed_ranges` both report the effective union. `additional_excluded_seed_ranges` preserves the caller's list. `next_episode_indices` contains `None` only when a current episode is `u64::MAX`; resetting then fails before any slot mutates. Metadata is JSON serializable.

## Reservations and fresh-environment continuation

The mandatory inclusive B interval cannot be disabled. Additional intervals are validated, sorted, and merged, including adjacency, without overflowing at `u32::MAX`. A reversed interval or a union covering all u32 values is rejected before game construction. Training retains the original tuple hash and counter rehash, with default `training_seed` outputs unchanged. Exclusions are applied before every `NativeGame::new`, not as a post-run filter. `mandatory_b_plus_inclusive_union_rehash_v1` separately versions the exclusion semantics.

Tests force both inclusive B/D/E edges through the rejection loop, reject a known first candidate without random searching, compare the resulting initial game observations and step against explicit evaluation of its replacement seed, and verify thread/chunk invariance. The parent training caller must still supply D and E: their default additional list is empty.

`initial_episode_indices` defaults to all zero and otherwise contains one u64 per stable slot. Construction consumes those explicit episodes; each reset advances by one. Evaluation indexes the explicit per-slot lists at those indices, permits reserved held-out seeds, and never falls back to the training generator. Nonzero indices support later `fresh_env` learner continuation; no live episode serialization, snapshot injection, or checkpoint loader was added.

## GIL and concurrent access evidence

`src/python.rs` uses `Python::detach` around complete Rust construction/startup, step K loops and Rayon chunks, feature/render work, observation collection, and resets. NumPy input guards are local to the copying helper and are gone before detach. Detached closures capture only Rust-owned data and Rust environment borrows. Python dictionaries and arrays are constructed after reattachment. No Python pointer, NumPy view, or callback enters Rayon.

`gil-proof.json` records bounded runtime witnesses. Each test sets Python's thread switch interval to 60 seconds, wakes a previously blocked witness, and performs one native call without a Python payload loop. The witness must execute strictly inside that call. Constructor, step, reset_all, and reset_done pass. A `ctypes.PyDLL` call holding the GIL fails that same witness condition as expected, providing a negative control. A further witness overwrites caller actions with invalid IDs during step; output still matches the independent environment using the copied original actions.

Concurrent same-environment resets fail immediately with PyO3's borrow error while step/reset holds its exclusive borrow. They neither deadlock nor poison the environment. There is no added mutex. These checks establish bounded CPython GIL-release and ownership behavior; they do not measure speedup or prove free-threaded Python support.

Rust unit-test environments contain existing Send-only raw observer closures. The binding module is excluded only from the crate's `cfg(test)` unit-test artifact, leaving those fixtures unchanged. The normal library is checked with all features by Clippy, and the built extension is exercised by Python tests.

## Executed checks and boundaries

- Default `cargo +1.97.1 test --locked -p dodge-rl-env -- --nocapture --test-threads=1`: 41 unit tests and 35 primitive tests passed; one bounded replay remained ignored; zero doc tests. These are 76 current crate tests, including seven new seed tests. No whole-workspace Rust test run or new core test count is claimed.
- `cargo +1.97.1 fmt --all -- --check`: passed.
- `cargo +1.97.1 clippy --locked --workspace --all-targets --all-features -- -D warnings`: passed.
- Release `maturin develop` and wheel build: passed.
- Real-extension pytest: 68 cases passed. Coverage includes schema/dtypes/padding/finite values/palette, strict whole-request validation, fresh seeds and reservations, explicit evaluation exhaustion, initial counter continuation and overflow, ragged caps/bootstrap, real death/terminal feature versus retained pixel behavior, requested subset alignment, ownership, thread/chunk trajectories, reward identity, GIL release, concurrent borrow safety, and input copying.

The unchanged Rust fixtures executed here cover hidden-field invariance, literal offscreen geometry, poison recovery, positive score on the death frame, repeated native death events, and death on the cap frame. No production hidden-state or restore interface was introduced to expose those fixtures to Python. Python's real neutral death trajectory checks one death penalty and reward accounting, but does not claim a positive death-frame pickup occurred in that trajectory.

`failure-ledger.json` retains the packaging configuration warning, corrected test assumption, all-feature unit-test Sync conflict, dynamic-ledger audit assertion, and freeze receipt assertion. Full failed logs remain. Intermediate extension binaries from early develop attempts were overwritten before independent binary hashes/archives were captured. Their source hashes and logs remain; final installed binary and matching wheel are archived. The first complete freeze, before comment-only ownership wording corrections, is also retained in `pre-comment-correction/`.

Independent parent Codex review remains required before the parent freezes this binding together with its separate validation harness and starts one bounded campaign. No leak, long-run memory, throughput, full baseline parity, PPO performance, or teacher qualification claim follows from these tests.
