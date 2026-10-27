# Same-phase D2 continuation preparation

This is a preparation artifact for `D2-continuation-20261025-r1`. It adapts the audited r5 normal D2 runner and launcher to continue the exact successful update-72 D2 candidate. It does not train, roll environments, evaluate, edit historical checkpoint metadata, mutate state/lease, or grant future-training eligibility.

The only admissible parent is `D2-training-v3-20261025-r1/checkpoint-000072-candidate.pt` with SHA-256 `2e13b46edad5b2790cec52b47d33b643cbd6846387994c24fe14d5d36f0521a2`, parent registration SHA-256 `d502c6761064727a610127fc58073e3a4c062fc928ea1e26de5718ad6aee6dcb`, and a separate parent-authoritative terminal receipt. At preparation time that receipt file is absent. The runner fails closed until receipt and child registration bind exact parent, receipt, and pins. The receipt fixture tests exercise the proposed authority contract only; they do not substitute for the real parent receipt.

The continuation uses the same run seed `810631976`, exact saved `next_episode_indices`, and fresh environments. It does not resume live environment state. It preserves the 64 parent abandoned-live-episode records, logs their provenance, and starts D2 phase indices at 72. New local counters are 0 through 72; cumulative update count advances 120 through 192. Parent inclusive wall anchor remains `1188.34122675` seconds, separate from current iteration wall time. Work remains 1600 seconds with an inclusive 1800-second deadline and separate 6 GiB RSS/MPS caps.

Evaluation occurs at D2 phase indices 72 and 144 on the same 64 development seeds with deterministic argmax. Score remains in reward. The `mean_alive_frames >= 3060` predicate remains competence evidence only. All candidate metadata remains provisional and `training_eligible=false`.

`test_torch_restore.py` restores the real parent model, Adam, and MPS RNG without environment construction, evaluation, gradient, or optimizer step. Other tests use explicit contract fixtures. No training or game validation is claimed. Parent must review the exact real receipt shape, register/freeze inputs, and launch any campaign separately.
