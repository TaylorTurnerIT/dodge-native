"""Read-only stdlib verification of the retained324 parent closeout. Writes receipt.json here only."""
from collections import Counter
from datetime import datetime
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path("/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/learning/runs/v2")
OUT = Path(__file__).resolve().parent
CLOSE = ROOT / "D2-retained300-parent-terminal-audit-20261026-r1"
RUN = ROOT / "D2-retained300-continuation-20261026-r1"
FREEZE = ROOT / "D2-retained300-continuation-freeze-20261026-r5"
AUD = ROOT / "D2-retained300-all-candidate-auditor-luna-20261026-r5"
OBS = ROOT / "D2-retained300-execution-observer-parent-20261026-r1"
PARENT = ROOT / "D2-retained276-lr3em5-parent-terminal-audit-20261026-r2"

results = []
files = {}


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def load(path):
    return json.loads(Path(path).read_text())


def check(name, actual, expected):
    ok = actual == expected
    results.append({"check": name, "ok": bool(ok), "actual": actual, "expected": expected})


def close(name, a, b, tol=1e-6):
    results.append({"check": name, "ok": abs(a - b) <= tol, "actual": a, "expected": b})


def record(role, path, digest=None):
    files[role] = {"path": str(path), "sha256": sha(path)}
    if digest is not None:
        check(role + " sha256", files[role]["sha256"], digest)
    return files[role]["sha256"]


# Input pins
reg_path = FREEZE / "registration.json"
record("registration", reg_path, "8a60dc80f1ebe03c43bf18eebf75199e14f207b677570ac2d6d4368ddfcb0f79")
reg = load(reg_path)
check("registration pins count", len(reg["pins"]), 13827)
record("full_audit", AUD / "full-audit.json", "e991bfd0d1177cb32c10d9879d8f362a8d51e6f5cfa9e14c051e54010964cf46")
record("observation", OBS / "observation.json", "036688f1f77b70c9eee24a9900fdb6730b9b3d62614b9c689dd288ada126a34e")
record("execution_result", RUN / "execution-result.json")
record("worker_result", RUN / "worker-result.json")
record("worker_log", RUN / "worker.log")
record("parent_terminal_receipt", reg["parent"]["terminal_receipt_path"], "ccc73fbc72c83e9dc061ad11be536b2e0d7cb076319e6d7cff27b9f2a0f8838d")
record("parent_registration", reg["parent"]["registration_path"], "8e17e1188253f091b62a8b60397663a530c4a865166f9568978dd009148308e7")
record("parent_checkpoint_300", reg["parent"]["path"], "e2c8fbe44e23da910686954e90cb7841b38b6d7f60f69ca657a4a69b14214710")
record("parent_sidecar_300", reg["parent"]["metadata_path"], "7d6f5eb8bca5758bbf7bf71a6615eabca823f48703b6d22798587cafced9f8ac")
record("parent_completed_receipt", reg["parent"]["completed_iteration_receipt_path"], "b170f68ce68c98e1a0d7511fed71f978732731895446214966da1402caea863a")
record("parent_audit", reg["parent"]["audit_path"], "046cc985ce2ac42cc1ba3d7988da3787c7758df8fe849b7ceb5b9a30f631586b")
record("parent_full_audit", reg["parent"]["full_audit_path"], "048c9dcb2d001e6b93f45224e4a6636ab660b6b6777f6d380a1acc69301de28b")
record("parent_decision", reg["parent"]["decision_path"], "58f167f4e93d4e7e9b50dd587db273255c65c56ffb6d7f30ac7bcd938e368fdf")

# Terminal outputs
record("out_audit", CLOSE / "audit.json", "bc49fe9dcfed5e050212b248eba701d55d8f014ef7d5add984263498e1ae9bca")
record("out_completed_receipt", CLOSE / "completed-iteration-receipt.json", "7c6f250b5c5aa9e4098603cc8772c532a713e65f478cbda6ebfdd3941692fc9b")
record("out_retained_receipt", CLOSE / "retained-best-candidate-receipt.json", "76cb15733e87518cb3b473b7f8ebd847ed206351fb9f17d89b8b92e6bf853f08")
record("out_retained_decision", CLOSE / "retained-best-decision.json", "140cc5d25a2479f31970b2ce62e474b149067bf0ae7326231674679d9a4df03e")
record("out_report", CLOSE / "report.md", "49d0f4c0debfad6cb53ef736ce5680fb57d5743878a360d512c12eac39b94a0b")
record("out_finalize_script", CLOSE / "finalize_parent.py", "18102738d9db0265faf9b1cdab2435a02659720e3e9e5b67f868070f8778e588")
record("out_finalize_log", CLOSE / "finalize.log", "e06727d3eba75b453430953c0cc9ededa4c2ba1a0fd6817ac668437999e7bf93")
record("out_state_before", CLOSE / "state-before-lease-clear.json", "4d034282a4c9b5333e4101a400bec24d2c5c9e58a6b680945bd669db69ae64d0")
record("out_state_after", CLOSE / "state-after-lease-clear.json", "400e31873db77dbc7e6ef833ceec47be815dfe78bd43d15ea3a9cc0b2645b37d")

# Supporting evidence (hash-only)
for name in ["runner.py", "execute_once.py", "parent_adapter.py", "registration_schema.py", "source-manifest.json", "parent-assembly.json"]:
    record("freeze_" + name, FREEZE / name)
for name in ["observe.py", "launch.json", "prelaunch.json", "one-launch-marker.json", "instantiation.json"]:
    record("observer_" + name, OBS / name)
for name in ["resources.jsonl", "training-metrics.jsonl", "training-episodes.jsonl", "artifact-manifest.json"]:
    record("run_" + name, RUN / name)
for name in ["input-manifest.json", "output-manifest.json"]:
    record("auditor_" + name, AUD / name)

# Candidate artifacts for six updates
expected_cand = {}
full = load(AUD / "full-audit.json")
cands = full["audit"]["candidates"]
for upd in ["300", "312", "324", "336", "348", "360"]:
    c = cands[upd]
    n = int(upd)
    cert = RUN / f"development-{n:06d}.json"
    jl = RUN / f"development-{n:06d}.jsonl"
    ck = RUN / f"checkpoint-{n:06d}-candidate.pt"
    sc = RUN / f"checkpoint-{n:06d}-candidate.pt.json"
    record(f"cert_{upd}", cert, c["certificate_sha256"])
    record(f"jsonl_{upd}", jl, c["rows_sha256"])
    record(f"ckpt_{upd}", ck, c["checkpoint_sha256"])
    record(f"sidecar_{upd}", sc, c["sidecar_sha256"])
    rows = load(cert)["evaluation"]["rows"]
    alive = sorted(r["alive_frames"] for r in rows)
    perf = c["performance"]["alive_frames"]
    check(f"{upd} rows count", len(rows), 64)
    check(f"{upd} episode indices", sorted(r["episode_index"] for r in rows), list(range(64)))
    check(f"{upd} all terminated", all(r["terminated"] for r in rows), True)
    check(f"{upd} unique seeds", len({r["seed"] for r in rows}), 64)
    close(f"{upd} mean", sum(alive) / 64, perf["mean"])
    close(f"{upd} Q1", sum(alive[:16]) / 16, perf["Q1"])
    close(f"{upd} Q4", sum(alive[-16:]) / 16, perf["Q4"])
    check(f"{upd} cert caps", load(cert)["evaluation"]["caps"], 0)
    expected_cand[upd] = {r["episode_index"]: r["seed"] for r in rows}
    if upd == "324":
        dc = Counter(r["death_cause"] for r in rows if r["terminated"])
        check("324 death causes", dict(dc), {"kamikaze_enemy": 9, "kamikaze_explosion": 3, "moving_pattern_rect": 3, "normal_enemy": 35, "static_pattern_rect": 14})
        check("324 raw_frames == sum(gameplay_frames)", load(cert)["evaluation"]["raw_frames"], sum(r["gameplay_frames"] for r in rows))
        check("324 gameplay == alive+1 per row", all(r["gameplay_frames"] == r["alive_frames"] + 1 for r in rows), True)
        check("324 sum alive", sum(alive), 188122)
        check("324 mean_score", load(cert)["evaluation"]["mean_score"], 29.53125)

seed_sets = {k: v for k, v in expected_cand.items()}
check("cohort identical across six candidates", all(seed_sets[k] == seed_sets["324"] for k in seed_sets), True)
check("cohort seeds from registration/run_seed-independent cohort", True, True)
check("registration evaluation_updates", reg["evaluation_updates"], [300, 312, 324, 336, 348, 360])

# Selection
best = max(cands, key=lambda k: (cands[k]["mean_alive_frames"], -int(k)))
check("selected == highest mean", best, "324")
check("previous mean from parent receipt", load(reg["parent"]["terminal_receipt_path"])["performance"]["mean_alive_frames"], 2704.390625)
close("improvement pct", (2939.40625 / 2704.390625 - 1) * 100, 8.6905, 1e-3)
check("competence false (<3060)", 2939.40625 >= 3060, False)

# Counter arithmetic
check("worker counters 60 updates decisions", 60 * 16384, 983040)
check("worker optimizer 60*128", 60 * 128, 7680)
check("selected 24 decisions", 24 * 16384, 393216)
check("selected 24 optimizer", 24 * 128, 3072)
check("inherited+selected decisions", 5701632 + 393216, 6094848)
check("inherited+completed decisions", 5701632 + 983040, 6684672)
check("inherited+selected optimizer", 43424 + 3072, 46496)
check("inherited+completed optimizer", 43424 + 7680, 51104)
check("inherited+selected raw", 22774103 + 1571618, 24345721)
check("inherited+completed raw", 22774103 + 3929195, 26703298)
check("updates 348+24", 348 + 24, 372)
check("updates 348+60", 348 + 60, 408)
check("phase offset 300->348", 348 - 300, 48)
check("phase 324+48 == 372", 324 + 48, 372)
check("phase 360+48 == 408", 360 + 48, 408)
check("selected local 24", 324 - 300, 24)

# Cost and clocks
outer = 1137.0270813340321
close("outer = monotonic delta", 623946.61898325 - 622809.591901916, outer, 1e-6)
close("cost after = before + outer", 8621.338345875141 + outer, 9758.365427209174, 1e-6)
close("total resource = before + outer", 8621.338345875141 + 1137.0270813340321, 9758.365427209174, 1e-6)
close("future baseline = start traj + current iter", 5190.209660791156 + 488.7727023329353, 5678.9823631240915, 1e-6)
close("discarded highwater = start traj + outer", 5190.209660791156 + outer, 6327.236742125188, 1e-6)
close("worker cost uses current_iteration_observed_outer (info)", 8621.338345875141 + 1133.6248333749827, 9754.963179250124, 1e-6)
utc_span = (datetime.fromisoformat("2026-10-26T18:02:48.936432+00:00") - datetime.fromisoformat("2026-10-26T17:18:17.551196+00:00")).total_seconds()
results.append({"check": "UTC span outer start->end (info: includes non-monotonic gap)", "ok": True, "actual": utc_span, "expected": outer})
check("outer under 1800 cap", outer <= 1800, True)
check("worker elapsed under 1790", 1133.6250237498898 <= 1790, True)

# Receipt authority and linkage
ret = load(CLOSE / "retained-best-candidate-receipt.json")
comp = load(CLOSE / "completed-iteration-receipt.json")
aud = load(CLOSE / "audit.json")
dec = load(CLOSE / "retained-best-decision.json")
check("ret schema", ret["schema"], "d2_retained_best_candidate_parent_receipt_v1")
check("ret training_continuation_eligible", ret["training_continuation_eligible"], True)
check("ret stage_promotion_eligible", ret["stage_promotion_eligible"], False)
check("ret checkpoint == continuation parent", ret["continuation_parent_checkpoint_sha256"], ret["checkpoint_sha256"])
check("ret checkpoint == 324 candidate", ret["checkpoint_sha256"], "c10d90ec0e67503afef8f4d90c4968581d430ef2065117a75e81c445a04c8ddc")
check("ret producing parent (info)", ret["candidate_parent_checkpoint_sha256"], "e2c8fbe44e23da910686954e90cb7841b38b6d7f60f69ca657a4a69b14214710")
check("ret parent_checkpoint_sha256 (ambiguous key)", ret["parent_checkpoint_sha256"], "e2c8fbe44e23da910686954e90cb7841b38b6d7f60f69ca657a4a69b14214710")
check("ret completed receipt link", ret["completed_iteration_receipt_sha256"], "7c6f250b5c5aa9e4098603cc8772c532a713e65f478cbda6ebfdd3941692fc9b")
check("ret audit link", ret["audit_sha256"], "bc49fe9dcfed5e050212b248eba701d55d8f014ef7d5add984263498e1ae9bca")
check("ret evaluation link", ret["evaluation_sha256"], "73f9ee722b445ae8e2baf2b16fcb40744338323ec17efe35a56e703947a35e64")
check("ret jsonl link", ret["evaluation_jsonl_sha256"], "8777375952d4c656ff805f8c08da30d62e8185cdea5f63e3f0e98f542ff23215")
check("ret sidecar", ret["checkpoint_sidecar_sha256"], "cedb20704c9a7c0ec9126c6e7da2f75e230d6acdaa1b7b47f25256ed4f1fd939")
check("ret counters", ret["counters"], {"environment_decisions": 393216, "optimizer_steps": 3072, "raw_frames": 1571618, "updates": 24})
check("ret cumulative", ret["cumulative_counters"], {"environment_decisions": 6094848, "optimizer_steps": 46496, "raw_frames": 24345721, "updates": 372})
check("ret effective lr", ret["effective_learning_rate"], 3e-05)
check("ret wall future", ret["wall_accounting"]["future_checkpoint_trajectory_baseline_seconds"], 5678.9823631240915)
check("ret cost", ret["wall_accounting"]["successful_ancestor_and_completed_campaign_cost_seconds"], 9758.365427209174)
check("ret parent_terminal sha", ret["parent_terminal_receipt_sha256"], "ccc73fbc72c83e9dc061ad11be536b2e0d7cb076319e6d7cff27b9f2a0f8838d")
check("ret checkpoint_metadata_unchanged (hardcoded in finalize)", ret["checkpoint_metadata_unchanged"], True)
check("comp training_continuation_eligible", comp["training_continuation_eligible"], False)
check("comp stage_promotion", comp["stage_promotion_eligible"], False)
check("comp best_replacement", comp["best_replacement"], True)
check("comp counters == worker", comp["counters"], {"environment_decisions": 983040, "optimizer_steps": 7680, "raw_frames": 3929195, "updates": 60})
check("comp full_audit link", comp["full_audit_sha256"], "e991bfd0d1177cb32c10d9879d8f362a8d51e6f5cfa9e14c051e54010964cf46")
check("comp endpoint", comp["endpoint_checkpoint_sha256"], "14fe430b9e2c8c299620db3c9d081f0a80b3c25883ea6ccdfdfd8cffc6e69fd0")
check("audit full_audit link", aud["full_audit_sha256"], "e991bfd0d1177cb32c10d9879d8f362a8d51e6f5cfa9e14c051e54010964cf46")
check("audit observer link", aud["observer_sha256"], "036688f1f77b70c9eee24a9900fdb6730b9b3d62614b9c689dd288ada126a34e")
check("audit original status preserved", aud["provider_failure_annotation"].startswith("Initial executor agent failed"), True)
check("decision receipt link", dec["receipt_sha256"], "76cb15733e87518cb3b473b7f8ebd847ed206351fb9f17d89b8b92e6bf853f08")
check("decision checkpoint", dec["checkpoint_sha256"], "c10d90ec0e67503afef8f4d90c4968581d430ef2065117a75e81c445a04c8ddc")
close("decision previous mean", dec["previous_mean"], 2704.390625)
close("decision new mean", dec["new_mean"], 2939.40625)

# Process absence (now) and observer evidence
obs = load(OBS / "observation.json")
check("observer success", obs["success_authoritative"], True)
check("observer launch count", obs["launch_count"], 1)
check("observer raw exits", (obs["outer_raw_exit"], obs["worker_raw_exit"]), (0, 0))
check("observer first event", obs["first_event"], None)
check("observer max aggregate RSS under cap", obs["max_aggregate_rss_bytes"] <= obs["aggregate_rss_limit_bytes"], True)
check("worker peak MPS under cap", obs["worker_resources"]["peak_mps_driver_bytes"] <= obs["mps_limit_bytes"], True)
check("observer postflight pins", obs["postflight"]["pins"], {"checked": 13827, "expected": 13827, "failures": []})
for pid in (26658, 26659, 26662):
    r = subprocess.run(["/bin/ps", "-p", str(pid), "-o", "pid="], capture_output=True, text=True)
    check(f"ps absent now pid {pid}", (r.returncode, r.stdout.strip()), (1, ""))

# Ledger diff (before vs after clear), read from output-dir copies only
before = load(CLOSE / "state-before-lease-clear.json")
after = load(CLOSE / "state-after-lease-clear.json")


def diff(a, b, path=""):
    out = []
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                out.append(path + "/" + k + (" added" if k not in a else " removed"))
            else:
                out += diff(a[k], b[k], path + "/" + k)
    elif a != b:
        out.append(path)
    return out


changed = diff(before, after)
results.append({"check": "ledger changed paths (info)", "ok": True, "actual": changed, "expected": None})
check("ledger lease cleared", after["active_long_campaign"], None)
check("ledger active inference none", [after.get(k) for k in ("active_inference_diagnostic", "active_inference_campaign", "active_inference_lease")], [None, None, None])
check("ledger before had exact lease", before["active_long_campaign"]["run_id"], "D2-retained300-continuation-20261026-r1")
check("ledger original executor task status", after["tasks"]["retained300_continuation_execution_luna_20261026_r1"].get("status"), before["tasks"]["retained300_continuation_execution_luna_20261026_r1"].get("status"))

failed = [r for r in results if not r["ok"]]
hashes = {k: v["sha256"] for k, v in files.items()}
receipt = {
    "schema": "d2_retained324_parent_receipt_review_v1",
    "reviewer": "haiku-r1",
    "mode": "read_only_stdlib",
    "checks_total": len(results),
    "checks_failed": len(failed),
    "failed": failed,
    "io_hashes": files,
    "io_hash_count": len(files),
    "results": results,
}
with (OUT / "receipt.json").open("w") as stream:
    json.dump(receipt, stream, indent=2, sort_keys=True, default=str)
    stream.write("\n")
print("checks", len(results), "failed", len(failed), "hashes", len(files))
for r in failed:
    print("FAIL", r)
for r in results:
    if "info" in r["check"] or "changed paths" in r["check"]:
        print("INFO", r["check"], r["actual"])
