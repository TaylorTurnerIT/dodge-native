# DODGE-065 Linux/A100 training source

Source preparation only. No VM, native import/constructor/game, GPU work, seed
pool read, campaign claim or ledger write is performed by preparing this packet.
The parent owns allocation, billing, the global lease, final review/registration,
runtime admission, retrieval, terminal acceptance and release.

The engine is the exact 46-file archive bound to Mac binary `ae923867...`, not
current HEAD. `native_source_manifest.json` retains source SHA `0bcb713b...`;
Cargo.lock is `f1c145a1...`. The verified locked crate sources are vendored in
the owned source packet. Official Rust1.97.1 x86_64 Linux component SHA pins are
in `linux_toolchain_source.json`; no compiler is installed during preparation.

The candidate cloud ABI is the actual archived Python3.13.16 / NumPy2.1.3 /
Torch2.11.0+cu130 runtime, with exact recorded binary/source hashes. PyO3 is the
locked0.27.2. A different A100 image stops before compilation or engine import;
there is no pip/image fallback. Linux compilation and ABI behavior remain
unobserved: no local Linux container is available.

The parent sends `unpack_launcher.py` as CLI TEXT after uploading the source TAR
and unchanged registration. Existing control/input directories are allowed;
existing source/vendor/build/artifact outputs or consumed claims are rejected.
The parent then sends `stage_launcher.py` as TEXT with registered environment
variables. It starts a separate Python process and explicitly forwards argparse
flags; CLI exec itself does not forward program argv.

Build writes a pre-import ELF/SOABI/source/toolchain/runtime/library certificate.
The parent validates it, writes separate `runtime-admission.json`, and advances
the expiring control file to train. A runtime import/type/loader receipt precedes
every native constructor. ELF alone does not establish Python/NumPy ABI validity.

`scientific_recipe.json` preserves056's ABBA order, both roots/stream hashes,
original420+named Adam each, K1/N64/T1024, macro2048/micro512, LR3e-5, exact
gamma/lambda,36 updates,2359296 gameplay frames/job,9437184 total. Startup frames
are separately recorded. First2 updates count and must pass passive GAE/return
identity, resources and full-path20%+IO forecasts. Work5400+receipt180/job and
22320 overall are unchanged. CUDA APIs receive explicit `torch.device('cuda',0)`.
No PPO stall gate, evaluation, resume, checkpoint selection or promotion is added.

Workers own counted exposure, partial observations, telemetry and snapshots.
Supervisors own exits, group absence and sampled RSS/driver memory. Missing worker
counters stay unknown. Training receipts explicitly allow saved snapshots;
build/import stages explicitly declare no saved trained weights. Snapshots are
diagnostic endpoints, never full simulator restores or automatic-resume grants.

The archive writer inventories actual claims, stdout/stderr, logs, checkpoints
and partial files. The real decoder consumes that archive, with independent
schema/identity/counter/hash checks. CPU fixtures exercise these actual writers,
the TEXT wrapper, interrupt-after-return, missing-field corruption, partials,
timeouts, cancellation and resource failures. They use dummy boundaries/processes
and placeholder checkpoint bytes; they cannot qualify native or CUDA training.

The final parent financial/controller authority is pending. Its planned24000s /
48CU /7CU-hour terms are not launch pins here. D10-D13 stay unopened; the061
archived synthetic acceptance preserves060's original failure.
