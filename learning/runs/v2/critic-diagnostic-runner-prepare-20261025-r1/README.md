# Bounded critic diagnostic runner

Preparation only: no training, gameplay, model execution or checkpoint decoding was performed here. The first synthetic contract suite passed 13 tests. The registration example also passed structural checks and hashing of all 13,551 input files.

`registration.example.json` supplies the actual parent, native binary, runtime, dependency and source paths. Its master seed `123456789` is a placeholder. The parent must choose and record a fresh allowed u32 master seed, freeze the resulting registration, complete independent review, and install the exact `expected_lease` object at the authoritative state's `active_long_campaign` before execution. The example itself is not authorization to launch.

The registration is externally anchored by `--registration-sha256`; do not include its own digest inside its contents. An optional registration digest in the lease would otherwise create a hash cycle. The lease in the registration is the exact object the parent must install. Neither program writes or clears state.

The one registered command is:

```text
python/.venv/bin/python -B learning/runs/v2/critic-diagnostic-runner-prepare-20261025-r1/execute_once.py --registration ABSOLUTE_REGISTRATION_PATH --registration-sha256 SHA256
```

The launcher validates registration structure and all pinned bytes before starting one new-session worker. It writes an exclusive launch marker, records direct wait/raw exit, checks that the group is gone, revalidates generated evidence, then rehashes all inputs and the exact lease before publishing success. Cancellation or a failure triggers only the exact owned group's existing five-second TERM/five-second KILL cleanup policy. The parent must audit the result and clear its lease. No retry occurs.

The worker restores only the accepted D1 model, Adam and Python/NumPy/Torch CPU/MPS RNG, verifies exact equality before creating fresh D2 environments, and uses the frozen learner settings. It runs 48 updates and evaluations at 0, 24 and 48, with a 1,680-second work deadline and a 1,800-second inclusive absolute deadline. Resources are cooperative observed caps, 6 GiB each for process peak RSS and MPS driver allocation. There is no resource sample-gap failure threshold or full-tree timer.

Development results include survival and score Q1/Q4/mean, native death causes, caps and a diagnostic survival-gate label. Evaluation and checkpointing must preserve model, Adam, RNG and live environments. Checkpoints use `critic_diagnostic_checkpoint_v1`, not the historical candidate schema, and remain ineligible for training. Post-update critic fit is in-sample on the same self-bootstrapped targets; no EV threshold or promotion occurs.

Before actual execution the parent still needs independent runner review and any desired real-OS supervision integration check. Synthetic tests establish control-flow contracts, not actual training, MPS performance or OS cleanup capability. The accepted installed extension remains untouched.

Current best cohort survival: Q1 **648.25**, Q4 **4,508.8125**, mean **2,240 frames**. This fresh D1-to-D2 diagnostic covers early learning and cannot alone explain the late 384-update EV decline.
