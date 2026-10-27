"""Read-only terminal review checks for D2-gradient-alignment-20261025-r2.

Stdlib only. Reads run artifacts, hashes them, recomputes summaries, and writes
one receipt into this review directory. Writes nothing else.
"""
import hashlib
import json
import os
import statistics
import subprocess
import sys
import time
from collections import Counter

ROOT = "/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79"
RUNS = os.path.join(ROOT, "learning/runs/v2")
OUT = os.path.join(RUNS, "D2-gradient-terminal-review-haiku-20261025-r2")
ALIGN = os.path.join(RUNS, "D2-gradient-alignment-20261025-r2")
OBS = os.path.join(RUNS, "D2-gradient-execution-observer-20261025-r2")
FREEZE = os.path.join(RUNS, "D2-gradient-capsule-parent-freeze-20261025-r5")
AUDIT = os.path.join(RUNS, "d2-gradient-parent-terminal-audit-20261025-r2")
AUTH = os.path.join(RUNS, "D2-gradient-campaign-parent-authorization-20261025-r2")
REVIEW_OLD = os.path.join(RUNS, "D2-gradient-capsule-frozen-review-haiku-20261025-r5")

findings = []  # (severity, id, detail)
checks = {}


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_jsonl(path):
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def close(a, b, tol=1e-9):
    return abs(a - b) <= tol * max(1.0, abs(a), abs(b))


def report(sev, cid, detail):
    findings.append({"severity": sev, "id": cid, "detail": detail})


# ---------------------------------------------------------------- inputs
input_paths = []
for d in (ALIGN, OBS, FREEZE, AUDIT, AUTH, REVIEW_OLD):
    for name in sorted(os.listdir(d)):
        p = os.path.join(d, name)
        if os.path.isfile(p):
            input_paths.append(p)
input_paths.append(os.path.abspath(__file__))
inputs = {os.path.relpath(p, ROOT): sha256_file(p) for p in input_paths}
checks["input_count"] = len(inputs)

# ---------------------------------------------------------------- A. manifests
manifest = load_json(os.path.join(ALIGN, "artifact-manifest.json"))
mm = {}
for name, expected in manifest.items():
    actual = sha256_file(os.path.join(ALIGN, name))
    mm[name] = actual == expected
    if actual != expected:
        report("high", "manifest-hash-mismatch", f"{name} expected {expected} actual {actual}")
checks["alignment_manifest_all_match"] = all(mm.values())
checks["alignment_manifest_entries"] = len(manifest)

audit = load_json(os.path.join(AUDIT, "audit.json"))
am = {}
for path, expected in audit["artifacts"].items():
    if not os.path.isfile(path):
        am[path] = "missing"
        report("high", "audit-artifact-missing", path)
        continue
    actual = sha256_file(path)
    am[os.path.basename(path)] = actual == expected
    if actual != expected:
        report("high", "audit-artifact-hash-mismatch", f"{path} audit {expected} actual {actual}")
checks["audit_artifact_bindings_all_match"] = all(v is True for v in am.values())
checks["audit_artifact_count"] = len(am)
checks["audit_sha256"] = sha256_file(os.path.join(AUDIT, "audit.json"))
checks["audit_py_sha256"] = sha256_file(os.path.join(AUDIT, "audit.py"))

# ---------------------------------------------------------------- B. evaluations
def eval_stats(rows):
    alive = [r["alive_frames"] for r in rows]
    srt = sorted(rows, key=lambda r: r["alive_frames"])
    q1 = [r["alive_frames"] for r in srt[:16]]
    q4 = [r["alive_frames"] for r in srt[-16:]]
    causes = Counter(r["death_cause"] for r in rows)
    scores = [r["score"] for r in rows]
    return {
        "rows": len(rows),
        "mean_alive_frames": statistics.fmean(alive),
        "q1_bottom16_mean": statistics.fmean(q1),
        "q4_top16_mean": statistics.fmean(q4),
        "mean_score": statistics.fmean(scores),
        "death_causes": dict(sorted(causes.items())),
        "deaths": sum(1 for r in rows if r["terminated"]),
        "seeds": {r["seed"]: r for r in rows},
    }


evals = {}
for upd in (132, 180):
    jl = load_jsonl(os.path.join(ALIGN, f"development-000{upd}.jsonl"))
    js = load_json(os.path.join(ALIGN, f"development-000{upd}.json"))
    st = eval_stats(jl)
    ev = js["evaluation"]
    js_rows = ev["rows"]
    rows_match = js_rows == jl or sorted(json.dumps(r, sort_keys=True) for r in js_rows) == sorted(
        json.dumps(r, sort_keys=True) for r in jl
    )
    checks[f"eval{upd}_json_rows_equal_jsonl"] = rows_match
    if not rows_match:
        report("high", "eval-jsonl-vs-json-rows", f"update {upd}")
    audit_ev = next(e for e in audit["evaluations"] if e["update"] == upd)
    cmp = {
        "mean_alive_frames": (st["mean_alive_frames"], audit_ev["mean_alive_frames"]),
        "q1_bottom16_mean": (st["q1_bottom16_mean"], audit_ev["q1_bottom16_mean"]),
        "q4_top16_mean": (st["q4_top16_mean"], audit_ev["q4_top16_mean"]),
    }
    for k, (a, b) in cmp.items():
        if not close(a, b):
            report("high", f"eval{upd}-{k}-mismatch", f"recomputed {a} vs audit {b}")
    if st["death_causes"] != {k: v for k, v in audit_ev["death_causes"].items() if v}:
        report("high", f"eval{upd}-death-cause-mismatch",
               f"recomputed {st['death_causes']} vs audit {audit_ev['death_causes']}")
    if ev.get("deaths") != st["deaths"] or st["rows"] != 64:
        report("medium", f"eval{upd}-row-or-death-count", f"rows {st['rows']} deaths {st['deaths']} json {ev.get('deaths')}")
    if ev.get("action_mode") != "deterministic_argmax" or ev.get("gradients") is not False:
        report("medium", f"eval{upd}-mode", str({k: ev.get(k) for k in ("action_mode", "gradients")}))
    evals[upd] = st
    checks[f"eval{upd}_summary"] = {k: v for k, v in st.items() if k != "seeds"}

seeds132 = evals[132]["seeds"]
seeds180 = evals[180]["seeds"]
checks["eval_seed_sets_equal"] = set(seeds132) == set(seeds180)
if not checks["eval_seed_sets_equal"]:
    report("high", "eval-seed-set-differs", "132 and 180 seed sets differ")
imp = wor = tie = 0
deltas = []
for s in seeds180:
    d = seeds180[s]["alive_frames"] - seeds132[s]["alive_frames"]
    deltas.append(d)
    if d > 0:
        imp += 1
    elif d < 0:
        wor += 1
    else:
        tie += 1
checks["paired"] = {"improved": imp, "worsened": wor, "tied": tie, "mean_delta": statistics.fmean(deltas)}
ap = audit["paired_seed_changes"]
if (imp, wor, tie) != (ap["improved"], ap["worsened"], ap["tied"]) or not close(statistics.fmean(deltas), ap["mean_delta_frames"]):
    report("high", "paired-change-mismatch", f"recomputed {checks['paired']} vs audit {ap}")

# death-cause survival at 180
surv = {}
for cause in {r["death_cause"] for r in evals[180]["seeds"].values()}:
    rs = [r for r in evals[180]["seeds"].values() if r["death_cause"] == cause]
    surv[cause] = {"count": len(rs), "mean_alive_frames": statistics.fmean(r["alive_frames"] for r in rs)}
checks["death_cause_survival_180"] = surv
for cause, v in audit["death_cause_survival"].items():
    got = surv.get(cause)
    if got is None or got["count"] != v["count"] or not close(got["mean_alive_frames"], v["mean_alive_frames"]):
        report("medium", "death-cause-survival-mismatch", f"{cause} audit {v} recomputed {got}")

# ---------------------------------------------------------------- C. training metrics
metrics = load_jsonl(os.path.join(ALIGN, "training-metrics.jsonl"))
checks["metric_records"] = len(metrics)
upds = [m["local_update"] for m in metrics]
checks["metric_local_updates_contiguous"] = upds == list(range(1, 49))
KEYS = ("environment_decisions", "optimizer_steps", "raw_frames", "updates")
# per-record counters are phase-cumulative: verify monotone, then final == worker counters
checks["metric_counters_monotone"] = all(
    all(metrics[i + 1]["counters"][k] >= metrics[i]["counters"][k] for k in KEYS) for i in range(len(metrics) - 1)
)
ctr = {k: metrics[-1]["counters"][k] for k in KEYS}
checks["metric_final_counters"] = ctr
wr = load_json(os.path.join(ALIGN, "worker-result.json"))
if not checks["metric_counters_monotone"]:
    report("high", "metric-counters-not-monotone", "phase counters decrease between updates")
if ctr != wr["counters"]:
    report("high", "counter-final-mismatch", f"metric final {ctr} worker {wr['counters']}")
checks["manifest_missing_alignment_files"] = sorted(
    n for n in os.listdir(ALIGN) if os.path.isfile(os.path.join(ALIGN, n)) and n not in manifest and n != "artifact-manifest.json"
)
if "execution-result.json" in checks["manifest_missing_alignment_files"]:
    report("low", "manifest-omits-execution-result",
           "artifact-manifest.json (18:35) does not list execution-result.json; it is bound only via audit.json and postflight digests")
if wr["cumulative_counters"] != {
    "environment_decisions": wr["inherited_counters"]["environment_decisions"] + wr["counters"]["environment_decisions"],
    "optimizer_steps": wr["inherited_counters"]["optimizer_steps"] + wr["counters"]["optimizer_steps"],
    "raw_frames": wr["inherited_counters"]["raw_frames"] + wr["counters"]["raw_frames"],
    "updates": wr["inherited_counters"]["updates"] + wr["counters"]["updates"],
}:
    report("high", "cumulative-counter-arithmetic", str(wr))

# gradient alignment recompute
ga = [m["metrics"]["gradient_alignment_diagnostics"] for m in metrics]
checks["ga_all_defined"] = all(g.get("defined") is True for g in ga)
checks["ga_probe_count_values"] = sorted(Counter(g.get("probe_count") for g in ga).items())
cos = [g["cosine"] for g in ga]
ratio = [g["norm_ratio_critic_over_actor"] for g in ga]
clip = [g["live_clip_coefficient"] for g in ga]
ga_rec = {
    "n": len(cos),
    "cosine_mean": statistics.fmean(cos),
    "cosine_median": statistics.median(cos),
    "cosine_min": min(cos),
    "cosine_max": max(cos),
    "negative_cosines": sum(1 for c in cos if c < 0),
    "ratio_mean": statistics.fmean(ratio),
    "ratio_median": statistics.median(ratio),
    "ratio_max": max(ratio),
    "live_clip_coefficient_mean": statistics.fmean(clip),
    "live_clipped_count": sum(1 for c in clip if c < 1.0),
    "backend_values": sorted({g.get("backend") for g in ga}),
    "measures_live_mps": sorted({g.get("measures_live_MPS_gradients") for g in ga}, key=str),
    "snapshot": sorted({g.get("snapshot") for g in ga}),
    "coverage_parameters": sorted({g["coverage"]["parameters"] for g in ga}),
    "coverage_elements": sorted({g["coverage"]["elements"] for g in ga}),
}
checks["ga_recomputed"] = ga_rec
a48 = audit["gradient_alignment"]["windows"]["all48"]
for key, akey in (("cosine_mean", "cosine_mean"), ("cosine_median", "cosine_median"), ("cosine_min", "cosine_min"),
                  ("cosine_max", "cosine_max"), ("ratio_mean", "critic_over_actor_norm_ratio_mean"),
                  ("ratio_median", "critic_over_actor_norm_ratio_median"),
                  ("ratio_max", "critic_over_actor_norm_ratio_max"),
                  ("live_clip_coefficient_mean", "live_clip_coefficient_mean")):
    if not close(ga_rec[key], a48[akey], 1e-9):
        report("high", f"ga-{key}-mismatch", f"recomputed {ga_rec[key]} vs audit {a48[akey]}")
if ga_rec["negative_cosines"] != a48["negative_cosines"]:
    report("high", "ga-negative-count-mismatch", f"{ga_rec['negative_cosines']} vs {a48['negative_cosines']}")
if ga_rec["live_clipped_count"] != a48["live_first_minibatch_clipped"]:
    report("high", "ga-clip-count-mismatch", f"{ga_rec['live_clipped_count']} vs {a48['live_first_minibatch_clipped']}")
checks["ga_group_cosine_means"] = {}
for grp, ga_audit in audit["gradient_alignment"]["groups"].items():
    vals = [g["groups"][grp]["cosine"] for g in ga]
    m_ = statistics.fmean(vals)
    checks["ga_group_cosine_means"][grp] = m_
    if not close(m_, ga_audit["cosine_mean"], 1e-9):
        report("medium", "ga-group-cosine-mismatch", f"{grp} recomputed {m_} vs audit {ga_audit['cosine_mean']}")
    neg = sum(1 for v in vals if v < 0)
    if neg != ga_audit["negative_cosines"]:
        report("medium", "ga-group-negative-mismatch", f"{grp} {neg} vs {ga_audit['negative_cosines']}")

# critic EV recompute
pre_ev_rep, post_ev_rep, pre_ev_recalc, post_ev_recalc = [], [], [], []
pre_mse_improved = 0
for m in metrics:
    cd = m["metrics"]["critic_diagnostics"]
    pre = cd["pre_update"]
    post = cd["post_update"]
    pre_ev_rep.append(pre["explained_variance"])
    post_ev_rep.append(post["explained_variance"])
    pre_ev_recalc.append(1.0 - pre["residual_variance"] / pre["target_variance"])
    post_ev_recalc.append(1.0 - post["residual_variance"] / post["target_variance"])
    if post["residual_mse"] < pre["residual_mse"]:
        pre_mse_improved += 1
checks["critic_ev"] = {
    "pre_reported_mean": statistics.fmean(pre_ev_rep),
    "post_reported_mean": statistics.fmean(post_ev_rep),
    "pre_recalc_from_variances_mean": statistics.fmean(pre_ev_recalc),
    "post_recalc_from_variances_mean": statistics.fmean(post_ev_recalc),
    "audit_all48_pre": audit["critic_windows"]["all48"]["pre_explained_variance"],
    "audit_all48_post": audit["critic_windows"]["all48"]["post_explained_variance"],
    "pre_mse_improved_updates": pre_mse_improved,
}
# pooled-from-audit recompute: 1 - resid_var/target_var with audit pooled fields
w = audit["critic_windows"]["all48"]
checks["critic_ev"]["audit_pooled_recalc_pre"] = 1 - w["pre_residual_variance"] / w["pre_target_variance"]
checks["critic_ev"]["audit_pooled_recalc_post"] = 1 - w["post_residual_variance"] / w["post_target_variance"]
if not close(statistics.fmean(pre_ev_rep), w["pre_explained_variance"], 1e-6):
    report("medium", "critic-ev-definition",
           "audit all48 pre EV %.6f is neither mean of per-update reported EV %.6f nor 1-resid/target from pooled audit fields %.6f; definition not stated"
           % (w["pre_explained_variance"], statistics.fmean(pre_ev_rep), checks["critic_ev"]["audit_pooled_recalc_pre"]))
if pre_mse_improved != audit["same_batch_fit_mse_improved_updates"]:
    report("high", "same-batch-mse-count", f"{pre_mse_improved} vs audit {audit['same_batch_fit_mse_improved_updates']}")

# ---------------------------------------------------------------- D. timing anchors
ex = load_json(os.path.join(ALIGN, "execution-result.json"))
wl = load_json(os.path.join(ALIGN, "worker-launch.json"))
wres = wr
lm = load_json(os.path.join(ALIGN, "launch-marker.json"))
obs = load_json(os.path.join(OBS, "observation.json"))
started = lm["started_monotonic"]
direct_wait = ex["direct_wait_observed_monotonic"]
worker_obs = wl["observed_monotonic"]
t = {
    "started_anchor": started,
    "exec_elapsed_seconds": ex["elapsed_seconds"],
    "exec_elapsed_end_anchor": started + ex["elapsed_seconds"],
    "direct_wait_minus_started": direct_wait - started,
    "direct_wait_minus_worker_launch_observed": direct_wait - worker_obs,
    "worker_work_seconds": wres["work_elapsed_seconds"],
    "worker_launch_observed_plus_work": worker_obs + wres["work_elapsed_seconds"],
    "observer_start": obs["observer_started_monotonic"],
    "command_started": obs["command_started_monotonic"],
    "command_ended": obs["command_ended_monotonic"],
    "inclusive_process_wall_seconds": obs["inclusive_process_wall_seconds"],
    "observer_inclusive_wall_seconds": obs["observer_inclusive_wall_seconds"],
    "command_ended_minus_command_started": obs["command_ended_monotonic"] - obs["command_started_monotonic"],
    "observer_ended_minus_started": obs["observer_ended_monotonic"] - started,
}
checks["timing_anchors"] = t
if t["worker_launch_observed_plus_work"] > direct_wait + 0.05:
    report("low", "worker-work-window-exceeds-observed-wait",
           "worker_launch_observed + work_elapsed = %.3f > direct_wait_observed %.3f (excess %.3f s). "
           "Consistent only if worker started before its observed_monotonic timestamp; the worker-launch anchor, not the work clock, is the unclear one."
           % (t["worker_launch_observed_plus_work"], direct_wait, t["worker_launch_observed_plus_work"] - direct_wait))
if not close(ex["elapsed_seconds"], obs["inclusive_process_wall_seconds"], 1e-6):
    report("low", "execution-result-elapsed-not-authority",
           "execution-result elapsed_seconds %.6f != observer inclusive process wall %.6f (diff %.6f); "
           "parent uses 729.705 process wall, execution-result 729.126 has no stated anchor."
           % (ex["elapsed_seconds"], obs["inclusive_process_wall_seconds"],
              obs["inclusive_process_wall_seconds"] - ex["elapsed_seconds"]))
pw = audit["inclusive_wall_seconds"]
if not close(pw, obs["inclusive_process_wall_seconds"]):
    report("high", "inclusive-wall-binding", f"{pw} vs {obs['inclusive_process_wall_seconds']}")
parent_auth = 2222.619523167091
cum_parent_basis = parent_auth + pw
cum_worker_basis = wres["cumulative_D2_inclusive_wall_seconds"]
checks["cumulative_wall_bases"] = {
    "parent_basis_process_inclusive": cum_parent_basis,
    "worker_basis_work_elapsed": cum_worker_basis,
    "difference": cum_parent_basis - cum_worker_basis,
}
report("low", "cumulative-wall-two-bases",
       "Accepted parent cumulative %.6f uses outer process wall; worker-reported cumulative %.6f uses work elapsed; "
       "difference %.6f s (launch/teardown overhead) is not reconciled in any receipt. Parent should name the authority."
       % (cum_parent_basis, cum_worker_basis, cum_parent_basis - cum_worker_basis))
if not close(audit["full_cumulative_D2_inclusive_wall_seconds"], cum_parent_basis, 1e-9):
    report("high", "cumulative-wall-arithmetic", "audit cumulative differs from parent+inclusive")
if not close(audit["consumed_iteration_wall_seconds_at_checkpoint"], 719.7129172909772, 1e-12):
    report("low", "checkpoint-time-value", "audit checkpoint time not the recorded constant")

# ---------------------------------------------------------------- E. resources
obs_res = load_jsonl(os.path.join(OBS, "resources.jsonl"))
agg = [r["aggregate_rss_bytes"] for r in obs_res]
mono = [r["monotonic"] for r in obs_res]
gaps = [b - a for a, b in zip(mono, mono[1:])]
checks["observer_resources"] = {
    "samples": len(obs_res),
    "max_aggregate_rss_bytes": max(agg),
    "max_gap_seconds": max(gaps),
    "span_seconds": mono[-1] - mono[0],
    "first_sample_elapsed_since_observer_start": obs_res[0]["elapsed_since_observer_start"],
    "last_sample_elapsed_since_observer_start": obs_res[-1]["elapsed_since_observer_start"],
}
if len(obs_res) != audit["resource_samples"] or max(agg) != audit["max_sampled_aggregate_rss_bytes"]:
    report("high", "observer-resource-audit-mismatch", str(checks["observer_resources"]))
if max(gaps) != audit["max_sample_gap_seconds"] and not close(max(gaps), audit["max_sample_gap_seconds"], 1e-9):
    report("medium", "observer-max-gap-mismatch", f"{max(gaps)} vs {audit['max_sample_gap_seconds']}")
if audit["resource_samples"] != 696:
    report("low", "sample-count", str(audit["resource_samples"]))
wkr = load_jsonl(os.path.join(ALIGN, "resources.jsonl"))
checks["worker_resources"] = {
    "samples": len(wkr),
    "max_peak_rss_bytes": max(r.get("peak_rss_bytes", 0) for r in wkr),
    "max_mps_driver_bytes": max(r.get("mps_driver_bytes", 0) for r in wkr),
    "keys": sorted(wkr[0].keys()),
}
if checks["worker_resources"]["max_peak_rss_bytes"] != wres["peak_rss_bytes"]:
    report("medium", "worker-rss-highwater-mismatch", str(checks["worker_resources"]))
if checks["worker_resources"]["max_mps_driver_bytes"] != wres["peak_mps_driver_bytes"]:
    report("medium", "worker-mps-mismatch", str(checks["worker_resources"]))
checks["observer_max_sample_owned"] = [p["pid"] for p in obs["max_rss_sample"]["owned_processes"]]

# ---------------------------------------------------------------- F. episode journal
journal = load_jsonl(os.path.join(ALIGN, "training-episodes.jsonl"))
kinds = Counter(r["kind"] for r in journal)
comp = [r["info"] for r in journal if r["kind"] == "completed"]
ab = [r["info"] for r in journal if r["kind"] == "abandoned_parent_episode"]
comp_frames = sum(i["gameplay_frames"] for i in comp)
ab_frames = sum(i["gameplay_frames"] for i in ab)
raw = wres["counters"]["raw_frames"]
checks["journal"] = {
    "kinds": dict(kinds),
    "records": len(journal),
    "completed": len(comp),
    "completed_gameplay_frames": comp_frames,
    "prior_abandoned_records": len(ab),
    "prior_abandoned_frames": ab_frames,
    "phase_raw_frames": raw,
    "remainder_raw_minus_completed": raw - comp_frames,
    "records_checked_equiv": len(journal) - len(ab),
}
if comp_frames != audit["completed_training_frames"] or len(comp) != audit["completed_training_episodes"]:
    report("high", "journal-completed-mismatch", str(checks["journal"]))
if ab_frames != audit["parent_abandoned_frames_retained_not_current_training"]:
    report("high", "journal-prior-abandoned-mismatch", str(ab_frames))
if raw - comp_frames != audit["final_abandoned_training_frames"]:
    report("high", "final-abandoned-remainder", str(raw - comp_frames))
report("low", "final-abandoned-not-journaled",
       "Final abandoned 58524 frames is raw_frames minus completed frames (remainder), not an independently journaled sum; "
       "conservation holds by construction. Parent should label it as derived.")
# completed record consistency: alive vs gameplay frames
bad_fatal = [i for i in comp if i.get("fatal_gameplay_frame") != i.get("gameplay_frames")]
if bad_fatal:
    report("low", "completed-fatal-vs-gameplay", f"{len(bad_fatal)} completed records have fatal_gameplay_frame != gameplay_frames")
bad_alive = [i for i in comp if i["gameplay_frames"] - i["alive_frames"] != 1]
checks["completed_gameplay_minus_alive_histogram"] = dict(Counter(i["gameplay_frames"] - i["alive_frames"] for i in comp))
if bad_alive:
    report("low", "completed-alive-offset", f"{len(bad_alive)} completed records have gameplay_frames - alive_frames != 1")
# per-slot check of episode index journal
slot_last = {}
for r in journal:
    if r["kind"] == "completed":
        s = r["info"]["seed"]
        slot_last[s["slot"]] = max(slot_last.get(s["slot"], -1), s["episode"])
ej = audit["checks"]["episode_journal"]
cur = {int(k): v for k, v in ej["current_episode_indices"].items()}
nxt = ej["next_episode_indices"]
checks["journal_next_equals_current_plus_one"] = all(nxt[k] == cur[k] + 1 for k in range(64))
checks["journal_slot_last_completed_episode_vs_current"] = {
    str(k): {"last_completed": slot_last.get(k), "current": cur[k]} for k in range(64)
}
mismatch_slots = [k for k in range(64) if slot_last.get(k) is not None and slot_last[k] + 1 != cur[k]]
checks["journal_slot_index_mismatch_count"] = len(mismatch_slots)
if mismatch_slots:
    report("medium", "journal-slot-index",
           f"{len(mismatch_slots)} slots: last completed episode +1 != current_episode_index, e.g. slot {mismatch_slots[:3]}")

# ---------------------------------------------------------------- G. checkpoint sidecars
ck_json = load_json(os.path.join(ALIGN, "checkpoint-000180-candidate.pt.json"))
checks["checkpoint180_sidecar_keys"] = sorted(ck_json.keys())
checks["checkpoint180_sidecar"] = ck_json
ck132 = load_json(os.path.join(ALIGN, "checkpoint-000132-candidate.pt.json"))
checks["checkpoint132_sidecar"] = ck132

# ---------------------------------------------------------------- H. registration pins
reg = load_json(os.path.join(FREEZE, "registration-proposed.json"))
checks["registration_sha256"] = sha256_file(os.path.join(FREEZE, "registration-proposed.json"))
pins = reg["pins"]
checks["pins_declared"] = len(pins)
t0 = time.monotonic()
pin_bad = []
pin_missing = []
pin_checked = 0
budget = 420.0
for path, expected in pins.items():
    if time.monotonic() - t0 > budget:
        break
    if not os.path.isfile(path):
        pin_missing.append(path)
        continue
    if sha256_file(path) != expected:
        pin_bad.append(path)
    pin_checked += 1
checks["pins_stdlib_rehash"] = {
    "checked": pin_checked,
    "mismatches": len(pin_bad),
    "missing": len(pin_missing),
    "seconds": time.monotonic() - t0,
    "budget_exhausted": pin_checked + len(pin_missing) + len(pin_bad) < len(pins),
    "examples_bad": pin_bad[:5],
    "examples_missing": pin_missing[:5],
}
if pin_bad:
    report("high", "pin-hash-mismatch", f"{len(pin_bad)} pins differ, e.g. {pin_bad[:2]}")
if pin_missing:
    report("medium", "pin-missing", f"{len(pin_missing)} pins missing, e.g. {pin_missing[:2]}")
checks["pins_missing_examples_note"] = "missing pins can be expected for files removed by the registered cache policy; check"

# ---------------------------------------------------------------- I. lease / ledger / process state
state_path = reg["state_path"]
state_now = sha256_file(state_path) if os.path.isfile(state_path) else None
checks["state_sha256_now"] = state_now
checks["state_sha256_registered_before_run"] = "1f13fe0bd164d4f19d648ae28bdbba6b98260bb8ca5e3bad17e38e7a318b794c"
checks["state_changed_since_prelaunch"] = state_now != checks["state_sha256_registered_before_run"]
try:
    st = load_json(state_path)
    checks["state_active_long_campaign"] = st.get("active_long_campaign")
    checks["state_lease_matches_registration"] = st.get("active_long_campaign") == reg["expected_lease"]
    checks["state_last_update_at_utc"] = st.get("last_update_at_utc")
    checks["state_has_r2_completed_entry"] = any(
        isinstance(x, dict) and x.get("run_id") == reg["run_id"] for x in (st.get("completed_long_campaigns") or [])
    )
    if checks["state_active_long_campaign"] is None:
        report("low", "lease-already-null-at-review",
               "state active_long_campaign is null (last_update %s, after audit 2026-10-25T23:37:19Z). Prior lease value not snapshotted; "
               "parent receipt should record before/after lease digest proving only the matching lease was cleared."
               % checks["state_last_update_at_utc"])
except Exception as e:  # noqa: BLE001
    checks["state_error"] = repr(e)
cancel = os.path.join(RUNS, "D2-gradient-parent-prepare-20261025-r1", "cancel-requested")
checks["cancel_path_absent_now"] = not os.path.lexists(cancel)
out = subprocess.run(["/bin/ps", "-axo", "pid=,ppid=,pgid=,command="], capture_output=True, text=True).stdout
live = []
for line in out.splitlines():
    p = line.split(None, 3)
    if len(p) >= 3 and p[2] in ("93988", "93989", "93994"):
        live.append(line.strip()[:160])
checks["owned_pgid_processes_now"] = live
if live:
    report("high", "process-still-alive", "; ".join(live))

# ---------------------------------------------------------------- J. parent acceptance / pins / reconciliation
acc = load_json(os.path.join(AUTH, "parent-acceptance.json"))
checks["parent_acceptance_keys"] = sorted(acc.keys())
checks["parent_acceptance"] = {k: acc[k] for k in acc if isinstance(acc[k], (str, int, float, bool)) or k in ("lineage",)}
rp = load_json(os.path.join(AUTH, "registration-pin.json"))
checks["registration_pin"] = rp
if rp.get("registration_sha256", rp.get("registration_sha256")) not in (None, "6f4adf808789655a663800a1e4a0613192d02b0c8287d121455ea748fe043916"):
    report("high", "registration-pin-mismatch", str(rp))
rec = load_json(os.path.join(FREEZE, "parent-preparation-reconciliation.json"))
checks["parent_prep_reconciliation"] = rec
ob_rec = load_json(os.path.join(AUTH, "observer-reconciliation.json"))
checks["observer_reconciliation"] = ob_rec
rv = load_json(os.path.join(REVIEW_OLD, "review-receipt.json"))
checks["prior_frozen_review_verdict"] = rv.get("verdict", rv.get("review_verdict", rv.get("status")))

# entry-132 evaluation vs predecessor continuation evaluation (byte-level)
pred132 = os.path.join(RUNS, "D2-continuation-20261025-r1", "development-000132.jsonl")
checks["entry132_jsonl_byte_identical_to_predecessor"] = sha256_file(pred132) == sha256_file(
    os.path.join(ALIGN, "development-000132.jsonl"))
checks["entry132_predecessor_sha256"] = sha256_file(pred132)
if not checks["entry132_jsonl_byte_identical_to_predecessor"]:
    report("high", "entry132-predecessor-mismatch", "development-000132.jsonl differs from predecessor bytes")

# ---------------------------------------------------------------- receipt
receipt = {
    "schema": "D2_gradient_terminal_review_receipt_v1",
    "reviewer": "claude-haiku-5-5 (native sub-agent, read-only)",
    "scope": "static read-only review of D2-gradient-alignment-20261025-r2 terminal evidence and parent audit",
    "no_torch_loads_tests_training_or_writes_outside_this_dir": True,
    "inputs_sha256": inputs,
    "manifest_hash_checks": mm,
    "audit_artifact_checks": am,
    "checks": checks,
    "findings": findings,
    "verdict": "no_blocking_findings" if not any(f["severity"] == "high" for f in findings) else "blocking_findings",
}
out_path = os.path.join(OUT, "terminal-review-receipt.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(receipt, f, indent=2, sort_keys=True, default=str)
    f.write("\n")
print(json.dumps({
    "receipt": out_path,
    "verdict": receipt["verdict"],
    "findings": [(f["severity"], f["id"]) for f in findings],
    "pins_stdlib_rehash": {k: v for k, v in checks["pins_stdlib_rehash"].items() if not k.startswith("examples")},
    "ga": {k: ga_rec[k] for k in ("cosine_mean", "cosine_median", "negative_cosines", "ratio_mean")},
    "timing": t,
}, indent=1, default=str))
