# r2 minimal delta

- Copied the frozen r1 continuation bundle into this new preparation directory and rebound run/output/launcher/config paths to r2.
- One production delta in the copied runner: pass `progress=progress` to the existing `ppo_update` call. No PPO algorithm, model, weights, optimizer, LR, reward, or validator behavior changed.
- Kept fresh unused run seed `3791628419`, config SHA `f858a63c324fc312f794c0423aa56db2daf60793b62990cd51fa400afe3af628`, parent checkpoint SHA `0b5cf72b4eb9629fa4f10ce2cecb3625b56f8787c0eca6395b9fe17161e6b292`, and phase 276 to 348 schedule.
- No lease install, environment construction, MPS operation, optimizer step, training campaign, or launch occurred.
