# M1 staging blocker

The single LAN transfer failed with `[Errno 65] No route to host`. The M1 delegate preserved the zero-byte partial and first-failure receipt. No dependencies were installed. Import, native, MPS, checkpoint, or training work did not run. No accelerator lease was acquired.

The accepted source is pushed. M1 fetched closeout `d5eacc538db65d7c015e53a6d4fe2c12dbdb944d` and verified accepted runner ancestry `20338f462a95fd751be2569f7e8b0da8089990a8`. Its main tracked working tree stayed unchanged.

The owner verified the exact M4 listener PID25219/start/PGID, cancelled that unused listener, and directly reaped exec49507 with exit143. The owned process group and TCP listener are absent. This is transfer cleanup, not an experiment failure or lease release.

Remote report: `/Users/taylor/Projects/dodge-native/learning/runs/v2/m1-stage-20261102-r1/REPORT.md`, SHA256 `3033606a7ba403545c725583cef111476ed18d822e2c74143703d90f0a7d9777`. Remote evidence manifest SHA256 `641a12d86184bac804eceb6d7b52465cf160e24bc866633933aedb1000dab14e`. These hashes are delegate-reported. Parent receipt: `blocking-incident.json`.

The next preparation gate is a verified private artifact route between the Macs. No retry, network-control change, replacement schedule, or new training followed. The control12 lower-LR proposal still awaits Taylor's recipe decision. DODGE-067 remains accepted/released and was not repeated.
