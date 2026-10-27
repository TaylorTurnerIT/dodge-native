# Source and registration review: expanded-ranking-parent-20261026-r1

**Verdict:** No ranking defect found that would make the 1024-seed ranking wrong, leak confirmation, or promote a result. Two concrete abort hazards remain. Both fail closed, but each spends the one-shot marker, so a trip mid-run requires a new run id and registration. The parent should close or explicitly accept both before the marker is claimed. This is not launch clearance. Nothing was launched, imported, or executed.

## Scope and method

Read-only, static. Read the draft, preparation record, the R6 `build_registration.py`, `execute_once.py`, `worker.py`, the evaluator `expanded_eval.py` (r4), the parent evidence under `expanded-dev64-benchmark-parent-20261026-r1/`, the proposal and seed manifests, the seed-lineage receipt, the candidate receipts, the protocol JSON, and the v2 orchestration `state.json`. Hashes were computed with `shasum`. No Python, Torch, MPS, native code, checkpoints, lease, marker, or ledger was read in a way that loads or changes it. The `.pt` bytes and the 13 runtime member files were not hashed; their pins were compared textually.

## Reviewed bytes (sha256)

| file | sha256 | result |
|---|---|---|
| `expanded-ranking-parent-20261026-r1/registration-draft.json` | 0151fe7e73849d99d8650fb95679a5954083a7f912d55ed86771c427b2770e66 | matches preparation pin |
| `expanded-runner-final-parent-20261026-r6/build_registration.py` | 280650effba15ca1763707bbf054d081f6d4fb662da83f6a70a299243b07e8eb | matches |
| `expanded-runner-final-parent-20261026-r6/execute_once.py` | e68567f0225fa2bbc49944c1fc28518250747be1e0dcf274c23586dbac79b09f | matches |
| `expanded-runner-final-parent-20261026-r6/worker.py` | da212582802e9119095b96057d38158d400d046128299ff1b845d420e236b162 | matches |
| `expanded-evaluator-publication-repair-parent-20261026-r4/expanded_eval.py` | a3439c33152b082471cd9f9a36ef4bb03783b9544ae7c1e3fe1878e607b128aa | matches |
| `expanded-dev64-benchmark-parent-20261026-r1/accepted-benchmark-evidence.json` | b78c60530a37f4e31fbab9e7dc6e168cd31f2ebd9561f2062285e4c26e2219b0 | matches wrapper pin |
| `expanded-dev64-benchmark-parent-20261026-r1/outputs/benchmark.json` | 09fdabcb775921a3a2d5f6408229f4dc65535fd2487e2b43827b28f93cd0c7aa | matches wrapper |
| `expanded-dev64-benchmark-parent-20261026-r1/outputs/benchmark.json.outer-receipt.json` | 49e87b65c12f1272488a95ba62eee938570b75ea18e6a07157b2297c32986d24 | matches wrapper |
| `expanded-dev64-benchmark-parent-20261026-r1/parent-postflight.json` | 727eee3ee2774789ff3c05b292cbc27ba6d1733d6a04ede889d26b4608890c58 | matches draft review record |
| `expanded-evaluation-registration-proposal-parent-20261026-r5/proposal.json` | 187e0464ba966b29124b29cf606c831d7097adeea99ccfc0e336598ad3fc9765 | matches |
| `…r5/ranking-seed-manifest.json` | e4aafa70226a5191f926f07961025e829466373bcfab30303af5f3a862f9f3ed | matches |
| `…r5/confirmation-seed-manifest.json` | d2594d710820ee2942aff20a11ca4dd049f1d605f6cce2950ce0018a71994d67 | matches (not read for outcomes) |
| `expanded-seed-lineage-parent-validation-20261026-r5/receipt.json` | fe4b0cc6cbbc4b9ff4335c4462dbc120954f1bac0bac8c6c761d5c18636c0949 | matches |
| `D2-retained324-linear-lr-20261026-r1/development-000348.jsonl` | d6e914345dcc955f678db41eb08d9f20af8e77490652f8d25f7ee09550a63a03 | matches |
| `docs/v2-m3-run-protocol.json` | 9e0d82028011f83e0cf6ddaef5f5e118591158d8a557f6698c82c150d5a69bab | matches evaluator |
| six candidate `source_receipt` files | per-candidate pins in draft | match proposal; all six `status` values are in the evaluator's accepted set |
| `python/.venv/bin/python` | 8dcafa7835e861e88a8f8ac7e61effbf5a987f32b0ec47bb1f3c9987caf9216d | matches review record |

## Checked, no defect

- **Budget arithmetic.** Benchmark raw frames are 198344 + 198344 = 396688. Elapsed is 9.162925707991235 + 6.86147266603075 = 16.024398374021985. Then `ceil(2*elapsed/raw*110592000 + 10)` = 8945, outer = 8955, and confirmation projection = 5967. Those match the draft, `build_registration.py:70,79`, and `execute_once.py:118-120`. The worker-only elapsed (16.024) is about 2% below the supervisor wall (16.339). The 2x multiplier covers that gap.
- **Frame cap is a real bound.** `expanded_eval.py:300,315` rejects any row with `gameplay_frames` above 18000. So 6144 episodes × 18000 = 110592000 bounds the sum of gameplay frames.
- **Anchor, cohort, and call plan.** `worker.py:133` requires ranking `--candidate-update 348`. `worker.py:47` builds six calls in sorted update order, each with cohort `ranking` and output `-candidate-{k}`. `execute_once.py:75` plans the same names.
- **Seeds.** Ranking manifest is 1024 seeds, 0xD1000000 through 0xD10003FF, role `ranking`, `outcomes_opened: false`. It does not overlap the B excluded range, the D0 dev64 block, the E excluded range, or the D2 confirmation block. `expanded_eval.py:98-113` enforces this, and the seed-lineage receipt reports 110911 unique seeds with zero collisions.
- **Metric and tie-break.** Proposal metric is `mean_alive_frames_all_1024_including_caps`, tie-break `earlier_phase_update`. `expanded_eval.py:331-333` produces `performance.mean` as that mean. `worker.py:230` sorts by `(-mean, update)`, which matches. The winner is selection-only.
- **Confirmation stays closed.** Ranking never calls `validate_selection`. `worker.py:138` and `execute_once.py:178-180,306-308` run it only for confirmation. The confirmation manifest is only hashed and counted, and `expanded_eval.py:219` validates only the chosen cohort's seeds. No ranking path reads confirmation outcomes.
- **Benchmark-to-ranking binding.** A jq diff of `source`, `runtime`, `observer`, and `limits` against the accepted benchmark `registration-final.json` shows only budget fields, `output_dir`, and the `pycache_prefix` differ. The 13-member runtime map is identical to `expanded_eval.py:34-48`. Each of the 13 pinned hashes appears in the evaluator.
- **Exclusive outputs.** `execute_once.py:152` requires an empty output dir. `execute_once.py:226` claims the marker before spawn, and `execute_once.py:77` checks planned outputs and receipts for collisions. `worker.py:136-137` checks the same, and `expanded_eval.py:266` requires the output to be new. The `outputs/` directory and `empty-pycache/` are both empty now.
- **Order-independent golden checks.** The golden JSONL is survival-sorted. Every check in the ranking path (`execute_once.py:103-110`, `worker.py:44`, `expanded_eval.py:344-363`, `build_registration.py:36`) indexes by seed, so the sort order does not matter.
- **Sequential-call logic.** The benchmark already ran two calls in one process, which exercises `_trusted_module_cache` and `_BACKEND_IDENTITY` (`expanded_eval.py:384-395,469-479`). Six calls take the same path. Benchmark heartbeat at end showed RSS 610 MB and MPS driver 183 MB, well under the 6 GiB caps.
- **Startup grace.** The first `import torch` happens after `_validate_static` hashing (`expanded_eval.py:462-475`). That work is about 40 MB of reads and should be a few seconds, under the 12 s grace (`worker.py:114`). The benchmark passed with the same ordering.

## Finding 1: `ps` timeout can abort the run

- **Where:** `execute_once.py:38` runs `ps -axo pid=,pgid=,rss=` with `timeout=0.2`. `execute_once.py:48-51` (`aggregate_rss`) does not catch the timeout. `execute_once.py:242-243` catches it and sets `reason='process_group_sampling_failed:...'`, then breaks and terminates the group.
- **Trigger:** any single `ps` call that takes longer than 0.2 s. This is likely on a loaded machine, since the supervisor samples about every 0.2 s.
- **Consequence:** the worker is killed mid-run. A partial receipt is written, the marker stays spent, and a retry needs a new run id and registration. The benchmark had about 80 polls with no failure. A typical ranking run (about 770 s) is about 3,850 polls, and a run at the full budget is about 44,700. The benchmark does not show the tail behavior at that count.
- **Suggested action:** before claiming the marker, measure `ps` latency on the launch machine under the expected load. If any sample approaches 0.2 s, the fix is a larger timeout or tolerance for a few consecutive failures. That changes `execute_once.py`, so it needs a new source pin and review.

## Finding 2: non-atomic `state.json` writes can race the 0.2 s reads

- **Where:** `execute_once.py:258` reads `state_path` every poll, outside any try block. `worker.py:64` reads it in the heartbeat sampler at `worker.py:113-117`. The writer `learning/scripts/v2_run_m0_campaign.py:29-30` uses `path.write_text(...)`, which is not atomic. The file is 530 KB and was last written at 18:15 today.
- **Trigger:** any process writes `v2-orchestration/state.json` while the run is active, and a read lands during the write window.
- **Consequence:** a partial JSON read raises in the supervisor (`supervisor_exception` path) or in the worker sampler (`check_guard` raises). The run stops fail-closed with a partial receipt, and the marker stays spent.
- **Suggested action:** the parent does not touch the ledger during the run, or the writer switches to temp file plus `os.replace`. Neither is required to keep the evidence correct, only to keep the run alive.

## Non-blocking notes

- **Draft is hand-edited, not builder output.** `build_registration.make_draft` emits `expected_lease: null`, `state_path: null`, `evaluator_review_status: "pending"`, and `sha256: null` for review pins. The on-disk draft has the lease and ledger populated, `evaluator_review_status: "accepted"`, and real review pins. The final registration should be generated from the draft with `run_id` and lease set, then checked against `build_registration.validate_final` semantics and `execute_once.preflight`. Do not copy the draft byte-for-byte as final without that check.
- **Lease and ledger state.** `state.json` currently has `active_inference_diagnostic: null` and `active_long_campaign: null`. The parent must install the exact `expected_lease` dict before launch (`execute_once.py:136,138`, `worker.py:65`). The lease `registration_path` points to `registration-final.json`, which does not exist yet.
- **Anchor is not checked by the supervisor.** `execute_once.py:68-69` does not check `candidate_update` for ranking. A value other than 348 is caught only by `worker.py:133`, after the marker is claimed. Pass 348.
- **Torch thread count is not pinned in code.** `expanded_eval.py:409` passes `num_threads=1` to the env factory, but nothing sets torch intra-op threads, and `execute_once.py:234` does not pass an environment. Launch with the same environment as the benchmark. Otherwise the per-frame timing ratio may not transfer.
- **Review records.** The ranking draft omits the R4 benchmark-acceptance and heartbeat reviews that the benchmark pinned. The parent's plan to append this review's pin is what the ranking needs. The evaluator's `provenance.evaluator_review_status` is `accepted`, and nothing in the code enforces `ranking_registration_review_status: pending`.
- **Monotonic deadline across processes.** `execute_once.py:210` passes a `time.monotonic()` value to the worker as `--deadline`. On Darwin this clock is system-wide, so the comparison holds. On another OS it may not.
- **Heartbeat cost.** The worker and supervisor each read the 530 KB ledger and rehash sources about 5 times per second. This is GIL and CPU overhead, not a correctness issue.

## Limits

- No checkpoint `.pt` bytes were hashed, and the 13 runtime member files were not hashed on disk. Their pins were matched textually to the evaluator and the benchmark registration.
- No preflight, test, or build was run. This is static reading plus shell hashing and jq.
- The per-frame timing is taken from a single 64-seed benchmark, so ranking throughput at 1024 seeds is extrapolated. The 2x multiplier and the worst-case full-cap bound are what cover that gap.
- Repeat 1 of the benchmark ran about 33% slower per frame than repeat 2 (4.62e-5 vs 3.46e-5 s/frame), likely warm-up. The budget uses the two-repeat sum, which is conservative.
- The "typical ~769 s" figure in the brief was not re-derived here.
- Ranking results do not exist yet. Nothing here evaluates candidate quality.
