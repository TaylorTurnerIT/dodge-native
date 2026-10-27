# Gradient alignment preparation

This cloned PPO implementation adds optional measurement of raw shared-trunk gradients on the first existing minibatch of epoch zero. Actor objective is `policy_loss - ent_coef * entropy`; critic objective is `vf_coef * value_loss`. Both transformer blocks and embedding/input projection groups appear in summaries. Unused gradients count as zero, with coverage reported. Dot products and norms reduce detached vectors on CPU in float64.

Negative cosine means opposing raw gradients, near zero means orthogonal, and positive means aligned. These values do not establish behavioral harm or Adam update interference. Global clipping coefficient is reported from the existing global preclip norm. Measurement adds autograd traversals, but does not intentionally alter gradients, parameters, optimizer, RNG, batch, or modes.

Preparation stopped at first unexpected MPS NaN in the measurement output. Do not integrate or use this implementation in a campaign until the NaN path is understood and exact CPU/MPS parity plus finite summaries pass. The enabled/disabled MPS model, RNG, and common metrics matched exactly in the fixture, but NaN diagnostic values invalidate acceptance. Timings are synthetic fixture measurements, not training performance guarantees.
