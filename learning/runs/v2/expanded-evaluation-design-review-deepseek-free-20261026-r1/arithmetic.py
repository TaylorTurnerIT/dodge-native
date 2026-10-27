#!/usr/bin/env python3
"""Read-only arithmetic checks for the expanded D2 evaluation proposal review.

Stdlib only. No checkpoint deserialization, no environment, no launch.
Writes arithmetic-output.json next to this script and prints a summary.
"""

import hashlib
import json
import math
import os
import statistics

ROOT = "/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79"
V2 = os.path.join(ROOT, "learning/runs/v2")
PARENT = os.path.join(V2, "expanded-evaluation-registration-proposal-parent-20261026-r2")
OUT = os.path.join(V2, "expanded-evaluation-design-review-deepseek-free-20261026-r1")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def seed_range_disjoint(a, b):
    return a[1] < b[0] or b[1] < a[0]


def load_dev_rows(path):
    rows = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            if isinstance(d, dict) and "seed" in d and "alive_frames" in d:
                rows[d["seed"]] = d["alive_frames"]
            elif isinstance(d, dict) and "rows" in d:
                for r in d["rows"]:
                    rows[r["seed"]] = r["alive_frames"]
    return rows


def main():
    result = {"schema": "expanded_eval_design_review_arithmetic_v1", "sources": {}, "checks": {}}

    # ---- 1. File and candidate byte reconciliation ----
    manifest = load_json(os.path.join(PARENT, "manifest.json"))
    proposal = load_json(os.path.join(PARENT, "proposal.json"))
    result["sources"]["proposal_json_sha256"] = sha256_file(os.path.join(PARENT, "proposal.json"))
    result["sources"]["proposal_md_sha256"] = sha256_file(os.path.join(PARENT, "proposal.md"))
    result["sources"]["manifest_json_sha256"] = sha256_file(os.path.join(PARENT, "manifest.json"))
    result["sources"]["ranking_seed_manifest_sha256"] = sha256_file(os.path.join(PARENT, "ranking-seed-manifest.json"))
    result["sources"]["confirmation_seed_manifest_sha256"] = sha256_file(os.path.join(PARENT, "confirmation-seed-manifest.json"))

    file_checks = {}
    for name, claimed in manifest["files"].items():
        actual = sha256_file(os.path.join(PARENT, name))
        file_checks[name] = {"claimed": claimed, "actual": actual, "match": actual == claimed}
    result["checks"]["manifest_files"] = file_checks
    result["checks"]["proposal_sha_matches_review_brief"] = (
        result["sources"]["proposal_json_sha256"]
        == "a1070cc5a6d6d01edfbbc04b67aadf58184a606516ee8643d6857edbaa3f1cb2"
    )

    cand_checks = {}
    for c in proposal["candidates"]:
        ck = os.path.join(c["checkpoint_path"])
        actual = sha256_file(ck) if os.path.exists(ck) else None
        rec_path = c.get("source_receipt_path") or c.get("source_audit_path")
        rec_actual = sha256_file(rec_path) if os.path.exists(rec_path) else None
        claimed_rec = c.get("source_receipt_sha256") or c.get("source_audit_sha256")
        # Does the receipt/audit itself pin the checkpoint hash?
        rec_pins = False
        if os.path.exists(rec_path):
            blob = open(rec_path, "r", encoding="utf-8").read()
            rec_pins = c["checkpoint_sha256"] in blob
        cand_checks[str(c["phase_update"])] = {
            "checkpoint_sha256_claimed": c["checkpoint_sha256"],
            "checkpoint_sha256_actual": actual,
            "checkpoint_match": actual == c["checkpoint_sha256"],
            "receipt_sha256_claimed": claimed_rec,
            "receipt_sha256_actual": rec_actual,
            "receipt_match": rec_actual == claimed_rec,
            "receipt_pins_checkpoint_sha256": rec_pins,
            "integrity_status": c["integrity_status"],
        }
    result["checks"]["candidates"] = cand_checks

    # ---- 2. Seed range arithmetic ----
    # Known reserved / development ranges, cited from
    # paired-LR-eval-seed-audit-haiku-20261026-r1/report.md.
    known = {
        "B_qualification": [2952790016, 2952791015],
        "D128_development": [3489660928, 3489661055],
        "dev64": [3489660928, 3489660991],
        "E_reserved_replication": [3758096384, 3758097383],
    }
    proposed = {
        "ranking": proposal["cohorts"]["ranking"]["range_inclusive"],
        "confirmation": proposal["cohorts"]["confirmation"]["range_inclusive"],
    }
    all_ranges = dict(known)
    all_ranges.update(proposed)
    disjoint = {}
    names = list(all_ranges)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            disjoint[f"{a} vs {b}"] = seed_range_disjoint(all_ranges[a], all_ranges[b])
    # dev64 is intentionally a subset of D128; exclude that known nesting from the
    # disjointness assertion, but keep it visible in the pairwise table.
    nested_known = {"D128_development vs dev64", "dev64 vs D128_development"}
    disjoint_assertion = {k: v for k, v in disjoint.items() if k not in nested_known}
    result["checks"]["seed_ranges"] = {
        "known": known,
        "proposed": proposed,
        "pairwise_disjoint": disjoint,
        "known_nesting": "dev64 [3489660928,3489660991] is a subset of D128 [3489660928,3489661055]",
        "all_disjoint_excluding_known_nesting": all(disjoint_assertion.values()),
        "ranking_count": proposed["ranking"][1] - proposed["ranking"][0] + 1,
        "confirmation_count": proposed["confirmation"][1] - proposed["confirmation"][0] + 1,
        "ranking_hex": [hex(proposed["ranking"][0]), hex(proposed["ranking"][1])],
        "confirmation_hex": [hex(proposed["confirmation"][0]), hex(proposed["confirmation"][1])],
    }

    # ---- 3. Frame accounting ----
    ranking_eps = 6 * 1024
    confirmation_eps_max = 2 * 1024
    total_eps = ranking_eps + confirmation_eps_max
    cap = proposal["evaluation"]["raw_frame_cap"]
    frames_max = total_eps * cap
    result["checks"]["frames"] = {
        "ranking_episodes": ranking_eps,
        "confirmation_episodes_max": confirmation_eps_max,
        "total_episodes_max": total_eps,
        "raw_frame_cap": cap,
        "raw_frames_max": frames_max,
        "proposal_claim": proposal["budget"]["raw_frames_max"],
        "proposal_claim_matches": frames_max == proposal["budget"]["raw_frames_max"],
        "arithmetic": f"{total_eps} * {cap} = {frames_max}",
    }

    # Training replication frames: parse the linear run's terminal metrics line.
    metrics_path = os.path.join(V2, "D2-retained324-linear-lr-20261026-r1/training-metrics.jsonl")
    last = None
    with open(metrics_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                last = json.loads(line)
    run_frames = last["counters"]["raw_frames"]
    run_updates = last["counters"]["updates"]
    rep = proposal["training_replication"]
    arms = 2
    rep_runs = arms * rep["training_seeds_per_arm"]
    rep_train_frames = rep_runs * run_frames
    rep_eval_max = rep_runs * 1024 * cap
    result["checks"]["replication_frames"] = {
        "run_raw_frames_60_updates": run_frames,
        "run_updates": run_updates,
        "arms_primary": arms,
        "seeds_per_arm": rep["training_seeds_per_arm"],
        "runs_primary": rep_runs,
        "training_frames_primary": rep_train_frames,
        "eval_frames_max_if_1024_seeds": rep_eval_max,
        "total_eval_frames_max_with_replication": frames_max + rep_eval_max,
        "arms_with_optional_control": 3,
        "runs_with_optional_control": 3 * rep["training_seeds_per_arm"],
        "training_frames_with_optional_control": 3 * rep["training_seeds_per_arm"] * run_frames,
        "eval_frames_max_with_optional_control": 3 * rep["training_seeds_per_arm"] * 1024 * cap,
        "total_eval_frames_max_with_optional_control": frames_max + 3 * rep["training_seeds_per_arm"] * 1024 * cap,
        "note": "147456000 covers ranking+confirmation only; replication is not included.",
    }

    # ---- 4. Memory arithmetic ----
    host = proposal["concurrency"]["host_physical_memory_bytes_observed"]
    rss_cap = proposal["concurrency"]["per_campaign_RSS_bytes"]
    mps_cap = proposal["concurrency"]["per_campaign_MPS_driver_bytes"]
    two_campaigns = proposal["concurrency"]["initial_max_active_training_campaigns"]
    headroom = 12 * (1 << 30)
    worst_disjoint = two_campaigns * (rss_cap + mps_cap)
    result["checks"]["memory"] = {
        "host_bytes": host,
        "host_gib": host / (1 << 30),
        "per_campaign_rss_bytes": rss_cap,
        "per_campaign_mps_bytes": mps_cap,
        "per_campaign_rss_gib": rss_cap / (1 << 30),
        "per_campaign_mps_gib": mps_cap / (1 << 30),
        "campaigns": two_campaigns,
        "worst_case_disjoint_sum_bytes": worst_disjoint,
        "worst_case_disjoint_sum_gib": worst_disjoint / (1 << 30),
        "headroom_bytes": headroom,
        "worst_case_plus_headroom_gib": (worst_disjoint + headroom) / (1 << 30),
        "fits_host": worst_disjoint + headroom <= host,
        "slack_gib": (host - worst_disjoint - headroom) / (1 << 30),
    }

    # Observed peaks from the 348 full audit.
    audit = load_json(os.path.join(V2, "D2-retained324-linear-auditor-prepare-luna-20261026-r3/full-audit.json"))
    gates = audit["terminal_gates"]
    result["checks"]["observed_peaks_348"] = {
        "peak_worker_rss_bytes": gates["peak_worker_rss_bytes"],
        "max_aggregate_rss_bytes": gates["max_aggregate_rss_bytes"],
        "peak_mps_driver_bytes": gates["peak_mps_driver_bytes"],
        "outer_inclusive_wall_seconds": gates["outer_inclusive_wall_seconds"],
        "note": "One 60-update run; MPS and RSS are separate overlapping measures on Apple unified memory.",
    }

    # ---- 5. Pilot paired statistics and confirmation power ----
    dev = {
        180: os.path.join(V2, "D2-gradient-alignment-20261025-r2/development-000180.jsonl"),
        204: os.path.join(V2, "D2-best180-branch-luna-20261026-r1/development-000204.jsonl"),
        276: os.path.join(V2, "D2-retained204-lr1e4-20261026-r1/development-000276.jsonl"),
        300: os.path.join(V2, "D2-retained276-lr3em5-20261026-r2/development-000300.jsonl"),
        324: os.path.join(V2, "D2-retained300-continuation-20261026-r1/development-000324.jsonl"),
        348: os.path.join(V2, "D2-retained324-linear-lr-20261026-r1/development-000348.jsonl"),
    }
    data = {k: load_dev_rows(p) for k, p in dev.items()}
    base = 348
    v = list(data[base].values())
    m = statistics.mean(v)
    sd = statistics.stdev(v)
    n_conf = 1024
    pilot = {
        "348_mean_alive_frames": m,
        "348_sd_alive_frames": sd,
        "348_n": len(v),
        "348_se_at_1024": sd / math.sqrt(n_conf),
        "348_ci95_halfwidth_at_1024": 1.96 * sd / math.sqrt(n_conf),
        "348_cap_hits": sum(1 for x in v if x >= cap),
        "pairs_vs_348": {},
    }
    for k in (324, 300, 276, 204, 180):
        common = sorted(set(data[k]) & set(data[base]))
        diffs = [data[base][s] - data[k][s] for s in common]
        dm = statistics.mean(diffs)
        dsd = statistics.stdev(diffs)
        se = dsd / math.sqrt(n_conf)
        # One-sided 95% decision: reject if observed diff > 1.645*SE.
        thr50 = 1.645 * se
        mde80 = (1.645 + 0.8416212335729143) * se
        mde90 = (1.645 + 1.2815515655446004) * se
        z = dm / se
        power = 0.5 * (1.0 + math.erf((z - 1.645) / math.sqrt(2.0)))
        n80 = ((1.645 + 0.8416212335729143) * dsd / dm) ** 2 if dm > 0 else None
        n90 = ((1.645 + 1.2815515655446004) * dsd / dm) ** 2 if dm > 0 else None
        pilot["pairs_vs_348"][str(k)] = {
            "n_paired_seeds": len(common),
            "mean_diff_348_minus_candidate": dm,
            "sd_diff": dsd,
            "se_at_1024": se,
            "lb_zero_threshold_50pct_power": thr50,
            "mde_80pct_power": mde80,
            "mde_90pct_power": mde90,
            "power_at_pilot_effect": power,
            "required_n_80pct_at_pilot_effect": n80,
            "required_n_90pct_at_pilot_effect": n90,
        }
    result["checks"]["pilot_power"] = pilot

    # ---- 6. Post-Adam LR controller arithmetic ----
    # Existing linear run: origin 372, horizon 60, u = cum - origin.
    origin = 372
    horizon = 60
    start_lr = 3e-5
    end_lr = 1e-5
    # 348 is phase 348 = cumulative 396 (offset 48 established by phase324=cum372, phase384=cum432).
    cum348 = 396
    u348 = cum348 - origin
    lr348 = start_lr - (start_lr - end_lr) * (u348 - 1) / (horizon - 1)
    new_origin = cum348
    first_new_cum = cum348 + 1
    lr_first = start_lr - (start_lr - end_lr) * ((first_new_cum - new_origin) - 1) / (horizon - 1)
    lr_last = start_lr - (start_lr - end_lr) * ((new_origin + horizon - new_origin) - 1) / (horizon - 1)
    result["checks"]["lr_controller"] = {
        "existing_schedule_origin_cumulative_update": origin,
        "existing_horizon_updates": horizon,
        "existing_spec_sha256": "7ceed85c5dc277602f2f51937b4ac003e2013e2689341a963ce5d82d5b64c9e4",
        "phase348_cumulative_update": cum348,
        "phase348_u": u348,
        "phase348_lr": lr348,
        "new_origin_cumulative_update": new_origin,
        "first_new_cumulative_update": first_new_cum,
        "first_new_u": first_new_cum - new_origin,
        "first_new_lr": lr_first,
        "last_new_cumulative_update": new_origin + horizon,
        "last_new_lr": lr_last,
        "note": "348 sits at ~2.2203e-5 under the old schedule; both new arms reset to 3e-5 at the first new update.",
    }

    # ---- 7. Replication inference unit arithmetic ----
    rep_inf = {}
    for n in (2, 3, 4, 5, 6):
        # exact one-sided sign-test minimum p when all pairs favor one arm
        rep_inf[str(n)] = {
            "min_one_sided_sign_test_p_all_same_direction": 0.5 ** n,
            "paired_t_df": n - 1,
            "paired_t_critical_95_one_sided": {
                1: 6.3138, 2: 2.9200, 3: 2.3534, 4: 2.1318, 5: 2.0150
            }.get(n - 1),
        }
    result["checks"]["replication_inference"] = rep_inf

    # ---- 8. Sibling seed audit reconciliation ----
    audit_path = os.path.join(V2, "expanded-evaluation-seed-exposure-audit-luna-20261026-r1/audit.json")
    recon_path = os.path.join(V2, "expanded-evaluation-seed-coverage-reconcile-luna-20261026-r2/reconciliation.json")
    if os.path.exists(audit_path):
        a = load_json(audit_path)
        result["sources"]["seed_exposure_audit_sha256"] = sha256_file(audit_path)
        result["checks"]["sibling_seed_audit"] = {
            "records_scanned": a.get("records_scanned"),
            "source_file_count": a.get("source_file_count"),
            "distinct_seed_values": a.get("distinct_seed_values"),
            "evaluation_seed_records": a.get("evaluation_seed_records"),
            "ranking_collisions": a["cohorts"]["ranking"]["collision_count"],
            "confirmation_collisions": a["cohorts"]["confirmation"]["collision_count"],
            "limits": a.get("limits"),
        }
    if os.path.exists(recon_path):
        r = load_json(recon_path)
        result["sources"]["seed_coverage_reconciliation_sha256"] = sha256_file(recon_path)
        result["checks"]["sibling_reconciliation"] = {
            "coverage_conclusion": r.get("coverage_conclusion"),
            "minimal_missing_artifacts": r.get("minimal_missing_artifacts"),
            "ancestry_statuses": sorted({x["ancestry_status"] for x in r.get("ancestors", [])}),
        }

    out_path = os.path.join(OUT, "arithmetic-output.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, sort_keys=True)
        f.write("\n")
    print(json.dumps(result["checks"]["frames"], indent=2))
    print(json.dumps(result["checks"]["pilot_power"], indent=2))
    print(json.dumps(result["checks"]["lr_controller"], indent=2))
    print("wrote", out_path)


if __name__ == "__main__":
    main()
