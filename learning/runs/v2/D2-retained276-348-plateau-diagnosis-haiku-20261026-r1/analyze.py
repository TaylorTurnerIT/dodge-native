#!/usr/bin/env python3
"""Read-only evidence analysis: retained204->276 (LR1e-4) vs 276->348 (LR1e-4) D2 continuation.

Stdlib only. Reads completed artifacts; writes metrics.json and receipt.json next to this file.
No checkpoint load, model, environment, MPS, training, evaluation, lease, or source writes.
"""
import hashlib
import json
import math
import random
import statistics as st
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]  # learning/runs/v2/<this>/ -> repo root
RUN204 = ROOT / "learning/runs/v2/D2-retained204-lr1e4-20261026-r1"
RUN276 = ROOT / "learning/runs/v2/D2-retained276-continuation-20261026-r2"
AUD204 = ROOT / "learning/runs/v2/D2-retained204-lr1e4-parent-terminal-audit-20261026-r1"
AUD276 = ROOT / "learning/runs/v2/D2-retained276-continuation-parent-terminal-audit-20261026-r2"
PREP276 = ROOT / "learning/runs/v2/D2-retained276-continuation-prepare-luna-20261026-r2"
EXISTING = [
    ROOT / "reports/PPO explained variance diagnosis.md",
    ROOT / "reports/PPO innovations for Dodge.md",
    ROOT / "learning/runs/v2-orchestration/state.json",
    ROOT / "learning/runs/v2/gradient-alignment-MPS-diagnosis-haiku-20261025-r1/diagnosis.md",
    ROOT / "learning/runs/v2/D2-gradient-final-review-haiku-20261025-r1/review.md",
    ROOT / "docs/v2-critic-diagnostic-2026-10-25.md",
    ROOT / "docs/v2-D2-training-2026-10-25.md",
]
CAND204 = [204, 216, 228, 240, 252, 264, 276]
CAND276 = [276, 288, 300, 312, 324, 336, 348]
BOOT_B = 2000
SEED = 20261026
NEAR_ZERO = 0.05  # descriptive band only; not a threshold claim
STRONG_NEG = -0.10  # descriptive band only

INPUTS = {}


def rel(p):
    return str(p.relative_to(ROOT))


def read_bytes_hashed(p):
    data = p.read_bytes()
    INPUTS[rel(p)] = hashlib.sha256(data).hexdigest()
    return data


def load_json(p):
    return json.loads(read_bytes_hashed(p))


def load_jsonl(p):
    return [json.loads(x) for x in read_bytes_hashed(p).decode().splitlines() if x.strip()]


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def safe_stats(xs):
    vals = [x for x in xs if x is not None and not (isinstance(x, float) and math.isnan(x))]
    n_missing = len(xs) - len(vals)
    if not vals:
        return {"n": 0, "n_missing": n_missing}
    out = {
        "n": len(vals),
        "n_missing": n_missing,
        "mean": sum(vals) / len(vals),
        "median": st.median(vals),
        "min": min(vals),
        "max": max(vals),
    }
    if len(vals) > 1:
        out["sd"] = st.stdev(vals)
        out["se_mean"] = out["sd"] / math.sqrt(len(vals))
    return out


def ols_slope(xs, ys):
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx


def boot_ci(values, rng, fn=None):
    """Percentile 95% interval for a statistic from resampling items with replacement."""
    n = len(values)
    draws = []
    for _ in range(BOOT_B):
        idx = [rng.randrange(n) for _ in range(n)]
        draws.append(fn(idx))
    draws = [d for d in draws if d is not None]
    draws.sort()
    lo = draws[int(0.025 * len(draws))]
    hi = draws[int(0.975 * len(draws)) - 1]
    return [lo, hi]


# ---------- evaluations ----------

def load_eval(run_dir, update):
    d = load_json(run_dir / f"development-{update:06d}.json")
    rows = d["evaluation"]["rows"]
    if len(rows) != 64:
        raise SystemExit(f"unexpected row count {len(rows)} for {update}")
    by_seed = {r["seed"]: r for r in rows}
    alive = {s: r["alive_frames"] for s, r in by_seed.items()}
    causes = Counter(r["death_cause"] for r in rows)
    vals = sorted(alive.values())
    perf = d["performance"]["alive_frames"]
    recomputed = {
        "mean": sum(vals) / len(vals),
        "Q1": sum(vals[:16]) / 16,
        "Q4": sum(vals[-16:]) / 16,
    }
    check_ok = all(abs(recomputed[k] - perf[k]) < 1e-9 for k in ("mean", "Q1", "Q4"))
    return {
        "update": update,
        "checkpoint_sha256": d["checkpoint_sha256"],
        "alive": alive,
        "perf_alive": perf,
        "recomputed_matches_reported": check_ok,
        "deaths": d["evaluation"]["deaths"],
        "caps": d["evaluation"]["caps"],
        "death_causes": {k: causes.get(k, 0) for k in
                         ["normal_enemy", "static_pattern_rect", "kamikaze_enemy",
                          "moving_pattern_rect", "kamikaze_explosion", "unknown", "unavailable"]},
        "raw_frames": d["evaluation"]["raw_frames"],
    }


def eval_block(run_dir, cands, label):
    evs = {u: load_eval(run_dir, u) for u in cands}
    seeds = sorted(evs[276]["alive"])
    out = {"candidates": {}, "paired_vs_276": {}, "tail_paired": {}}
    for u in cands:
        e = evs[u]
        out["candidates"][str(u)] = {
            "mean_alive": e["perf_alive"]["mean"],
            "Q1_alive": e["perf_alive"]["Q1"],
            "Q4_alive": e["perf_alive"]["Q4"],
            "recomputed_matches_reported": e["recomputed_matches_reported"],
            "deaths": e["deaths"],
            "caps": e["caps"],
            "death_causes": e["death_causes"],
            "raw_frames": e["raw_frames"],
            "checkpoint_sha256": e["checkpoint_sha256"],
        }
    return evs, seeds, out


def paired_block(evs, seeds, ref_u, cands):
    rng = random.Random(SEED)
    ref = evs[ref_u]["alive"]
    ref_vals = [ref[s] for s in seeds]
    ordered = sorted(seeds, key=lambda s: (ref[s], s))
    bottom16 = ordered[:16]
    top16 = ordered[-16:]
    res = {}
    for u in cands:
        if u == ref_u:
            continue
        c = evs[u]["alive"]
        diffs = [c[s] - ref[s] for s in seeds]
        md = sum(diffs) / len(diffs)
        ci = boot_ci(diffs, rng, fn=lambda idx: sum(diffs[i] for i in idx) / len(idx))
        res[str(u)] = {
            "mean_diff_vs_ref": md,
            "boot95_ci_mean_diff": ci,
            "improved_seeds": sum(1 for d in diffs if d > 0),
            "worsened_seeds": sum(1 for d in diffs if d < 0),
            "tied_seeds": sum(1 for d in diffs if d == 0),
            "bottom16_ref_seeds_mean_change": sum(c[s] - ref[s] for s in bottom16) / 16,
            "top16_ref_seeds_mean_change": sum(c[s] - ref[s] for s in top16) / 16,
            "bottom16_ref_seeds_cand_mean": sum(c[s] for s in bottom16) / 16,
            "top16_ref_seeds_cand_mean": sum(c[s] for s in top16) / 16,
        }
    return res, ref_vals


def trend_block(evs, seeds, cands):
    xs = [u for u in cands]
    rng = random.Random(SEED + 1)
    means = [mean([evs[u]["alive"][s] for s in seeds]) for u in cands]
    slope = ols_slope(xs, means)

    def slope_for_idx(idx):
        ms = []
        for u in cands:
            a = evs[u]["alive"]
            ms.append(sum(a[seeds[i]] for i in idx) / len(idx))
        return ols_slope(xs, ms)

    ci = boot_ci(seeds, rng, fn=slope_for_idx)
    return {"slope_alive_per_update": slope, "boot95_ci_slope": ci,
            "candidate_means": dict(zip(map(str, cands), means))}


# ---------- training series ----------

def series(rows):
    out = []
    for r in rows:
        m = r["metrics"]
        cd = m.get("critic_diagnostics", {})
        pre = cd.get("pre_update", {})
        post = cd.get("post_update", {})
        ga = m.get("gradient_alignment_diagnostics", {})
        g = ga.get("groups", {})
        ek = m.get("epoch_approx_kls") or []

        def gg(name, key):
            return g.get(name, {}).get(key)

        out.append({
            "phase_update": r["phase_update"],
            "ev_pre": pre.get("explained_variance"),
            "ev_post": post.get("explained_variance"),
            "ev_logged_top": m.get("explained_variance"),
            "target_var_pre": pre.get("target_variance"),
            "target_var_post": post.get("target_variance"),
            "target_mean_pre": pre.get("target_mean"),
            "resid_var_pre": pre.get("residual_variance"),
            "resid_var_post": post.get("residual_variance"),
            "resid_mse_pre": pre.get("residual_mse"),
            "resid_mse_post": post.get("residual_mse"),
            "resid_mean_pre": pre.get("residual_mean"),
            "pred_var_pre": pre.get("prediction_variance"),
            "pred_var_post": post.get("prediction_variance"),
            "mean_abs_value_change": cd.get("mean_absolute_value_change"),
            "rms_value_change": cd.get("rms_value_change"),
            "approx_kl_last_epoch": m.get("approx_kl"),
            "approx_kl_max_epoch": max(ek) if ek else None,
            "clip_fraction": m.get("clip_fraction"),
            "entropy": m.get("entropy"),
            "epochs_completed": m.get("epochs_completed"),
            "early_stop_kl": m.get("early_stop_kl"),
            "optimizer_steps": m.get("optimizer_steps"),
            "transitions": m.get("transitions"),
            "actor_grad_norm": m.get("actor_grad_norm"),
            "critic_grad_norm": m.get("critic_grad_norm"),
            "trunk_grad_norm": m.get("trunk_grad_norm"),
            "grad_norm": m.get("grad_norm"),
            "policy_loss": m.get("policy_loss"),
            "value_loss": m.get("value_loss"),
            "ga_defined": ga.get("defined"),
            "ga_cos": ga.get("cosine"),
            "ga_dot": ga.get("dot"),
            "ga_actor_norm": ga.get("actor_norm"),
            "ga_weighted_critic_norm": ga.get("weighted_critic_norm"),
            "ga_ratio": ga.get("norm_ratio_critic_over_actor"),
            "ga_live_clip_coef": ga.get("live_clip_coefficient"),
            "ga_live_preclip_norm": ga.get("live_preclip_grad_norm"),
            "ga_probe_count": ga.get("probe_count"),
            "ga_minibatch_count": ga.get("minibatch_count"),
            "ga_coverage_elements": ga.get("coverage", {}).get("elements"),
            "cos_embeddings": gg("embeddings_and_input_projections", "cosine"),
            "cos_final_norm": gg("final_norm", "cosine"),
            "cos_layers0": gg("layers.0", "cosine"),
            "cos_layers1": gg("layers.1", "cosine"),
            "ratio_embeddings": gg("embeddings_and_input_projections", "norm_ratio_critic_over_actor"),
            "ratio_final_norm": gg("final_norm", "norm_ratio_critic_over_actor"),
            "ratio_layers0": gg("layers.0", "norm_ratio_critic_over_actor"),
            "ratio_layers1": gg("layers.1", "norm_ratio_critic_over_actor"),
        })
    return out


SERIES_KEYS = [
    "ev_pre", "ev_post", "target_var_pre", "target_mean_pre", "resid_var_pre", "resid_var_post",
    "resid_mse_pre", "resid_mse_post", "resid_mean_pre", "pred_var_pre", "pred_var_post",
    "mean_abs_value_change", "rms_value_change", "approx_kl_last_epoch", "approx_kl_max_epoch",
    "clip_fraction", "entropy", "epochs_completed", "optimizer_steps", "actor_grad_norm",
    "critic_grad_norm", "trunk_grad_norm", "grad_norm", "policy_loss", "value_loss",
    "ga_cos", "ga_dot", "ga_actor_norm", "ga_weighted_critic_norm", "ga_ratio",
    "ga_live_clip_coef", "ga_live_preclip_norm", "cos_embeddings", "cos_final_norm",
    "cos_layers0", "cos_layers1", "ratio_embeddings", "ratio_final_norm", "ratio_layers0",
    "ratio_layers1",
]


def angle_bound_deg(ratio, cos):
    """Max rotation (deg) of ga+gc away from ga, given ||gc||/||ga||=ratio and angle(ga,gc) from cos."""
    if ratio is None or cos is None:
        return None
    s = math.sqrt(max(0.0, 1.0 - cos * cos))
    x = min(1.0, ratio * s)
    return math.degrees(math.asin(x))


def phase_bins(rows, n_bins=3):
    n = len(rows)
    size = n // n_bins
    bins = []
    for b in range(n_bins):
        lo = b * size
        hi = n if b == n_bins - 1 else (b + 1) * size
        bins.append((lo, hi))
    return bins


def training_block(rows, label):
    ser = series(rows)
    bins = phase_bins(ser)
    names = [f"{lo}-{hi - 1}" for lo, hi in bins]
    out = {"n_updates": len(ser), "phase_range": [ser[0]["phase_update"], ser[-1]["phase_update"]],
           "bins_local_index": names, "by_bin": {}, "trend_per_update": {}, "cosine": {}}
    rng = random.Random(SEED + 2)
    for key in SERIES_KEYS:
        out["by_bin"][key] = []
        for lo, hi in bins:
            out["by_bin"][key].append(safe_stats([r[key] for r in ser[lo:hi]]))
        xs = [i for i, r in enumerate(ser) if r[key] is not None]
        ys = [ser[i][key] for i in xs]
        if len(xs) > 3:
            slope = ols_slope(xs, ys)

            def slope_idx(idx, xs=xs, ys=ys):
                px = [xs[i] for i in idx]
                py = [ys[i] for i in idx]
                if len(set(px)) < 2:
                    return None
                return ols_slope(px, py)

            ci = boot_ci(list(range(len(xs))), rng, fn=slope_idx)
            ups = sum(1 for a, b in zip(ys, ys[1:]) if b > a)
            downs = sum(1 for a, b in zip(ys, ys[1:]) if b < a)
            out["trend_per_update"][key] = {"ols_slope": slope, "boot95_ci": ci,
                                            "consecutive_rises": ups, "consecutive_falls": downs}
    # cosine distribution (one probe per update, first minibatch of epoch 0)
    cos = [r["ga_cos"] for r in ser if r["ga_cos"] is not None]
    neg = [c for c in cos if c < 0]
    out["cosine"] = {
        "n": len(cos),
        "n_undefined_or_missing": len(ser) - len(cos),
        "mean": sum(cos) / len(cos),
        "median": st.median(cos),
        "min": min(cos),
        "max": max(cos),
        "se_mean": st.stdev(cos) / math.sqrt(len(cos)),
        "frac_negative": len(neg) / len(cos),
        "n_negative": len(neg),
        "mean_of_negatives": (sum(neg) / len(neg)) if neg else None,
        "n_near_zero_abs_lt_0.05": sum(1 for c in cos if abs(c) < NEAR_ZERO),
        "n_strong_negative_lt_-0.10": sum(1 for c in cos if c < STRONG_NEG),
        "n_strong_positive_gt_0.10": sum(1 for c in cos if c > -STRONG_NEG),
        "bands_note": "descriptive bands only, not thresholds",
    }
    ang = [angle_bound_deg(r["ga_ratio"], r["ga_cos"]) for r in ser]
    ang = [a for a in ang if a is not None]
    out["cosine"]["critic_rotation_bound_deg"] = safe_stats(ang)
    out["cosine"]["critic_rotation_bound_note"] = (
        "max angle between (actor+weighted critic) and actor on the probed shared params, "
        "from norm ratio and cosine; a bound on directional effect, not a measured step change")
    # clip and optimizer stats
    coefs = [r["ga_live_clip_coef"] for r in ser if r["ga_live_clip_coef"] is not None]
    out["live_clip"] = {
        "n": len(coefs),
        "frac_updates_probe_clipped_lt_1": sum(1 for c in coefs if c < 1.0) / len(coefs) if coefs else None,
        "clip_coef": safe_stats(coefs),
    }
    out["early_stop_kl_count"] = sum(1 for r in ser if r["early_stop_kl"])
    out["optimizer_steps_total"] = sum((r["optimizer_steps"] or 0) for r in ser)
    out["transitions_total"] = sum((r["transitions"] or 0) for r in ser)
    out["epochs_completed_hist"] = dict(Counter(r["epochs_completed"] for r in ser))
    out["probe_count_hist"] = dict(Counter(r["ga_probe_count"] for r in ser))
    out["minibatch_count_hist"] = dict(Counter(r["ga_minibatch_count"] for r in ser))
    out["ga_coverage_elements_hist"] = dict(Counter(r["ga_coverage_elements"] for r in ser))
    return out


def main():
    # training
    m204 = load_jsonl(RUN204 / "training-metrics.jsonl")
    m276 = load_jsonl(RUN276 / "training-metrics.jsonl")
    lr204 = load_json(RUN204 / "lr-transition.json")
    lr276 = load_json(RUN276 / "effective-learning-rate.json")
    cfg = load_json(PREP276 / "continuation-config.json")
    aud204 = load_json(AUD204 / "full-audit.json")
    aud276 = load_json(AUD276 / "full-audit.json")
    rep204 = read_bytes_hashed(AUD204 / "report.md")
    for name in ["artifact-manifest.json", "execution-result.json", "worker-result.json", "entry-restoration.json"]:
        read_bytes_hashed(RUN204 / name)
        read_bytes_hashed(RUN276 / name)
    for name in ["full-audit.log", "audit-invocation.json"]:
        if (AUD276 / name).exists():
            read_bytes_hashed(AUD276 / name)
    read_bytes_hashed(AUD204 / "parent-terminal-receipt.json")
    read_bytes_hashed(AUD204 / "retained-best-selection.json")
    for p in EXISTING:
        read_bytes_hashed(p)
    for run in (RUN204, RUN276):
        for u in (CAND204 if run == RUN204 else CAND276):
            read_bytes_hashed(run / f"development-{u:06d}.json")

    # evaluations
    ev204, seeds204, out204 = eval_block(RUN204, CAND204, "run204")
    ev276, seeds276, out276 = eval_block(RUN276, CAND276, "run276")
    same_seed_set = seeds204 == seeds276
    shared_276_identical = ev204[276]["alive"] == ev276[276]["alive"]
    cross_ref = {
        "same_64_seed_set": same_seed_set,
        "rerun_276_alive_identical_to_204run_276": shared_276_identical,
        "ref204_276_mean": ev204[276]["perf_alive"]["mean"],
        "run276_entry_276_mean": ev276[276]["perf_alive"]["mean"],
    }

    # paired comparisons
    p204, ref204_vals = paired_block(ev204, seeds204, 276, CAND204)
    p276, ref276_vals = paired_block(ev276, seeds276, 276, CAND276)
    out204["paired_vs_276"] = p204
    out276["paired_vs_276"] = p276
    # bottom/top16 descriptive for 276's own tails
    out204["trend"] = trend_block(ev204, seeds204, CAND204)
    out276["trend"] = trend_block(ev276, seeds276, CAND276)
    # 288-348 pooled, to estimate what the 276 value would look like without its selection
    post_means = [out276["candidates"][str(u)]["mean_alive"] for u in CAND276[1:]]
    out276["post_276_candidates_mean_of_means"] = sum(post_means) / len(post_means)
    out276["post_276_candidates_sd_of_means"] = st.stdev(post_means)
    out276["candidate_276_minus_post_mean"] = (
        out276["candidates"]["276"]["mean_alive"] - out276["post_276_candidates_mean_of_means"])
    # best-of-7 check in run204 (276 selected as max in its own sweep)
    means204 = {u: out204["candidates"][str(u)]["mean_alive"] for u in CAND204}
    out204["max_candidate"] = max(means204, key=means204.get)

    # training
    t204 = training_block(m204, "run204")
    t276 = training_block(m276, "run276")

    # ---- consistency checks ----
    checks = {
        "run204_phase_range": t204["phase_range"],
        "run276_phase_range": t276["phase_range"],
        "run204_optimizer_steps_total": t204["optimizer_steps_total"],
        "run276_optimizer_steps_total": t276["optimizer_steps_total"],
        "run204_ev_logged_equals_pre": sum(
            1 for r in series(m204) if r["ev_logged_top"] is not None and r["ev_pre"] is not None
            and abs(r["ev_logged_top"] - r["ev_pre"]) < 1e-6),
        "run276_ev_logged_equals_pre": sum(
            1 for r in series(m276) if r["ev_logged_top"] is not None and r["ev_pre"] is not None
            and abs(r["ev_logged_top"] - r["ev_pre"]) < 1e-6),
        "lr_history": {
            "run204_lr_transition_before_after": lr204["actual_group_lr_delta"],
            "run276_effective_lr": lr276["restored_group_lrs"],
            "run276_config_learning_rate": cfg["ppo"]["learning_rate"],
        },
        "aud204_all_candidates_recomputed_matches": all(
            out204["candidates"][str(u)]["recomputed_matches_reported"] for u in CAND204),
        "aud276_all_candidates_recomputed_matches": all(
            out276["candidates"][str(u)]["recomputed_matches_reported"] for u in CAND276),
        "aud204_authority_flags": aud204["authority"],
        "aud276_authority_flags": aud276["authority"],
    }

    metrics = {
        "schema": "d2_retained276_348_plateau_metrics_v1",
        "analysis_script": "analyze.py",
        "bootstrap": {"draws": BOOT_B, "seed": SEED, "unit": "seed (eval) or update (training)"},
        "descriptive_bands": {"near_zero_abs_cos": NEAR_ZERO, "strong_negative_cos": STRONG_NEG,
                              "note": "descriptive only, not thresholds"},
        "cross_run_checks": cross_ref,
        "eval_run204_lineage_204_to_276": out204,
        "eval_run276_continuation_276_to_348": out276,
        "training_run204_204_to_276": t204,
        "training_run276_276_to_348": t276,
        "checks": checks,
        "continuation_config_ppo": cfg["ppo"],
        "continuation_config_device": cfg["device"],
        "continuation_config_rollout_steps": cfg["rollout_steps"],
        "continuation_config_batch_size": cfg["batch_size"],
    }
    mpath = HERE / "metrics.json"
    text = json.dumps(metrics, indent=1, sort_keys=True, default=lambda o: None)
    mpath.write_text(text + "\n")
    receipt = {
        "schema": "d2_retained276_348_plateau_diagnosis_receipt_v1",
        "role": "research sub-agent, read-only analysis",
        "status": "analysis_complete_no_training_no_eval_no_state_change",
        "inputs_sha256": INPUTS,
        "outputs_sha256": {
            "metrics.json": hashlib.sha256(mpath.read_bytes()).hexdigest(),
        },
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "scope_limits": [
            "Development-cohort (64 fixed seeds) only; no held-out evaluation.",
            "Training gradient probe is one minibatch per update (ga probe_count=1), CPU shadow, not live MPS.",
            "No causal attribution is made; all cross-run comparisons are observational.",
        ],
    }
    Path(HERE / "receipt.json").write_text(json.dumps(receipt, indent=1, sort_keys=True) + "\n")
    print("wrote", mpath.name, "and receipt.json; inputs hashed:", len(INPUTS))


if __name__ == "__main__":
    main()
