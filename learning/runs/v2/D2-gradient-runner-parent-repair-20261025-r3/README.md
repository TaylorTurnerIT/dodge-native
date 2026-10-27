# D2 phase 132 to 180 CPU-shadow gradient preparation

This folder prepares one bounded continuation from the accepted D2 phase-132 checkpoint. It carries 48 updates, phases 133–180, and preserves the parent checkpoint, sidecar, registration digest, terminal receipt, saved episode indices, and 64 abandoned live episodes. The continuation uses a fresh environment at those saved indices; it does not resume the prior native trajectory.

The optional alignment probe is enabled only by this new runner. It measures CPU reference gradients on one existing 512-sample minibatch captured before the live optimizer step. `minibatch_count` currently means sample count (`512`), not number of minibatches. The probe does not measure live MPS gradients or the full rollout gradient. It reports shared trunk, layer, embedding/input projection, and final normalization alignment. It is diagnostic only and does not affect competence or eligibility.

The registered runtime transition must pin every old and new runtime file. Only `ppo.py` changes and `gradient_alignment.py` is added. All other files, including the native extension, retain exact pins. The runner checks this transition explicitly and retains exact runtime identity validation. Different old and new runtime manifest hashes are expected and bound by the parent registration.

The accepted parent's full inclusive D2 wall is `2222.619523167091` seconds. New cumulative wall adds the new iteration's full outer wall to that value. Current iteration caps remain 1600 seconds work and 1800 seconds total, with separate 6 GiB RSS and MPS limits. Measured synthetic overhead supports a 1527.1306787202134-second work estimate; it is not a production guarantee.

Synthetic output fixtures cover counter, hash, wall, probe scope, undefined cosine, math identities, and episode provenance. The actual accepted phase-132 checkpoint restoration test checks MPS model, Adam, settings, and RNG restoration and verifies checkpoint and sidecar remain unchanged. No environment, rollout, evaluation, optimizer step, registration, lease mutation, or campaign launch occurs here.

Haiku's frozen source/runtime review remains parent-owned. The parent must resolve that review and register this exact adapter before any later launch.
