# Retained324 auditor R2 preparation

Status: PASS. Independent auditor draft and tests frozen under this R2 directory.

- Twelve CPU controls passed against immutable checkpoint 000324 and its real development JSON/JSONL. Tests include positive and negative parent, model/Adam/RNG, clocks, raw-frame, gradient, death-map, entry-evaluation, observer, source-boundary, and wrapper controls.
- Startup-only unmocked bootstrap passed under exact active lease. Checked 13,846 pins and five Dodge module origins; Torch/NumPy origins matched registered venv pins.
- Full audit did not run. No current training outputs were read; no MPS, environment construction, training, or optimizer steps occurred.
- Source registration SHA: `44ac8185b24de2d98cc1c870191f18be47734b5cc11c7c6ff91b9feacb34cd5a`; runner `43e93f7469c8dc3b0719f8f218ccb7f58f6860fcd5e0625e0fa580320d7e0c10`; launcher `7215ae6628c364fe74bafba68e66cb1c688000a3b7d648dba9248fc2d812310e`; adapter `355880c2cddc455219c4714b8fd57b7a59075ef0581086b153d7b89b05a26a26`; schema `87497edebf9f94f705b73fb899b1f290d96d8de2a0e66e28c30c75983ca2f57f`.
- Auditor SHA: `1addab847a70adfdfa2585e837a9e964c15099786e47996c4087d8c6a5cb9719`. Wrapper pins this digest.
- Parent checkpoint SHA: `c10d90ec0e67503afef8f4d90c4968581d430ef2065117a75e81c445a04c8ddc`; parent eval JSON `73f9ee722b445ae8e2baf2b16fcb40744338323ec17efe35a56e703947a35e64`; JSONL `8777375952d4c656ff805f8c08da30d62e8185cdea5f63e3f0e98f542ff23215`.
- CPU log SHA: `0bda9c8cc5e7bf8683c1d6775fdc3f4a1fd40ac37d3e1b42fab07fb81eb33fdb`. Bootstrap log SHA: `d1913b411e4988abfee10a7d1a66f7756b029776f5c6052f53c7fc7579f7d86e`. Bootstrap record SHA: `dee75085c8dbe9f4a9cf32c27bc6803ec4d53c3f5f94f5744ecbd58161187488`.

Parent-only full-mode invocation, not run during preparation:

```sh
cd /Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/learning/runs/v2/D2-retained324-all-candidate-auditor-luna-20261026-r2
env -u PYTHONPATH PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX=/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/learning/runs/v2/D2-retained324-all-candidate-auditor-luna-20261026-r2/empty-pycache OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 /Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/python/.venv/bin/python -B -c 'import wrapper; wrapper.full_mode(observer_dir="/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/learning/runs/v2/D2-retained324-execution-observer-parent-20261026-r1", name="full-audit.json")'
```

Run only after parent confirms all writers and processes are absent and output receipts are closed. Child CLI refuses full mode.
