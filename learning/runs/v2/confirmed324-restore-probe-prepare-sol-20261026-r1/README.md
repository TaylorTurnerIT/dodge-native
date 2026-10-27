# Confirmed324 replica-1 claimed restore probe preparation

Source preparation only. **94 stdlib synthetic controls passed: 48 carried predecessor controls and 46 focused restore/registration/consumer/worker/supervisor controls.** No real Torch, NumPy, native package, MPS, checkpoint deserialization, model, environment, training, evaluation or actual probe ran. No real lease or marker was installed, no training seed was consumed, and no delegation, commit or push occurred. All writes stay in this directory.

The next parent-owned run uses one independent worker process for the existing `paired-lr-confirmed324-20261026-r1` study, replica 1, arm `A_constant_3e-5`. It qualifies replica 1 only, pending parent audit. It does not loop through replicas, retry, produce candidates or authorize a training campaign.

## Review surface

- [supervisor_cli.py](supervisor_cli.py): reviewed R5 marker/signal/process-group/cleanup/finalization architecture, with typed restore preflight, independent consumer, complete immutable postflight and sampled process-group RSS evidence.
- [worker_cli.py](worker_cli.py): bounded initialization, one claimed transition, durable events/resources, release/synchronize/cache cleanup, success commit or partial failure evidence.
- [probe.py](probe.py): strict registration/result/commit schemas, verified private R3 imports, narrow adapter context, state observations, forbidden-call guards and replica-1 consumer.
- [build_registration.py](build_registration.py), [registration-template.json](registration-template.json), [parent-run-command-template.json](parent-run-command-template.json): inert templates, with pending identity/token and uncreated parent destinations.
- [production-diff.patch](production-diff.patch), [exact-diff.patch](exact-diff.patch), [source-manifest.json](source-manifest.json), [input-manifest.json](input-manifest.json), [receipt.json](receipt.json).

The exact accepted R3 manifest is `5cb2cdf6bb857473600c7671caa579bb9d49bd3b3bc573ee4c76d635508757ab`. Its adapter/contracts and five R5 members are loaded from hash-checked buffers under private module identities. Local imports route only to those verified members. No historical worker or full training CLI executes. Accepted code objects, method bindings and R5 private callback globals stay intact; no production monkeypatch replaces them.

The adapter receives only `runtime_root`, `runtime_versions`, `initial_episode_indices`, and `vector`, plus read-only manifest/parent/vector context. These are the fields its actual initialization/bootstrap/source API consumes. This is a new restore-probe registration, not the 60-update registration; R3's training registration validator and 1790/1800-second limits are not invoked or weakened.

## Future operation and evidence

All immutable/runtime-member/reference/accepted-parent gates pass before the exclusive outer marker. R3 authenticates loaded runtime code, deserializes and validates accepted324, then constructs a disposable pinned entity transformer and Adam. Bootstrap applies the existing constructor seed; it does not restore accepted learner state. The unchanged R5 `AttemptClaim` durably consumes the separately registered subclaim before its trusted zero-argument restore.

The probe fingerprints disposable bootstrap, accepted restore before study reseeding, reseeded state before LR assignment, and post-LR state. Each snapshot includes full model/Adam/raw RNG fingerprints, all six raw RNG component digests and LR groups. The accepted restore must match the parent model/Adam/raw RNG fingerprints. Reseeding must match the existing replica-1 CPU/MPS state reference, with Python/NumPy scratch-instance readback. Model and full Adam stay exact. The 3e-5 override is explicitly a no-op; the complete pre/post-LR snapshots must match. No optional shuffle or action draws advance these states.

The profile observes and rejects Python environment/rollout/forward/PPO/optimizer-step/save entrypoints during bootstrap and transition. R5 restore count must be one; all training/environment/candidate counts must be zero. Concrete pinned source and the absent environment provide the construction boundary; the profile is not general native-code instrumentation. No `make_env`, `update`, `candidate`, `save_checkpoint`, rollout, forward or optimizer step is called by the probe.

Loaded class/module/native identities, trusted callback sources, runtime versions and Torch dependency metadata are recorded. RSS evidence distinguishes process-group current RSS from worker process lifetime high-water RSS. MPS driver bytes are sampled separately. Before adapter validation, heartbeat MPS status is explicitly unavailable, never a measured zero. Phase resource samples, durable event ordering, raw worker status, group absence, all immutable inputs, source/registration/interpreter, exact lease, cache, spent marker and subclaim receive postflight checks. Failed checks do not suppress independent observations. The parent retains lease ownership for its audit.

Work 45s; outer decisions 55s; cleanup at most 10s within remaining outer time; startup 12s; poll 0.2s; stale heartbeat 2s; RSS and MPS each 6442450944 bytes. These are proposed caps, not measured qualification. Controlled worker failures attempt every release/synchronize/cache stage. Parent supervision terminates/reaps remaining groups, including uncooperative failures. SIGKILL cannot run worker cleanup. Handled worker signals cancel before its outcome boundary; publication ignores them after that boundary. Supervisor R5 outcome freezing remains unchanged.

## Synthetic evidence and limits

[tests.log](tests.log) and [fake-test-summary.json](fake-test-summary.json): 46 focused controls, including exact-class toy transition, spent claim, wrong reference, mutation, no environment/forward/PPO, strict event/result/native/callback identities, worker failure/SIGTERM cleanup, and new supervisor success/semantic rejection. An import guard rejects real runtime imports. Worker controls instrument only test subprocesses; supervisor controls substitute a stdlib child while retaining production preflight, marker, supervision, cleanup and consumer. Fabricated semantic payloads are test data, not actual runtime evidence.

[lifecycle-tests-pass2.log](lifecycle-tests-pass2.log): all 48 predecessor controls replayed in owned `tmp/lifecycle/`. Only checkout-relative lookup paths changed. They cover the retained lifecycle and initial-reference consumer; that predecessor consumer is not the new restore consumer. Initial failed preparation passes remain in logs. Final source hashes and retained synthetic receipts are indexed separately.

No hard watchdog covers blocking filesystem/hash/fsync/finalization. Imports and checkpoint validation precede actual MPS telemetry. Package bytes are unpinned; versions, origins and observed hashes do not qualify dependencies. Memory is sampled, not a continuous MPS peak measurement. Exclusive JSON publication may leave partial files; it has no atomic visibility or directory-fsync crash guarantee. I/O failures can prevent complete receipts. Preservation equality covers the enumerated read set, not a global filesystem audit.

Parent must separately assign a unique run/output/token/outer marker/subclaim, create a fresh empty cache, freeze full registration/source/input pins, review exact source, resolve runtime/resource calibration, audit fresh state, install the exact probe lease, authorize and execute once, then audit terminal receipts/process absence. This controller and its templates grant none of those authorities. Actual restore behavior, dependency compatibility, timing, memory and replica-1 qualification remain untested.
