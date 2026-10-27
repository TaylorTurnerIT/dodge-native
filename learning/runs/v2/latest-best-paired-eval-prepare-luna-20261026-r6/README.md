# Current paired D2 inference preparation R6

R6 pairs parent-selected checkpoint update 204 with completed endpoint update 252. It preserves the frozen 512-episode protocol and creates new source pins after addressing the R5 review findings.

R6 loads its paired evaluator by exact path under a private module name. The future worker and probe must assert every module origin before use. The input manifest pins source files only for the frozen runtime; bytecode caches are excluded. Audit-bound receipt validation checks the pinned parent audit's actual `raw_exits`, process absence, before-and-after pins, observer disposition, all-seven evaluation count, and passed status.

The worker checks resource freshness before each policy decision batch. It ignores a trailing partial sample line and rejects missing samples, malformed complete lines, future timestamps, or samples older than 1.0 seconds. The 10.0-second startup gate, 0.25-second sample period, separate 6 GiB RSS and MPS caps, 590-second work budget, and 10-second cleanup allowance remain unchanged. Exact lease checks run before and after each decision batch and after every eight active-environment step calls. The future calibration must report lease-check count, total and maximum lease-read cost, worker RSS high-water mark, supervisor process current RSS, and sampled MPS driver high-water mark.

Preparation uses CPU only. It verifies inputs, receipt anchors, and strict CPU checkpoint loads for both pinned checkpoints. It runs focused fake-environment tests only. No MPS call, actual game episode, training, optimizer, checkpoint write, lease write, or campaign launch occurs here.

The R1 calibration remains failed and preserved. R2 contains only a fixed, bounded proposal for one separately registered future probe: at most 120 outer seconds, including cleanup, with at most 90 seconds of representative fake-environment worker load. This directory does not authorize that probe. Parent must register a fresh run ID and client request ID, install the exact reservation, and authorize it after a new frozen review. Training keeps MPS priority.

This diagnostic makes no qualification, D3, B/E, student, held-out, or generalization claim. Fresh independent review and parent reconciliation remain required before any future campaign.
