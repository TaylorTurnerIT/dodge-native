# Current pair resource calibration R5 preparation

Fresh CPU only proposal derived from frozen R4. R4 review and receipt are retained here. R4 plan, source pins, state, leases, training files, and historical bytecode were not changed.

R5 keeps the historical R6 `best204` and `latest252` resource workload. It makes no current best276 comparison, 512 episode comparison, actual game episode, training, hardware acceptance, qualification, or probe claim.

Launcher cleanup now shares the 120 second outer deadline and caps cleanup at 10 seconds. It uses process group signals only after fresh birth identity and exact PGID checks. Otherwise it terminates and reaps only its Popen direct child. Unproven absence is recorded as `unknown`.

Resource validation retains startup samples but measures sample count, gaps, freshness, and positive MPS allocation inside the post model load representative active window. Startup zero is valid. Active zero only fails closed.

Preparation ran 13 bounded CPU controls with no more than four CPU threads. First failed harness run is retained as `cpu-tests-attempt-1-failed.log`; corrected run is `cpu-tests-final.log`. No reservation, marker, probe, MPS, game, training, state, or lease write occurred.

Independent review of the exact R5 freeze and parent side plan hash verification, distinct reservation, and one shot authorization remain pending.
