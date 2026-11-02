# Corrected host execution route

The one non-training preflight passed at 2026-11-02 01:34:35 CST. An existing M4 task ran the exact SSH command in client-execution.json. It entered the M1 host session, where /bin/ps, self/child inspection, cancellation, direct reap and process-group absence all worked. Receipt SHA256: bea39dfe0434eb5fc96507bd4c230474b955ae778ead9b2e0c20da284c775093.

The actual route was Taylors-MacBook-Pro-2.local to Taylors-MacBook-Pro.local, with SSH_CONNECTION=100.93.220.126 59701 100.79.157.37 22. The server used uid/euid 501 and arm64 CPython 3.12.15. Parent 96722 was /usr/bin/login; preflight 96723 was in group 96722. context.json records the executable, arguments, identities and successful process observations. This proof comes from the actual command context, not a provider permission label.

One CPU-nothing child 96727 waited in signal.pause. Controlled synthetic SIGTERM reached only its pinned owned group. It exited 0, was directly reaped, and its group was absent. Sampled peak child-group RSS was 27,033,600 bytes; observed parent+child RSS was 58,490,880 bytes. The 15-second watchdog and 256 MiB guard applied only to this preflight. Training keeps separate 6 GiB RSS/MPS limits and no elapsed-time cutoff.

Read-only checks matched 11 installed package metadata versions, 19 source pins and 35 input pins. No model/checkpoint load, native game, optimizer, MPS operation or lease operation occurred. All 20 recorded frozen 070 files stayed hash-identical. Ledger bytes stayed unchanged and its active campaign stayed null. No 070 entrypoint was invoked or modified.

Minimal route correction: an M4-side execution task runs the M1 host caller through existing trusted SSH. It must not directly run Python in the restricted M1 provider context. No provider permission, model, host-key, firewall or Tailscale policy changed. No runner algorithm changed, and no native/capacity audit was repeated.

Callback correction: completed SSH remote-compute task result -> accountable M4 owner -> department t3_thread_send(auto). This preflight returned through that task-result path. M1 sends no cross-environment message; no reverse pairing or recurring polling is needed. See callback-architecture.json.

A non-authorizing successor draft is staged at /Users/taylor/Projects/dodge-native/learning/runs/v2/control12-lr1e5-m1-20261102-r2. Config SHA256: 222e17c7127b8acf17bb008f2c47e0fc6eb41f7bd79e3e9ad8290504f459d611. Both execution_authorized and training_authorized are false. No record ID is assigned. No claim, lease or entrypoint invocation occurred. All 19 algorithm source files match the accepted source. The host caller changes only its fixed config-hash literal.

Proposed successor command, NOT EXECUTED:

```sh
/usr/bin/ssh -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=12 macbook-1 'env PYTHONDONTWRITEBYTECODE=1 /private/tmp/dodge-m1-readiness-20261102-kYIx4A/venv/bin/python -B /Users/taylor/Projects/dodge-native/learning/runs/v2/control12-lr1e5-m1-20261102-r2/host_driver.py'
```

The remaining disposition is concrete: assign the new record, finalize new authority/config/hash binding, and review only that registration/admission/route delta. Reuse the accepted recipe, runtime, source and test proofs. Actual training qualification still belongs to the first two counted updates of a later authorized run. Frozen 070 stays failed. No successor training was launched.
