# Parent-owned full audit invocation

Run only after all six actual candidate boundaries exist, worker and launcher terminal receipts succeeded, the terminal files are closed, and the exact observer reports zero raw exits and owned process/group absence. Parent still owns final publication checks, acceptance, and lease clearing.

```sh
cd /Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/learning/runs/v2/D2-retained276-lr3em5-prepare-luna-20261026-r1
env -u PYTHONPATH PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX="$PWD/empty-pycache" OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4 VECLIB_MAXIMUM_THREADS=4 /Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/python/.venv/bin/python -B -c 'import wrapper; wrapper.full_mode(observer_dir=wrapper.OBSERVER_DIR, name="lr3em5-full-audit.json")'
```

This invokes the explicit parent-only Python function. The CLI deliberately refuses full mode. It writes `lr3em5-full-audit.json` only inside this preparation directory.
