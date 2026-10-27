# D2 retained324 continuation: execution observation

- Run: `D2-retained324-continuation-20261026-r1`; one observer invocation, one outer launcher, one worker launch.
- Terminal: observer exit 0; outer raw exit 0; worker raw exit 0. Observer-reported outer wall: 1066.4701513750479 s. Launcher direct-reap elapsed: 1066.131702166982 s. Worker work elapsed: 1062.4969264999963 s; worker-reported elapsed: 1062.497074374929 s.
- Registration SHA-256: `44ac8185b24de2d98cc1c870191f18be47734b5cc11c7c6ff91b9feacb34cd5a`; 13,846/13,846 pins passed, zero failures. Runner SHA-256: `43e93f7469c8dc3b0719f8f218ccb7f58f6860fcd5e0625e0fa580320d7e0c10`; observer SHA-256: `1f991a9a984b18eb8861248ef45b285bdd6288b9e80f5a209af61e15a371f71b`.
- Entry restoration matched model, Adam, and RNG hashes. Run completed 60 updates, cumulative update 432, 7,680 optimizer steps, six evaluations at 324/336/348/360/372/384. `first_failure` null; postflight inputs unchanged; worker directly reaped; owned process group absent. Cleanup signals: none.
- Peak aggregate RSS: 2,295,365,632 bytes. Worker peak RSS: 2,202,910,720 bytes. Worker peak MPS driver memory: 2,456,387,584 bytes. Each stayed below 6,442,450,944-byte caps.
- Observer stdout/stderr empty. No execution error recorded. Worker result status `completed`; execution result status `passed`; `competence_passed` false, `training_eligible` false, `promoted` false. All candidates remain provisional for parent terminal acceptance. Lease was not cleared; no receipts were published.
- Evidence: `learning/runs/v2/D2-retained324-execution-observer-parent-20261026-r1/` and `learning/runs/v2/D2-retained324-continuation-20261026-r1/`.
