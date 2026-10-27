# Native practice cutoff preparation

Source preparation only; frozen with a failed binding link and unrun unit tests. No qualification, registration or launch authority.

`source/` contains isolated copies of `dodge-core`, `dodge-rl-env`, cartridge/build inputs and Cargo files. `originals/` preserves exact input bytes. Only the owned environment crate adds behavior; the core is unchanged. The reduced workspace removes runner/viewer members; Cargo prunes their unused lock entries without changing retained package versions/checksums. No collector, PPO, LR, reward, GAE, step loop, observation schema or `EpisodeInfo` schema changes.

## Exact API

Rust: `VecDodgeEnv::truncate_practice(&mut self, indices: &[usize], horizons: &[u32]) -> Result<Vec<EpisodeInfo>, EnvError>`.

Python native class: `VecDodgeEnv.truncate_practice(indices, horizons) -> list[dict]`, using the existing owned `EpisodeInfo` serialization and strict `integer_input` parser. Accept one-dimensional NumPy `int64` arrays or Python integer lists/tuples. Reject booleans, floats, unsupported arrays, integer overflow and negative values without wrapping. Both inputs are copied and checked before detached native work.

The whole request validates before mutation: equal lengths; unique in-range slots; alive `Mode::Game`, neither terminated nor truncated; positive 1000-multiple horizon below the configured ordinary cap; `action_repeat == 4`; exact, aligned `gameplay_frames == horizon`; and no episode-index increment overflow. The experiment's ordinary cap remains 18000. Explicit death/cap-ended slots reject the whole request. Empty requests return an empty list for an unpoisoned K4 environment. Poison always rejects without clearing diagnostics. The operation does not reserve the next seed; normal reset retains its seed-exhaustion validation.

Success changes only each selected slot's `truncated` flag to true. `terminated` remains false by validation. No stepping, reward or death penalty, counters, seed/index, native state, observation, history or death diagnostics change. Returned independent snapshots follow request order and equal the selected `episode_info()` rows. They contain no observation payload or curriculum metadata. H18000 uses the existing ordinary cap and requires no practice call.

Parent collector must exclude already ended slots; replace only selected retained result truncation flags and info with native returns before audit/storage/bootstrap; preserve final observations, rewards and step counts; then perform one normal subset reset in ascending slot order. No Python-only boundary, `reset_all`, arbitrary timer or production force-death API was added.

## Evidence and stop

- Design experiment/scheduler hashes match the supplied exact pins. Accepted phase324/cumulative372 checkpoint SHA `c10d90ec0e67503afef8f4d90c4968581d430ef2065117a75e81c445a04c8ddc` is supplied/design metadata only; the checkpoint was never read.
- Rustfmt completed. Offline `cargo build --lib --features extension-module` stopped after 9.177 seconds, exit101: ``error: linking with `cc` failed: exit status: 1``; undefined CPython symbols including `_PyBaseObject_Type`; `ld: symbol(s) not found for architecture arm64`. No retry, installation or native import occurred. See [build log](logs/binding-build.log) and [check results](check-results.json).
- Direct Cargo did not supply macOS extension dynamic-lookup linker arguments. Existing Python packaging uses maturin. Parent must establish and pin a working successor build invocation in a new preparation; no linker fix or second attempt was made here. The probe used installed Python3.11 for PyO3 build configuration; existing package metadata requires Python>=3.12. This is not accepted-runtime identity evidence.
- Ten focused Rust CPU tests were authored but never compiled or run because the binding build failed first. They cover H1000/H2000, ordinary18000, mixed death/cutoff/continuing slots, whole-request errors, owned final buffers, history diagnostics, reward/count preservation, one reset increment, poison, overflow/exhaustion, and thread/chunk layouts. Synthetic snapshot fixtures remove spawn points and inject moving enemies using existing test-only wire machinery. Exact H-1/H/H+1 death tests are planned at both horizons. No simulation executed in this lane.
- [Python binding tests](binding_tests_pending.py) were authored and AST-checked only; they require explicit parent opt-in before importing an extension or constructing Python environments.
- Initial system Python3.9 setup lacked `tomllib` and stopped before writes; installed Python3.11 resolved script preparation without installation. Both failures are preserved.

[Source manifest](source-manifest.json), [exact diff](exact.diff), [receipt](receipt.json) and [freeze manifest](freeze-manifest.json) record hashes and limits. Before/after coverage applies to listed inputs, not a concurrent whole-workspace audit. Cache, temporary files and failed build products remain inside this successor and are retained read-only.

## Remaining parent gates

1. Build/link the exact successor and run the ten native tests, strict Python binding tests and final-observation/history/death parity checks. No unit test pass is claimed here.
2. Integrate collector synchronization and final-value-before-reset ordering; validate inherited bootstrap/GAE masks, decision256/cross-rollout boundaries and no abandoned transitions. Keep scheduler assignment metadata external.
3. Prove disabled-cutoff parity against the accepted runtime on pinned synthetic seeds/actions. Current Rust input hashes do not prove correspondence to the accepted binary. Pin one new binary/runtime/config/evaluator for both arms, with only curriculum enablement differing; complete successor identity/member/evaluator validation without weakening frozen validators.
4. Complete authenticated accepted324 restore/reseed references, full seed ancestry/exclusions and reservations, resource calibration, cleanup, one-shot controls, independent review and registration before any launch. Preserve B/E unopened. No real checkpoint reads/deserialization, study seeds, MPS, training/evaluation campaign, subdelegation or launch occurred here.
