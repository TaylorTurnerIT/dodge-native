# Latest-versus-best paired D2 evaluation

Status: prepared for frozen Haiku review. No campaign launch, game episode, training, optimizer, or gradient has run.

## Review files

- `protocol-proposed.json`: registered experimental and execution contract.
- `input-manifest.json`: exact immutable inputs, runtime, interpreter, and source hashes.
- `paired_eval.py`: deterministic sampler, canonical summaries, contrasts, and bootstrap.
- `worker.py`: one 64-seed inference arm using the frozen runtime helpers.
- `supervisor.py`: one-shot owned-child runner, resource/lease monitor, and bounded finalization.
- `tests/test_paired_eval.py`: fake-environment controls; includes strict CPU loads of both pinned checkpoints, but no environment construction for those loads.
- `preparation-receipt.json`: preparation commands, checks, and final source hashes.

## Future launch gate

Do not run this preparation directory's `supervisor.py` until Haiku review and parent reconciliation finish. Parent must install one exact `active_inference_diagnostic` lease, keep `active_long_campaign` null, mark the review gate fields described in `protocol-proposed.json`, and ensure no concurrent long MPS training. The lease remains parent-owned; this harness never edits `state.json` or clears the lease.

The only execution entrypoint is the supervisor. It uses the lexical `python/.venv/bin/python` path with `-B`, records the symlink target, sets a new empty cache prefix under the owned output directory, and refuses an existing output path. It launches once. Any failure keeps its partial evidence; no retry is permitted.

Example command after review, reconciliation, and exact lease installation:

```sh
/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/python/.venv/bin/python \
  -B /Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/learning/runs/v2/latest-best-paired-eval-prepare-luna-20261026-r1/supervisor.py \
  --output /Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/learning/runs/v2/latest-best-paired-eval-prepare-luna-20261026-r1/campaign-output
```

This example is documentation only. It has not been run. A successful worker produces a diagnostic result pending parent acceptance; worker status alone never accepts it.

## Limits

The report uses only the existing 64 D development seeds. It makes no held-out, generalization, qualification, B/E, D3, or student claim. Repeated argmax rows are reproducibility controls, not new environment-seed evidence. Wide confidence intervals that include zero remain inconclusive. The sampler is registered CPU float64 inverse-CDF behavior; it differs from the historical MPS `Categorical` generator. Future run output must retain every censored episode and report its denominator and restricted uncensored summaries.
