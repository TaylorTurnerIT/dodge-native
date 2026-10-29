"""Pure-Python checks of the death-trace aggregation helpers (no native code)."""
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "learning" / "scripts"


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


a = load("death_trace_analysis")
parity = load("death_trace_parity")


def test_phase_edges_follow_alive_frames():
    assert [a.phase_index(x) for x in (0, 999, 1000, 1999, 2000, 2999, 3000, 4999, 5000, 17999)] == \
        [0, 0, 1, 1, 2, 2, 3, 3, 4, 4]


def test_recency_exposure_partitions_every_frame_exactly():
    triggers, end = [10, 200, 205], 1500
    for lo, hi in ((0, 10**9), (0, 1000), (1000, 2000), (150, 650)):
        got = a.recency_exposure(triggers, end, lo, hi)
        assert sum(got.values()) == max(0, min(hi, end) - lo)
    got = a.recency_exposure([10, 200], 700, 0, 10**9)
    assert dict(got) == {"never": 10, "1-100": 200, "101-300": 290, "301-600": 200}


def test_recency_uses_triggers_strictly_before_the_frame():
    # Frame 11 is the first frame whose last trigger (frame 10) is strictly earlier.
    got = a.recency_exposure([10], 11, 10, 10**9)
    assert dict(got) == {"1-100": 1}
    assert a.last_trigger_before([10, 20], 20) == 10
    assert a.last_trigger_before([10, 20], 10) is None


def row(seed, alive, terminated=True, cause="normal_enemy", triggers=(), spans=(), death=None):
    end = alive + 1 if terminated else alive
    context = None
    if terminated:
        context = dict(cause=cause, frame=end, killer=dict(personality=0, fyou_spawned=True, age_frames=40),
                       enemies_alive_normal=3, enemies_alive_kamikaze=0, enemies_alive_explosion=0,
                       enemies_alive_powerup=0, fyou_enemies_alive=2, center_dwell_frames=60, fyou_timer=0,
                       fyou_enabled=True, active_pattern=None, last_pattern_end_frame=None, freeze_active=False)
        context.update(death or {})
    return dict(seed=seed, alive_frames=alive, gameplay_frames=end, terminated=terminated, truncated=not terminated,
                death_cause=cause if terminated else None, fatal_gameplay_frame=end if terminated else None,
                trace=dict(frames=end, center_dwell_frames_at_end=60, fyou_trigger_frames=list(triggers),
                           fyou_trigger_spawned=[4] * len(triggers), patterns=list(spans), death=context))


def test_columns_and_bootstrap_ratios_on_synthetic_games():
    family = {1: "1+2", 2: "1+2"}
    rows = [row(1, 500, triggers=[100]), row(2, 1500, triggers=[300, 1400]), row(3, 2500),
            row(4, 18000, terminated=False, triggers=[50])]
    games = [a.prepare_game(r) for r in rows]
    cols = a.build_columns(games, family)
    sums = a.cluster_sum(cols, games, [1, 2, 3, 4])
    boot = a.Bootstrap(4, 50, 1)
    table = a.Table(sums, boot)
    assert table.total("died|0-1k") == 1 and table.total("died|1k-2k") == 1 and table.total("died|2k-3k") == 1
    assert table.total("atrisk|1k-2k") == 3  # seeds 2, 3, 4 were alive at 1000
    assert table.total("atrisk|1k-2k|fy1") == 2  # seeds 2 (trigger 300) and 4 (trigger 50)
    assert table.total("died|0-1k|fy_any") == 1 and table.total("died|2k-3k|fy_any") == 0
    # Trigger at 1400, death frame 1501: 101 frames apart.
    assert table.total("died|1k-2k|fy_w100") == 0 and table.total("died|1k-2k|fy_w300") == 1
    assert table.ratio("died|0-1k|fy_any", "died|0-1k")["est"] == 1.0
    assert table.total("expo|5k+|all") == 18000 - 5000
    # Exposure buckets partition each phase.
    for phase, lo, hi in a.PHASES:
        buckets = sum(table.total(f"expo|{phase}|{label}") for label in ["never", "1-100", "101-300", "301-600", "601+"])
        assert buckets == table.total(f"expo|{phase}|all")


def test_unterminated_games_never_count_as_deaths():
    games = [a.prepare_game(row(1, 18000, terminated=False))]
    cols = a.build_columns(games, {})
    assert not any(name.startswith("died|") for name in cols.data)


def test_inconsistent_trace_is_rejected():
    bad = row(1, 500)
    bad["trace"]["death"]["frame"] += 1
    with pytest.raises(AssertionError):
        a.prepare_game(bad)


def test_parity_compare_flags_any_difference(tmp_path):
    new = dict(rows=[row(1, 500), row(2, 900)])
    saved = dict(rows=[{k: v for k, v in r.items() if k != "trace"} for r in new["rows"]])
    (tmp_path / "n.json").write_text(json.dumps(new))
    (tmp_path / "s.json").write_text(json.dumps(saved))
    assert parity.compare(tmp_path / "n.json", tmp_path / "s.json")["mismatches"] == []
    saved["rows"][1]["alive_frames"] += 1
    (tmp_path / "s.json").write_text(json.dumps(saved))
    assert len(parity.compare(tmp_path / "n.json", tmp_path / "s.json")["mismatches"]) == 1


def test_pattern_exposure_partitions_frames_and_matches_death_state():
    span = dict(id=1, pattern_type=0, start_frame=900, end_frame=1100)
    active = dict(id=1, pattern_type=0, variants=[2], start_frame=1450, frames_since_start=51)
    rows = [row(1, 1500, spans=[span, dict(id=5, pattern_type=1, start_frame=1450, end_frame=None)],
                death=dict(active_pattern=active))]
    games = [a.prepare_game(r) for r in rows]
    cols = a.build_columns(games, {1: "1+2", 5: "5"})
    sums = a.cluster_sum(cols, games, [1])
    table = a.Table(sums, a.Bootstrap(1, 10, 1))
    # Span 1 covers frames 901-1100; span 5 covers 1451-1501 (death frame).
    assert table.total("pexpo|0-1k|active") == 100 and table.total("pexpo|1k-2k|active") == 100 + 51
    for phase, lo, hi in a.PHASES:
        assert table.total(f"pexpo|{phase}|active") + table.total(f"pexpo|{phase}|inactive") == \
            table.total(f"expo|{phase}|all")
    assert table.total("died|1k-2k|pat_active") == 1
