# Progressive1000 historical seed closure R2

Partial closure delivered; freshness remains blocked. Exact R1 vectors and cohort are unchanged. Parent alone approves freshness and reserves a cohort.

- Six requested journal-free directory cases now have finite coverage or preconstructor/copy proofs. Nineteen original campaigns have pinned masters, actual initial offsets, terminal/resume indices, failure disposition, source identity and conservative failed-reset endpoints. All original seed metadata replayed with zero derivation mismatches. [Campaigns](campaign-closure.json), [six cases](six-directory-closure.json), [source semantics](source-semantics.json).
- All 1,096 R1 unresolved paths have an evidence role: **974 file roles closed; 122 remain unresolved in seven named groups**. These are file counts, not independent campaigns. Remaining work concerns exact early native test constructors and an outcome-free gate-baseline seed receipt. [Every path](r1-unresolved-path-closure.json), [precise remaining actions](remaining-gap-register.json).
- Current nested journal inventory has **837 empty files and two exact ancestor copies**, verified by bytes. R1's 843 paths included four symlink aliases. Empty journal content does not prove its surrounding job never constructed an environment. [Hash proof](nested-journal-proof.json).
- Raw native controls and outside-v2 episode records add **149** observed seed values: **87,579 merged observed**, including the original **70,301 training values**. Retaining R1's **164,385-value** zero-origin envelope and adding finite known attempt/reset bounds and fixed lists yields **189,743 conservative values**. **Zero proposed-cohort collisions** appear in these covered finite sets. [Collision check](cohort-collision-check.json), [merged set](merged-conservative-seeds.json), [new observations](additional-observed-seeds.json).
- `97593849` remains in the retained R1 envelope. Its historical tuple is master `4200000000`, slot44, episode48; actual construction for that slot starts at **episode262**. It is absent from observed history and the tighter known-attempt set. This is an unused-prefix arithmetic match, not consumption. No filtering or seed replacement occurred. [Reconciliation](97593849-reconciliation.json).
- Registered M3 D3 master `5562881586070242563` has an explicit original/current `not_started` lifecycle status, a closeout receipt, and no matching retained M3 D3 run/launch path. This closes that registered campaign's no-attempt question within retained evidence. Fixed-seed native difficulty-D3 baselines are distinct. [D3 evidence](d3-no-attempt.json).

**Boundary breach:** source searches inadvertently surfaced B baseline expected-result tables in loose `baseline_expected.rs` and archived `m0_expected.rs`. Those rows were excluded from seed-collision evidence. This audit cannot claim the requested qualification-content isolation was preserved. Parent review remains required. [Incident](boundary-incident.json).

The proposal remains `progressive1000-confirmed324-20261026-r1`, replicas1..3, accepted324 offsets, cohort `0xD3000000..0xD30003FF` (1024), and the exact canonical six-range future exclusion union. Vector file SHA-256: `698557ed337cf795c1e587ca325a7a3d2645391837b0df18d8857987e634febf`. Cohort file SHA-256: `dd0d28697823eb3d3171789befb46da6f09b928f89328b3c91cb69a353104f45`. [Updated status](updated-proposal-status.json).

The existing 98,304-draw future sample independently reproduces against merged history: only `97593849` intersects, with zero cohort hits. [Bounded recheck](future-merged-recheck.json). No full future stream was enumerated. Reviewed native exclusions must avoid the cohort before every construction/reset in both arms. Matching master/offset streams do not imply identical realized episode counts. No extra requirement that all future training seeds avoid all historical training seeds was imposed.

Input sealing found externally changed/removed `confirmed324-restore-probe-prepare-sol-20261026-r1/{prepare_files.py,probe.py,supervisor_cli.py}` and multiple orchestration-state versions. Known campaign and R1 proposal evidence pins remained stable. These external changes were recorded without editing or reverting predecessors. [Recheck](input-recheck.json), [state versions](input-version-changes.json).

Verification: **17 inherited controls and 12 independent controls passed**, using owned copies and independent stdlib derivation/coverage checks. Initial control-copy setup failure is retained. No checkpoint metadata loads were needed; no model, native environment, training, evaluation, study run, reservation, subdelegation, commit or push occurred. R1 preparation was never rerun. [Receipt](receipt.json), [input pins](input-pins.json), [input recheck](input-recheck.json), [coverage closure map](coverage-closure-map.json).

Reproduce arithmetic controls from workspace root (writes no predecessors):

```sh
PYTHONPYCACHEPREFIX="$PWD/learning/runs/v2/progressive1000-seed-history-closure-sol-20261026-r2/empty-pycache" python3 -B learning/runs/v2/progressive1000-seed-history-closure-sol-20261026-r2/test_controls.py
PYTHONPYCACHEPREFIX="$PWD/learning/runs/v2/progressive1000-seed-history-closure-sol-20261026-r2/empty-pycache" python3 -B learning/runs/v2/progressive1000-seed-history-closure-sol-20261026-r2/test_closure.py
```
