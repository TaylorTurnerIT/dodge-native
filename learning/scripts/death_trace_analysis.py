"""Aggregate death-trace group files into phase / fyou / pattern tables.

Every statistic is a ratio of sums over games, so one set of seed-cluster
bootstrap draws (resampling seeds, keeping every game of a seed together)
yields all intervals and the paired 1-frame versus 4-frame contrasts.

    python -I death_trace_analysis.py --out tables.json \
        --setting argmax_r1=fresh/argmax_r1.json --setting argmax_r4=fresh/argmax_r4.json \
        --pattern-table pattern_table.json

Settings that name several files (comma separated) pool them as repetitions of
the same seed list. Resampling is by seed across all settings listed together
in one `--set` group, so paired contrasts use the same cluster indices.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

PHASES = [("0-1k", 0, 1000), ("1k-2k", 1000, 2000), ("2k-3k", 2000, 3000), ("3k-5k", 3000, 5000),
          ("5k+", 5000, 10**9)]
CAUSES = ("normal_enemy", "kamikaze_enemy", "kamikaze_explosion", "static_pattern_rect",
          "moving_pattern_rect", "unknown")
FYOU_WINDOWS = (100, 300, 600)
RECENCY = (("1-100", 1, 100), ("101-300", 101, 300), ("301-600", 301, 600), ("601+", 601, 10**9))
DWELL_BINS = (("0", 0, 0), ("1-25", 1, 25), ("26-50", 26, 50), ("51+", 51, 10**9))
ENEMY_BINS = (("0-4", 0, 4), ("5-9", 5, 9), ("10-14", 10, 14), ("15+", 15, 10**9))
AGE_BINS = (("<=30", 0, 30), ("31-100", 31, 100), ("101-300", 101, 300), ("301-600", 301, 600),
            ("601+", 601, 10**9))
PAT_BINS = (("<=60", 0, 60), ("61-180", 61, 180), ("181-600", 181, 600), ("601+", 601, 10**9))
TYPE_NAMES = {0: "static", 1: "moving"}
WALL_MARGIN = 20  # pixels from the 128x128 field edge


def phase_index(frames):
    for i, (_, lo, hi) in enumerate(PHASES):
        if lo <= frames < hi:
            return i
    raise ValueError(frames)


def bin_label(value, bins):
    for label, lo, hi in bins:
        if lo <= value <= hi:
            return label
    raise ValueError(value)


def last_trigger_before(triggers, frame):
    """Most recent trigger frame strictly before `frame` (None if none)."""
    best = None
    for t in triggers:
        if t < frame:
            best = t
        else:
            break
    return best


def recency_exposure(triggers, end, lo, hi):
    """Frames f in (lo, min(hi, end)] by time since the last trigger strictly before f."""
    stop = min(hi, end)
    out = defaultdict(int)
    if stop <= lo:
        return out
    marks = [0] + list(triggers)
    for k, t in enumerate(marks):
        seg_lo = t  # frames (t, nxt] have last trigger t; k == 0 means none yet
        nxt = marks[k + 1] if k + 1 < len(marks) else 10**9
        a, b = max(seg_lo, lo), min(nxt, stop)
        if b <= a:
            continue
        if k == 0:
            out["never"] += b - a
            continue
        for label, r_lo, r_hi in RECENCY:
            # s = f - t in [r_lo, r_hi]  <=>  f in [t + r_lo, t + r_hi]
            x = max(a + 1, t + r_lo)
            y = min(b, t + r_hi)
            if y >= x:
                out[label] += y - x + 1
    return out


def prepare_game(row):
    trace = row["trace"]
    terminated = row["terminated"]
    end = row["fatal_gameplay_frame"] if terminated else row["gameplay_frames"]
    death = trace["death"]
    if terminated:
        assert death is not None and death["frame"] == end and death["cause"] == row["death_cause"]
        assert row["alive_frames"] + 1 == end
    else:
        assert death is None
    triggers = [f for f in trace["fyou_trigger_frames"]]
    assert triggers == sorted(triggers)
    return dict(seed=row["seed"], alive=row["alive_frames"], end=end, terminated=terminated,
                cause=row["death_cause"], triggers=triggers, patterns=trace["patterns"], death=death,
                dwell_end=trace["center_dwell_frames_at_end"])


class Columns:
    """Named per-game columns; unknown names are created lazily as zeros."""

    def __init__(self, n):
        self.n = n
        self.data = {}

    def add(self, name, i, value=1.0):
        column = self.data.get(name)
        if column is None:
            column = self.data[name] = np.zeros(self.n)
        column[i] += value

    def touch(self, name):
        self.data.setdefault(name, np.zeros(self.n))


def build_columns(games, pattern_family):
    cols = Columns(len(games))
    for i, g in enumerate(games):
        end, alive, triggers = g["end"], g["alive"], g["triggers"]
        d = g["death"]
        for p, (pname, lo, hi) in enumerate(PHASES):
            if alive >= lo:
                cols.add(f"atrisk|{pname}", i)
                has_fy = any(t <= lo for t in triggers) if lo > 0 else False
                key = "fy1" if has_fy else "fy0"
                cols.add(f"atrisk|{pname}|{key}", i)
                recent = any(lo - 300 < t <= lo for t in triggers) if lo > 0 else False
                rkey = "rec300" if recent else "norec300"
                cols.add(f"atrisk|{pname}|{rkey}", i)
            for label, n_frames in recency_exposure(triggers, end, lo, hi).items():
                cols.add(f"expo|{pname}|{label}", i, n_frames)
            cols.add(f"expo|{pname}|all", i, max(0, min(hi, end) - lo))
        for pname, lo, hi in PHASES:
            window_end = min(hi, end)
            total = max(0, window_end - lo)
            active = 0
            for span in g["patterns"]:
                stop = span["end_frame"] if span["end_frame"] is not None else end
                overlap = max(0, min(stop, window_end) - max(span["start_frame"], lo))
                active += overlap
                ptype = TYPE_NAMES.get(span["pattern_type"], span["pattern_type"])
                cols.add(f"pexpo|{pname}|{ptype}", i, overlap)
            cols.add(f"pexpo|{pname}|active", i, active)
            cols.add(f"pexpo|{pname}|inactive", i, total - active)
        if not g["terminated"]:
            continue
        p = phase_index(alive)
        pname = PHASES[p][0]
        died = f"died|{pname}"
        cols.add(died, i)
        cols.add(f"{died}|cause|{g['cause']}", i)
        hazard_key = "fy1" if (PHASES[p][1] > 0 and any(t <= PHASES[p][1] for t in triggers)) else "fy0"
        cols.add(f"died_hazard|{pname}|{hazard_key}", i)
        rkey = "rec300" if (PHASES[p][1] > 0 and any(PHASES[p][1] - 300 < t <= PHASES[p][1] for t in triggers)) \
            else "norec300"
        cols.add(f"died_hazard|{pname}|{rkey}", i)
        # Recency exposure bucket at death frame.
        last = last_trigger_before(triggers, end)
        if last is None:
            bucket = "never"
        else:
            bucket = bin_label(end - last, RECENCY)
        cols.add(f"deathrec|{pname}|{bucket}", i)
        # Fyou before death.
        upto = [t for t in triggers if t <= end]
        cols.add(f"{died}|fy_any", i, 1.0 if upto else 0.0)
        for w in FYOU_WINDOWS:
            cols.add(f"{died}|fy_w{w}", i, 1.0 if upto and end - upto[-1] <= w else 0.0)
        cols.add(f"{died}|fy_count", i, len(upto))
        # Cause x fyou-within-300.
        if upto and end - upto[-1] <= 300:
            cols.add(f"{died}|cause|{g['cause']}|fy_w300", i)
        # Killer provenance.
        killer = d["killer"]
        if killer is not None:
            cols.add(f"{died}|enemy_kill", i)
            if killer["fyou_spawned"] is not None:
                cols.add(f"{died}|killer_known", i)
                if killer["fyou_spawned"]:
                    cols.add(f"{died}|killer_fyou", i)
                if killer["personality"] == 0:
                    cols.add(f"{died}|normal_kill_known", i)
                    if killer["fyou_spawned"]:
                        cols.add(f"{died}|normal_kill_fyou", i)
                prov = "fyou" if killer["fyou_spawned"] else "other"
                if killer["age_frames"] is not None:
                    cols.add(f"{died}|killer_age|{prov}|{bin_label(killer['age_frames'], AGE_BINS)}", i)
                    cols.add(f"{died}|killer_age_known|{prov}", i)
                cols.add(f"{died}|killer_prov|{prov}", i)
        # Pattern at death.
        ap = d["active_pattern"]
        if ap is not None:
            cols.add(f"{died}|pat_active", i)
            cols.add(f"{died}|pat_id|{ap['id']}", i)
            cols.add(f"{died}|pat_type|{TYPE_NAMES.get(ap['pattern_type'], ap['pattern_type'])}", i)
            cols.add(f"{died}|pat_family|{pattern_family[ap['id']]}", i)
            cols.add(f"{died}|pat_t|{bin_label(ap['frames_since_start'], PAT_BINS)}", i)
            cols.add(f"{died}|pat_cause|{g['cause']}", i)
        else:
            cols.add(f"{died}|pat_none", i)
            lpe = d["last_pattern_end_frame"]
            if lpe is not None and end - lpe <= 120:
                cols.add(f"{died}|post_pattern_120", i)
        # Center dwell / enemies alive / fyou enemies alive.
        cols.add(f"{died}|dwell|{bin_label(d['center_dwell_frames'], DWELL_BINS)}", i)
        cols.add(f"{died}|dwell_sum", i, d["center_dwell_frames"])
        cols.add(f"{died}|dwell_pos", i, 1.0 if d["center_dwell_frames"] >= 1 else 0.0)
        others = (d["enemies_alive_normal"] + d["enemies_alive_kamikaze"] + d["enemies_alive_explosion"]
                  + d["enemies_alive_powerup"])
        cols.add(f"{died}|enemies_sum", i, others)
        cols.add(f"{died}|enemies|{bin_label(others, ENEMY_BINS)}", i)
        if d["fyou_enemies_alive"] is not None:
            cols.add(f"{died}|fyou_alive_known", i)
            cols.add(f"{died}|fyou_alive_sum", i, d["fyou_enemies_alive"])
            cols.add(f"{died}|fyou_alive_any", i, 1.0 if d["fyou_enemies_alive"] > 0 else 0.0)
        px, py = d["player_x_raw"] / 65536.0, d["player_y_raw"] / 65536.0
        near = [px < WALL_MARGIN or px > 127 - WALL_MARGIN, py < WALL_MARGIN or py > 127 - WALL_MARGIN]
        cols.add(f"{died}|loc|{'corner' if all(near) else 'edge' if any(near) else 'interior'}", i)
        cols.add(f"{died}|freeze", i, 1.0 if d["freeze_active"] else 0.0)
        cols.add(f"{died}|fyou_enabled", i, 1.0 if d["fyou_enabled"] else 0.0)
    # Pattern encounters (assigned to the phase of the encounter start).
    for i, g in enumerate(games):
        spans = g["patterns"]
        d = g["death"]
        for k, span in enumerate(spans):
            sp = phase_index(max(0, span["start_frame"] - 1))
            pname = PHASES[sp][0]
            pid, ptype = span["id"], TYPE_NAMES.get(span["pattern_type"], span["pattern_type"])
            fam = pattern_family[pid]
            stop = span["end_frame"] if span["end_frame"] is not None else g["end"]
            active = max(0, stop - span["start_frame"])
            fatal = (g["terminated"] and k == len(spans) - 1 and d["active_pattern"] is not None
                     and d["active_pattern"]["start_frame"] == span["start_frame"]
                     and d["active_pattern"]["id"] == pid)
            rect_fatal = fatal and g["cause"] in ("static_pattern_rect", "moving_pattern_rect")
            for scope in (f"id|{pid}", f"type|{ptype}", f"family|{fam}", "all"):
                for ph in (pname, "all"):
                    cols.add(f"enc|{ph}|{scope}", i)
                    cols.add(f"pact|{ph}|{scope}", i, active)
                    if fatal:
                        cols.add(f"encdeath|{ph}|{scope}", i)
                    if rect_fatal:
                        cols.add(f"encrect|{ph}|{scope}", i)
    return cols


class Bootstrap:
    def __init__(self, n_clusters, draws, seed):
        rng = np.random.default_rng(seed)
        idx = rng.integers(0, n_clusters, size=(draws, n_clusters))
        self.weights = np.zeros((draws, n_clusters), dtype=np.float64)
        for b in range(draws):
            np.add.at(self.weights[b], idx[b], 1.0)
        self.draws, self.n = draws, n_clusters


def cluster_sum(cols, games, seeds):
    index = {s: j for j, s in enumerate(seeds)}
    owner = np.array([index[g["seed"]] for g in games])
    out = {}
    for name, column in cols.data.items():
        out[name] = np.bincount(owner, weights=column, minlength=len(seeds))
    return out


class Table:
    """Ratio statistics over one cluster-summed dataset, with bootstrap draws."""

    def __init__(self, sums, boot):
        self.sums, self.boot = sums, boot
        self.cache = {}

    def total(self, name):
        column = self.sums.get(name)
        return 0.0 if column is None else float(column.sum())

    def boot_total(self, name):
        if name not in self.cache:
            column = self.sums.get(name)
            self.cache[name] = (np.zeros(self.boot.draws) if column is None else self.boot.weights @ column)
        return self.cache[name]

    def ratio(self, num, den, scale=1.0):
        n, d = self.total(num), self.total(den)
        bn, bd = self.boot_total(num), self.boot_total(den)
        with np.errstate(divide="ignore", invalid="ignore"):
            draws = np.where(bd > 0, bn / bd, np.nan) * scale
        lo, hi = (np.nanpercentile(draws, [2.5, 97.5]) if np.isfinite(draws).any() else (math.nan, math.nan))
        est = (n / d * scale) if d > 0 else math.nan
        return dict(est=est, lo=float(lo), hi=float(hi), num=n, den=d)

    def ratio_draws(self, num, den, scale=1.0):
        bn, bd = self.boot_total(num), self.boot_total(den)
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.where(bd > 0, bn / bd, np.nan) * scale


def contrast(table_a, table_b, num, den, scale=1.0):
    """Paired a - b difference of one ratio (same bootstrap draws)."""
    a = table_a.ratio(num, den, scale)
    b = table_b.ratio(num, den, scale)
    draws = table_a.ratio_draws(num, den, scale) - table_b.ratio_draws(num, den, scale)
    lo, hi = np.nanpercentile(draws, [2.5, 97.5]) if np.isfinite(draws).any() else (math.nan, math.nan)
    return dict(est=a["est"] - b["est"], lo=float(lo), hi=float(hi), a=a["est"], b=b["est"])


def post_fyou_standardized(tables, boot, window_labels=("1-100", "101-300")):
    """Deaths within 300 frames after a fyou trigger versus deaths expected at each phase's
    never-triggered rate over the same frames (indirect standardization; pools tables)."""
    ph_names = [p[0] for p in PHASES]

    def total(kind, ph, label):
        return sum(t.total(f"{kind}|{ph}|{label}") for t in tables)

    def draws(kind, ph, label):
        return sum(t.boot_total(f"{kind}|{ph}|{label}") for t in tables)

    def obs_exp(get):
        observed = sum(get("deathrec", ph, lab) for ph in ph_names for lab in window_labels)
        expected = 0.0
        for ph in ph_names:
            frames = sum(get("expo", ph, lab) for lab in window_labels)
            denom = get("expo", ph, "never")
            rate = np.where(denom > 0, get("deathrec", ph, "never") / np.where(denom > 0, denom, 1), 0.0) \
                if isinstance(denom, np.ndarray) else (get("deathrec", ph, "never") / denom if denom > 0 else 0.0)
            expected = expected + frames * rate
        return observed, expected

    observed, expected = obs_exp(total)
    b_obs, b_exp = obs_exp(draws)
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(b_exp > 0, b_obs / b_exp, np.nan)
    lo, hi = np.nanpercentile(ratio, [2.5, 97.5]) if np.isfinite(ratio).any() else (math.nan, math.nan)
    return dict(window="1-300 frames after the last fyou trigger", observed_deaths=observed, expected_deaths=expected,
                frames=sum(total("expo", ph, lab) for ph in ph_names for lab in window_labels),
                observed_over_expected=dict(est=observed / expected if expected > 0 else math.nan,
                                            lo=float(lo), hi=float(hi)))


def build_tables(table: Table, pattern_info):
    out = {}
    ph_names = [p[0] for p in PHASES]
    # T1 phase overview
    rows = []
    for pname in ph_names:
        rows.append(dict(phase=pname, at_risk=table.total(f"atrisk|{pname}"), deaths=table.total(f"died|{pname}"),
                         hazard=table.ratio(f"died|{pname}", f"atrisk|{pname}"),
                         rate_per_10k_frames=table.ratio(f"died|{pname}", f"expo|{pname}|all", 10000.0)))
    out["phase_overview"] = rows
    # T2 cause shares
    out["cause_share"] = [dict(phase=p, deaths=table.total(f"died|{p}"),
                               shares={c: table.ratio(f"died|{p}|cause|{c}", f"died|{p}") for c in CAUSES})
                          for p in ph_names]
    # T3 fyou in deaths
    rows = []
    for p in ph_names:
        d = f"died|{p}"
        rows.append(dict(
            phase=p, deaths=table.total(d),
            fy_any=table.ratio(f"{d}|fy_any", d),
            **{f"fy_w{w}": table.ratio(f"{d}|fy_w{w}", d) for w in FYOU_WINDOWS},
            mean_triggers_before_death=table.ratio(f"{d}|fy_count", d),
            enemy_kills=table.total(f"{d}|enemy_kill"),
            killer_fyou_of_enemy_kills=table.ratio(f"{d}|killer_fyou", f"{d}|killer_known"),
            killer_fyou_of_all_deaths=table.ratio(f"{d}|killer_fyou", d),
            killer_fyou_of_normal_enemy_kills=table.ratio(f"{d}|normal_kill_fyou", f"{d}|normal_kill_known"),
            fyou_enemy_alive_any=table.ratio(f"{d}|fyou_alive_any", f"{d}|fyou_alive_known"),
            mean_fyou_enemies_alive=table.ratio(f"{d}|fyou_alive_sum", f"{d}|fyou_alive_known"),
            fyou_enabled_at_death=table.ratio(f"{d}|fyou_enabled", d)))
    out["fyou_in_deaths"] = rows
    # cause x fyou within 300
    out["cause_given_fyou_w300"] = [dict(phase=p, cause=c,
                                         share_with_fyou_w300=table.ratio(f"died|{p}|cause|{c}|fy_w300", f"died|{p}|cause|{c}"))
                                    for p in ph_names for c in CAUSES]
    # T4 hazard by fyou at phase start
    rows = []
    for p in ph_names[1:]:
        for a, b, label in (("fy1", "fy0", "triggered_by_phase_start"), ("rec300", "norec300", "trigger_in_prior_300")):
            ha = table.ratio(f"died_hazard|{p}|{a}", f"atrisk|{p}|{a}")
            hb = table.ratio(f"died_hazard|{p}|{b}", f"atrisk|{p}|{b}")
            draws = (table.ratio_draws(f"died_hazard|{p}|{a}", f"atrisk|{p}|{a}")
                     - table.ratio_draws(f"died_hazard|{p}|{b}", f"atrisk|{p}|{b}"))
            lo, hi = (np.nanpercentile(draws, [2.5, 97.5]) if np.isfinite(draws).any() else (math.nan, math.nan))
            rows.append(dict(phase=p, split=label, at_risk_yes=table.total(f"atrisk|{p}|{a}"),
                             at_risk_no=table.total(f"atrisk|{p}|{b}"), hazard_yes=ha, hazard_no=hb,
                             difference=dict(est=ha["est"] - hb["est"], lo=float(lo), hi=float(hi))))
    out["hazard_by_fyou_at_phase_start"] = rows
    # T5 exposure hazard by recency since last fyou
    labels = ["never"] + [r[0] for r in RECENCY]
    for label in labels:
        for kind in ("deathrec", "expo"):
            parts = [table.sums.get(f"{kind}|{q}|{label}") for q in ph_names]
            table.sums[f"{kind}|all|{label}"] = sum(c for c in parts if c is not None) if any(
                c is not None for c in parts) else np.zeros(table.boot.n)
    rows = []
    for p in ph_names + ["all"]:
        for label in labels:
            num, den = f"deathrec|{p}|{label}", f"expo|{p}|{label}"
            rows.append(dict(phase=p, since_last_fyou=label, deaths=table.total(num), frames=table.total(den),
                             deaths_per_10k_frames=table.ratio(num, den, 10000.0)))
    out["hazard_by_time_since_fyou"] = rows
    # Base rate for "pattern active at death": deaths per frame, active vs not.
    rows = []
    for p in ph_names:
        d = f"died|{p}"
        rows.append(dict(
            phase=p, share_of_frames_pattern_active=table.ratio(f"pexpo|{p}|active", f"expo|{p}|all"),
            deaths_active=table.total(f"{d}|pat_active"), frames_active=table.total(f"pexpo|{p}|active"),
            per_10k_active=table.ratio(f"{d}|pat_active", f"pexpo|{p}|active", 10000.0),
            deaths_inactive=table.total(f"{d}|pat_none"), frames_inactive=table.total(f"pexpo|{p}|inactive"),
            per_10k_inactive=table.ratio(f"{d}|pat_none", f"pexpo|{p}|inactive", 10000.0),
            per_10k_static=table.ratio(f"{d}|pat_type|static", f"pexpo|{p}|static", 10000.0),
            per_10k_moving=table.ratio(f"{d}|pat_type|moving", f"pexpo|{p}|moving", 10000.0)))
    out["hazard_by_pattern_state"] = rows
    # T6 patterns at death
    rows = []
    for p in ph_names:
        d = f"died|{p}"
        rows.append(dict(
            phase=p, deaths=table.total(d), pattern_active=table.ratio(f"{d}|pat_active", d),
            no_pattern=table.ratio(f"{d}|pat_none", d),
            post_pattern_120=table.ratio(f"{d}|post_pattern_120", d),
            type={t: table.ratio(f"{d}|pat_type|{t}", d) for t in ("static", "moving")},
            frames_since_pattern_start={b[0]: table.ratio(f"{d}|pat_t|{b[0]}", f"{d}|pat_active") for b in PAT_BINS},
            cause_given_pattern_active={c: table.ratio(f"{d}|pat_cause|{c}", f"{d}|pat_active") for c in CAUSES}))
    out["pattern_at_death"] = rows
    # death counts by pattern id per phase
    ids = sorted(pattern_info)
    rows = []
    for pid in ids:
        row = dict(id=pid, pattern_type=TYPE_NAMES.get(pattern_info[pid]["pattern_type"]),
                   family=pattern_info[pid]["family"], by_phase={})
        for p in ph_names:
            row["by_phase"][p] = dict(deaths=table.total(f"died|{p}|pat_id|{pid}"),
                                      share_of_phase_deaths=table.ratio(f"died|{p}|pat_id|{pid}", f"died|{p}"))
        rows.append(row)
    out["deaths_by_pattern_id"] = rows
    # T7 per-encounter rates
    rows = []

    def observed_over_expected(scope):
        """Deaths during encounters / deaths expected if each encounter died at its start phase's overall rate."""
        observed = table.boot_total(f"encdeath|all|{scope}")
        expected = np.zeros(table.boot.draws)
        for ph in ph_names:
            with np.errstate(divide="ignore", invalid="ignore"):
                rate = np.where(table.boot_total(f"enc|{ph}|all") > 0,
                                table.boot_total(f"encdeath|{ph}|all") / table.boot_total(f"enc|{ph}|all"), 0.0)
            expected += table.boot_total(f"enc|{ph}|{scope}") * rate
        point_expected = 0.0
        for ph in ph_names:
            all_enc = table.total(f"enc|{ph}|all")
            if all_enc > 0:
                point_expected += table.total(f"enc|{ph}|{scope}") * table.total(f"encdeath|{ph}|all") / all_enc
        with np.errstate(divide="ignore", invalid="ignore"):
            draws = np.where(expected > 0, observed / expected, np.nan)
        lo, hi = np.nanpercentile(draws, [2.5, 97.5]) if np.isfinite(draws).any() else (math.nan, math.nan)
        est = table.total(f"encdeath|all|{scope}") / point_expected if point_expected > 0 else math.nan
        return dict(est=est, lo=float(lo), hi=float(hi), observed=table.total(f"encdeath|all|{scope}"),
                    expected=point_expected)

    for pid in ids:
        scope = f"id|{pid}"
        row = dict(id=pid, pattern_type=TYPE_NAMES.get(pattern_info[pid]["pattern_type"]),
                   family=pattern_info[pid]["family"], by_start_phase={},
                   observed_over_expected=observed_over_expected(scope))
        for ph in ["all"] + ph_names:
            e = f"enc|{ph}|{scope}"
            row["by_start_phase"][ph] = dict(
                encounters=table.total(e), deaths_during=table.total(f"encdeath|{ph}|{scope}"),
                rect_deaths=table.total(f"encrect|{ph}|{scope}"),
                death_per_encounter=table.ratio(f"encdeath|{ph}|{scope}", e),
                rect_death_per_encounter=table.ratio(f"encrect|{ph}|{scope}", e),
                deaths_per_10k_active_frames=table.ratio(f"encdeath|{ph}|{scope}", f"pact|{ph}|{scope}", 10000.0))
        rows.append(row)
    out["encounter_rates_by_pattern_id"] = rows
    rows = []
    for scope in ["all", "type|static", "type|moving"] + sorted({f"family|{v['family']}" for v in pattern_info.values()},
                                                                 key=lambda s: (len(s), s)):
        row = dict(scope=scope, by_start_phase={})
        for ph in ["all"] + ph_names:
            e = f"enc|{ph}|{scope}"
            row["by_start_phase"][ph] = dict(
                encounters=table.total(e), deaths_during=table.total(f"encdeath|{ph}|{scope}"),
                rect_deaths=table.total(f"encrect|{ph}|{scope}"),
                death_per_encounter=table.ratio(f"encdeath|{ph}|{scope}", e),
                rect_death_per_encounter=table.ratio(f"encrect|{ph}|{scope}", e),
                deaths_per_10k_active_frames=table.ratio(f"encdeath|{ph}|{scope}", f"pact|{ph}|{scope}", 10000.0))
        rows.append(row)
    out["encounter_rates_by_scope"] = rows
    # T8 scenarios
    rows = []
    for p in ph_names:
        d = f"died|{p}"
        rows.append(dict(
            phase=p, deaths=table.total(d),
            dwell={b[0]: table.ratio(f"{d}|dwell|{b[0]}", d) for b in DWELL_BINS},
            dwell_positive=table.ratio(f"{d}|dwell_pos", d),
            mean_center_dwell=table.ratio(f"{d}|dwell_sum", d),
            enemies_on_screen_excluding_killer={b[0]: table.ratio(f"{d}|enemies|{b[0]}", d) for b in ENEMY_BINS},
            mean_other_enemies=table.ratio(f"{d}|enemies_sum", d),
            location={k: table.ratio(f"{d}|loc|{k}", d) for k in ("corner", "edge", "interior")},
            freeze_active=table.ratio(f"{d}|freeze", d),
            killer_age_fyou={b[0]: table.ratio(f"{d}|killer_age|fyou|{b[0]}", f"{d}|killer_age_known|fyou")
                             for b in AGE_BINS},
            killer_age_other={b[0]: table.ratio(f"{d}|killer_age|other|{b[0]}", f"{d}|killer_age_known|other")
                              for b in AGE_BINS},
            killer_fyou_n=table.total(f"{d}|killer_prov|fyou"), killer_other_n=table.total(f"{d}|killer_prov|other")))
    out["scenarios"] = rows
    return out


def load_group(path):
    return json.loads(Path(path).read_text())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--setting", action="append", required=True, help="name=file[,file...] (repetitions)")
    parser.add_argument("--pattern-table", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--records-out", type=Path)
    parser.add_argument("--draws", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=202610290901)
    args = parser.parse_args()

    table_rows = json.loads(args.pattern_table.read_text())
    parent = {r["id"]: r["id"] for r in table_rows}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for r in table_rows:
        for v in r["variants"]:
            parent[find(r["id"])] = find(v)
    family = {r["id"]: "+".join(map(str, sorted(i for i in parent if find(i) == find(r["id"])))) for r in table_rows}
    pattern_info = {r["id"]: dict(pattern_type=r["pattern_type"], family=family[r["id"]], mins=r["mins"],
                                  maxs=r["maxs"], rects=r["rects"]) for r in table_rows}

    settings, seeds = {}, None
    for spec in args.setting:
        name, files = spec.split("=", 1)
        games, meta = [], []
        for f in files.split(","):
            group = load_group(f)
            meta.append({k: v for k, v in group.items() if k not in ("rows", "seeds")})
            games.extend(prepare_game(r) for r in group["rows"])
            group_seeds = group["seeds"]
            if seeds is None:
                seeds = group_seeds
            assert group_seeds == seeds, "all settings must share one seed list"
        settings[name] = dict(games=games, meta=meta)
    boot = Bootstrap(len(seeds), args.draws, args.seed)
    tables, tabs = {}, {}
    for name, s in settings.items():
        cols = build_columns(s["games"], family)
        sums = cluster_sum(cols, s["games"], seeds)
        tabs[name] = Table(sums, boot)
        tables[name] = dict(n_games=len(s["games"]), n_seeds=len(seeds), meta=s["meta"],
                            tables=build_tables(tabs[name], pattern_info))
    contrasts = {}
    names = list(settings)
    if "argmax_r1" in tabs and "argmax_r4" in tabs:
        a, b = tabs["argmax_r1"], tabs["argmax_r4"]
        c = {}
        for p in [x[0] for x in PHASES]:
            d = f"died|{p}"
            c[p] = dict(
                hazard=contrast(a, b, d, f"atrisk|{p}"),
                rate_per_10k=contrast(a, b, d, f"expo|{p}|all", 10000.0),
                fy_any=contrast(a, b, f"{d}|fy_any", d), fy_w300=contrast(a, b, f"{d}|fy_w300", d),
                killer_fyou_of_enemy_kills=contrast(a, b, f"{d}|killer_fyou", f"{d}|killer_known"),
                pattern_active=contrast(a, b, f"{d}|pat_active", d),
                **{f"cause_{cause}": contrast(a, b, f"{d}|cause|{cause}", d) for cause in CAUSES[:5]})
        contrasts["argmax_r1_minus_r4"] = c
    post = {}
    groups = {name: [name] for name in names}
    pooled = [n for n in names if n.startswith("argmax") or n.startswith("sampled")]
    if len(pooled) > 1:
        groups["pooled_all_settings"] = pooled
    for label, members in groups.items():
        post[label] = post_fyou_standardized([tabs[m] for m in members], boot)
    result = dict(schema="death_trace_analysis_v1", bootstrap=dict(draws=args.draws, seed=args.seed,
                  unit="game_seed_cluster", n_clusters=len(seeds)), phases=[list(p) for p in PHASES],
                  pattern_info={str(k): v for k, v in pattern_info.items()}, settings=tables, contrasts=contrasts, post_fyou_standardized=post)
    args.out.write_text(json.dumps(result, separators=(",", ":"), allow_nan=True))
    if args.records_out:
        records = {name: [dict(seed=g["seed"], alive_frames=g["alive"], fatal_or_end_frame=g["end"],
                               terminated=g["terminated"], death_cause=g["cause"],
                               fyou_trigger_frames=g["triggers"],
                               patterns=[[p["id"], p["pattern_type"], p["start_frame"], p["end_frame"]]
                                         for p in g["patterns"]],
                               death=g["death"]) for g in s["games"]] for name, s in settings.items()}
        args.records_out.write_text(json.dumps(records, separators=(",", ":")))
    print(json.dumps({n: dict(games=t["n_games"]) for n, t in tables.items()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
