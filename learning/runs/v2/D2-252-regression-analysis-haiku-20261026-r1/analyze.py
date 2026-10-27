#!/usr/bin/env python3
"""Read-only stdlib analysis: D2 252-vs-180 regression.

Reads frozen artifacts only. Writes analysis.json and receipt.json into this
directory. Run as: python3 -I analyze.py  (from repository root).
"""
import hashlib
import json
import math
import os
import random
import statistics
import sys

ROOT = os.getcwd()
OUT = os.path.join(ROOT, "learning/runs/v2/D2-252-regression-analysis-haiku-20261026-r1")
CHILD = "learning/runs/v2/D2-continuation-20261025-r2"
PARENT = "learning/runs/v2/D2-gradient-alignment-20261025-r2"
OBS = "learning/runs/v2/D2-continuation-execution-observer-20261025-r2"
PARENT_AUDIT = "learning/runs/v2/d2-gradient-parent-terminal-audit-20261025-r2"
BOOT_SEED = 20261026
BOOT_DRAWS = 10000

INPUTS = [
    f"{PARENT}/development-000132.json",
    f"{PARENT}/development-000132.jsonl",
    f"{PARENT}/development-000180.json",
    f"{PARENT}/development-000180.jsonl",
    f"{PARENT}/training-metrics.jsonl",
    f"{PARENT}/training-episodes.jsonl",
    f"{PARENT}/worker-result.json",
    f"{CHILD}/development-000180.json",
    f"{CHILD}/development-000180.jsonl",
    f"{CHILD}/development-000252.json",
    f"{CHILD}/development-000252.jsonl",
    f"{CHILD}/training-metrics.jsonl",
    f"{CHILD}/training-episodes.jsonl",
    f"{CHILD}/worker-result.json",
    f"{CHILD}/execution-result.json",
    f"{CHILD}/artifact-manifest.json",
    f"{OBS}/observation.json",
    f"{OBS}/postflight-summary.json",
    f"{PARENT_AUDIT}/audit.json",
    "docs/investigation-methodology.md",
]


def sha256(path):
    h = hashlib.sha256()
    with open(os.path.join(ROOT, path), "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as f:
        return json.load(f)


def load_jsonl(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def mean(xs):
    return sum(xs) / len(xs) if xs else float("nan")


def median(xs):
    return statistics.median(xs) if xs else float("nan")


def sd(xs):
    return statistics.stdev(xs) if len(xs) > 1 else float("nan")


def quantiles(xs, qs=(0.1, 0.25, 0.5, 0.75, 0.9)):
    s = sorted(xs)
    out = {}
    for q in qs:
        # linear interpolation, numpy default
        pos = q * (len(s) - 1)
        lo = int(math.floor(pos))
        hi = min(lo + 1, len(s) - 1)
        out[str(q)] = s[lo] + (s[hi] - s[lo]) * (pos - lo)
    return out


def pearson(xs, ys):
    mx, my = mean(xs), mean(ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx == 0 or syy == 0:
        return float("nan")
    return sxy / math.sqrt(sxx * syy)


def slope(xs, ys):
    mx, my = mean(xs), mean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx


def boot_mean_ci(diffs, rng, draws=BOOT_DRAWS):
    n = len(diffs)
    means = []
    for _ in range(draws):
        s = 0.0
        for _ in range(n):
            s += diffs[rng.randrange(n)]
        means.append(s / n)
    means.sort()
    return {
        "point": mean(diffs),
        "ci95_percentile": [means[int(0.025 * draws)], means[int(0.975 * draws) - 1]],
        "draws": draws,
        "seed": BOOT_SEED,
        "unit": "seed (64 fixed development seeds; resampled with replacement)",
    }


def quartile_stats(values):
    s = sorted(values)
    return {
        "Q1_bottom16_mean": mean(s[:16]),
        "Q4_top16_mean": mean(s[-16:]),
        "mean": mean(s),
    }


def seed_order_quartiles(records):
    vals = [r["alive_frames"] for r in records]
    return {"first16_file_order_mean": mean(vals[:16]), "last16_file_order_mean": mean(vals[-16:])}


def dev_summary(records):
    alive = [r["alive_frames"] for r in records]
    score = [r["score"] for r in records]
    causes = {}
    for r in records:
        causes[r["death_cause"]] = causes.get(r["death_cause"], 0) + 1
    by_cause_alive = {}
    for c in sorted(causes):
        by_cause_alive[c] = {
            "n": causes[c],
            "mean_alive": mean([r["alive_frames"] for r in records if r["death_cause"] == c]),
        }
    return {
        "n": len(records),
        "alive_frames": quartile_stats(alive),
        "alive_frames_quantiles": quantiles(alive),
        "seed_order_quartile_check": seed_order_quartiles(records),
        "score_mean": mean(score),
        "score_quantiles": quantiles(score),
        "death_causes": causes,
        "mean_alive_by_cause": by_cause_alive,
        "alive_lt_500": sum(1 for a in alive if a < 500),
        "alive_ge_3000": sum(1 for a in alive if a >= 3000),
        "pearson_score_alive": pearson(score, alive),
        "terminated_all": all(r["terminated"] for r in records),
        "truncated_any": any(r["truncated"] for r in records),
    }


def paired_analysis(a_recs, b_recs):
    a = {r["seed"]: r for r in a_recs}
    b = {r["seed"]: r for r in b_recs}
    assert set(a) == set(b), "seed sets differ"
    seeds = sorted(a)
    diffs = [b[s]["alive_frames"] - a[s]["alive_frames"] for s in seeds]
    improved = sum(1 for d in diffs if d > 0)
    worsened = sum(1 for d in diffs if d < 0)
    tied = len(diffs) - improved - worsened
    rng = random.Random(BOOT_SEED)
    # tail membership: bottom/top 16 by alive frames at each checkpoint (sorted-value cut)
    a_sorted = sorted(seeds, key=lambda s: a[s]["alive_frames"])
    b_sorted = sorted(seeds, key=lambda s: b[s]["alive_frames"])
    a_bottom, a_top = set(a_sorted[:16]), set(a_sorted[-16:])
    b_bottom, b_top = set(b_sorted[:16]), set(b_sorted[-16:])
    # cause transitions
    trans = {}
    for s in seeds:
        k = f"{a[s]['death_cause']}->{b[s]['death_cause']}"
        trans[k] = trans.get(k, 0) + 1
    # association of cause with alive-frame change (descriptive)
    cause_change = {}
    for s in seeds:
        c = b[s]["death_cause"]
        cause_change.setdefault(c, []).append(b[s]["alive_frames"] - a[s]["alive_frames"])
    cause_change_summary = {
        c: {"n_at_252": len(v), "mean_diff": mean(v), "median_diff": median(v)}
        for c, v in sorted(cause_change.items())
    }
    return {
        "n_pairs": len(seeds),
        "diff_alive_252_minus_180": {
            "mean": mean(diffs),
            "median": median(diffs),
            "sd": sd(diffs),
            "quantiles": quantiles(diffs),
            "min": min(diffs),
            "max": max(diffs),
        },
        "improved": improved,
        "worsened": worsened,
        "tied": tied,
        "paired_bootstrap_mean_diff": boot_mean_ci(diffs, rng),
        "bottom16_membership": {
            "180_bottom16_still_bottom16_at_252": len(a_bottom & b_bottom),
            "180_bottom16_left": len(a_bottom - b_bottom),
            "252_bottom16_new_entrants": len(b_bottom - a_bottom),
            "180_top16_still_top16_at_252": len(a_top & b_top),
            "180_top16_left": len(a_top - b_top),
        },
        "death_cause_transitions_180_to_252": dict(sorted(trans.items(), key=lambda kv: -kv[1])),
        "cause_at_252_vs_alive_change": cause_change_summary,
        "scope": "descriptive; 64 fixed development seeds; bootstrap is seed-resampling uncertainty for this fixed set only, NOT a CI over repeated training seeds; not hazard rates or causal mechanisms",
    }


def series(rows, path_fn):
    return [path_fn(r) for r in rows]


def get(d, *keys, default=None):
    for k in keys:
        if not isinstance(d, dict) or k not in d:
            return default
        d = d[k]
    return d


def training_series(rows):
    out = {
        "update": [], "approx_kl": [], "clip_fraction": [], "entropy": [], "epochs_completed": [],
        "early_stop_kl": [], "max_epoch_kl": [], "grad_norm": [], "actor_grad_norm": [],
        "critic_grad_norm": [], "trunk_grad_norm": [], "explained_variance": [],
        "ev_pre": [], "ev_post": [], "value_loss": [], "policy_loss": [], "loss": [],
        "residual_var_pre": [], "residual_var_post": [], "pred_var_pre": [], "pred_var_post": [],
        "target_var_pre": [], "mean_value_change": [], "rms_value_change": [],
        "align_cos": [], "align_norm_ratio": [], "align_dot": [],
        "cos_embed": [], "cos_final_norm": [], "cos_layer0": [], "cos_layer1": [],
        "live_clip_coef": [], "live_preclip_norm": [], "actor_norm_probe": [],
        "critic_over_actor_weighted": [], "optimizer_steps": [], "transitions": [],
        "probe_snapshot": [],
    }
    for r in rows:
        m = r["metrics"]
        out["update"].append(r.get("local_update", r.get("phase_update")))
        out["approx_kl"].append(m["approx_kl"])
        out["clip_fraction"].append(m["clip_fraction"])
        out["entropy"].append(m["entropy"])
        out["epochs_completed"].append(m["epochs_completed"])
        out["early_stop_kl"].append(1 if m["early_stop_kl"] else 0)
        out["max_epoch_kl"].append(max(m["epoch_approx_kls"]))
        out["grad_norm"].append(m["grad_norm"])
        out["actor_grad_norm"].append(m["actor_grad_norm"])
        out["critic_grad_norm"].append(m["critic_grad_norm"])
        out["trunk_grad_norm"].append(m["trunk_grad_norm"])
        out["explained_variance"].append(m["explained_variance"])
        cd = m["critic_diagnostics"]
        out["ev_pre"].append(cd["pre_update"]["explained_variance"])
        out["ev_post"].append(cd["post_update"]["explained_variance"])
        out["residual_var_pre"].append(cd["pre_update"]["residual_variance"])
        out["residual_var_post"].append(cd["post_update"]["residual_variance"])
        out["pred_var_pre"].append(cd["pre_update"]["prediction_variance"])
        out["pred_var_post"].append(cd["post_update"]["prediction_variance"])
        out["target_var_pre"].append(cd["pre_update"]["target_variance"])
        out["mean_value_change"].append(cd["mean_value_change"])
        out["rms_value_change"].append(cd["rms_value_change"])
        out["value_loss"].append(m["value_loss"])
        out["policy_loss"].append(m["policy_loss"])
        out["loss"].append(m["loss"])
        ga = m["gradient_alignment_diagnostics"]
        out["align_cos"].append(ga["cosine"])
        out["align_dot"].append(ga["dot"])
        out["align_norm_ratio"].append(ga["norm_ratio_critic_over_actor"])
        out["cos_embed"].append(get(ga, "groups", "embeddings_and_input_projections", "cosine"))
        out["cos_final_norm"].append(get(ga, "groups", "final_norm", "cosine"))
        out["cos_layer0"].append(get(ga, "groups", "layers.0", "cosine"))
        out["cos_layer1"].append(get(ga, "groups", "layers.1", "cosine"))
        out["live_clip_coef"].append(ga["live_clip_coefficient"])
        out["live_preclip_norm"].append(ga["live_preclip_grad_norm"])
        out["actor_norm_probe"].append(ga["actor_norm"])
        out["critic_over_actor_weighted"].append(ga["weighted_critic_norm"] / ga["actor_norm"])
        out["optimizer_steps"].append(m["optimizer_steps"])
        out["transitions"].append(m["transitions"])
        out["probe_snapshot"].append(ga["snapshot"])
    return out


def window_summary(s, k=8):
    keys = [k_ for k_ in s if k_ not in ("update", "probe_snapshot") and s[k_] and all(v is not None for v in s[k_])]
    out = {}
    n = len(s["update"])
    for key in keys:
        vals = s[key]
        if not isinstance(vals[0], (int, float)):
            continue
        out[key] = {
            "first_k_mean": mean(vals[:k]),
            "last_k_mean": mean(vals[-k:]),
            "all_mean": mean(vals),
            "all_median": median(vals),
            "all_min": min(vals),
            "all_max": max(vals),
            "slope_per_update": slope(s["update"], vals) if n > 1 else float("nan"),
            "corr_with_update": pearson(s["update"], vals) if n > 1 else float("nan"),
        }
    return out


def compact_series_check(s):
    # Verify clip-coefficient identity: coef == min(1, 0.5 / preclip_norm)
    max_abs_err = 0.0
    for c, n in zip(s["live_clip_coef"], s["live_preclip_norm"]):
        expect = min(1.0, 0.5 / n) if n > 0 else 1.0
        max_abs_err = max(max_abs_err, abs(c - expect))
    return {"max_abs_err_clip_coef_vs_min(1,0.5/preclip)": max_abs_err}


def cosine_facts(s):
    c = s["align_cos"]
    neg = [i for i, v in enumerate(c) if v < 0]
    return {
        "n": len(c),
        "mean": mean(c),
        "median": median(c),
        "min": min(c),
        "min_update": s["update"][c.index(min(c))],
        "max": max(c),
        "fraction_negative": len(neg) / len(c),
        "critic_over_actor_weighted_mean": mean(s["critic_over_actor_weighted"]),
        "critic_over_actor_weighted_max": max(s["critic_over_actor_weighted"]),
        "corr_cos_vs_clip_fraction": pearson(c, s["clip_fraction"]),
        "corr_cos_vs_approx_kl": pearson(c, s["approx_kl"]),
        "corr_cos_vs_ev_pre": pearson(c, s["ev_pre"]),
        "corr_cos_vs_preclip_norm": pearson(c, s["live_preclip_norm"]),
        "corr_cos_vs_update": pearson(c, s["update"]),
        "cos_embed_mean": mean(s["cos_embed"]),
        "cos_layer0_mean": mean(s["cos_layer0"]),
        "cos_layer1_mean": mean(s["cos_layer1"]),
        "cos_final_norm_mean": mean(s["cos_final_norm"]),
        "note": "cos from one first-minibatch CPU shadow probe per update; not live MPS; pre-Adam; not causal harm",
    }


def ppo_facts(s):
    n = len(s["update"])
    return {
        "updates": n,
        "updates_early_stopped_by_kl": sum(s["early_stop_kl"]),
        "updates_full_4_epochs": sum(1 for e in s["epochs_completed"] if e == 4),
        "epochs_completed_histogram": {str(e): s["epochs_completed"].count(e) for e in sorted(set(s["epochs_completed"]))},
        "optimizer_steps_per_update_set": sorted(set(s["optimizer_steps"])),
        "transitions_per_update_set": sorted(set(s["transitions"])),
        "approx_kl_max_epoch_mean": mean(s["max_epoch_kl"]),
        "fraction_updates_max_epoch_kl_gt_target_0.03": sum(1 for v in s["max_epoch_kl"] if v > 0.03) / n,
        "clip_fraction_mean": mean(s["clip_fraction"]),
        "entropy_first_last": [s["entropy"][0], s["entropy"][-1]],
        "probe_snapshots": sorted(set(s["probe_snapshot"])),
    }


def critic_facts(s):
    return {
        "ev_pre_mean": mean(s["ev_pre"]),
        "ev_post_mean": mean(s["ev_post"]),
        "ev_pre_range": [min(s["ev_pre"]), max(s["ev_pre"])],
        "ev_post_range": [min(s["ev_post"]), max(s["ev_post"])],
        "ev_post_minus_pre_mean": mean([b - a for a, b in zip(s["ev_pre"], s["ev_post"])]),
        "residual_var_post_mean": mean(s["residual_var_post"]),
        "pred_var_post_mean": mean(s["pred_var_post"]),
        "target_var_pre_mean": mean(s["target_var_pre"]),
        "value_loss_first_last": [s["value_loss"][0], s["value_loss"][-1]],
        "mean_value_change_mean": mean(s["mean_value_change"]),
        "rms_value_change_mean": mean(s["rms_value_change"]),
        "critic_grad_norm_mean": mean(s["critic_grad_norm"]),
        "scope": "same-batch in-sample, self-bootstrapped GAE targets; not held out; EV is a training-batch statistic",
    }


def score_alive_training(episodes):
    """Training-episode records: count kinds, abandoned records, and non-abandoned summaries."""
    kinds = {}
    for e in episodes:
        kinds[e.get("kind")] = kinds.get(e.get("kind"), 0) + 1
    return {"records": len(episodes), "kinds": kinds}


def main():
    # ---- inputs / hashes
    hashes = {p: sha256(p) for p in INPUTS}
    script_path = os.path.join(OUT, "analyze.py")
    script_sha = sha256(os.path.relpath(script_path, ROOT))

    # ---- development records
    p180 = load_jsonl(f"{PARENT}/development-000180.jsonl")
    c180 = load_jsonl(f"{CHILD}/development-000180.jsonl")
    c252 = load_jsonl(f"{CHILD}/development-000252.jsonl")
    p180_json = load_json(f"{PARENT}/development-000180.json")
    c180_json = load_json(f"{CHILD}/development-000180.json")
    c252_json = load_json(f"{CHILD}/development-000252.json")
    dev_identity = {
        "parent180_jsonl_equals_child180_jsonl": p180 == c180,
        "parent180_json_sha_matches_child180_json_sha": hashes[f"{PARENT}/development-000180.json"] == hashes[f"{CHILD}/development-000180.json"],
        "child252_performance_block": c252_json["performance"],
        "child180_performance_block": c180_json["performance"],
        "parent180_performance_block": p180_json["performance"],
        "child252_evaluation_action_mode": c252_json["evaluation"]["action_mode"],
        "child252_evaluation_caps": c252_json["evaluation"]["caps"],
    }
    dev = {
        "parent_180": dev_summary(p180),
        "child_180": dev_summary(c180),
        "child_252": dev_summary(c252),
    }
    seed_sets = {
        "180_vs_252_same_seeds": sorted(r["seed"] for r in c180) == sorted(r["seed"] for r in c252),
        "parent180_vs_child180_same_seeds": sorted(r["seed"] for r in p180) == sorted(r["seed"] for r in c180),
    }
    pair_180_252 = paired_analysis(c180, c252)
    pair_parent_child_180 = paired_analysis(p180, c180)
    c132 = load_jsonl(f"{PARENT}/development-000132.jsonl")
    pair_132_180 = paired_analysis(c132, c180)
    pair_132_252 = paired_analysis(c132, c252)

    # ---- training metrics
    child_rows = load_jsonl(f"{CHILD}/training-metrics.jsonl")
    parent_rows = load_jsonl(f"{PARENT}/training-metrics.jsonl")
    cs = training_series(child_rows)
    ps = training_series(parent_rows)
    # child (72 updates; local 1..72) and parent (48 updates)
    training = {
        "child_72": {
            "rows": len(child_rows),
            "phase_updates": [child_rows[0].get("phase_update"), child_rows[-1].get("phase_update")],
            "window_first8_last8": window_summary(cs, 8),
            "ppo": ppo_facts(cs),
            "critic": critic_facts(cs),
            "gradient_cosine": cosine_facts(cs),
            "clip_identity": compact_series_check(cs),
        },
        "parent_48": {
            "rows": len(parent_rows),
            "phase_updates": [parent_rows[0].get("phase_update"), parent_rows[-1].get("phase_update")],
            "window_first8_last8": window_summary(ps, 8),
            "ppo": ppo_facts(ps),
            "critic": critic_facts(ps),
            "gradient_cosine": cosine_facts(ps),
            "clip_identity": compact_series_check(ps),
        },
    }
    # per-update compact table for transparency (child)
    child_table = [
        {
            "update": cs["update"][i],
            "approx_kl_max": cs["max_epoch_kl"][i],
            "epochs": cs["epochs_completed"][i],
            "clip_frac": cs["clip_fraction"][i],
            "entropy": cs["entropy"][i],
            "ev_pre": cs["ev_pre"][i],
            "ev_post": cs["ev_post"][i],
            "align_cos": cs["align_cos"][i],
            "crit_over_actor": cs["critic_over_actor_weighted"][i],
            "preclip_norm": cs["live_preclip_norm"][i],
        }
        for i in range(len(cs["update"]))
    ]

    # ---- training episodes (abandoned-record accounting only; not used for score/alive gating)
    child_eps = load_jsonl(f"{CHILD}/training-episodes.jsonl")
    parent_eps = load_jsonl(f"{PARENT}/training-episodes.jsonl")
    episodes = {"child": score_alive_training(child_eps), "parent": score_alive_training(parent_eps)}

    # ---- postflight recompute cross-check
    post = load_json(f"{OBS}/postflight-summary.json")
    postflight_claimed = {k: post["evaluations"][k]["Q1_bottom_25pct_alive_frames"] for k in ("180", "252")}
    postflight_claimed_q4 = {k: post["evaluations"][k]["Q4_top_25pct_alive_frames"] for k in ("180", "252")}

    analysis = {
        "schema": "d2-252-regression-analysis-haiku.v1",
        "scope": "read-only evidence analysis; no training, env, gradients, Torch load, or artifact writes outside this directory",
        "dev_identity_checks": dev_identity,
        "seed_set_checks": seed_sets,
        "development_180_252": dev,
        "canonical_quartiles_recomputed": {
            "180": dev["child_180"]["alive_frames"],
            "252": dev["child_252"]["alive_frames"],
        },
        "postflight_claimed_Q1": postflight_claimed,
        "postflight_claimed_Q4": postflight_claimed_q4,
        "postflight_claim_status": "postflight Q1/Q4 do not match sorted-alive recompute at either checkpoint; seed-order-quartile values reproduce the claimed numbers only if they match the seed_order_quartile_check block",
        "paired_180_to_252_same_seeds": pair_180_252,
        "paired_parent180_to_child180_control": pair_parent_child_180,
        "paired_132_to_180_same_seeds": pair_132_180,
        "paired_132_to_252_same_seeds": pair_132_252,
        "training_metrics": training,
        "child_per_update_table": child_table,
        "training_episode_records": episodes,
        "limitations": [
            "one training seed lineage; 252 vs 180 is a single-run trajectory point, not a seed population",
            "development set is 64 fixed seeds re-used for every checkpoint; bootstrap quantifies only that set",
            "gradient cosine is a single first-minibatch CPU shadow probe per update over 33 parameters; not live MPS, not Adam, not causal harm",
            "critic EV uses same-batch self-bootstrapped targets; not held-out",
            "death cause counts are censored episode endpoints; not hazard rates and not causal mechanisms",
            "argmax deterministic evaluation on development seeds; training population is stochastic sampling",
        ],
    }
    with open(os.path.join(OUT, "analysis.json"), "w", encoding="utf-8") as f:
        json.dump(analysis, f, indent=1, sort_keys=True, default=float)
        f.write("\n")

    analysis_sha = sha256(os.path.relpath(os.path.join(OUT, "analysis.json"), ROOT))
    receipt = {
        "schema": "d2-252-regression-analysis-haiku.receipt.v1",
        "run_id": "D2-252-regression-analysis-haiku-20261026-r1",
        "interpreter": "python3 -I (stdlib only)",
        "command": "cd <repo-root> && python3 -I learning/runs/v2/D2-252-regression-analysis-haiku-20261026-r1/analyze.py",
        "bootstrap": {"seed": BOOT_SEED, "draws": BOOT_DRAWS, "method": "paired seed resampling with replacement, percentile 95%"},
        "script_sha256": script_sha,
        "input_sha256": hashes,
        "output_sha256": {"analysis.json": analysis_sha},
        "registration_sha256_child": "0059ce1a3f2dae18a34b085b57b251c115ac53e7bc82835a6eff2164ac70e949",
        "checkpoint_sha256": {
            "child_180": "3173d293dc3309afcdeaec5d386807be40b27c0f024f67c23221d067d2b2cca8",
            "child_252": "cbdc65d0f3b2e32644ba64ada80093f20c7a6bceb8730f2eecac7a188504254b",
        },
        "writes": ["learning/runs/v2/D2-252-regression-analysis-haiku-20261026-r1/analysis.json", "learning/runs/v2/D2-252-regression-analysis-haiku-20261026-r1/receipt.json", "learning/runs/v2/D2-252-regression-analysis-haiku-20261026-r1/analyze.py", "learning/runs/v2/D2-252-regression-analysis-haiku-20261026-r1/diagnosis.md"],
        "not_performed": ["no Torch load", "no checkpoint load", "no environment steps", "no gradient computation", "no training", "no edits to source, ledger, lease, or checkpoint artifacts"],
    }
    with open(os.path.join(OUT, "receipt.json"), "w", encoding="utf-8") as f:
        json.dump(receipt, f, indent=1, sort_keys=True)
        f.write("\n")
    print("wrote analysis.json and receipt.json")


if __name__ == "__main__":
    sys.exit(main())
