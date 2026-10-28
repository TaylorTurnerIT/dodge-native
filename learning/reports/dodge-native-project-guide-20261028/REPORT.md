# Dodge Native: game, reinforcement learning, and project findings

*Newcomer guide. Evidence current through 2026-10-28; see [SOURCES.md](SOURCES.md) for the source map and exact evidence files.*

## What this project is trying to achieve

Dodge is a small arcade game ported from Artridge’s PICO-8 cartridge to a native Rust game. The learning project asks a harder question than “can a program stay alive?”: can an agent observe the game, choose movement, collect useful opportunities, score, and still survive as the game reacts to that score? The desired endpoint is a capable player that sees only the same screen a person sees. The present learning work is earlier: train a structured, entity-based policy against a fast native simulator, then use it as a teacher for a vision policy. This is a research plan, not a claim that a qualified teacher or deployed vision agent already exists.

The port keeps a playable frontend and deterministic Rust game core. A separate Python process uses a native Rust environment wrapper for fast episode stepping and PyTorch for policy optimization. The split matters: game rules and collisions stay in Rust, while neural networks, rollout collection, and PPO stay in Python. Headless stepping avoids drawing a window for every training frame while retaining the game’s random-number sequence and gameplay behavior. It is not a second approximate game.

A project design document describes later visual distillation and possible student training. That document is a specification, not evidence that the student stage ran. In particular, older `learning/README.md` and `learning/TEACHER.md` describe superseded approaches; they must not be used as current model or feature facts. The current teacher is a non-clairvoyant structured entity transformer. It does not receive the game’s future random numbers or hidden timers.

## The game and its mechanics

The playfield is a 128-by-128 pixel square, updated at 60 frames per second. The player moves in eight directions or stays still. Movement has inertia: velocity decays, then input accelerates it, with a speed cap and boundary clamp. Diagonal actions are not normalized to the same length as cardinal actions. Because movement persists briefly after input changes, a useful action depends on where the player is moving, not just where it is now.

Enemies enter, move, grow, collide with one another, or interact with patterns. Some enemies chase the player; kamikaze enemies can slow near the player and leave a growing explosion. Powerups can explode enemies, slow the game, or shrink the player. Patterns add large static rectangles that charge before becoming lethal, or moving rectangles that cross the playfield. Their positions, sizes, and hazards can extend beyond the visible screen. Collision geometry therefore must follow the game code, not a simplified “everything inside the screen” model.

The game also discourages camping near the center. Remaining in its central-region test for more than 50 consecutive frames triggers extra corner enemies; leaving that region resets the counter. This is a native mechanic, not a training penalty added to force movement. Learning when to move therefore involves both immediate collision avoidance and how the game responds to the player's position.

The game’s numeric score is the central objective. It rises when enemies die and when useful powerups are collected; exact values depend on the event. Score events also increase difficulty. The native game adjusts speed, enemy spawn timing, and pattern parameters as score grows. So a policy that scores early can create a more difficult later game. This feedback loop is essential: a high score is evidence of progress, but can also make future survival harder.

The learning reward currently combines raw score change with a small alive-time term and a death penalty: `score_delta + alive_frames / 100 - 5 on true death`. At the per-frame level, that is score change plus `0.01` for each frame the player remains alive, with `-5` once on death. This makes survival useful, but does not make survival the sole objective. A score-neutral agent can gain a little reward by lasting longer; a score-producing agent can earn much more while raising difficulty. Reports must keep three things separate: game score, shaped training reward, and survival duration. They are related but not interchangeable.

“Natural death” means the game ended because a collision killed the player. A “practice cutoff” means an experiment deliberately stopped an otherwise-live episode after some frame count. For example, a 1,000-frame practice cutoff can show whether a learner handles the opening without spending the full evaluation budget. It is not a game death, and it must not receive the death penalty. Nor does passing that cutoff demonstrate full-game skill: a player can survive the opening and fail soon after.

## Why the opening is difficult

The early game is not necessarily the easiest part of a score-driven task. Learned policy weights persist across game episodes; the agent does not start each game with a blank model. What can reset is the game state and seed. Poor opening control and too little effective early-game practice are possible explanations for weak starts, but remain hypotheses. A single score event can change the game’s future difficulty, and short episodes can change which game ages the learner sees during training.

A curriculum changes which situations appear during training. One test compared a short opening stage with a full-game mixture, using matched pairs of training runs. The short stage stopped practice at 1,000 raw gameplay frames; the full-game group could continue. Across three pairs, the opening-stage survival rates were 70.38% for the control and 72.30% for the curriculum, a difference of 1.92 percentage points. Pair results went in both directions: +6.54, +0.78, and -1.56 points. Mean survival differences were also mixed (+145.69, -140.79, and -32.60 frames). No replica advanced past its first 1,000-frame stage. This tests a short-stage/full-game mixture, not a completed progressive curriculum. The “70/30” recipe refers to episode assignment, not 70% of action decisions.

A later full-game study emphasized difficult starts. Its frozen pool contained 256 seeds on which an earlier policy died before 1,000 frames and 256 on which it survived at least that long. Uniform sampling gave each of the 512 seeds equal probability, so the expected share of hard starts was 50%; finite-run counts can differ. The prioritized recipe mixed half uniform sampling with half draws from the hard half, giving an expected 75% hard starts. Six policies (three matched training pairs) were evaluated on the same 1,024 difficulty-2 seeds using sampled actions. In each pair, the prioritized policy had lower Q1 survival. Averaged across pairs, Q1 was 35.44 frames lower and overall mean survival 65.32 frames lower than uniform. This is descriptive evidence about these six policies, not proof that prioritization generally harms learning. The accepted parent checkpoint 324 was not evaluated on the D4-labeled cohort, so this comparison does not establish improvement or regression against that parent. In these run names, D2 often means the game’s difficulty-2 setting; D4 and D6 are seed-cohort labels, not difficulty-4 or difficulty-6 game settings.

These two results do not settle the opening problem. They show why a single intervention or a single mean is not enough. Curriculum design needs full-game follow-through, matched training lineages, and attention to the bottom of the survival distribution. The experiments were exploratory; the later choice of one uniform policy for continued training used Q1 after the first three difficulty-2 evaluations, rather than a preregistered selection rule.

The six completed 60-update saved models are shown below. All were evaluated with sampled actions on the same 1,024-seed cohort. Within each matched pair, both runs used the same parent checkpoint, recipe, and training-randomness vector; seed-sampling strategy was the intended difference. The three pairs used three distinct training-randomness vectors. Matching their starting randomness does not force identical later trajectories once actions and game lengths diverge. The 1,024 evaluation seeds are repeated tests of these six fixed policies; they are not 1,024 training replicas. All six models were evaluated at the fixed 60-update budget, without selecting an intermediate checkpoint from within those runs.

| Training pair | Sampling | Worst | Q1 (worst-quarter mean) | Mean | Q4 (best-quarter mean) | Best |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 1 | Uniform | 89 | 657.8398 | 2235.5293 | 4391.8047 | 8836 |
| 1 | Opening priority | 125 | 606.2734 | 2077.3193 | 4127.4648 | 7608 |
| 2 | Uniform (#2, selected) | 225 | 663.9922 | 2208.3076 | 4264.1055 | 7298 |
| 2 | Opening priority | 153 | 617.5742 | 2204.7080 | 4243.8516 | 7734 |
| 3 | Uniform | 153 | 625.7695 | 2142.2578 | 4215.3438 | 7970 |
| 3 | Opening priority | 136 | 617.4375 | 2108.1025 | 4138.8008 | 7140 |

Uniform #2 was selected by Q1 after these exploratory results. Its Q1 exceeded Uniform #1 by only 6.1523 frames, about 0.94%; this is not a claim of statistical superiority. The active continuation starts from this Uniform #2 candidate, while accepted reference checkpoint 324 remains unchanged.

## How the native simulator and learner fit together

An environment takes an action and returns the next observation, reward, and episode-boundary information. Here, the Rust game core advances raw frames. One policy decision is repeated for up to four game frames. The game can terminate early if death happens during those frames. Thus the agent chooses at 15 decisions per second in the ordinary four-frame-repeat setup, while the game itself still runs at 60 frames per second.

The native wrapper creates independent game instances, initializes each through the menu/start sequence, steps them without requiring a graphical window, and returns observations to Python. A typical observation has one global/player record and up to 80 entity records. The global record describes player position and velocity, size, game speed, score, and boundary distances. Entity records describe visible or inferable enemies, powerups, and pattern rectangles. Entity types distinguish, for example, a harmless powerup from a currently lethal rectangle. Capacity and visibility rules are explicit because silently dropping a nearby hazard could make training misleading.

The Python policy maps observations to nine action scores, called logits, and a value estimate. The actor is the part that chooses actions. The critic estimates future reward from the current observation. The present teacher is a small transformer: one global token plus 80 typed entity slots, width 128, two layers, four attention heads, and a 256-wide feed-forward block. “Attention” lets each token’s representation incorporate information from other tokens, such as comparing the player with nearby hazards. Padding slots are masked. The policy and value heads both use the global token representation.

The teacher’s geometry is privileged in the practical sense that the simulator supplies structured positions and boxes instead of pixels. That representation is not proof that a student can recover the same information from pixels and short frame history. It is not omniscient. It excludes private timers, random-number state, and future pattern schedules. Velocity and time-to-overlap features are calculated from current or recent observable state. This boundary is important for distillation: a vision student can only imitate decisions that are possible from images and their short history.

## Reinforcement learning concepts used here

A **policy** is the rule that maps an observation to an action distribution. The policy can assign probabilities to several actions. A **value function** predicts expected future reward from the current observation. It helps PPO judge whether an observed outcome was better or worse than expected; it is not the score and does not directly choose movement.

An **episode** is one game from a fresh start until death or an explicit time limit. A raw **frame** is one 1/60-second game update. A **decision** is one policy choice, usually held for four frames. A **PPO update** here means one rollout-and-optimization cycle, not one optimizer step. These units differ. For example, 1,000 frames at 60 Hz equal 16.67 seconds of game time, regardless of how long simulation takes on the computer. Wall-clock seconds measure computation and can vary with batching, hardware, rendering, and load.

A **reward** is the number the learner optimizes. A **metric** is a measurement used to judge behavior, such as score, survival frames, or the fraction reaching a milestone. Reward can include shaping terms that are not part of the game score. This project’s survival term is one such aid; it does not replace score as the objective.

**Discounting** gives near-term reward more weight than distant reward. With gamma `0.995` per decision and four raw frames per decision, reward many decisions ahead contributes less to the current estimate. This is a decision-time setting, not a per-frame gamma. **Generalized Advantage Estimation (GAE)** combines immediate reward, critic estimates, and a decay parameter lambda (`0.95`) to estimate whether an action was better than expected. GAE reduces variance while keeping a tunable amount of bias. Its result depends on correct episode boundaries and bootstrap values.

A death is **termination**: the game’s true terminal state, which should not bootstrap value beyond death. A practice or time cap while alive is **truncation**: the game was stopped by the experiment, so the learner can bootstrap from the last live state. Confusing them teaches the critic that a cutoff is as final as death. The environment therefore tracks these separately and records actual elapsed raw frames.

**Proximal Policy Optimization (PPO)** is an on-policy method: it collects actions from the current policy, then updates that policy using the collected batch. “On-policy” does not mean one gradient step per action; the same rollout is reused for a limited number of epochs. PPO clips the probability ratio between the updated and behavior policies, limiting how much an update can change action likelihoods. Approximate KL divergence monitors policy movement; an epoch-end threshold can stop additional epochs. Entropy measures randomness in action probabilities. An entropy bonus can discourage premature certainty, but too much randomness can hurt control. The clipping and KL controls are safeguards, not guarantees of good learning.

A **rollout** is a batch of decisions collected before optimization. Each cycle collects 256 decisions in each of 64 environments: 16,384 transitions total. At four raw frames per decision, this is up to 1,024 raw frames per environment, not a 1,000-frame episode cap. Trajectories may continue across PPO updates until the explicit boundary every 60 updates, when fresh environments are created and in-flight episodes are abandoned. PPO shuffles the rollout into 32 minibatches of 512 per epoch, for up to 128 optimizer steps over four epochs. An epoch-end KL threshold can stop later epochs early. “Batch” here means training examples processed together; it is not a game level. The fixed configuration includes learning rate `3e-5`, gamma `0.995`, GAE lambda `0.95`, clip coefficient `0.2`, entropy coefficient `0.01`, and reward scaling `0.1`. Reward scaling changes numerical units supplied to optimization, not the underlying game score.

During training, actions are usually sampled from the policy distribution. Sampling allows exploration: an action with lower probability can still occur. **Argmax** chooses the highest-probability action every time and is deterministic. It is useful for repeatable comparisons but can behave differently from sampling. A prior controlled diagnostic found sampling helped an entry checkpoint, while later checkpoints had no consistent sampled advantage; the latest complete checkpoint sampled worse on average than argmax. This is checkpoint-specific evidence, not a universal rule to use either mode.

A **privileged teacher** can learn from compact entity geometry. A **visual student** would receive four palette-indexed 128-by-128 frames and infer movement from pixels. Distillation means training the student to reproduce the teacher’s decisions or internal representations. The student cannot be assumed to match teacher competence: it has less direct information and must infer motion and hazards visually. The design proposes action imitation and auxiliary spatial targets, but no qualified deployed vision agent is established by those proposals.

A **curriculum** controls which start states or task difficulties appear during training. **Seed prioritization** samples some random game seeds more often, often because earlier policies failed quickly on them. It can focus practice, but can also narrow exposure or overfit a finite seed pool. Robustness means performance across different seeds and conditions, not one impressive run. **Lower-tail performance** summarizes the weaker episodes. Here, Q1 means the mean of the worst 25% of episodes; it is not the 25th percentile. Q4 is the mean of the best 25%. Worst and Best are the single minimum and maximum. Mean is the ordinary average. These measures answer different questions: the mean can rise while the weakest quarter falls.

Seed replicates are independent training runs, not hundreds of evaluation games from one model. Repeating evaluation over 1,024 seeds improves knowledge about those fixed policies, but it does not turn three training runs into 3,072 independent training replicates. **Development evaluation** supports tuning and diagnosis. **Confirmation evaluation** uses a held-out protocol after choices are fixed. These should not be conflated. A parent checkpoint, an exploratory candidate, and a qualified policy are distinct states; a successful process exit or passed software tests alone does not establish behavioral competence.

## Observations, actions, architecture, and reward

The nine actions are neutral, four cardinal directions, and four diagonals. There are no learned menu or retry actions during play. The wrapper repeats each selected action for at most four raw frames. If death occurs inside the repeat, stepping stops at that frame.

The structured observation contains 14 global/player features and 80 entity slots with 16 numeric features each, plus type IDs and masks. Features include normalized position, velocity, player size, score, speed, relative geometry, signed collision gaps, motion, and hazard timing estimates. A type ID gives each slot its meaning; a mask says whether it contains a real entity or padding. The model sees no seed identifier, debug counter, private RNG state, or hidden future timer. The optional visual input specified for a later student is four categorical palette frames, not ordinary RGB pixels.

Reward is accumulated over the raw frames actually executed. It includes raw score change, `0.01` per alive frame, and a single `-5` for natural death. The PPO implementation scales this aggregate reward by `0.1` before computing advantages and returns. A live time cap is a truncation and bootstraps; death is termination and does not. The cap is 18,000 gameplay frames, excluding 13 menu/startup frames. At 60 Hz, the cap is 300 seconds of game time; it is not a three-hundred-second wall-clock limit.

Current ordinary starts use difficulty 2 with patterns and powerups enabled. That is a setting, not proof that every evaluation uses identical sampling, policy mode, or selection criteria. Read each registration and result receipt before comparing numbers. The authoritative current campaign uses its pinned runtime under `learning/runs/v2/fullgame-seed-priority-experiment-luna-20261027-r3/runtime/dodge_rl/`; repository Python source can change independently and may not describe an already-registered run.

## How success is measured

Score and alive frames are recorded separately. Survival is measured in raw game frames at 60 Hz. Scores are raw numeric game score, not reward-scaled values. For an episode distribution, Worst and Best give extremes; Mean uses every episode; Q1 and Q4 average the bottom and top quartiles. For a small cohort, Q1 can still move substantially when a few weak episodes change.

A full-game evaluation allows the policy to play until death or the 18,000-frame cap. A 1,000-frame opening probe answers a narrower question and can end without any natural death. Milestone rates report how many episodes reached specified frame thresholds. A “snapshot qualification” validates a frozen artifact, protocol, and observed behavior for a defined gate; it does not establish universal competence or guarantee performance outside that evaluation distribution.

Always state the action mode (sampled or argmax), number of evaluation seeds, difficulty, repeat, frame cap, and whether the number summarizes development or confirmation data. Also state whether episodes ended by death or cap. A mean alone hides the lower tail; a maximum alone says little about typical play.

## Experiments and findings

The native engine baseline established that the simulator can run many times faster than real time and that a simple safe-powerup heuristic can score and survive longer than random or neutral control. At difficulty 2, 1,000 heuristic episodes averaged 6,114.6 alive frames (about 102 game seconds), compared with 255.3 for random and 187.9 for neutral. The heuristic reached the 18,000-frame cap in 15 episodes. This was a baseline and capacity study, not a trained policy result or proof that the model will learn the same strategy.

Early teacher training produced development policies with nontrivial survival, but did not clear the planned survival gates. A 48-update diagnostic on a fixed 64-seed development cohort raised deterministic mean survival from 295 frames at update zero to 1,102 at update 48. Q1 moved from 165 to 521 frames. Every episode still ended in death. The paired changes were mixed from update 24 to 48, and this short run does not diagnose why longer historical training later weakened. Critic explained variance improved on each collected batch, but that is fit to the same rollout’s self-generated targets, not held-out predictive skill.

Death telemetry showed the first fatal contact in a 64-episode fixed cohort: 29 normal enemies, 3 kamikaze bodies, 1 explosion, 21 fully expanded static rectangles, and 10 moving rectangles. These counts describe that checkpoint and seed set. They do not say what would have happened if the policy had taken a different action.

The opening curriculum and priority comparisons described above are the most relevant direct interventions on weak early play. They are small and mixed. They argue for careful full-game evaluation and replicated training, not for abandoning curriculum or declaring prioritization a general failure. Other diagnostics compared sampled and argmax behavior and examined critic fitting; neither yielded a universal action-mode rule or a causal explanation of long-run performance decline.

Source audits also established important engineering facts. Headless stepping needs to preserve rendering-related random-number side effects so the native environment remains aligned with the original game. Reward must accumulate every raw frame, including the final death frame’s score change. The wrapper must keep death separate from alive cutoffs and expose true elapsed frames. These are correctness requirements for interpreting learning results, not behavioral wins.

## What helped, what did not, and what remains uncertain

The verified safe-powerup heuristic is useful as a simulator baseline. Native source and result audits improved confidence that score, survival, terminal flags, and event accounting refer to the actual game. Entity geometry gives the teacher a compact way to reason about hazards without feeding it hidden future state. None of these proves that a particular architecture or reward caused later performance.

The short opening-stage curriculum did not show a consistent benefit across its three pairs. The seed-priority experiment’s lower-tail result favored uniform sampling across its three pairs, but sample size is too small for a method-wide conclusion. Neither study tested every possible curriculum. The learner’s earlier pattern of early improvement followed by a weaker later checkpoint also remains unexplained; comparisons across different training durations, seeds, and checkpoint selection cannot isolate a cause.

A correlation is not a mechanism. For example, scoring can correlate with subsequent harder play because the game’s code changes difficulty after score events. That causal link is in the game implementation. But a lower survival result after a score increase could still depend on policy behavior, seed, and timing. Likewise, early opening failures are visible; “insufficient early practice caused them” remains a hypothesis.

The vision stage is proposed, not qualified. The teacher has access to structured geometry; the student will need to infer that geometry from screen history. Any future transfer result must show that the student’s observations and labels do not leak hidden state, and that evaluation runs through the actual visual policy.

## Current training and next experiments

As of 2026-10-28, an authorized 600-update continuation is active from the selected uniform-sampling candidate. Its registration restores model, Adam optimizer, and random-number state; it uses the same reward and architecture, constant learning rate `3e-5`, 64 environments, 256 rollout decisions per environment, and 4 PPO epochs. It plans 9,830,400 policy decisions, ten fresh environment segments, and full difficulty-2 evaluation of the initial checkpoint and ten resulting checkpoints on 1,024 seeds each. Episodes in flight are deliberately abandoned at segment boundaries while model, optimizer, and RNG state continue. A [dated progress snapshot](progress-snapshot.json) recorded 43 of 600 updates completed, about 13.9 minutes after launch. The experiment has begun real optimizer updates; it is not merely a proposed plan. Its final outcomes remain incomplete and are not reported here.

The accepted reference checkpoint 324 remains unchanged. The selected Uniform #2 candidate came from 60 additional updates from checkpoint 324 (three matched pairs); the active 600-update continuation starts from Uniform #2. No result from the active continuation should be treated as a promoted or qualified policy until its registered run and parent review close. The selected starting checkpoint was chosen by Q1 after exploratory results; it was not selected using a preregistered confirmatory procedure.

A one-frame-decision follow-up is queued after the continuation, not launched. It proposes comparing action repeat one with repeat four under matched raw-frame budgets. That comparison must account for discount and GAE time units, observation history spacing, and the wrapper’s frame semantics. It should not be interpreted as a clean “more decisions are better” test unless these units are controlled.

Useful next questions are: can a complete progressive curriculum improve opening survival without reducing full-game score; does hard-seed practice help under more independent training replicas; which policy behavior changes when reward events raise difficulty; and can a visual student recover teacher behavior from four frames without hidden-state leakage? Each needs a frozen protocol, multiple training replicas, full-game and lower-tail reporting, and separate development and held-out confirmation cohorts. These are proposals, not current results.

## How to reproduce and navigate the project

Start with `README.md` for the native game, controls, and build structure. Read `docs/v2-source-audit.md` and `docs/v2-environment-contract.md` next for the implementation boundary and environment semantics. Read `docs/SPEC_PRIVILEGED_VIT_RL.md` as a design history, checking corrections in the source audit and contract where the specification conflicts with implementation. Then inspect `crates/dodge-core/src/game.rs`, `action.rs`, `patterns.rs`, and `config.rs` for the actual game rules; inspect `crates/dodge-rl-env` for the native Python boundary; and inspect `python/dodge_rl/ppo.py` and `models/teacher.py` for current repository implementations.

To play locally with the repository's Rust toolchain installed, run this from its root:

```sh
cargo run -p dodge-viewer
```

Use arrow keys to move, `R`, `X`, or `Space` to retry, and `Escape` to quit. Running the playable game is separate from launching a registered training campaign.

For completed empirical claims, follow the exact result JSON and its linked parent-terminal audit. The opening curriculum summary is under `learning/runs/v2/progressive1000-full-run-evaluator-parent-20261027-r2/`. The D4-labeled six-policy merge (game difficulty 2) and its paired audits are under `learning/runs/v2/fullgame-priority-D4-last-three-evaluator-sonnet-20261028-r1/`. The active 600-update continuation’s registration is under `learning/runs/v2/uniform2-continuation600-luna-20261028-r2/`; its first optimizer-update receipt is under `learning/runs/v2/uniform2-continuation600-repair-parent-20261028-r2/`. Do not use its active evaluation outcomes as completed evidence. `docs/v2-baseline-results.md`, `docs/v2-D2-training-2026-10-25.md`, `docs/v2-action-mode-results-2026-10-24.md`, `docs/v2-death-telemetry-2026-10-25.md`, `docs/v2-critic-diagnostic-2026-10-25.md`, and `docs/v2-transfer-diagnosis-2026-10-24.md` provide earlier context.

Reproducing a result means matching its pinned game/runtime source, registration, seeds, policy mode, caps, and evaluation procedure. A new run is a new experiment, not a reproduction merely because it uses the same checkpoint name. Historical raw data, weights, and builds remain local. This guide contains no model weights and authorizes no training, evaluation, or deployment.

## Glossary

- **Action repeat:** Hold one selected action for several raw game frames; current default is four.
- **Advantage:** Estimated reward improvement from an action over the critic’s expectation.
- **Argmax:** Always choose the action with highest policy probability.
- **Bootstrap:** Use a value estimate beyond a rollout or live truncation as an estimate of future return.
- **Clairvoyant:** Given hidden future information unavailable from the current observation.
- **Development cohort:** Data used to inspect and tune a method.
- **Distillation:** Train a smaller or differently informed model to imitate a teacher.
- **GAE:** Generalized Advantage Estimation; a method for computing policy advantages from reward and value estimates.
- **Logit:** Unnormalized score for an action before conversion to probabilities.
- **On-policy:** Learn from data sampled by the current or very recent policy.
- **PPO:** Proximal Policy Optimization, the clipped policy-gradient algorithm used here.
- **Q1 / Q4:** Mean survival of the worst / best 25% of episodes in these reports.
- **Raw frame:** One 60 Hz game update.
- **Rollout:** A collected batch of observations, actions, rewards, and value estimates.
- **Seed:** Initial simulator random state. With the same configuration and same actions, a seed reproduces a game trajectory; a seed alone does not force identical policy trajectories when actions differ.
- **Termination / truncation:** Natural end such as death / external cutoff while the game remains live.
- **Transformer token:** A vector representing one item, here the player/global state or one entity.

## Evidence and references

The primary-source map, claim-to-file links, and source hashes are in [SOURCES.md](SOURCES.md). The most important distinction is between source-verified game and learner contracts, audited completed experiments, and incomplete active work. General PPO concepts in this report explain the method; they do not imply that any one concept caused a Dodge result. The [original cartridge attribution](https://artridge.itch.io/dodge) identifies the game’s creator. General background: [PPO](https://arxiv.org/abs/1707.06347), [GAE](https://arxiv.org/abs/1506.02438), and [time limits in reinforcement learning](https://proceedings.mlr.press/v80/pardo18a.html). These papers explain algorithms and evaluation concerns; they do not establish causes or treatment effects in Dodge. See the three linked project literature reports in SOURCES.md for proposals and their limits.
