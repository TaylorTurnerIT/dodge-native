# Retained324 linear auditor successor r2

## State

Prepared and frozen in this OWN directory. The Haiku r1 auditor review findings are incorporated. This package has no `audit-binding.json`, no actual audit record, and no launch authority. Final binding awaits the parent-owned review assembly artifact and the parent-supplied expected binding digest.

The user reported no source blockers in the integrated r4 review and directed the parent to handle exact-lease CPU bootstrap and campaign work concurrently. This preparation did not inspect mutable campaign outputs or verify those operations.

## Repairs

- Parent must pass the exact `audit-binding.json` SHA-256 to both wrapper and auditor entry points. Wrapper and audit outputs record it; the binding path stays fixed to this directory.
- Builder requires the exact r2 frozen-manifest path and explicit digest. It checks each of five current auditor source files against that manifest and requires the reviewed assembly to bind the same manifest, registration, and source digests.
- Schedule modules load by exact OWN path and source digest. Their origins are checked before schedule validation.
- Independent registration pins remain constants: config `1c24df3eea150160451ada08e9f6844cd67645abf5fb8b712afd14abca930ce8`, selected parent `c10d90ec0e67503afef8f4d90c4968581d430ef2065117a75e81c445a04c8ddc`, parent terminal receipt `76cb15733e87518cb3b473b7f8ebd847ed206351fb9f17d89b8b92e6bf853f08`, and native `022d41dde9bace0b4f4c4c06b9b4ed007bc2c60013cd98734086e587d7bb997e`. Registration must be the actual `registration-final-r2.json` with 13,857 pins, exact root/runtime, source origins, and distinct latest-resource versus original-producing-cost provenance.
- Binding pins exact observer source and immutable instantiation digest. Full audit reads execution, worker, and observer JSON once, records their digests, and wrapper gates those same parsed bytes.
- Added parent-only `bootstrap_readiness.py`. It loads the actual runner, registration schema, parent adapter, launcher, and schedule modules, verifies origins and pins, and stops before candidate audit or checkpoint deserialization.
- Kept the existing candidate, terminal, resource, inventory, raw-frame, metrics, gradient, evaluation, death, and Q1/Q4 checks. LR mutation-before-commit and end-of-horizon hold remain the accepted schedule design; no optimizer rollback claim was added.

## Validation

24 CPU synthetic/source tests pass. They include builder success against the real frozen registration/source-manifest/observer inputs; negative external binding digests; parent substitution rejection; strict schedule module origins; metric-schedule integration; malformed saved-counter rejection; and frozen schedule-manifest verification. Tests did not load checkpoint binaries or run a full audit.

The registration/source contracts were checked read-only. No lease, state, marker, environment, MPS, or training operation ran. Protected `README.md` remains expected at SHA-256 `be478416b33c772a7ff9c28f2c974f767c205f7df77bcf7346ab36133d384652`.

## Parent completion steps

1. Parent creates the reviewed assembly JSON described by `review_assembly_contract.json`. It must contain the exact registration path/hash, exact frozen-manifest path/hash, and all five reviewed source paths/hashes. Parent freezes that artifact and supplies its SHA-256.
2. After the parent review freeze, create the binding only in this directory. Supply all digests explicitly:

```sh
/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/python/.venv/bin/python -B binding_builder.py \
  --registration "/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/learning/runs/v2/D2-retained324-linear-integrated-luna-20261026-r4/registration-final-r2.json" \
  --registration-sha256 0a6bf98221689ffcf62a28289dae7bb98eb89bc8d3c02b93127f4a04df75cb4e \
  --reviewed-manifest "/absolute/path/to/parent-reviewed-assembly.json" \
  --reviewed-manifest-sha256 "PARENT_REVIEW_ASSEMBLY_SHA256" \
  --observer-source "/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/learning/runs/v2/D2-retained324-linear-execution-observer-parent-20261026-r1/observe.py" \
  --observer-sha256 f271b2641b995fc34a90cebe420657953cb16ce9038886edc2fd74c184ccacad \
  --frozen-manifest "/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/learning/runs/v2/D2-retained324-linear-auditor-prepare-luna-20261026-r2/frozen-manifest.json" \
  --frozen-manifest-sha256 "9a732cff4646610b62ff399d01837fddf81199f698493bd997bc0b33a321b74c" \
  --output "/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/learning/runs/v2/D2-retained324-linear-auditor-prepare-luna-20261026-r2/audit-binding.json"
```

3. Parent computes `audit-binding.json` SHA-256 independently and supplies it as `EXPECTED_BINDING_SHA256`. Under the exact lease and intended Python environment, run the unmocked bootstrap check from this directory:

```sh
env -u PYTHONPATH PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX="$PWD/empty-pycache" OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 NUMEXPR_NUM_THREADS=1 /Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/python/.venv/bin/python -B bootstrap_readiness.py --binding-sha256 "$EXPECTED_BINDING_SHA256"
```

4. After the parent confirms run completion and is ready for the read-only full audit, invoke the parent-only API with that same externally supplied digest and the exact observer directory:

```sh
env -u PYTHONPATH PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX="$PWD/empty-pycache" OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 NUMEXPR_NUM_THREADS=1 /Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/python/.venv/bin/python -B -c 'import os, wrapper; wrapper.full_mode(observer_dir="/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/learning/runs/v2/D2-retained324-linear-execution-observer-parent-20261026-r1", expected_binding_sha256=os.environ["EXPECTED_BINDING_SHA256"], name="full-audit.json")'
```

The full audit remains provisional pending the parent-owned acceptance, lease release, and publication procedure. Do not call the binding frozen until parent review assembly, builder validation, independent binding hash, and bootstrap readiness all pass.
