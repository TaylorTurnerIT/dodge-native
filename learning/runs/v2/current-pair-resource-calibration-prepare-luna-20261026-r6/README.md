# Current pair resource calibration R6 preparation

Fresh CPU only proposal derived from R5. R5 files, failures, CPU logs, test fixtures, and provenance remain unchanged; copied R5 receipts are retained as historical evidence. R6 writes only within this directory.

R6 repairs the missing `cpu_preflight.py` CLI and its output path. The launcher checks subprocess exit and receipt before the fixed marker. A real launcher-command CPU test validates both checkpoints and lexical module origins. Active guards reject fresh MPS driver samples above 6 GiB. R5 bounded cleanup and startup-zero/active-window rules remain.

CPU validation used the lexical virtualenv, `-B`, `PYTHONDONTWRITEBYTECODE=1`, an empty R6 bytecode prefix, and at most four CPU threads. No reservation, marker, actual probe, MPS, game, training, checkpoint, state, or lease write occurred. No actual hardware acceptance is claimed.

Independent review of the exact R6 freeze and parent-side plan hash verification, distinct reservation, and one-shot authorization remain pending. No actual probe may run before both gates pass.
