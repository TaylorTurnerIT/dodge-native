# PPO innovations for Dodge: literature notes

Date of research: 2026-10-25. Scope: literature only. No Dodge code, model, training, or report was touched. Source details, access limits, and fetch failures are in `source_log.json`. Ranked experiments are in `experiments.json`.

Read scope legend: **html-read** = arXiv HTML fetched, specific sections read through a WebFetch summarizer (not verbatim text). **abs-only** = abstract page only. **search-only** = search snippet, not fetched.

## 1. Actor/critic interference and decoupled critic updates

### Takeaway
Shared trunks can be harmed by coupling between policy and value gradients. Separate value networks and infrequent auxiliary value phases are the best-supported fixes. Dodge's shared trunk is a plausible but unproven contributor to the critic decline, and separate critic updates are the cheapest discriminating test.

### Cited Findings
- PPG separates policy and value training into phases and optimizes the value head more aggressively. Its auxiliary phase keeps the policy close to its prior via a KL term and reports significantly better sample efficiency than PPO on Procgen. [PPG arXiv abs](https://arxiv.org/abs/2009.04416), html-read [PPG arXiv HTML v1](https://arxiv.org/html/2009.04416v1), Sec. 2 and 3.1.
- PPG defaults are N_pi = 32 policy iterations per cycle, E_aux = 6 auxiliary epochs, beta_clone = 1 (Appendix A.1). Sec. 3.4 varies N_pi from 2 to 32 and concludes that "relatively infrequent auxiliary phases are critical to success." Sec. 3.3: performance tapers off near 6 auxiliary epochs. [PPG arXiv HTML v1](https://arxiv.org/html/2009.04416v1)
- PPG's auxiliary value loss and joint loss share no parameter dependencies, so the value step can be optimized separately (Sec. 2; Appendix C says this is convenient, not strictly necessary). [PPG arXiv HTML v1](https://arxiv.org/html/2009.04416v1)
- Andrychowicz et al. 2020 ("What Matters in On-Policy RL", 50+ choices, 250k+ agents on 5 continuous-control environments): separate policy and value networks "appear to lead to better performance on four out of five environments" (Sec. 3.2, Fig. 15). [arXiv HTML v1](https://arxiv.org/html/2006.05990v1). Partial read: the fetch covered ~100k of ~218k characters.
- Ilyas et al. ("A Closer Look at Deep Policy Gradients", arXiv 1811.02553, abstract only): learned value estimators do not fit the true value function well, and gradient estimates correlate poorly with the true gradient. [arXiv abs](https://arxiv.org/abs/1811.02553). Supports checking critic fit against ground-truth returns, not EV alone.

### Inferences
- Known and established: separate critics and infrequent auxiliary value phases are published improvements for on-policy actor-critic. Dodge's shared trunk is a known risk, not a proven cause.
- Dodge-specific hypothesis: in Dodge's shared 81-token trunk, policy gradients degrade critic representations in late updates (the 9-16 to 41-48 window). Only a matched intervention can test this. Current evidence (EV fall, no held-out gate) does not.
- Speculative: PPG-style phasing may matter more with a transformer trunk than with an MLP trunk, but no source in this set tested transformers under PPG.

### Gaps
- No PPG or Andrychowicz evidence for transformer trunks with entity tokens. Both used MLP or CNN architectures.
- Did not read PPG Sec. 3 figure values; the Procgen numbers are not in the text the summarizer returned.

## 2. PPO implementation sensitivity (KL, epochs, clipping, advantage normalization, value loss, gradient coupling)

### Takeaway
Code-level choices (reward scaling, orthogonal init, observation normalization, value clipping, and advantage normalization) can change PPO outcomes as much as the algorithm itself. Some common defaults have contradictory support. Value-function clipping is a concrete example.

### Cited Findings
- Engstrom et al. 2020 (ICLR): code-level optimizations drive much of PPO's gain over TRPO, and reward scaling, orthogonal init, and Adam annealing significantly change the reward landscape (Sec. 3, Fig. 1; four ablated optimizations). [arXiv HTML v1](https://arxiv.org/html/2005.12729v1), html-read. Reward scaling was "necessary for attaining the highest PPO reward within the tested hyperparameter grid" (paraphrase by the summarizer).
- Engstrom et al. 2020, Sec. 4: the ratio-based trust region is not maintained in PPO (max ratio consistently violates 1+eps), and clipping alone does not enforce a trust region. KL stayed well below the TRPO bound of 0.07 in both PPO variants. [arXiv HTML v1](https://arxiv.org/html/2005.12729v1)
- Andrychowicz et al. 2020: per-minibatch advantage normalization "seems not to affect the performance too much" (Sec. 3.3, Fig. 35). Value-function clipping "hurts the performance regardless of the clipping threshold" (Sec. 3.4, Fig. 43). Observation normalization is crucial in all but one environment (Sec. 3.3, Fig. 33). Linear LR decay to zero helped on 44/55 tasks, with small gains (Sec. 3.7). KL penalties and constraints gave no significant benefit except on HalfCheetah (Sec. 3.8). [arXiv HTML v1](https://arxiv.org/html/2006.05990v1), partial read.
- Engstrom and Andrychowicz disagree on value clipping: Engstrom's Fig. 1 does not report a harmful effect of value clipping. Andrychowicz says it hurts. Treat as unresolved and test directly.
- Ilyas et al. (abs-only): gradient estimates and surrogate objectives do not match the true landscape. [arXiv abs](https://arxiv.org/abs/1811.02553).

### Inferences
- Dodge's teacher config (clip 0.2, target KL 0.03 with early epoch stop, 4 epochs, minibatch 512, advantage normalization on, global grad clip 0.5, vf coefficient 0.5) is standard. Its main untested knobs are value clipping and the KL stop. Given the literature, KL stop and value clipping are the cheapest checks to test with a single-variable ablation.
- Dodge's KL early stop fired in many updates in the earlier run (230/384 in the reference report). That means the policy step is often truncated, which changes how much the critic sees per rollout. This is an interaction to measure, not a literature finding.

### Gaps
- No source here tests PPO with a transformer policy/critic.
- Did not confirm the exact Andrychowicz value-clip finding in the truncated part of the text.

## 3. Value-target and reward scaling; return normalization; PopArt; value distributions

### Takeaway
Adaptive target normalization (PopArt) keeps value outputs stable when target magnitudes change. Its value for a fixed-reward-scale PPO critic is speculative, but it is a cheap, literature-backed change with a clear discriminator (target variance and critic gradient norm).

### Cited Findings
- PopArt (Pop-Art): running mean/std of targets, normalized target sigma^-1(Y - mu), and output-preserving rescaling of the last layer when stats change (Sec. 2, Eq. 4; Sec. 2.1, Prop. 1; Algorithm 1). The normalization is applied to the update step before the SGD step. [arXiv HTML v2 of 1602.07714](https://arxiv.org/html/1602.07714v2), html-read.
- Pop-Art in that text yields a median gradient-norm span about two orders smaller than unnormalized DQN on Atari (Sec. 4, Fig. 1b). Double DQN + PopArt matched or beat clipped Double DQN on 32 of 57 games (median +0.4%, mean +34%) (Table 1). Losses occur on some games. Step sizes were only "roughly tuned," and the agent uses gamma 0.99. [same source].
- **Source discrepancy:** the fetched arXiv 1602.07714 abstract describes adaptive target normalization without the name PopArt. The Pop-Art name and Atari-57 results match Hessel et al. 2018 ("Multi-task Deep RL with PopArt", arXiv 1809.04474), which I did not fetch. Verify citation before writing the report.
- Engstrom et al. (Sec. 3): reward scaling is a significant factor. Dodge uses reward scale 0.1 (fixed), which is a related design choice. [arXiv HTML v1](https://arxiv.org/html/2005.12729v1)
- Lyle et al. 2022 (arXiv 2204.09560, abs-only) report capacity loss under non-stationary value targets, worst in sparse-reward tasks, and propose InFeR (regress features toward initialization). [arXiv abs](https://arxiv.org/abs/2204.09560). Evidence is off-policy; no PPO result read.

### Inferences
- Dodge's per-decision reward (score delta plus alive/death terms) makes target magnitude depend on survival. As policy improves, targets move. This is a direct case for normalization, but PopArt was validated in value-based Atari, not in PPO.
- Speculative: PopArt-style normalization could reduce target-variance drift in the late window (target variance 0.06736 to 0.06284, a small change, so this is likely not the main driver). Measure before building.

### Gaps
- No PPO-specific return-normalization source was read. Return normalization in PPO is part of the Engstrom code-level list, but I did not read its ablation numbers.
- No distributional or robust value-target paper was read in this window. This is a coverage gap, not a negative finding.

## 4. Partial observability and temporal credit assignment

### Takeaway
Recurrent memory (GRU) was the best general memory model under PPO in the POPGym benchmark. Dodge's observation is already visible-state (no hidden anti-camp counter), so memory is a lower priority. Horizon and gamma/GAE choices are not covered by any source read in this window.

### Cited Findings
- POPGym (Morad et al. 2023, arXiv 2303.01859): GRU had the highest MMER (0.349; 0.326 excluding navigation). LSTM 0.255, IndRNN 0.259, Elman 0.249, MLP 0.067. Transformer-like linear-attention baselines scored lower (FART 0.138, FWP 0.112). Only PPO was tested. [arXiv HTML v1](https://arxiv.org/html/2303.01859v1), html-read Sec. 5-7, Fig. 3. The MLP scored highest on most navigation tasks, which the authors use to question navigation benchmarks. [same].
- POPGym: S4D was unstable and crashed from exploding weights in RL (Sec. 6). Elman nets matched LSTM efficiency (Sec. 6). [same]
- POPGym abstract: many baselines converge in under two hours on a consumer GPU (Sec. 1.1). [arXiv abs](https://arxiv.org/abs/2303.01859)

### Inferences
- If Dodge's policy is a memoryless 81-token transformer, a GRU wrapper is a possible addition, but POPGym does not test transformer-with-memory, so there's no support for a transformer-specific memory design.
- The more relevant question for Dodge is whether recent frame observations are enough, which is a task-specific check (frame-stack or velocity-feature ablation), not a literature fact.

### Gaps
- Gamma/GAE choices (gamma 0.995 per decision, lambda 0.95, K4 frame repeat): no source read. Cite nothing about these yet.
- POPGym v2 HTML returned 404; used v1 HTML.

## 5. Exploration, curriculum, rare lethal events, and plasticity

### Takeaway
Loss of plasticity is an active, plausible explanation for critic degradation in long runs, but the strongest evidence (Dohare et al.) is supervised learning on MNIST and ImageNet, with no on-policy RL test read. Treat as a hypothesis for long-run diagnostics, not a fix to build now.

### Cited Findings
- Dohare et al. (arXiv 2306.13812, abs-only): networks lose plasticity in continual supervised learning (ImageNet binary accuracy 89% to 77% over 2000 tasks). Continual backprop reinitializes low-use units; L2 regularization eases the loss. [arXiv abs](https://arxiv.org/abs/2306.13812). Nature publication status not confirmed.
- Lyle et al. 2022 (abs-only): capacity loss under non-stationary targets; InFeR as remedy. [arXiv abs](https://arxiv.org/abs/2204.09560).
- Primacy bias (Nikishin et al. 2022, ICML): deep RL overweights early experience; periodic reset is the fix. Tested on Atari 100k and DMC (off-policy). Found via search only (arXiv 2205.07802, ICML PMLR 162). [search snippet](https://arxiv.org/abs/2205.07802v1). Not fetched; cite only as a pointer.
- Engstrom et al. (Sec. 3) and Andrychowicz et al. treat exploration, entropy, and curriculum only lightly; no curriculum result was read here.

### Inferences
- Dodge's rare lethal events (kamikaze, moving rectangles, explosions) are heavy-tail deaths within an 81-token state. Literature here does not give a clear reward-shaping or curriculum recipe for this. Any curriculum would be a new design, not a published result.
- Dodge's entropy coefficient 0.01 is conventional. Entropy fell in the earlier run (1.880 to 1.745), so exploration narrowing is observable, but no literature result here tells us how far is too far.

### Gaps
- No exploration-under-rare-death PPO source read. Need a targeted search in a future window.
- Plasticity results are not confirmed for PPO transformers.

## Relative priorities for Dodge

Ranked in `experiments.json`. The strongest literature support is for separate or phased critic updates (1) and implementation-level ablations (2). Value normalization (3) is cheap and literature-backed but untested in PPO. Memory (4) and plasticity (5) are lower priority. The compute cost of plasticity or memory experiments is higher and needs longer-run evidence.

## Confounds to keep in view

- Single training seed in the D2 diagnostic (48 updates, 1101.9375 mean alive frames). No seed variance. Any experiment needs at least 2 training seeds before claiming improvement.
- Development seeds (64) were used for checkpoint selection. Qualification needs fresh seeds.
- EV is an in-sample, self-bootstrapped diagnostic. Falling EV can coincide with better survival (report uncertainty; no EV threshold).
- Duration confound: the earlier 2240-mean checkpoint was selected among 24 evals from a longer run; do not compare it with matched 48-update endpoints without accounting for this.
