# Prospective normal D2 iteration

Status: preparation, awaiting frozen Claude Haiku review and parent acceptance. No campaign has launched.

This revision makes the minimum normal-training adaptation of the successfully executed, audited critic runner. It preserves its one-use launcher, late-publication cancellation behavior, bounded owned-group cleanup, full preflight/postflight pins, and typed mapping comparator. Earlier r1–r4 prospective adapter attempts remain preserved and are not used for execution.

The registered scope is 72 new D2 updates from the exact accepted D1 checkpoint, one entry and one final 64-seed development evaluation, seed 810631976, 1600 seconds of work and 1800 seconds total, with separate 6 GiB RSS/MPS caps. Actor, critic, PPO settings and reward are unchanged. The legacy config file is a frozen learner reference; the actual fresh training seed is explicitly bound at registration, identity and checkpoint level.

Normal checkpoints contain exact model/Adam/RNG state, inherited and new/cumulative counters, registration/policy/runtime/native identities, current episode abandonment records, and saved future episode indices. They remain provisional and training-ineligible until a separate parent-authoritative terminal acceptance. Only the final update-72 checkpoint is considered. The v3 survival-only competence predicate is reported independently; this run never opens D3, B/E or student work.

The launcher allows worker receipt finalization inside the 1600–1800-second reserve while the worker enforces the 1600-second work boundary. An empty absolute PYTHONPYCACHEPREFIX and -B prevent stale bytecode reads and writes. Parent mutation of the lease is atomic and outside worker ownership.

Focused tests cover all inherited supervision regressions and real recorded episode payloads, multi-reset ordering, normal completion below competence, distinct checkpoint/registration digests, source-cache policy, seed continuity, raw-frame conservation, and refusal to mutate an already completed run. Test fixtures are synthetic evidence, not gameplay or training validation. A separate accepted-D1 source-only rehearsal verifies model/Adam/RNG restoration before any environment or gradients.
