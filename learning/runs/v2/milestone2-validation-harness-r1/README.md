# M2 validation harness, revision 1

This is a prepared campaign harness, not an executed M2 validation result. No native simulation, installed-extension operation, memory campaign, or throughput campaign was run during drafting. The Rust module remains an uncompiled template outside the crate. The binding implementation owns the live crate and Python package; this task changed neither.

The runner is `learning/scripts/v2_validate_environment.py`. The registered [plan](campaign-plan.json) fixes a single 1,800-second campaign and a 600-second receipt reserve before 13:00 UTC. Its stages run in order and stop on the first failure:

| Stage | Wall guard | Work |
| --- | ---: | --- |
| Native parity | 900 s | 1,000 original heuristic episodes at each of D2 and D3; exact score, alive/raw frames, death/cap reason, Death-event multiplicity and final fingerprint; full/headless state equality after every raw frame |
| Python trajectory | 120 s | Thread/chunk pairs 1/1 and 4/3, optional pixels/targets, owned-return mutation checks, explicit resets, default-cap death case and cap-17 ragged truncation case |
| Python memory | 600 s | B=8, four threads, chunk 2, rendered pixels and targets, 5,000 warmup step calls followed by 100,000 measured step calls |
| Public API throughput | 120 s | B=32, 200 warmup calls and 2,000 measured calls for each combination of headless/rendered and thread/chunk 1/1 or 4/8 |

The stage guards sum to 1,740 seconds. The total campaign guard is authoritative and also covers identity checks, result parsing, worker startup and summaries. Each worker has a sampled 6 GiB RSS guard; native/Python worker RSS is sampled every 0.5 seconds. Python workers additionally report their observed `ru_maxrss`, with macOS bytes distinguished from Linux KiB. Guards are cooperative and do not prove an unsampled allocation stayed below the ceiling. The runner never changes the orchestration ledger or scheduler.

## Native template integration

Wait until the binding child finishes. Only the parent should copy and register these files:

1. Copy `qualification_replay_tests.rs` to `crates/dodge-rl-env/src/qualification_replay_tests.rs`.
2. Copy `qualification_expected.rs` to `crates/dodge-rl-env/tests/support/qualification_expected.rs`.
3. Add `#[cfg(test)] mod qualification_replay_tests;` to the crate root.
4. Run relevant normal tests, formatting and Clippy on the integrated source, then compile the release test binary without executing the ignored parity test.

The template reuses the byte-identical `tests/support/m0_policy.rs`; it does not reimplement the policy. Including that module also compiles its existing helper tests under a second module path. Report those repetitions separately from new test coverage. The ignored test is named `qualification_replay_tests::frozen_m0_full_heuristic_d2_d3`.

The generated table contains exactly 1,000 rows for `nearest_lethal_aabb_safe_powerup` at each difficulty, ordered by `episode_index` and paired seed `0xB0000000+i`. The generator verified original D2 and D3 JSONL SHA256s and configuration/startup/completion fields before generation. Its [receipt](expected-generation.json) records the generated file hash. Random and neutral rows are excluded. Expected-table generation ran once and performed no native work.

The native test performs the same bounded four-frame queue comparison as the accepted small replay. It holds at most four validation-only `FullState` values, compares every field except the intentional `physical_screen` difference, updates the exact frozen policy after every raw frame, and checks each original final fingerprint. Aggregate pattern-frame counts are recomputed and compared with the original records by the Python parser. Validation snapshots and heuristic work never enter production throughput measurements.

A suitable parent build command is:

```sh
cargo +1.97.1 test --release --locked -p dodge-rl-env --no-default-features --lib --no-run --message-format=json
```

Retain its complete output and exact source/build receipt. Select the actual test `executable` from Cargo's compiler-artifact JSON; do not guess a stale path. A compile-only command is not a passed native campaign. The template has been formatted with `rustfmt --config skip_children=true` because its relative policy module path is valid only after integration.

## Identity, review and lease

After integration, binding verification, and a real build, freeze the installed runtime and native test binary using the isolated venv:

```sh
python/.venv/bin/python learning/scripts/v2_validate_environment.py freeze \
  --native-test-binary /absolute/path/to/compiled-test-binary \
  --build-receipt /absolute/path/to/retained-build-receipt \
  --output /absolute/path/to/new-frozen-identity.json
```

The identity includes all Rust and Python sources, including untracked source files, Cargo locks/config/toolchain, cartridge asset, relevant contracts, harness/template inputs, the actual installed extension path/hash, interpreter, NumPy version, hardware, native test binary and supplied build receipt. The parent must reconcile build provenance; an inventory alone does not establish that a binary was built from those sources. Freezing imports the binding but constructs no game environment. Source and binary identities are rechecked before each stage and after the campaign.

Obtain a read-only review of the integrated sources and frozen identity. The parent must then register exactly one `active_long_campaign` lease in `state.json`, without replacing another owner:

```json
{
  "run_id": "v2-m2-validation-20261024-r1",
  "identity_sha256": "SHA256_OF_FROZEN_IDENTITY_FILE",
  "kind": "M2_validation",
  "authorization": "frozen_reviewed_M2_campaign"
}
```

Use atomic ledger writes while the runner is checking its lease. Missing, changed or unreadable ownership fails closed. The runner neither acquires nor clears that lease. Launch once into a new output directory:

```sh
python/.venv/bin/python learning/scripts/v2_validate_environment.py campaign \
  --identity /absolute/path/to/new-frozen-identity.json \
  --run-id v2-m2-validation-20261024-r1 \
  --output /absolute/path/to/new-campaign-directory
```

Every output uses exclusive creation. Each subprocess gets its own recorded process group. On failure or wall/RSS/cutoff expiry, only the active owned group receives TERM and, if needed, KILL. Raw logs, partial episode/sample streams, process receipts, failure details and artifact hashes remain. There is no automatic retry or limit relaxation. If parsing an already-completed native log needs investigation, `audit-native --log ... --output NEW_FILE` reads that evidence without rerunning simulation.

## Memory and throughput interpretation

The memory workload uses generated training seeds with B, D and E reservations enforced before construction, then independently audits actual seed metadata. It explicitly resets ended slots. Step rewards and episode objectives are checked against exact fixed score and alive/death counts. Initial and reset seed metadata and completed episodes are streamed; the loop retains only fixed-size old-output sentinels and 101 RSS samples.

RSS samples cover the warmup boundary and every 1,000 measured step calls through 100,000. The predeclared plateau criterion is last-decile median RSS minus first-decile median RSS at most 64 MiB; each decile contains `ceil(0.1 * sample_count)` samples. OLS growth is reported as a diagnostic. This is an empirical allocator plateau under a fixed workload, not proof of zero leaks. Random short episodes exercise allocation/reset behavior; long mature-pattern coverage comes from native heuristic parity. Both step-call and actual raw-frame counts are reported.

Throughput uses an identical frozen action matrix and identical actual seed assignment sequence across the four configurations. Exact actual seed assignments are written after timing; their hashes and a limited work checksum must agree. Wall rates include the public Python step/reset API, featurization, output arrays and limited checksum/count bookkeeping. Construction and warmup are excluded. Fixed-work timing has an additional 60-second guard per configuration, inside the 120-second stage guard. These measurements do not establish a causal speedup against a historical engine benchmark with another workload.

## Draft verification and limits

Nine pure Python tests pass under the target Python environment with warnings treated as errors. They check cutoff arithmetic, exact lease identity, exclusive outputs, plateau acceptance/rejection, complete 2,000-row synthetic receipt parsing, censoring, and rejection of wrong/missing/duplicate scores, survival, caps, Death counts, fingerprints, pattern coverage and totals. Synthetic fixtures are assembled from original retained records; they are not native replays.

Python syntax checks and standalone Rust-template formatting pass. An initial rustfmt module-resolution failure and an initial passing parser-test log with resource warnings are retained in [failure-ledger.json](failure-ledger.json). Baseline file handles were closed explicitly; final pure tests pass with `-W error`. No native simulation was retried.

Pending evidence is explicit: Rust template compilation, binding/API integration, actual subprocess/RSS guard behavior, native full parity, Python thread/chunk behavior, 100,000 measured memory calls and throughput. No M2 runtime, teacher learning or teacher qualification claim follows from this draft.
