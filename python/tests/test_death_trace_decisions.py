"""Per-decision recording in the death-trace evaluator (CPU stub policy, no checkpoint)."""
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest
import torch

SCRIPTS = Path(__file__).resolve().parents[2] / "learning" / "scripts"
spec = importlib.util.spec_from_file_location("death_trace_eval", SCRIPTS / "death_trace_eval.py")
ev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ev)

SEEDS = [0xDA000000, 0xDA000001]


class Stub:
    """Deterministic policy whose logits depend on the observation, so replays agree."""

    def __call__(self, global_feats, entity_feats, entity_types, entity_mask):
        n = global_feats.shape[0]
        seed = (global_feats[:, 0, :4].sum(dim=1) * 1000).abs().long() % 9
        logits = torch.zeros(n, 9)
        logits[torch.arange(n), seed] = 2.0
        logits[:, 0] -= 1.0
        return type("Out", (), {"logits": logits})()


def env_factory(**kwargs):
    from dodge_rl import VecDodgeEnv
    try:
        return VecDodgeEnv(**kwargs)
    except TypeError as error:
        if "trace" in str(error):
            pytest.skip("importable extension predates the gameplay trace (no build performed)")
        raise


def collect(decisions):
    return ev.collect_rows(Stub(), env_factory, SEEDS, repeat=4, mode="argmax", backend="cpu",
                           guard=lambda: None, decisions=decisions)


def test_recording_does_not_change_outcomes_and_columns_align():
    plain, rich = collect(False), collect(True)
    for a, b in zip(plain, rich):
        assert {k: v for k, v in b.items() if k != "decisions"} == a
        cols = b["decisions"]
        assert set(cols) == set(ev.DECISION_COLUMNS)
        n = len(cols["a"])
        # One decision per four gameplay frames, the last possibly partial.
        assert n == -(-b["gameplay_frames"] // 4)
        assert all(len(v) == n for v in cols.values())
        assert cols["a"][-8:] == b["last_actions"][-8:]
        assert all(0 <= v <= 8 for v in cols["a"])
        assert all(0 <= e <= 220 for e in cols["ent"]) and all(0 <= p <= 1000 for p in cols["pa"])


def test_observation_gap_matches_trace_sample_at_shared_frames():
    # Decisions start at frames 0, 4, 8, ...; trace samples sit at frames 30, 60, ...
    # so frame 60k is both. The observation gap must agree with the trace's own gap.
    checked = 0
    for row in collect(True):
        samples = row["trace"]["samples"]
        for frame, gap, enemies in zip(samples["frame"], samples["enemy_gap"], samples["enemies"]):
            if frame % 60 or frame // 4 >= len(row["decisions"]["eg"]):
                continue
            eg = row["decisions"]["eg"][frame // 4]
            if gap >= 0 and eg >= 0:
                assert abs(eg / 10.0 - gap / 65536.0) < 0.15
                checked += 1
    assert checked > 3


def test_decision_columns_pick_nearest_lethal_entities():
    g = np.zeros((1, 1, 14), np.float32)
    g[0, 0, 0], g[0, 0, 1], g[0, 0, 9] = 0.5, -0.25, 1.0
    f = np.zeros((1, 80, 16), np.float32)
    t = np.zeros((1, 80), np.int64)
    m = np.zeros((1, 80), bool)

    def put(slot, kind, gx, gy, lethal, dx=0.0, dy=0.0):
        t[0, slot], m[0, slot] = kind, True
        f[0, slot, 10], f[0, slot, 11], f[0, slot, 15] = gx / 64.0, gy / 64.0, float(lethal)
        f[0, slot, 4], f[0, slot, 5] = dx / 128.0, dy / 128.0

    put(0, 1, 30.0, 40.0, True)              # enemy, gap 50
    put(1, 2, 3.0, 4.0, True, dx=-6, dy=2)   # enemy, gap 5 (nearest)
    put(2, 3, 1.0, 0.0, False)               # not lethal: ignored
    put(3, 5, 0.0, 0.0, True)                # powerup: ignored
    put(4, 7, 8.0, 6.0, True)                # lethal rectangle, gap 10
    put(5, 8, 2.0, 0.0, False)               # pending rectangle, gap 2
    out = ev.decision_columns(g, f, t, m)
    assert out["eg"][0] == 50 and (out["edx"][0], out["edy"][0]) == (-60, 20)
    assert out["rg"][0] == 100 and out["pg"][0] == 20 and out["pv"][0] == 1
    assert (out["x"][0], out["y"][0]) == (960, 480)


def load_actions():
    spec = importlib.util.spec_from_file_location("death_trace_actions", SCRIPTS / "death_trace_actions.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_bearing_class_uses_screen_axes_and_ignores_neutral():
    act = load_actions()
    # Enemy 10 px to the right and level: moving right is toward, left is away, up is sideways.
    a = np.array([2, 1, 3, 0, 6, 8])
    edx, edy = np.full(6, 100), np.zeros(6)
    got = act.bearing_class(a, edx, edy, np.ones(6, bool))
    assert got.tolist() == [0, 1, 2, 3, 0, 0]
    assert act.bearing_class(a, edx, edy, np.zeros(6, bool)).tolist() == [4] * 6


def test_action_metrics_are_proper_shares_with_ordered_intervals():
    act = load_actions()
    rows = collect(True)
    metrics = act.all_metrics(rows)
    total = sum(len(r["decisions"]["a"]) for r in rows)
    json.dumps(metrics, allow_nan=False)
    assert metrics["decisions"] == total
    hist = metrics["histogram_overall"][0]
    assert hist["decisions"] == total
    assert abs(sum(hist[name]["est"] for name in act.ACTIONS) - 1.0) < 1e-9
    for table in ("histogram_by_phase", "confidence_by_enemy_gap", "response_by_enemy_gap"):
        for entry in metrics[table]:
            for key, stat in entry.items():
                if isinstance(stat, dict):
                    assert stat["lo"] <= stat["est"] <= stat["hi"] or entry["decisions"] == 0
    # Pre-death index 0 is the fatal decision: its action is the last recorded one.
    last = [r["decisions"]["a"][-1] for r in rows]
    c = act.stack(rows)
    assert c["a"][c["before"] == 0].tolist() == last


def test_action_charts_render_from_metrics(tmp_path):
    act = load_actions()
    rows = collect(True)
    metrics_file = tmp_path / "metrics.json"
    metrics_file.write_text(json.dumps(dict(actions=act.ACTIONS, metrics=act.all_metrics(rows)), allow_nan=False))
    spec = importlib.util.spec_from_file_location("death_trace_action_charts", SCRIPTS / "death_trace_action_charts.py")
    charts = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(charts)
    import sys
    out = tmp_path / "charts.html"
    sys.argv = ["x", "--metrics", str(metrics_file), "--out", str(out), "--split-dir", str(tmp_path / "split")]
    charts.main()
    assert out.read_text().count("<svg") == 6
    assert len(list((tmp_path / "split").glob("action*.html"))) == 6
