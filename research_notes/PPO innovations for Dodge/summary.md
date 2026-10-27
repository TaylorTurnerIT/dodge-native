# PPO innovations for Dodge: summary receipt

Date: 2026-10-25. Literature-only research. Nothing under Dodge code, model, native, training, source, checkpoints, or existing reports was edited or run.

## Latest completed cohort (performance reference)

| Cohort | Q1 alive frames | Q4 alive frames | Mean alive frames |
| --- | ---: | ---: | ---: |
| D2 diagnostic, update 48 (single seed, 64 dev seeds) | 521.0625 | 2401.1875 | 1101.9375 |

## Ranked candidates

1. Critic gradient isolation (stop-grad from value loss into shared trunk). Cheapest, 48-update local run, 1 ablation.
2. Value-function clipping on vs off. Cheap, but sources disagree (Andrychowicz says it hurts; Engstrom does not report harm).
3. Return/target normalization (PopArt-style). Cheap, literature-backed in value-based RL, untested in PPO.
4. PPG-style infrequent auxiliary value phase. Needs longer run and more compute.
5. Plasticity intervention for the critic. Needs longer run; evidence is supervised or off-policy.

Memory (GRU), gamma/GAE, and exploration/curriculum were not covered by any source read in this window and are listed as gaps.

## Coverage

- Sources read: 10 entries in `source_log.json`. Reads are split between html-read (partial, tool-summarized), abs-only, and one search-only (primacy bias).
- Source discrepancy to resolve: the Pop-Art content fetched under arXiv 1602.07714 matches Hessel et al. 2018 (1809.04474), which was not fetched.
- Fetch failures and truncation are logged in `source_log.json`.

## Limits

- Fetched content is summarizer output, not verbatim paper text. Numbers should be checked against PDFs before quoting.
- No executed experiments. All listed experiments are proposals.
- One search query only. Discovery was mostly prior-knowledge-driven URL selection.
- No EV threshold used; EV is diagnostic only.
