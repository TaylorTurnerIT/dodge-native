# Confirmed324 runnable RNG reference probe

R3 is preparation only. It repairs R2 in this successor directory; R2 and frozen inputs remain untouched. The builder preserves the absolute venv invocation path, registers the parent acceptance path and SHA, and keeps the original limits: 45 seconds work, 55 seconds outer, 10 seconds cleanup, 12 seconds startup grace, 6 GiB RSS/MPS, 0.2 second polling, 2 second heartbeat staleness, and one marker after preflight.

Supervisor checks the external registration SHA, exact source paths and hashes, accepted update 324 binding, checkpoint and source integrity receipt pins, runtime executable bytes/version, and owned empty cache before marker claim. Worker imports neither `probe` nor runtime dependencies before registration/source gates. Both CLIs compile exact bytes only after checking their registered hashes. Probe references remain generator-only: no model/environment construction, checkpoint deserialization, training, evaluation, launch, or actual references in this preparation.

Fake runtime injection requires explicit synthetic status, authority, and environment gate. Parent registered mode rejects synthetic fields. The worker and supervisor retain fixed caps and source postflight checks. Supervisor resamples the owned process group for its final receipt after cleanup. The startup grace permits bounded imports before the first heartbeat; it does not claim heartbeat coverage during imports.

## Verification

Command used project Python 3.12.15 with `-B`, `PYTHONDONTWRITEBYTECODE=1`, and this output's empty cache:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX="$PWD/learning/runs/v2/confirmed324-probe-venv-source-repair-luna-20261026-r3/empty-pycache" python/.venv/bin/python -B -m unittest -v learning/runs/v2/confirmed324-probe-venv-source-repair-luna-20261026-r3/test_probe.py learning/runs/v2/confirmed324-probe-venv-source-repair-luna-20261026-r3/test_campaign.py
```

Seven fake-only tests passed, including a full synthetic CLI campaign and exclusive three-reference commit. No actual Torch/MPS import, real RNG read, checkpoint deserialization, evaluation, training, or launch occurred. Status remains `pending_notrun`; parent review and registration, exact lease installation, one-shot execution, and postflight remain outstanding.
