"""Closed-data temporal-credit audit for the D2 retained-324 fixed/linear-LR pair.

Reads only JSON/JSONL certificates and frozen source text. Standard library only:
no torch, no runtime/native imports, no checkpoint binaries, no environment runs.

Usage: python3 -I horizon_audit.py
Writes evidence.json, dev-phases.csv, per-update.csv into this directory.
"""
import csv
import hashlib
import json
import math
import os
import random
import statistics as st

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
RUNS = os.path.join(REPO, "learning", "runs", "v2")
ARMS = {
    "fixed": "D2-retained324-continuation-20261026-r1",
    "linear": "D2-retained324-linear-lr-20261026-r1",
}
PHASES = [324, 336, 348, 360, 372, 384]
RUNTIME = os.path.join(RUNS, "D2-gradient-capsule-parent-freeze-20261025-r5", "own", "runtime", "dodge_rl")
SOURCE = [
    os.path.join(RUNTIME, "ppo.py"),
    os.path.join(RUNTIME, "critic_diagnostics.py"),
    os.path.join(RUNTIME, "gradient_alignment.py"),
    os.path.join(RUNTIME, "dev_eval.py"),
    os.path.join(RUNTIME, "models", "teacher.py"),
    os.path.join(REPO, "crates", "dodge-rl-env", "src", "env.rs"),
    os.path.join(REPO, "crates", "dodge-rl-env", "src", "config.rs"),
    os.path.join(REPO, "crates", "dodge-rl-env", "src", "features.rs"),
    os.path.join(REPO, "docs", "SPEC_PRIVILEGED_VIT_RL.md"),
    os.path.join(RUNS, "D2-retained324-linear-integrated-luna-20261026-r4", "registration-final-r2.json"),
    os.path.join(RUNS, "D2-retained324-linear-integrated-luna-20261026-r4", "lr_schedule.py"),
    os.path.join(RUNS, "D2-retained276-lr3em5-prepare-luna-20261026-r2", "D2-retained276-lr3em5-config.json"),
]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def quartile_group_mean(values):
    """runner.py:729 semantics: Q1/Q4 are means of the lowest/highest 16 of 64."""
    ordered = sorted(values)
    return sum(ordered[:16]) / 16, sum(ordered[-16:]) / 16


def main():
    dev, train, metrics = {}, {}, {}
    for arm, run in ARMS.items():
        dev[arm] = {}
        for p in PHASES:
            d = json.load(open(os.path.join(RUNS, run, "development-%06d.json" % p)))
            dev[arm][p] = d
        metrics[arm] = [json.loads(line) for line in open(os.path.join(RUNS, run, "training-metrics.jsonl"))]
        train[arm] = [json.loads(line) for line in open(os.path.join(RUNS, run, "training-episodes.jsonl"))]

    # --- development certificates -------------------------------------------------
    phases = []
    for arm in ARMS:
        for p in PHASES:
            e = dev[arm][p]["evaluation"]
            alive = [r["alive_frames"] for r in e["rows"]]
            q1, q4 = quartile_group_mean(alive)
            phases.append({
                "arm": arm, "phase_update": p, "local_update": p - 324,
                "checkpoint_sha256": dev[arm][p]["checkpoint_sha256"],
                "mean_alive_frames": e["mean_alive_frames"],
                "median_alive_frames": st.median(alive),
                "q1_group_mean": q1, "q4_group_mean": q4,
                "certificate_q1": dev[arm][p]["performance"]["alive_frames"]["Q1"],
                "certificate_q4": dev[arm][p]["performance"]["alive_frames"]["Q4"],
                "mean_score": e["mean_score"], "deaths": e["deaths"], "caps": e["caps"],
                "competence_passed": dev[arm][p]["competence_passed"],
            })
    with open(os.path.join(HERE, "dev-phases.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(phases[0]))
        w.writeheader()
        w.writerows(phases)

    paired = {}
    for p in PHASES:
        a = [r["alive_frames"] for r in dev["linear"][p]["evaluation"]["rows"]]
        b = [r["alive_frames"] for r in dev["fixed"][p]["evaluation"]["rows"]]
        diff = [x - y for x, y in zip(a, b)]
        paired[p] = {
            "mean_diff": st.mean(diff),
            "se": st.stdev(diff) / math.sqrt(len(diff)),
            "gains": sum(1 for d in diff if d > 0),
            "losses": sum(1 for d in diff if d < 0),
        }

    # within-arm change versus the shared 324 baseline
    within = {}
    for arm in ARMS:
        within[arm] = {}
        for p in PHASES[1:]:
            d = [x - y for x, y in zip(
                [r["alive_frames"] for r in dev[arm][p]["evaluation"]["rows"]],
                [r["alive_frames"] for r in dev[arm][324]["evaluation"]["rows"]])]
            within[arm][p] = {"mean": st.mean(d), "se": st.stdev(d) / 8, "t": st.mean(d) / (st.stdev(d) / 8)}

    # sustained: each seed's mean over the five post-baseline phases
    sustained = {}
    for arm in ARMS:
        per_seed = [st.mean([dev[arm][p]["evaluation"]["rows"][i]["alive_frames"] for p in PHASES[1:]])
                    for i in range(64)]
        sustained[arm] = (st.mean(per_seed), st.stdev(per_seed) / 8, per_seed)
    diff_sustained = [l - f for l, f in zip(sustained["linear"][2], sustained["fixed"][2])]

    # selection-aware null for the best post-baseline phase (seed bootstrap, phase means removed)
    rng = random.Random(20261026)
    null_max = []
    for arm in ARMS:
        centred = {p: [r["alive_frames"] - st.mean([x["alive_frames"] for x in dev[arm][p]["evaluation"]["rows"]])
                       for r in dev[arm][p]["evaluation"]["rows"]] for p in PHASES}
        for _ in range(20000):
            idx = [rng.randrange(64) for _ in range(64)]
            null_max.append((arm, max(sum(centred[p][i] for i in idx) / 64 for p in PHASES[1:])))
    sel_p = {}
    for arm in ARMS:
        obs = st.mean([r["alive_frames"] for r in dev[arm][348]["evaluation"]["rows"]]) - \
              st.mean([r["alive_frames"] for r in dev[arm][324]["evaluation"]["rows"]])
        draws = sorted(x for a, x in null_max if a == arm)
        sel_p[arm] = {
            "observed_348_minus_324": obs,
            "null_max_mean": st.mean(draws),
            "null_max_p95": draws[int(0.95 * len(draws))],
            "p_max_ge_observed": sum(1 for x in draws if x >= obs) / len(draws),
        }

    blocks = {}
    for p in (348, 384):
        blocks[p] = []
        for b in range(4):
            sl = range(b * 16, (b + 1) * 16)
            between = st.mean([dev["linear"][p]["evaluation"]["rows"][i]["alive_frames"] -
                               dev["fixed"][p]["evaluation"]["rows"][i]["alive_frames"] for i in sl])
            within_b = st.mean([dev["linear"][p]["evaluation"]["rows"][i]["alive_frames"] -
                                dev["linear"][324]["evaluation"]["rows"][i]["alive_frames"] for i in sl])
            blocks[p].append({"block": b, "between_arm": between, "linear_vs_324": within_b})

    # --- training episodes --------------------------------------------------------
    episodes = {}
    for arm in ARMS:
        comp = [r["info"] for r in train[arm] if r.get("kind") == "completed"]
        frames = sorted(i["gameplay_frames"] for i in comp)
        deaths = {}
        for i in comp:
            deaths[i.get("death_cause")] = deaths.get(i.get("death_cause"), 0) + 1
        episodes[arm] = {
            "completed": len(comp),
            "terminated": sum(1 for i in comp if i["terminated"]),
            "truncated": sum(1 for i in comp if i["truncated"]),
            "abandoned_parent_episodes": sum(1 for r in train[arm] if r.get("kind") == "abandoned_parent_episode"),
            "frames_mean": st.mean(frames), "frames_median": st.median(frames),
            "frames_p95": frames[int(0.95 * (len(frames) - 1))], "frames_max": max(frames),
            "decisions_mean": st.mean(frames) / 4, "decisions_median": st.median(frames) / 4,
            "score_per_frame": sum(i["score"] for i in comp) / sum(frames),
            "objective_mean": st.mean([i["objective_return"] for i in comp]),
            "death_causes": deaths,
            "episodes_per_update": len(comp) / 60,
        }

    # --- per-update metrics -------------------------------------------------------
    rows = []
    for lu in range(60):
        row = {"local_update": lu + 1, "phase_update": 325 + lu}
        for arm in ARMS:
            m = metrics[arm][lu]
            cd = m["metrics"]["critic_diagnostics"]
            row["%s_ev_pre" % arm] = cd["pre_update"]["explained_variance"]
            row["%s_ev_post" % arm] = cd["post_update"]["explained_variance"]
            row["%s_target_var" % arm] = cd["pre_update"]["target_variance"]
            row["%s_target_mean" % arm] = cd["pre_update"]["target_mean"]
            row["%s_pred_var" % arm] = cd["pre_update"]["prediction_variance"]
            row["%s_entropy" % arm] = m["metrics"]["entropy"]
            row["%s_kl" % arm] = m["metrics"]["approx_kl"]
            row["%s_clip" % arm] = m["metrics"]["clip_fraction"]
            row["%s_value_loss" % arm] = m["metrics"]["value_loss"]
            row["%s_actor_gn" % arm] = m["metrics"]["actor_grad_norm"]
            row["%s_critic_gn" % arm] = m["metrics"]["critic_grad_norm"]
            ga = m["metrics"]["gradient_alignment_diagnostics"]
            row["%s_cos" % arm] = ga["cosine"]
            row["%s_norm_ratio" % arm] = ga["norm_ratio_critic_over_actor"]
            lrs = m.get("optimizer_group_lrs")
            row["%s_lr" % arm] = lrs[0] if lrs else "not_recorded"
        rows.append(row)
    with open(os.path.join(HERE, "per-update.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    # --- horizon arithmetic -------------------------------------------------------
    gamma, lam, repeat, reward_scale = 0.995, 0.95, 4, 0.1
    gl = gamma * lam
    score_rate = episodes["linear"]["score_per_frame"]
    # unscaled reward per decision: alive 0.01/frame plus score, both over K=4 frames
    per_decision = (0.01 + score_rate) * repeat * reward_scale
    horizon = {
        "gamma_per_decision": gamma,
        "gamma_horizon_decisions": 1 / (1 - gamma),
        "gamma_horizon_raw_frames": repeat / (1 - gamma),
        "gae_trace_sum_decisions": 1 / (1 - gl),
        "gae_trace_sum_raw_frames": repeat / (1 - gl),
        "gae_half_life_decisions": math.log(0.5) / math.log(gl),
        "gae_half_life_raw_frames": repeat * math.log(0.5) / math.log(gl),
        "lambda_gamma": gl,
        "learner_reward_per_decision": per_decision,
        "alive_only_reward_per_decision": 0.01 * reward_scale,
        "death_penalty_learner_units": -5.0 * reward_scale,
        "death_weight_by_distance": {str(k): -5.0 * reward_scale * gl ** k
                                     for k in (0, 5, 10, 18, 25, 50, 100, 200, 375, 750)},
        "value_of_survival": {},
    }
    for frames in (500, 1000, 2000, 3000, 4000, 6000, 8000, 18000):
        t = frames / repeat
        horizon["value_of_survival"][str(frames)] = per_decision * (1 - gamma ** t) / (1 - gamma) \
            - 5.0 * reward_scale * gamma ** t

    # Closed-loop check: the trajectory-mean value implied by each episode's realised
    # reward stream and length, compared with the logged GAE target mean.
    predicted = {}
    for arm in ARMS:
        comp = [r["info"] for r in train[arm] if r.get("kind") == "completed"]
        total = decisions = 0.0
        for i in comp:
            t = i["gameplay_frames"] / repeat
            rate = (i["score"] + i["alive_frames"] / 100.0) * reward_scale / t
            weighted = gamma * (1 - gamma ** t) / (1 - gamma)  # sum_t gamma^(T-t)
            avg = rate * (t - weighted) / (1 - gamma) / t - 0.5 * weighted / t
            total += avg * t
            decisions += t
        predicted[arm] = {"trajectory_mean_value_predicted": total / decisions,
                          "gae_target_mean_logged": st.mean([m["metrics"]["critic_diagnostics"]["pre_update"]["target_mean"] for m in metrics[arm]])}
    horizon["target_mean_check"] = predicted
    # Value-unit size of the observed 348 dev gain: +158.72 mean alive frames realised late in
    # an episode, expressed against the critic residual sd (scaled return units).
    gain_frames = dev["linear"][348]["evaluation"]["mean_alive_frames"] - dev["linear"][324]["evaluation"]["mean_alive_frames"]
    t_mid = dev["linear"][348]["evaluation"]["mean_alive_frames"] / repeat
    live_gain = per_decision * gamma ** t_mid * (gain_frames / repeat) \
        + 0.5 * (gamma ** t_mid - gamma ** (t_mid + gain_frames / repeat))
    ev_pre = st.mean([m["metrics"]["critic_diagnostics"]["pre_update"]["explained_variance"] for m in metrics["linear"]])
    tvar = st.mean([m["metrics"]["critic_diagnostics"]["pre_update"]["target_variance"] for m in metrics["linear"]])
    residual_sd = math.sqrt((1 - ev_pre) * tvar)
    horizon["dev_gain_in_value_units"] = {
        "gain_frames": gain_frames, "gain_value_units": live_gain,
        "critic_residual_sd": residual_sd,
        "gain_over_residual_sd": live_gain / residual_sd,
    }

    # --- provenance ---------------------------------------------------------------
    provenance = {
        "model": "opencode/deepseek-v4.1-flash-free",
        "provider_instance_id": "opencode",
        "paid_fallback": False,
        "parent_checkpoint_sha256": "c10d90ec0e67503afef8f4d90c4968581d430ef2065117a75e81c445a04c8ddc",
        "training_run_seed": 4200000001,
        "registration": "D2-retained324-linear-integrated-luna-20261026-r4/registration-final-r2.json",
        "runtime_root": "D2-gradient-capsule-parent-freeze-20261025-r5/own/runtime",
        "runtime_sha256": "2cf10e9f056f41b39dc17845192e9adf553a5f699546d4f5dcea764a23e36b31",
        "ppo_sha256": sha256(SOURCE[0]),
        "source_hashes": {os.path.relpath(p, REPO): sha256(p) for p in SOURCE if os.path.exists(p)},
        "evidence_hashes": {},
    }
    for arm, run in ARMS.items():
        for name in ["training-metrics.jsonl", "training-episodes.jsonl", "entry-restoration.json",
                     "artifact-manifest.json"] + ["development-%06d.json" % p for p in PHASES]:
            provenance["evidence_hashes"]["%s/%s" % (arm, name)] = sha256(os.path.join(RUNS, run, name))

    evidence = {
        "schema": "ppo_credit_assignment_audit_v1",
        "scope": "closed JSON/JSONL certificates plus frozen source text; no runtime imports, no checkpoint loads",
        "provenance": provenance,
        "development": {
            "phases": phases,
            "paired_linear_minus_fixed": {str(k): v for k, v in paired.items()},
            "within_arm_vs_324": {a: {str(k): v for k, v in d.items()} for a, d in within.items()},
            "sustained_post_baseline": {
                "fixed_mean": sustained["fixed"][0], "linear_mean": sustained["linear"][0],
                "diff": st.mean(diff_sustained), "se": st.stdev(diff_sustained) / 8,
                "gains": sum(1 for d in diff_sustained if d > 0),
            },
            "selection_null": sel_p,
            "blocks": {str(k): v for k, v in blocks.items()},
            "quartile_semantics": "runner.py:729 Q1/Q4 are means of lowest/highest 16 episodes, not percentiles",
        },
        "training_episodes": episodes,
        "horizon": horizon,
        "source_audit": {
            "gae_file": "dodge_rl/ppo.py",
            "gae_lines": "163-174 (compute_gae)",
            "bootstrap_masking": "bootstrap = ~terminated; continuation = ~(terminated|truncated) (ppo.py:166-169)",
            "next_value_zeroing": "ppo.py:337-338 zeroes next_values at terminated only; truncation keeps final V",
            "reward_identity": "env.rs:451-452 and ppo.py:245,435; audit at ppo.py:440",
            "reward_scale_applied_once": "ppo.py:333",
            "value_clipping": "absent (ppo.py:6, ppo.py:505)",
            "explained_variance": "ppo.py:573-575; in-sample frozen rollout values",
            "critic_fit_scope": "critic_diagnostics.py:131 in_sample_self_bootstrapped_targets;not_held_out",
            "truncation_trigger": "env.rs:224 at gameplay_frames >= raw_frame_cap (18000)",
            "shown_truncations": {"fixed": episodes["fixed"]["truncated"], "linear": episodes["linear"]["truncated"]},
            "gradient_shadow": "ppo.py:488-529 and gradient_alignment.py:67-89; one CPU probe at first minibatch of epoch 0",
            "label_defect": "gradient_alignment.py:88 'minibatch_count' is len(actions)=512 samples, not 32 minibatches",
            "runtime_vs_repo_ppo": "only gradient_alignment diagnostic hooks differ; compute_gae is byte-identical and covered by python/tests/test_ppo.py:31-71",
            "death_proximity_share": {
                "within_50_decisions": episodes["linear"]["completed"] * 50 / 983040,
                "within_10_decisions": episodes["linear"]["completed"] * 10 / 983040,
            },
        },
        "training_metrics_summary": {
            arm: {
                "ev_pre_mean": st.mean([r["metrics"]["critic_diagnostics"]["pre_update"]["explained_variance"] for r in metrics[arm]]),
                "ev_post_mean": st.mean([r["metrics"]["critic_diagnostics"]["post_update"]["explained_variance"] for r in metrics[arm]]),
                "target_variance_mean": st.mean([r["metrics"]["critic_diagnostics"]["pre_update"]["target_variance"] for r in metrics[arm]]),
                "prediction_variance_mean": st.mean([r["metrics"]["critic_diagnostics"]["pre_update"]["prediction_variance"] for r in metrics[arm]]),
                "entropy_mean": st.mean([r["metrics"]["entropy"] for r in metrics[arm]]),
                "approx_kl_mean": st.mean([r["metrics"]["approx_kl"] for r in metrics[arm]]),
                "early_stop_kl": sum(r["metrics"]["early_stop_kl"] for r in metrics[arm]),
                "optimizer_steps": sum(r["metrics"]["optimizer_steps"] for r in metrics[arm]),
                "cosine_mean": st.mean([r["metrics"]["gradient_alignment_diagnostics"]["cosine"] for r in metrics[arm]]),
                "cosine_sd": st.stdev([r["metrics"]["gradient_alignment_diagnostics"]["cosine"] for r in metrics[arm]]),
                "critic_over_actor_norm": st.mean([r["metrics"]["gradient_alignment_diagnostics"]["norm_ratio_critic_over_actor"] for r in metrics[arm]]),
            } for arm in ARMS
        },
    }
    with open(os.path.join(HERE, "evidence.json"), "w") as fh:
        json.dump(evidence, fh, indent=1, sort_keys=True)
    print(json.dumps({
        "paired": paired,
        "sustained": evidence["development"]["sustained_post_baseline"],
        "selection": sel_p,
        "episodes": {a: {k: episodes[a][k] for k in ("completed", "truncated", "frames_mean", "frames_max")} for a in ARMS},
        "horizon": {k: horizon[k] for k in ("gamma_horizon_raw_frames", "gae_trace_sum_raw_frames", "gae_half_life_raw_frames")},
    }, indent=1))


if __name__ == "__main__":
    main()
