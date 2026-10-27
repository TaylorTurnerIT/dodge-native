# Native build repair

Preparation complete: 12 focused Rust tests and 6 CPU binding tests pass. The owned extension links and imports with project Python3.12.15. These results do not qualify a runtime or authorize launch.

Only this successor contains writes. R1's failed link and all 4155 files in its freeze manifest were verified unchanged. Core and the retained dependency lock are unchanged. The exact [R1 diff](r1-to-r2.diff) adds an explicit H<18000 guard, stronger test-only history inspection and two native tests; [original-to-successor diff](original-to-r2.diff) includes the inherited API. Both patches reconstruct the source exactly.

The API validates the whole request before changing only selected truncated flags. It requires equal-length strict integer inputs and unique in-range alive/non-ended K4 slots at the exact aligned horizon. Horizons must be positive multiples of 1000, below 18000 and the configured cap. Ended slots reject the whole request. Owned EpisodeInfo follows request order. Existing step/reward/death, history/observation, counters/seeds, reset, poison and overflow/exhaustion behavior is preserved. [Source review](review.md) records evidence and limits.

Build invocation, from owned `source/`, with all environment overrides captured in [build record](logs/extension-build-final.json):

```sh
/Users/taylor/.rustup/toolchains/1.97.1-aarch64-apple-darwin/bin/cargo rustc --locked --offline -p dodge-rl-env --lib --features extension-module -- -C link-arg=-undefined -C link-arg=dynamic_lookup
```

`PYO3_PYTHON` is `/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/python/.venv/bin/python3.12`; that invocation reports 3.12.15 and retains the project venv. No executable named `python3.12.15` exists there. CARGO_HOME, target and TMP are successor-owned. Only source and copied immutable offline registry inputs were reused. Link flags apply only to this Cargo invocation; no configuration or runtime installation changed. Ancestor Cargo configuration includes the existing `/usr/bin/nice` rustc wrapper; its exact contents are recorded in the host manifest. The staged binary is a dev/debug artifact, not an accepted release runtime.

- Final extension: `extension/final/_native.cpython-312-darwin.so`, SHA256 `29d49a1317ebe1367932e88514f744242a8e67cf7e6d7d0ab64d5f008cbed567`.
- R1 diff SHA256 `9cd5fc5972e337cb56c5c3bc5b4ed8dd8aa256d134e558b251ac2cc747da45ef`.
- Cargo.lock SHA256 `f1c145a16d4cad6689b59e92fc7850f8ea2194d1d58266a81de2c630b2b58db9`.
- [Source manifest](source-manifest.json), [dependency manifest](dependency-manifest.json), [binary/interpreter manifest](extension/final/manifest.json), [host manifest](host-manifest.json), [command logs](logs/), [receipt](receipt.json), [freeze manifest](freeze-manifest.json).

[Rust tests](logs/native-practice-final.log) run without Python features. They cover H1000/H2000, ordinary18000, exact boundary deaths, mixed slots, whole-request atomicity, history/final buffers, rewards/counters, one reset, poison, overflow/exhaustion and thread/chunk invariance. [Binding tests](logs/binding-first.log) import only the explicit owned extension, reject bool/float/overflow/negative/dtype/dimension/duplicate inputs, and verify live H1000 order/ownership plus ordinary-cap output ownership. They use only fixed synthetic seeds; no Torch/MPS is imported.

One successor setup failure is preserved in [first-failure log](logs/setup-first-failure.log): an already-created scripts directory caused FileExistsError after copying. Recovery verified copied hashes and completed setup. Both Rust test runs and both extension builds succeeded; the initial pre-ceiling binary is retained under `extension/initial/` and was never imported. Its source manifest was corrected to the actual pre-edit baseline after staging. All build/test/check subprocesses have captured 300-second process-group deadlines. Initial setup ran directly and its failure log is a labeled transcript of the tool result.

Remaining parent gates: accepted-binary disabled-cutoff parity; collector synchronization and final-value-before-reset/GAE/rollout boundaries; common successor identity/runtime/evaluator validation; accepted324 restore/reseed references; seed ancestry/reservations; resource/cleanup/one-shot calibration; independent review, registration and acceptance. Current Rust hashes do not establish accepted-binary correspondence. Accepted phase324/cumulative372 remains metadata only; no checkpoint was read. No automatic replacement, study cohort use, B/E opening, training/evaluation campaign, subdelegation, commit or push occurred.
