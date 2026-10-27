# Parent-only terminal invocation

Run only after the parent confirms the observer and launcher writers are terminal, reaped, and their output receipts are closed. This is the only full-mode entry point; child CLI refuses full mode.

```sh
cd /Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/learning/runs/v2/D2-retained300-all-candidate-auditor-luna-20261026-r5
env -u PYTHONPATH PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX=/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/learning/runs/v2/D2-retained300-all-candidate-auditor-luna-20261026-r5/empty-pycache OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 /Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/python/.venv/bin/python -B -c 'import wrapper; wrapper.full_mode(observer_dir="/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/learning/runs/v2/D2-retained300-execution-observer-parent-20261026-r1", name="full-audit.json")'
```

Invocation reads the actual continuation outputs. Do not run before terminal observer receipts. Output is created exclusively as `full-audit.json` in this auditor directory. It reports all candidates as provisional pending parent terminal acceptance.
