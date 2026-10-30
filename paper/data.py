"""Figure data. Provenance: the Transformer-Based-Dodge-Bot project's result
files under learning/runs/v2/ (names given per block)."""

# Teacher progress on the 64-seed development cohort, in evaluation order.
# (label, mean alive frames, hollow=capped/endpoint)
HISTORY = [
    ("v1", 197, 0), ("v1", 198, 0), ("v1", 108, 0), ("v1", 189, 0), ("v1", 197, 0), ("v1", 254, 0),
    ("D1", 223, 0), ("D1", 990, 0), ("D1cap", 1918, 1),
    ("D2", 295, 0), ("D2", 870, 0), ("D2", 940, 0), ("D2", 1149, 0), ("D2", 1342, 0), ("D2", 1093, 0),
    ("long", 2240, 0), ("longend", 1655, 1),
    ("c", 1178, 0), ("c", 1519, 0), ("c", 1854, 0), ("c", 1604, 0), ("c", 1921, 0), ("c", 2244, 0),
    ("c", 2484, 0), ("c", 2301, 0), ("c", 2273, 0), ("c", 2704, 0), ("c", 2607, 0), ("c", 2939, 0),
    ("c", 2525, 0), ("c", 3098, 0), ("c", 2271, 0),
]
PHASES = [("v1", 0, 5), ("D1", 6, 8), ("D2", 9, 14), ("long", 15, 16), ("retained lineage", 17, 31)]

# Retained checkpoints: (update, 64-seed mean, 1,024-seed mean, 1,024 Q1, 1,024 Q4)
# expanded-ranking-parent-20261026-r1/parent-postflight.json
RETAINED = [
    (180, 1854, 1771.55, 577.06, 3564.73),
    (204, 1921, 1672.86, 555.77, 3498.88),
    (276, 2484, 2380.34, 679.00, 4649.62),
    (300, 2704, 2478.40, 691.44, 4778.01),
    (324, 2939, 2630.96, 759.74, 4945.13),
    (348, 3098, 2604.49, 720.48, 4905.46),
]
# 2,048 fresh confirmation seeds: mean for checkpoint 324 and 348 (348 = 2673 - 195.71)
CONFIRM_324_348 = (2673.0, 2477.3)

# 600-update continuation from Uniform #2, 4-frame decisions, 1,024-seed cohort.
# (updates, mean, Q1, Q4)  uniform2-continuation600 / uniform2-recovery240 evaluation-*.json
CONT = [
    (0, 2162.0, 645.8, 4233.9), (60, 2405.9, 678.7, 4704.4), (120, 2320.0, 673.8, 4454.2),
    (180, 2428.3, 687.4, 4613.1), (240, 2530.9, 682.3, 4926.1), (300, 2385.4, 651.5, 4652.5),
    (360, 2484.1, 659.3, 4818.2), (420, 2616.5, 731.5, 4965.6), (480, 2593.4, 709.9, 4926.2),
    (540, 2620.1, 667.6, 5064.9), (600, 2701.7, 708.3, 5161.9),
]

# Checkpoint 420, frozen weights; control-frequency-confirmation-parent-20261029-r1 (256 fresh seeds;
# sampled conditions pool 3 repetitions = 768 games).
CONFIRM = {
    "argmax_r1": {"Mean": 4432.0, "Q1": 1783.5, "Q4": 6991.3, "Best": 12480},
    "argmax_r4": {"Mean": 3120.8, "Q1": 969.4, "Q4": 5628.5, "Best": 9682},
    "sampled_r1": {"Mean": 4386.6, "Q1": 1627.8, "Q4": 7242.6, "Best": 11999},
    "sampled_r4": {"Mean": 2626.2, "Q1": 693.8, "Q4": 5146.6, "Best": 8866},
}
# Same conditions, earlier screen (control-frequency-screen / audit-repair, 256 seeds).
SCREEN = {
    "argmax_r1": {"Mean": 4242.8, "Q1": 1659.2, "Q4": 6891.4, "Best": 12441},
    "argmax_r4": {"Mean": 3430.1, "Q1": 1070.4, "Q4": 5999.2, "Best": 8404},
    "sampled_r1": {"Mean": 4474.7, "Q1": 1580.6, "Q4": 7490.1, "Best": 12824},
    "sampled_r4": {"Mean": 2564.8, "Q1": 662.2, "Q4": 4998.6, "Best": 8050},
}

# Share (%) of games alive at 0,1k,...,12k gameplay frames (confirmation cohort).
ARGMAX_R1 = [100, 94.1, 85.9, 75.4, 61.3, 40.2, 22.3, 9.0, 3.1, 0.8, 0.4, 0.4, 0.4]
SAMPLED_R1 = [100, 94.3, 83.5, 68.6, 56.1, 41.4, 23.6, 10.9, 5.5, 3.0, 1.2, 0.3, 0.0]
SAMPLED_R4 = [100, 77.0, 55.5, 36.5, 22.9, 12.2, 4.8, 1.6, 0.3, 0.0, 0.0, 0.0, 0.0]

# Death cause by survival window, sampled actions, 768 games per setting.
# rows: (n, % of all games, normal, kamikaze, static, moving)
DEATHS = {
    "r4": [(177, 23.0, 105, 33, 10, 29), (165, 21.5, 102, 24, 18, 21), (146, 19.0, 99, 21, 22, 4),
           (186, 24.2, 120, 21, 39, 6), (94, 12.2, 53, 13, 25, 3)],
    "r1": [(44, 5.7, 22, 7, 3, 12), (83, 10.8, 38, 12, 18, 15), (114, 14.8, 57, 17, 31, 9),
           (209, 27.2, 107, 31, 63, 8), (318, 41.4, 179, 36, 98, 5)],
}
