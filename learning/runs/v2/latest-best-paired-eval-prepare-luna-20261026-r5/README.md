# Current paired D2 inference preparation R5

R5 pairs the parent-selected checkpoint at phase update 204 with the completed normal-training endpoint at update 252. It supersedes the stale 180/252 pair for any future diagnostic.

The best204 input is bound to `d2_retained_best_candidate_parent_receipt_v1`, candidate counters at local update 24, and the whole accepted 72-update iteration receipt and audit. The latest252 input is bound to the standard `d2_normal_training_parent_terminal_receipt_v1` endpoint. Both checkpoints load through the frozen checkpoint loader and strict model state loading. Metadata remains unchanged and provisional.

The registered protocol remains 512 inference-only episodes: both complete canonical argmax controls first, then three sampled replicates per checkpoint, each across the same 64 existing D development seeds. CPU float64 inverse-CDF sampling and common private uniforms are unchanged. The RNG key excludes checkpoint label and active-batch position. C4 interaction remains primary; bootstrap uses 10,000 paired seed clusters and seed 764002. Wide intervals crossing zero remain inconclusive; equivalence requires the full interval inside ±100 frames.

The R4 sampler and after-read resource reader stay frozen. Freshness remains 1.0 seconds, startup remains 10.0 seconds, and RSS/MPS caps remain separate at 6 GiB. The single calibration receipt lives in the sibling `current-pair-resource-calibration-luna-20261026-r1/` output. Calibration failure makes this preparation ineligible for launch.

No episodes, training, gradients, optimizer, or checkpoint writes occurred during preparation. Independent frozen review, parent reconciliation, and a separate exact new campaign lease remain required. Training retains MPS priority.
