# Latest-versus-best paired D2 evaluation r4 (preparation only)

R4 is a successor to frozen r3 (`learning/runs/v2/latest-best-paired-eval-prepare-luna-20261026-r3/`, receipt `a57a89c7…2381945`). It fixes the five findings in `learning/runs/v2/latest-best-paired-eval-r3-frozen-review-haiku-20261026-r1/review.md`.

Fixes:
1. Freshness clock is read after the resource log read (`supervisor.latest_resource_sample`). Negative age cannot come from loop-clock ordering; no negative-age tolerance was added.
2. Worker waits for a first complete owned sample (bounded, 10 s) before any MPS model load, and `guard()` plus model-load boundaries call `ResourceSampler.require_live()`. Sampler error before the first sample fails closed. A missing sample is unknown, never zero MPS.
3. Partial-only log equals the empty log (unknown). Malformed complete lines still fail.
4. Postflight reads through the same tolerant parser (`read_resource_log`) and records `resource_log_partial_tail_bytes`. Passing still requires samples and caps.
5. Owned-group cleanup signals a surviving group whenever `group_exists` is true, including after a clean leader exit. Signals stop once absence is observed. Raw exit and reap evidence are kept.

Resource sampling policy: 1.0 s freshness (4 sample periods) and 10 s startup bound are kept unchanged and are NOT measured under real worker load. The justification and required pre-campaign calibration probe are recorded in `protocol-proposed.json` under `resources.sampling_policy`.

Tests write nothing into this directory: `PAIRED_EVAL_FIXTURE_RESULT` must name a caller-owned file, otherwise the native fixture result is not written.

No 512-episode campaign, training, gradients, optimizer, MPS job, checkpoint write, promotion, lease, state, or old-candidate change occurred. Campaign launch count 0.
