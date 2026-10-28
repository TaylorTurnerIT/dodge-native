# Next controlled RL experiments

1. **Full-game seed priority:** compare uniform and capped opening-priority sampling from the same training-only pool. Freeze the first priority rule; collect fresh full-game PPO rollouts.
2. **Adaptive curriculum:** replace fixed episode assignments with mastery-gated scheduling and measured full-game exposure. A full-game trajectory does not guarantee reaching late states.
3. **Learning-rate schedule:** compare constant 3e-5 with one linear decay to 1e-5, keeping sampler, parent, Adam state, epochs and experience budget matched.

Start with offline exposure and PPO-update diagnostics. Each new run gets a fresh reviewed registration; retained parent stays 324. Evaluate terminal endpoints on fresh reserved seeds and report Worst, Q1, Mean, Q4, Best and milestone rates.
