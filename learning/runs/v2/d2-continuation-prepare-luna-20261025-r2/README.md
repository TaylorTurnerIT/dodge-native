# Same-phase D2 continuation preparation

This preparation artifact copies the prior r1 files as its starting point. The r1 directory and implementation-result remain unchanged. This revision repairs continuation counters, registration authority, inclusive wall accounting, and episode assertion matching. It does not train, roll environments, evaluate, edit historical checkpoint metadata, mutate state/lease, or grant future-training eligibility.

The only admissible parent is `D2-training-v3-20261025-r1/checkpoint-000072-candidate.pt` with SHA-256 `2e13b46edad5b2790cec52b47d33b643cbd6846387994c24fe14d5d36f0521a`, parent registration SHA-256 `d502c6761064727a610127fc58073e3a4c062fc928ea1e26de5718ad6aee6dcb`, and externally pinned parent terminal receipt SHA-256 `533235fd4c3b808c3be84e97e84485d74933e3a55edaf21c62301ca20ac47255`. The registration requires an explicit continuation lease kind and authorization, exact parent identity, critical pins, and an absolute cancellation path.

Continuation uses seed `810631976`, exact saved `next_episode_indices`, and fresh environments. It preserves 64 parent abandoned-live-episode records. D2 phase indices remain 72 to 144; local updates are 0 to 72; cumulative updates are 120 to 192. Parent inclusive wall anchor is `1188.34122675` seconds. Checkpoints and worker receipt track parent, current-iteration, and cumulative inclusive wall. Work remains 1600 seconds within 1800 seconds total, with separate 6 GiB RSS and MPS caps.

Evaluation is limited to D2 indices 72 and 144 on the same 64 development seeds. Score remains in reward. All candidate metadata stays provisional with `training_eligible=false`. No exact environment trajectory resume is claimed.

Launcher has no internal aggregate RSS observer. Actual campaign execution requires the parent-owned external observer to cover aggregate RSS and total wall through final CPU decode. This output is preparation only; do not freeze/register/launch yet.
