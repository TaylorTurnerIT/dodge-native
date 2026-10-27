#!/usr/bin/env python3
"""Survival-loss decomposition: D2 best 180 vs latest 252 on 64 fixed development seeds.

Read-only over frozen artifacts. Stdlib only. Run as: python3 -I analyze.py
Writes analysis.json and receipt.json beside this file. With --finalize, adds the
diagnosis hash to receipt.json after concisediagnosis.md is written.
No checkpoint load, no environment steps, no gradients, no training.
"""
import hashlib
import json
import math
import os
import platform
import random
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
B = 10000
BOOT_SEED = 20261026
RUN_ID = "survival-loss-decomposition-haiku-20261026-r1"
CAUSES = ["normal_enemy", "kamikaze_enemy", "kamikaze_explosion",
          "moving_pattern_rect", "static_pattern_rect", "unknown"]

INPUTS = {
    "best_jsonl": "learning/runs/v2/D2-gradient-alignment-20261025-r2/development-000180.jsonl",
    "latest_jsonl": "learning/runs/v2/D2-continuation-20261025-r2/development-000252.jsonl",
    "best_json": "learning/runs/v2/D2-gradient-alignment-20261025-r2/development-000180.json",
    "latest_json": "learning/runs/v2/D2-continuation-20261025-r2/development-000252.json",
    "reconciliation": "learning/runs/v2/d2-continuation252-parent-terminal-audit-20261026-r1/analysis-reconciliation.json",
    "prior_analysis": "learning/runs/v2/D2-252-regression-analysis-haiku-20261026-r1/analysis.json",
    "prior_diagnosis": "learning/runs/v2/D2-252-regression-analysis-haiku-20261026-r1/diagnosis.md",
    "prior_receipt": "learning/runs/v2/D2-252-regression-analysis-haiku-20261026-r1/receipt.json",
    "impl_plan": "docs/implementation-plan-v2.md",
    "spec": "docs/SPEC_PRIVILEGED_VIT_RL.md",
}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def rel(p):
    return os.path.join(ROOT, p)


def load_jsonl(path):
    with open(path, encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    assert len(rows) == 64, (path, len(rows))
    by_seed = {r["seed"]: r for r in rows}
    assert len(by_seed) == 64, "duplicate seeds"
    return by_seed


def mean(x):
    x = list(x)
    return sum(x) / len(x)


def median(x):
    s = sorted(x)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def q_means(vals):
    """Bottom-16 and top-16 means of sorted values (not percentiles)."""
    s = sorted(vals)
    return mean(s[:16]), mean(s[-16:])


def solve(M, v):
    n = len(v)
    A = [row[:] + [v[i]] for i, row in enumerate(M)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(A[r][c]))
        A[c], A[p] = A[p], A[c]
        for r in range(n):
            if r != c:
                f = A[r][c] / A[c][c]
                for k in range(c, n + 1):
                    A[r][k] -= f * A[c][k]
    return [A[i][n] / A[i][i] for i in range(n)]


def ols_common_slope(obs):
    """obs: list of (group 0|1, score, alive). Model alive = a_g + b*score."""
    XtX = [[0.0] * 3 for _ in range(3)]
    Xty = [0.0] * 3
    for g, s, y in obs:
        x = [1.0 if g == 0 else 0.0, 1.0 if g == 1 else 0.0, s]
        for i in range(3):
            Xty[i] += x[i] * y
            for j in range(3):
                XtX[i][j] += x[i] * x[j]
    a0, a1, b = solve(XtX, Xty)
    return a0, a1, b


def boot(stat, n):
    """Paired seed bootstrap: resample seed indices with replacement."""
    rng = random.Random(BOOT_SEED)
    draws = sorted(stat([rng.randrange(n) for _ in range(n)]) for _ in range(B))
    return {"lo95": draws[int(0.025 * B)], "hi95": draws[min(int(0.975 * B), B - 1)],
            "se": (sum((d - mean(draws)) ** 2 for d in draws) / (B - 1)) ** 0.5}


def sign_test_p(k, n):
    """Exact two-sided binomial p for k of n non-tied pairs in the smaller tail."""
    lo = min(k, n - k)
    tail = sum(math.comb(n, i) for i in range(lo + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def hyper_le(k, N, K, n):
    """P(X <= k), X ~ Hypergeometric(N population, K successes, n draws)."""
    return sum(math.comb(K, x) * math.comb(N - K, n - x) for x in range(0, k + 1)) / math.comb(N, n)


def finalize():
    rec_path = os.path.join(HERE, "receipt.json")
    with open(rec_path, encoding="utf-8") as f:
        rec = json.load(f)
    rec["output_sha256"]["concisediagnosis.md"] = sha256(os.path.join(HERE, "concisediagnosis.md"))
    rec["output_sha256"]["analyze.py"] = sha256(os.path.abspath(__file__))
    with open(rec_path, "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=2)
        f.write("\n")
    print(json.dumps(rec["output_sha256"], indent=2))


def main():
    best = load_jsonl(rel(INPUTS["best_jsonl"]))
    latest = load_jsonl(rel(INPUTS["latest_jsonl"]))
    seeds = sorted(best)
    assert seeds == sorted(latest), "seed sets differ"
    A = [best[s] for s in seeds]
    Bc = [latest[s] for s in seeds]

    # --- integrity checks ---
    ident = {}
    for name, rows in (("best", A), ("latest", Bc)):
        res = [abs(r["objective_return"] - (0.01 * r["alive_frames"] + r["score"] - 5.0)) for r in rows]
        ident[name] = {
            "objective_return_equals_0p01_alive_plus_score_minus_5_max_abs_resid": max(res),
            "gameplay_frames_eq_alive_plus_1": all(r["gameplay_frames"] == r["alive_frames"] + 1 for r in rows),
            "fatal_frame_eq_gameplay_frames": all(r["fatal_gameplay_frame"] == r["gameplay_frames"] for r in rows),
            "all_terminated_not_truncated": all(r["terminated"] and not r["truncated"] for r in rows),
            "lethal_contact_sum_not_one": sum(
                1 for r in rows if sum(r["death_observed_lethal_contacts"].values()) != 1),
            "cause_matches_single_contact": sum(
                1 for r in rows if r["death_observed_lethal_contacts"].get(r["death_cause"], 0) != 1),
        }

    a_alive = [r["alive_frames"] for r in A]
    b_alive = [r["alive_frames"] for r in Bc]
    a_score = [r["score"] for r in A]
    b_score = [r["score"] for r in Bc]
    a_ret = [r["objective_return"] for r in A]
    b_ret = [r["objective_return"] for r in Bc]

    # --- per-checkpoint summary ---
    def summ(rows):
        alive = [r["alive_frames"] for r in rows]
        score = [r["score"] for r in rows]
        ret = [r["objective_return"] for r in rows]
        q1, q4 = q_means(alive)
        cnt = Counter(r["death_cause"] for r in rows)
        by_cause_alive = {}
        by_cause_score = {}
        for c in CAUSES:
            sel = [r for r in rows if r["death_cause"] == c]
            by_cause_alive[c] = mean(r["alive_frames"] for r in sel) if sel else None
            by_cause_score[c] = mean(r["score"] for r in sel) if sel else None
        return {
            "n": len(rows), "mean_alive": mean(alive), "median_alive": median(alive),
            "q1_bottom16_mean": q1, "q4_top16_mean": q4,
            "mean_score": mean(score), "median_score": median(score),
            "mean_objective_return": mean(ret),
            "mean_survival_term_0p01_per_frame": mean(0.01 * x for x in alive),
            "mean_score_term": mean(score),
            "death_term": -5.0,
            "death_cause_counts": {c: cnt.get(c, 0) for c in CAUSES},
            "mean_alive_by_cause": by_cause_alive,
            "mean_score_by_cause": by_cause_score,
        }

    summary = {"best_180": summ(A), "latest_252": summ(Bc)}

    # --- paired changes (252 minus 180, same seed) ---
    d_alive = [y - x for x, y in zip(a_alive, b_alive)]
    d_score = [y - x for x, y in zip(a_score, b_score)]
    d_ret = [y - x for x, y in zip(a_ret, b_ret)]
    d_surv = [0.01 * d for d in d_alive]

    def pstats(d):
        n_imp = sum(1 for x in d if x > 0)
        n_wor = sum(1 for x in d if x < 0)
        n_tie = len(d) - n_imp - n_wor
        return {"mean": mean(d), "median": median(d), "improved": n_imp, "worsened": n_wor, "tied": n_tie,
                "sign_test_two_sided_p": sign_test_p(n_imp, n_imp + n_wor)}

    paired = {
        "alive_frames": pstats(d_alive),
        "score": pstats(d_score),
        "objective_return": pstats(d_ret),
        "survival_term": pstats(d_surv),
    }
    paired["alive_frames"]["boot_mean_ci"] = boot(lambda idx: mean(d_alive[i] for i in idx), 64)
    paired["score"]["boot_mean_ci"] = boot(lambda idx: mean(d_score[i] for i in idx), 64)
    paired["objective_return"]["boot_mean_ci"] = boot(lambda idx: mean(d_ret[i] for i in idx), 64)
    paired["survival_term"]["boot_mean_ci"] = boot(lambda idx: mean(d_surv[i] for i in idx), 64)

    # return decomposition: mean drop = survival part + score part
    decomp = {
        "mean_return_change": mean(d_ret),
        "from_survival_term": mean(d_surv),
        "from_score_term": mean(d_score),
    }

    # --- contribution of largest per-seed losses ---
    order = sorted(range(64), key=lambda i: d_alive[i])
    gross_loss = sum(-x for x in d_alive if x < 0)
    gross_gain = sum(x for x in d_alive if x > 0)
    net = sum(d_alive)
    worst8 = sum(d_alive[i] for i in order[:8])
    worst16 = sum(d_alive[i] for i in order[:16])
    rest48 = net - worst16
    contrib = {
        "net_sum_alive_frames": net,
        "gross_loss_sum": gross_loss,
        "gross_gain_sum": gross_gain,
        "worst8_sum": worst8,
        "worst16_sum": worst16,
        "rest48_sum": rest48,
        "worst16_share_of_gross_loss": worst16 / -gross_loss if gross_loss else None,
        "mean_excluding_worst8_losers": mean(d_alive[i] for i in order[8:]),
        "mean_excluding_worst16_losers": mean(d_alive[i] for i in order[16:]),
        "worst10": [
            {"seed": seeds[i], "alive_180": a_alive[i], "alive_252": b_alive[i], "delta": d_alive[i],
             "cause_180": A[i]["death_cause"], "cause_252": Bc[i]["death_cause"]}
            for i in order[:10]
        ],
    }

    # --- first fatal cause transitions (per-policy, same env seed) ---
    trans = Counter((A[i]["death_cause"], Bc[i]["death_cause"]) for i in range(64))
    changed = [i for i in range(64) if A[i]["death_cause"] != Bc[i]["death_cause"]]
    by_new_cause = {}
    for c in CAUSES:
        idx = [i for i in changed if Bc[i]["death_cause"] == c]
        if idx:
            by_new_cause[c] = {"n_changed_into": len(idx),
                               "median_delta_alive": median(d_alive[i] for i in idx),
                               "mean_delta_alive": mean(d_alive[i] for i in idx)}
    transitions = {
        "changed_cause_count": len(changed),
        "matrix_180_to_252": {f"{a}->{b}": n for (a, b), n in sorted(trans.items())},
        "changed_grouped_by_252_cause": by_new_cause,
    }

    # --- Q1/Q4 membership overlap ---
    ord_a = sorted(range(64), key=lambda i: (a_alive[i], seeds[i]))
    ord_b = sorted(range(64), key=lambda i: (b_alive[i], seeds[i]))
    bot_a, top_a = set(ord_a[:16]), set(ord_a[-16:])
    bot_b, top_b = set(ord_b[:16]), set(ord_b[-16:])
    membership = {
        "bottom16_overlap": len(bot_a & bot_b),
        "bottom16_left": len(bot_a - bot_b),
        "bottom16_entered": len(bot_b - bot_a),
        "bottom16_overlap_P_le_observed_under_independence": hyper_le(len(bot_a & bot_b), 64, 16, 16),
        "top16_overlap": len(top_a & top_b),
        "top16_left": len(top_a - top_b),
        "top16_entered": len(top_b - top_a),
        "top16_overlap_P_le_observed_under_independence": hyper_le(len(top_a & top_b), 64, 16, 16),
        "expected_overlap_under_independence": 16 * 16 / 64,
        "boundary_ties_180": {
            "value_at_bottom16_edge": a_alive[ord_a[15]],
            "count_equal_to_edge": sum(1 for x in a_alive if x == a_alive[ord_a[15]]),
            "value_at_top16_edge": a_alive[ord_a[-16]],
            "count_equal_to_edge": sum(1 for x in a_alive if x == a_alive[ord_a[-16]]),
        },
        "boundary_ties_252": {
            "value_at_bottom16_edge": b_alive[ord_b[15]],
            "count_equal_to_edge": sum(1 for x in b_alive if x == b_alive[ord_b[15]]),
            "value_at_top16_edge": b_alive[ord_b[-16]],
            "count_equal_to_edge": sum(1 for x in b_alive if x == b_alive[ord_b[-16]]),
        },
    }

    # --- descriptive strata (not causal) ---
    def stratum(idx_list, label):
        if not idx_list:
            return {"label": label, "n": 0}
        return {"label": label, "n": len(idx_list),
                "mean_alive_180": mean(a_alive[i] for i in idx_list),
                "mean_alive_252": mean(b_alive[i] for i in idx_list),
                "mean_delta_alive": mean(d_alive[i] for i in idx_list),
                "mean_score_180": mean(a_score[i] for i in idx_list),
                "mean_score_252": mean(b_score[i] for i in idx_list),
                "improved": sum(1 for i in idx_list if d_alive[i] > 0),
                "worsened": sum(1 for i in idx_list if d_alive[i] < 0)}

    strata = {
        "by_180_alive_membership": [
            stratum(ord_a[:16], "180 bottom16"),
            stratum(ord_a[16:48], "180 middle32"),
            stratum(ord_a[48:], "180 top16"),
        ],
        "by_180_score": [
            stratum([i for i in range(64) if a_score[i] < 5], "180 score<5"),
            stratum([i for i in range(64) if 5 <= a_score[i] < 15], "180 score 5-<15"),
            stratum([i for i in range(64) if a_score[i] >= 15], "180 score>=15"),
        ],
        "by_252_score": [
            stratum([i for i in range(64) if b_score[i] < 5], "252 score<5"),
            stratum([i for i in range(64) if 5 <= b_score[i] < 15], "252 score 5-<15"),
            stratum([i for i in range(64) if b_score[i] >= 15], "252 score>=15"),
        ],
    }

    # --- score-matched survival: alive = a_g + b*score, shared slope ---
    obs = [(0, a_score[i], a_alive[i]) for i in range(64)] + [(1, b_score[i], b_alive[i]) for i in range(64)]
    a0, a1, slope = ols_common_slope(obs)
    matched = {"slope_alive_per_score_point": slope, "intercept_180": a0, "intercept_252": a1,
               "matched_score_alive_diff_252_minus_180": a1 - a0}

    def matched_stat(idx):
        ob = [(0, a_score[i], a_alive[i]) for i in idx] + [(1, b_score[i], b_alive[i]) for i in idx]
        x0, x1, _ = ols_common_slope(ob)
        return x1 - x0

    matched["boot_ci"] = boot(matched_stat, 64)

    # --- bootstrap for Q1/Q4 change (paired seeds) ---
    q1_chg = lambda idx: q_means([b_alive[i] for i in idx])[0] - q_means([a_alive[i] for i in idx])[0]
    q4_chg = lambda idx: q_means([b_alive[i] for i in idx])[1] - q_means([a_alive[i] for i in idx])[1]
    tail = {
        "q1_change_point": q_means(b_alive)[0] - q_means(a_alive)[0],
        "q1_change_boot_ci": boot(q1_chg, 64),
        "q4_change_point": q_means(b_alive)[1] - q_means(a_alive)[1],
        "q4_change_boot_ci": boot(q4_chg, 64),
    }

    # --- reproduce prior reconciliation values ---
    with open(rel(INPUTS["reconciliation"]), encoding="utf-8") as f:
        recon = json.load(f)
    point = mean(d_alive)
    prior_check = {
        "prior_observed_mean_change": recon["observed_fixed_cohort_mean_change"],
        "recomputed_mean_change": point,
        "matches_prior_mean_change": abs(recon["observed_fixed_cohort_mean_change"] - point) < 1e-9,
        "prior_percent_change": recon["observed_percent_change"],
        "recomputed_percent_change": 100.0 * point / mean(a_alive),
        "prior_bootstrap_ci_from_frozen_diagnosis": [-691, 176],
        "recomputed_bootstrap_ci": paired["alive_frames"]["boot_mean_ci"],
    }

    # --- carried prior EV/gradient numbers (quoted, NOT recomputed here) ---
    carried = {
        "note": "Quoted from frozen prior diagnosis.md / task brief. Not recomputed. No new gradient or EV evidence.",
        "ev_pre_update_first8_to_last8_child_181_252": [0.435, 0.460],
        "critic_mse_fits_improved": "72/72 (as reported)",
        "cpu_shadow_cosine_mean_child": 0.0101,
        "cpu_shadow_cosine_negative_count": "31/72",
        "vf_weighted_norm_ratio_mean_child": 0.0189,
        "causal_adam_preconditioned_claim": False,
    }

    analysis = {
        "run_id": RUN_ID,
        "schema": "survival-loss-decomposition-haiku.analysis.v1",
        "scope": "descriptive decomposition of paired 64-seed development endpoints; no held-out, population, or training-replicate claim",
        "integrity": ident,
        "summary": summary,
        "paired": paired,
        "return_decomposition": decomp,
        "loss_contribution": contrib,
        "death_transitions": transitions,
        "q_membership": membership,
        "strata_descriptive_only": strata,
        "score_matched_survival": matched,
        "q_tail_bootstrap": tail,
        "prior_reconciliation_check": prior_check,
        "carried_prior_findings": carried,
        "bootstrap": {"draws": B, "seed": BOOT_SEED, "method": "paired seed resampling with replacement, percentile 95%"},
    }
    out_path = os.path.join(HERE, "analysis.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(analysis, f, indent=2)
        f.write("\n")

    inputs_sha = {k: sha256(rel(p)) for k, p in INPUTS.items()}
    receipt = {
        "run_id": RUN_ID,
        "schema": "survival-loss-decomposition-haiku.receipt.v1",
        "command": "python3 -I learning/runs/v2/survival-loss-decomposition-haiku-20261026-r1/analyze.py",
        "interpreter": f"python3 -I (stdlib only), Python {platform.python_version()}",
        "bootstrap": analysis["bootstrap"],
        "input_paths_and_sha256": {p: inputs_sha[k] for k, p in INPUTS.items()},
        "script_sha256": sha256(os.path.abspath(__file__)),
        "output_sha256": {
            "analysis.json": sha256(out_path),
            "analyze.py": sha256(os.path.abspath(__file__)),
        },
        "not_performed": ["no Torch load", "no checkpoint load", "no environment steps",
                          "no gradient computation", "no training", "no edits outside this directory"],
        "writes": [
            f"learning/runs/v2/{RUN_ID}/analysis.json",
            f"learning/runs/v2/{RUN_ID}/receipt.json",
            f"learning/runs/v2/{RUN_ID}/concisediagnosis.md",
        ],
    }
    with open(os.path.join(HERE, "receipt.json"), "w", encoding="utf-8") as f:
        json.dump(receipt, f, indent=2)
        f.write("\n")
    print("wrote analysis.json and receipt.json")
    print(json.dumps({"mean_alive_change": point, "ci": paired["alive_frames"]["boot_mean_ci"],
                      "matched_diff": matched["matched_score_alive_diff_252_minus_180"],
                      "matched_ci": matched["boot_ci"], "membership": membership,
                      "decomp": decomp, "contrib": {k: v for k, v in contrib.items() if k != "worst10"}},
                     indent=2))


if __name__ == "__main__":
    if "--finalize" in sys.argv:
        finalize()
    else:
        main()
