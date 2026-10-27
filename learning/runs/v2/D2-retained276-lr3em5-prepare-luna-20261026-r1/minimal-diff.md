# Exact proposed changes

- Parent state, identity, counters, episode indices, model, Adam, and RNG remain bound to original checkpoint `0b5cf72b4eb9629fa4f10ce2cecb3625b56f8787c0eca6395b9fe17161e6b292` and original receipt `d64d0f803d02a8d2c33da9fa0ba862f06ba7d9c56dcf4f0494e559a49e48fcc4`.
- `ppo.learning_rate`: `0.0001` to `0.00003`, applied after exact restore. No other config setting changes.
- New bounded arm: phase update 276 through 336, 60 updates, evaluations at 276/288/300/312/324/336, seed `3791628420`.
- Separate completed resource-cost anchor: receipt `711b2949fb4123381d9af6618e47f4628540f424a0973785bb6392e14169b4c3`; full cost `7118.78208862512` seconds; selected branch baseline `4760.062404125177` seconds.
- The 60 update estimate is `1515.1336842565406` seconds with 15% margin; planned work 1650 seconds, hard work cap 1790 seconds, outer cap 1800 seconds. Caps unchanged.
- No actual campaign outputs are produced here. Parent review, exact lease, unmocked preflight, and actual run remain pending.
