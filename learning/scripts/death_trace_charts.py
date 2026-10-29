"""Render the death-trace findings as one self-contained HTML page of SVG charts.

Inputs: the analysis tables and per-game records written by death_trace_analysis.py, plus the
second-pass group files (`fresh2/`) that carry path, gap and sample telemetry.
"""
from __future__ import annotations

import argparse
import html
import json
import math
from pathlib import Path

import numpy as np

# Reference palette slots (blue, orange, aqua) and ink; text never wears series color.
BLUE, ORANGE, AQUA, MAGENTA, VIOLET = "#2a78d6", "#eb6834", "#1baf7a", "#e87ba4", "#6250d6"
INK, INK2, MUTED = "var(--foreground)", "var(--muted-foreground)", "#898781"
GRID = "color-mix(in srgb, var(--foreground) 12%, transparent)"
FIELD = 128  # px: the playfield

CSS = """
:root{color-scheme:light dark}
*{box-sizing:border-box}
body{font-family:system-ui,-apple-system,'Segoe UI',sans-serif;color:var(--foreground);margin:0}
.chart{margin:0 0 34px}
.chart h3{font-size:15px;font-weight:600;margin:0 0 2px}
.chart p.sub{font-size:12.5px;color:var(--muted-foreground);margin:0 0 8px;line-height:1.4}
.chart p.take{font-size:12.5px;margin:6px 0 0;line-height:1.45}
svg{display:block;width:100%;height:auto;overflow:visible;margin-bottom:10px}
svg text{font-family:inherit;fill:var(--foreground)}
svg .m{fill:#898781}
svg .s{fill:var(--muted-foreground)}
.legend{display:flex;gap:16px;flex-wrap:wrap;font-size:12px;color:var(--muted-foreground);margin:2px 0 6px}
.legend i{display:inline-block;width:10px;height:10px;border-radius:5px;margin-right:6px;vertical-align:-1px}
.legend i.ln{width:16px;height:2px;border-radius:1px;vertical-align:3px}
details{font-size:12px;color:var(--muted-foreground);margin-top:6px}
details table{border-collapse:collapse;margin-top:6px}
details td,details th{padding:2px 8px;text-align:right;border-bottom:1px solid var(--border)}
details th:first-child,details td:first-child{text-align:left}
.hit:hover{opacity:.85}
"""


def esc(x):
    return html.escape(str(x))


def nice_max(v):
    if v <= 0:
        return 1
    mag = 10 ** math.floor(math.log10(v))
    for m in (1, 2, 2.5, 5, 10):
        if v <= m * mag:
            return m * mag
    return 10 * mag


class Svg:
    def __init__(self, w, h):
        self.w, self.h, self.parts = w, h, []

    def add(self, s):
        self.parts.append(s)

    def text(self, x, y, s, cls="m", size=11, anchor="start", weight=400, extra=""):
        self.add(f'<text x="{x:.1f}" y="{y:.1f}" class="{cls}" font-size="{size}" text-anchor="{anchor}" '
                 f'font-weight="{weight}" {extra}>{esc(s)}</text>')

    def line(self, x0, y0, x1, y1, color=GRID, w=1, extra=""):
        self.add(f'<line x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y1:.1f}" stroke="{color}" '
                 f'stroke-width="{w}" {extra}/>')

    def render(self):
        return f'<svg viewBox="0 0 {self.w} {self.h}" role="img">' + "".join(self.parts) + "</svg>"


def table_view(header, rows):
    head = "".join(f"<th>{esc(h)}</th>" for h in header)
    body = "".join("<tr>" + "".join(f"<td>{esc(c)}</td>" for c in r) + "</tr>" for r in rows)
    return f"<details><summary>Table view</summary><table><tr>{head}</tr>{body}</table></details>"


def legend(items):
    out = []
    for label, color, kind in items:
        cls = "ln" if kind == "line" else ""
        out.append(f'<span><i class="{cls}" style="background:{color}"></i>{esc(label)}</span>')
    return '<div class="legend">' + "".join(out) + "</div>"


def chart(title, sub, body, take="", extra=""):
    return (f'<section class="chart"><h3>{esc(title)}</h3><p class="sub">{sub}</p>{body}'
            f'{f"<p class=take>{take}</p>" if take else ""}{extra}</section>')


# ---------------------------------------------------------------- chart 1: pattern vs no pattern
def chart_pattern_base_rate(tables):
    t = tables["settings"]["argmax_r1"]["tables"]["hazard_by_pattern_state"]
    phases = [r["phase"] for r in t]
    W, H, L, R, T, B = 700, 280, 44, 10, 24, 34
    ymax = nice_max(max(r["per_10k_active"]["hi"] for r in t))
    s = Svg(W, H)
    for k in range(5):
        v = ymax * k / 4
        y = H - B - (H - T - B) * v / ymax
        s.line(L, y, W - R, y)
        s.text(L - 6, y + 4, f"{v:g}", "s", anchor="end")
    band = (W - L - R) / len(phases)
    bw = 22
    for i, r in enumerate(t):
        cx = L + band * (i + 0.5)
        for j, (key, color) in enumerate((("per_10k_inactive", "#898781"), ("per_10k_active", BLUE))):
            st = r[key]
            h = (H - T - B) * st["est"] / ymax
            x = cx - bw - 1 + j * (bw + 2)
            y = H - B - h
            tip = f'{r["phase"]}, {"pattern active" if j else "no pattern"}: {st["est"]:.2f} deaths per 10k frames [{st["lo"]:.2f}, {st["hi"]:.2f}]'
            s.add(f'<g class="hit"><title>{esc(tip)}</title><path d="M{x},{H-B} V{y+4} Q{x},{y} {x+4},{y} H{x+bw-4} Q{x+bw},{y} {x+bw},{y+4} V{H-B} Z" fill="{color}"/></g>')
            if j == 1 or st["est"] > 0.01:
                s.text(x + bw / 2, y - 4, f'{st["est"]:.1f}', "s", 10.5, "middle")
        s.text(cx, H - B + 16, r["phase"], "s", 11.5, "middle")
        ratio = r["per_10k_active"]["est"] / max(r["per_10k_inactive"]["est"], 1e-9)
        s.text(cx, H - B + 30, f"{ratio:.0f}x", "m", 10.5, "middle")
    s.line(L, H - B, W - R, H - B, "#c3c2b7")
    s.text(L, T - 10, "deaths per 10k frames lived", "s", 11)
    rows = [[r["phase"], f'{r["per_10k_inactive"]["est"]:.2f}', f'{r["per_10k_active"]["est"]:.2f}',
             f'{100*r["share_of_frames_pattern_active"]["est"]:.0f}%'] for r in t]
    return chart(
        "Frames with a pattern on screen are 14-27x deadlier",
        "1-frame argmax, 2,048 games. Pattern frames are 42-49% of play time. The ratio under each phase is active / inactive.",
        legend([("No pattern active", "#898781", "dot"), ("Pattern active", BLUE, "dot")]) + s.render(),
        extra=table_view(["phase", "no pattern", "pattern", "frames with pattern"], rows))


# ---------------------------------------------------------------- chart 2: hazard vs time in pattern
def hazard_by_pattern_time(records, setting, ptype, edges):
    expo = np.zeros(len(edges) - 1)
    rect = np.zeros_like(expo)
    enemy = np.zeros_like(expo)
    for r in records[setting]:
        end = r["fatal_or_end_frame"]
        for pid, pt, st, en in r["patterns"]:
            if pt != ptype:
                continue
            dur = (en if en is not None else end) - st
            for b, (a, c) in enumerate(zip(edges[:-1], edges[1:])):
                expo[b] += max(0, min(c, dur) - a)
        d = r["death"]
        if d and d["active_pattern"] and d["active_pattern"]["pattern_type"] == ptype:
            b = min(len(rect) - 1, d["active_pattern"]["frames_since_start"] // (edges[1] - edges[0]))
            if r["death_cause"] in ("static_pattern_rect", "moving_pattern_rect"):
                rect[b] += 1
            else:
                enemy[b] += 1
    return expo, rect, enemy


def chart_time_in_pattern(records):
    edges = list(range(0, 721, 20))
    W, H, L, R, T, B = 700, 260, 44, 10, 24, 34
    settings = ("argmax_r1", "argmax_r4")
    panels = {}
    ymax = 0
    for name in settings:
        expo, rect, enemy = hazard_by_pattern_time(records, name, 0, edges)
        panels[name] = (1000 * rect / np.maximum(expo, 1), 1000 * enemy / np.maximum(expo, 1), expo, rect, enemy)
        ymax = max(ymax, panels[name][0].max(), panels[name][1].max())
    ymax = nice_max(ymax * 1.05)
    out = []
    for name in settings:
        rect_rate, enemy_rate, expo, rect, enemy = panels[name]
        s = Svg(W, H)
        xmax = edges[-1]
        X = lambda f: L + (W - L - R) * f / xmax
        Y = lambda v: H - B - (H - T - B) * v / ymax
        for k in range(5):
            v = ymax * k / 4
            s.line(L, Y(v), W - R, Y(v))
            s.text(L - 6, Y(v) + 4, f"{v:g}", "s", anchor="end")
        for f, label in ((0, "pattern starts"), (100, "rects fill (~100f)"), (610, "rects retract (~610f)")):
            s.line(X(f), T, X(f), H - B, "#c3c2b7", 1)
            s.text(X(f) + 4, T + 9, label, "m", 10)
        for series, color in ((enemy_rate, ORANGE), (rect_rate, BLUE)):
            pts = " ".join(f"{X(edges[i] + 10):.1f},{Y(v):.1f}" for i, v in enumerate(series[:-1]))
            s.add(f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>')
        for i in range(len(edges) - 2):
            for series, color, n, lab in ((enemy_rate, ORANGE, enemy, "enemy contact"), (rect_rate, BLUE, rect, "rectangle contact")):
                s.add(f'<circle cx="{X(edges[i]+10):.1f}" cy="{Y(series[i]):.1f}" r="7" fill="transparent" class="hit"><title>{esc(f"frames {edges[i]}-{edges[i+1]} after start: {series[i]:.2f} per 1,000 frames, {int(n[i])} deaths ({lab})")}</title></circle>')
        for f in range(0, 721, 100):
            s.text(X(f), H - B + 15, f, "s", 11, "middle")
        s.text(L + (W - L - R) / 2, H - 4, "frames since the pattern started", "s", 11, "middle")
        s.text(L, 10, f"deaths per 1,000 pattern frames - {'1-frame' if name.endswith('r1') else '4-frame'} argmax", "s", 11)
        out.append(s.render())
    rows = []
    for i in range(len(edges) - 2):
        rows.append([f"{edges[i]}-{edges[i+1]}"] + [f"{panels[n][0][i]:.2f}" for n in settings] + [f"{panels[n][1][i]:.2f}" for n in settings])
    return chart("Static patterns kill with rectangles at the fill, then mostly with enemies",
                 "Per-frame death rate by time since a static pattern started, 20-frame bins. Exposure is the pattern-frames still running in the bin (about 100k at the start).",
                 legend([("Enemy contact while pattern active", ORANGE, "line"), ("Rectangle contact", BLUE, "line")]) + "".join(out),
                 "Rectangle deaths spike when the rectangles fill (~100 frames) but then run at a steady ~0.3 per 1,000 frames for 500 more frames: the policy keeps running into rectangles that are already drawn. Enemy contacts run at 0.27 per 1,000 frames while a pattern is active against 0.023 outside patterns (11x; 9x at 4-frame control).",
                 table_view(["bin", "rect 1-frame", "rect 4-frame", "enemy 1-frame", "enemy 4-frame"], rows))


# ---------------------------------------------------------------- chart 3: per-pattern lethality
def chart_pattern_dots(tables, min_enc=30):
    t = tables["settings"]["argmax_r1"]["tables"]["encounter_rates_by_pattern_id"]
    t4 = {r["id"]: r for r in tables["settings"]["argmax_r4"]["tables"]["encounter_rates_by_pattern_id"]}
    rows = [r for r in t if r["by_start_phase"]["all"]["encounters"] >= min_enc]
    rows.sort(key=lambda r: -r["by_start_phase"]["all"]["death_per_encounter"]["est"])
    rowh = 17
    W, L, R, T, B = 700, 150, 70, 14, 28
    H = T + B + rowh * len(rows)
    s = Svg(W, H)
    X = lambda v: L + (W - L - R) * v
    for k in range(0, 101, 25):
        s.line(X(k / 100), T, X(k / 100), H - B)
        s.text(X(k / 100), H - B + 14, f"{k}%", "s", 11, "middle")
    s.text(L + (W - L - R) / 2, H - 2, "share of encounters in which the player died", "s", 11, "middle")
    for i, r in enumerate(rows):
        a = r["by_start_phase"]["all"]
        y = T + rowh * i + rowh / 2
        color = BLUE if r["pattern_type"] == "static" else ORANGE
        est, lo, hi = (a["death_per_encounter"][k] for k in ("est", "lo", "hi"))
        s.line(X(lo), y, X(hi), y, color, 2, 'stroke-linecap="round" opacity="0.45"')
        d4 = t4[r["id"]]["by_start_phase"]["all"]["death_per_encounter"]["est"] if r["id"] in t4 else None
        tip = (f'id {r["id"]} ({r["pattern_type"]}, family {r["family"]}): {100*est:.0f}% [{100*lo:.0f}, {100*hi:.0f}] of {int(a["encounters"])} encounters, '
               f'{int(a["deaths_during"])} deaths ({int(a["rect_deaths"])} by rectangle); observed/expected {r["observed_over_expected"]["est"]:.2f}'
               + (f'; 4-frame {100*d4:.0f}%' if d4 is not None else ""))
        s.add(f'<g class="hit"><title>{esc(tip)}</title><circle cx="{X(est):.1f}" cy="{y:.1f}" r="5" fill="{color}" stroke="var(--background)" stroke-width="2"/></g>')
        s.text(L - 10, y + 4, f'id {r["id"]}', "m", 11.5, "end")
        s.text(W - R + 10, y + 4, f'n={int(a["encounters"])}', "s", 10.5)
    body = (legend([("Static pattern", BLUE, "dot"), ("Moving pattern", ORANGE, "dot")]) + s.render())
    tab = table_view(["id", "type", "encounters", "death / encounter", "rect death / encounter", "obs / exp"],
                     [[r["id"], r["pattern_type"], int(r["by_start_phase"]["all"]["encounters"]),
                       f'{100*r["by_start_phase"]["all"]["death_per_encounter"]["est"]:.0f}%',
                       f'{100*r["by_start_phase"]["all"]["rect_death_per_encounter"]["est"]:.0f}%',
                       f'{r["observed_over_expected"]["est"]:.2f}'] for r in rows])
    return chart("Some patterns are a wall; others the policy handles",
                 f"1-frame argmax. Share of encounters ending in a death, 95% interval, patterns met at least {min_enc} times. Hover for details.",
                 body, "Ids 13, 14, 25, 26 (and the 36-39 family) are nearly always fatal. Pattern 3 kills 70% of the time but its transposed sibling 4 only 40%: the policy does not treat the two layouts equally.", tab)



P = 65536.0


def load_pass2(d, name):
    return json.loads((d / f"{name}.json").read_text())["rows"]


def px(v):
    return np.asarray(v, float) / P


# ---------------------------------------------------------------- chart 4: cause split by pattern state
def chart_cause_split(records):
    W, H, L, R, T, B = 700, 230, 250, 60, 14, 28
    rows = []
    for name, label in (("argmax_r1", "1-frame"), ("argmax_r4", "4-frame")):
        fa = fi = 0
        c = {"ea": 0, "ei": 0, "ra": 0}
        for r in records[name]:
            end = r["fatal_or_end_frame"]
            act = sum((en if en is not None else end) - st for _, _, st, en in r["patterns"])
            fa += act
            fi += end - act
            enemy = r["death_cause"] in ("normal_enemy", "kamikaze_enemy", "kamikaze_explosion")
            d = r["death"]
            if enemy:
                c["ea" if d["active_pattern"] else "ei"] += 1
            elif d["active_pattern"]:
                c["ra"] += 1
        rows += [(f"Enemy contact, no pattern ({label})", 1000 * c["ei"] / fi, "#898781", c["ei"], fi),
                 (f"Enemy contact, pattern active ({label})", 1000 * c["ea"] / fa, ORANGE, c["ea"], fa),
                 (f"Rectangle contact ({label})", 1000 * c["ra"] / fa, BLUE, c["ra"], fa)]
    xmax = nice_max(max(r[1] for r in rows))
    rowh = (H - T - B) / len(rows)
    s = Svg(W, H)
    X = lambda v: L + (W - L - R) * v / xmax
    for k in range(5):
        v = xmax * k / 4
        s.line(X(v), T, X(v), H - B)
        s.text(X(v), H - B + 14, f"{v:g}", "s", 11, "middle")
    s.text(L + (W - L - R) / 2, H - 2, "deaths per 1,000 frames in that state", "s", 11, "middle")
    for i, (lab, v, color, n, frames) in enumerate(rows):
        y = T + rowh * i + (rowh - 14) / 2
        tip = f"{lab}: {v:.3f} per 1,000 frames ({n} deaths over {frames:,} frames)"
        s.add(f'<g class="hit"><title>{esc(tip)}</title><path d="M{L},{y} H{X(v)-4} Q{X(v)},{y} {X(v)},{y+4} V{y+10} Q{X(v)},{y+14} {X(v)-4},{y+14} H{L} Z" fill="{color}"/></g>')
        s.text(L - 8, y + 11, lab, "m", 11, "end")
        s.text(X(v) + 6, y + 11, f"{v:.2f}", "s", 11)
    return chart("Most of the extra danger in patterns is enemies, not rectangles",
                 "Argmax, 2,048 games each. Enemy-contact deaths are 9-12x more frequent while a pattern is active, and that is a larger rate than rectangle contact itself.",
                 legend([("Enemy contact", ORANGE, "dot"), ("Rectangle contact", BLUE, "dot"), ("Enemy contact, no pattern", "#898781", "dot")]) + s.render(),
                 extra=table_view(["state", "per 1,000 frames", "deaths", "frames"], [[r[0], f"{r[1]:.3f}", r[3], f"{r[4]:,}"] for r in rows]))


# ---------------------------------------------------------------- chart 5: nearest-enemy distance CDF
def chart_enemy_gap_cdf(rows):
    act, ina = [], []
    for r in rows:
        smp = r["trace"]["samples"]
        for g, pid in zip(smp["enemy_gap"], smp["pattern_id"]):
            if g >= 0:
                (act if pid else ina).append(g / P)
    act, ina = np.sort(act), np.sort(ina)
    W, H, L, R, T, B = 700, 250, 44, 10, 14, 34
    s = Svg(W, H)
    X = lambda v: L + (W - L - R) * v / 60
    Y = lambda v: H - B - (H - T - B) * v / 0.5
    for k in range(0, 6):
        v = k / 10
        s.line(L, Y(v), W - R, Y(v))
        s.text(L - 6, Y(v) + 4, f"{int(v*100)}%", "s", 11, "end")
    for g in range(0, 61, 10):
        s.text(X(g), H - B + 15, g, "s", 11, "middle")
    s.text(L + (W - L - R) / 2, H - 2, "gap to the nearest lethal enemy (pixels, edge to edge)", "s", 11, "middle")
    for arr, color, lab in ((ina, "#898781", "no pattern"), (act, BLUE, "pattern active")):
        gs = np.linspace(0, 60, 121)
        cdf = np.searchsorted(arr, gs, side="right") / len(arr)
        pts = " ".join(f"{X(g):.1f},{Y(min(v, .5)):.1f}" for g, v in zip(gs, cdf))
        s.add(f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2" stroke-linejoin="round"/>')
        for g in (6, 12, 20):
            v = float(np.searchsorted(arr, g, side="right") / len(arr))
            s.add(f'<circle cx="{X(g):.1f}" cy="{Y(min(v,.5)):.1f}" r="4.5" fill="{color}" stroke="var(--background)" stroke-width="2"><title>{esc(f"{lab}: {100*v:.1f}% of sampled frames have an enemy within {g} px")}</title></circle>')
    s.text(L, 8, "share of sampled frames with an enemy at least this close", "s", 11)
    p6a, p6i = np.searchsorted(act, 6, side="right") / len(act), np.searchsorted(ina, 6, side="right") / len(ina)
    return chart("During patterns the policy is close to an enemy far more often",
                 f"4-frame argmax; {len(act):,} sampled frames with a pattern active, {len(ina):,} without (one sample every 30 frames).",
                 legend([("No pattern active", "#898781", "line"), ("Pattern active", BLUE, "line")]) + s.render(),
                 f"An enemy is within 6 px in {100*p6a:.1f}% of pattern frames against {100*p6i:.1f}% of other frames ({p6a/p6i:.0f}x).")


# ---------------------------------------------------------------- chart 6: approach to the killer
def approach(rows, causes, nmax=60):
    gap = []
    pv = []
    ev = []
    for r in rows:
        if r["death_cause"] not in causes:
            continue
        d = r["trace"]["death"]
        rc = d["recent"]
        kp = {a: (x / P, y / P) for a, x, y in d["killer_path"]}
        n = len(rc["x"])
        g = np.full(nmax, np.nan)
        v1 = np.full(nmax, np.nan)
        v2 = np.full(nmax, np.nan)
        for o in range(1, nmax):
            if o >= n or o not in kp or (o + 1) not in kp:
                continue
            i = n - o
            ppx, ppy = rc["x"][i] / P, rc["y"][i] / P
            kx, ky = kp[o]
            dx, dy = kx - ppx, ky - ppy
            dd = math.hypot(dx, dy)
            if dd < 1e-6:
                continue
            ux, uy = dx / dd, dy / dd
            g[o] = dd
            v1[o] = rc["vx"][i] / P * ux + rc["vy"][i] / P * uy
            v2[o] = -((kx - kp[o + 1][0]) * ux + (ky - kp[o + 1][1]) * uy)
        gap.append(g)
        pv.append(v1)
        ev.append(v2)
    return np.array(gap), np.array(pv), np.array(ev)


def line_panel(W, H, series, xlabel, ylabel, ymin, ymax, xmax=60, ticks=(0, 10, 20, 30, 40, 50, 60), reverse=True, hline=None):
    L, R, T, B = 48, 12, 22, 34
    s = Svg(W, H)
    X = lambda f: L + (W - L - R) * ((xmax - f) / xmax if reverse else f / xmax)
    Y = lambda v: H - B - (H - T - B) * (v - ymin) / (ymax - ymin)
    nt = 4
    for k in range(nt + 1):
        v = ymin + (ymax - ymin) * k / nt
        s.line(L, Y(v), W - R, Y(v))
        s.text(L - 6, Y(v) + 4, f"{v:g}", "s", 11, "end")
    if ymin < 0:
        s.line(L, Y(0), W - R, Y(0), "#c3c2b7")
    for f in ticks:
        s.text(X(f), H - B + 15, f"-{f}" if reverse and f else f, "s", 11, "middle")
    s.text(L + (W - L - R) / 2, H - 2, xlabel, "s", 11, "middle")
    s.text(L, 10, ylabel, "s", 11)
    if hline:
        v, lab = hline
        s.add(f'<line x1="{L}" x2="{W-R}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" stroke="#898781" stroke-width="1.5" stroke-dasharray="5 4"/>')
        s.text(W - R - 2, Y(v) - 5, lab, "m", 10.5, "end")
    for label, color, ys, lo, hi in series:
        xs = range(1, len(ys))
        if lo is not None:
            top = " ".join(f"{X(f):.1f},{Y(hi[f]):.1f}" for f in xs if not np.isnan(hi[f]))
            bot = " ".join(f"{X(f):.1f},{Y(lo[f]):.1f}" for f in reversed(list(xs)) if not np.isnan(lo[f]))
            s.add(f'<polygon points="{top} {bot}" fill="{color}" opacity="0.12"/>')
        pts = " ".join(f"{X(f):.1f},{Y(ys[f]):.1f}" for f in xs if not np.isnan(ys[f]))
        s.add(f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>')
        for f in (1, 5, 10, 20, 30, 45):
            if f < len(ys) and not np.isnan(ys[f]):
                s.add(f'<circle cx="{X(f):.1f}" cy="{Y(ys[f]):.1f}" r="5" fill="{color}" stroke="var(--background)" stroke-width="2"><title>{esc(f"{label}: {ys[f]:.2f} at {f} frames before death")}</title></circle>')
    return s.render()


def chart_approach(rows, base_gap):
    gap, pv, ev = approach(rows, ("normal_enemy", "kamikaze_enemy"))
    med = np.nanmedian(gap, axis=0)
    lo, hi = np.nanpercentile(gap, 25, axis=0), np.nanpercentile(gap, 75, axis=0)
    a = line_panel(700, 230, [("Distance to the killer", VIOLET, med, lo, hi)], "frames before death", "median distance to the killer enemy (px), band = quartiles", 0, 60, hline=(base_gap, "typical nearest-enemy gap"))
    pm = np.nanmedian(pv, axis=0)
    em = np.nanmedian(ev, axis=0)
    b = line_panel(700, 230, [("Player moving toward the killer", BLUE, pm, None, None), ("Killer moving toward the player", ORANGE, em, None, None)], "frames before death", "median speed along the line to the killer (px per frame)", -1, 2)
    return chart("Enemy deaths: a homing enemy closes steadily and the policy stops backing away",
                 f"4-frame argmax, {gap.shape[0]:,} enemy-contact deaths. Enemies home on the player at about 0.9 px per frame throughout.",
                 legend([("Distance to the killer (top)", VIOLET, "line"), ("Player toward killer; negative = fleeing (bottom)", BLUE, "line"), ("Killer toward player (bottom)", ORANGE, "line")]) + a + b,
                 "The distance falls from about 52 px at 45 frames out to 0. The player moves away at first (-0.35 px/frame, slower than the 0.8-0.9 px/frame the enemy closes at) and flips to moving toward the killer in the last 10-15 frames, 79% of deaths at 2 frames out. Either the policy runs out of room to flee or it commits into the enemy while avoiding something else.")


# ---------------------------------------------------------------- chart 7: approach to a killing rectangle
def chart_rect_approach(rows, base_gap):
    keys = ("static_pattern_rect", "moving_pattern_rect")
    out = []
    for cause, lab in (("static_pattern_rect", "static rectangle"), ("moving_pattern_rect", "moving rectangle")):
        sel = [r for r in rows if r["death_cause"] == cause]
        rg = np.full((len(sel), 61), np.nan)
        eg = np.full((len(sel), 61), np.nan)
        for i, r in enumerate(sel):
            rc = r["trace"]["death"]["recent"]
            n = len(rc["x"])
            for o in range(1, 61):
                if o > n:
                    break
                j = n - o
                lg, pg, g = rc["lethal_rect_gap"][j], rc["pending_rect_gap"][j], rc["enemy_gap"][j]
                best = lg if lg >= 0 else pg
                if best >= 0:
                    rg[i, o] = best / P
                if g >= 0:
                    eg[i, o] = g / P
        out.append(line_panel(700, 220, [("Distance to the rectangle that killed", BLUE, np.nanmedian(rg, axis=0), None, None),
                                         ("Distance to nearest enemy", ORANGE, np.nanmedian(eg, axis=0), None, None)],
                              "frames before death", f"median distance (px) - deaths by a {lab} (n={len(sel)})", 0, 40,
                              hline=(base_gap, "typical nearest-enemy gap")))
    return chart("Rectangle deaths: the policy is already being chased when it runs into the rectangle",
                 "4-frame argmax. For static rectangles the footprint is known during the ~100-frame warning, so the distance is to that footprint.",
                 legend([("Distance to the killing rectangle", BLUE, "line"), ("Distance to the nearest enemy", ORANGE, "line")]) + "".join(out),
                 "The nearest enemy is already close: about 22 px away 60 frames out and 14 px at 10 frames, against a typical 29 px. Players die at 2.2-2.4 px per frame, near top speed, so many of these look like escapes into a drawn rectangle rather than a misjudged fill. This is an association; the telemetry cannot show intent.")


# ---------------------------------------------------------------- chart 8: paths into death
def rect_union(rects):
    return [(x["x"] / P, x["y"] / P, x["width"] / P, x["height"] / P) for x in rects if x["lethal"]]


def chart_paths(rows, ids=(3, 4, 28, 29, 21, 39), npaths=45):
    cell, pad = 218, 8
    W = 3 * cell + 2 * pad
    H = 2 * (cell + 30) + pad
    s = Svg(W, H)
    for k, pid in enumerate(ids):
        sel = [r for r in rows if r["trace"]["death"] and r["trace"]["death"]["active_pattern"] and
               r["trace"]["death"]["active_pattern"]["id"] == pid and r["death_cause"] != "moving_pattern_rect"
               and r["trace"]["death"]["rects"] and all(x["lethal"] for x in r["trace"]["death"]["rects"])]
        ox, oy = (k % 3) * (cell + pad), (k // 3) * (cell + 30 + pad)
        sc = (cell - 2) / FIELD
        s.text(ox, oy + 12, f"pattern {pid}", "m", 12, weight=600)
        s.text(ox + cell, oy + 12, f"{len(sel)} deaths", "s", 11, "end")
        oy += 18
        s.add(f'<rect x="{ox}" y="{oy}" width="{cell-2}" height="{cell-2}" fill="none" stroke="{GRID}"/>')
        if sel:
            for rx, ry, rw, rh in rect_union(sel[0]["trace"]["death"]["rects"]):
                s.add(f'<rect x="{ox+rx*sc:.1f}" y="{oy+ry*sc:.1f}" width="{rw*sc:.1f}" height="{rh*sc:.1f}" fill="{BLUE}" opacity="0.22"/>')
        for r in sel[:npaths]:
            d = r["trace"]["death"]
            rc = d["recent"]
            m = min(60, len(rc["x"]))
            pts = " ".join(f'{ox + rc["x"][-m + i] / P * sc:.1f},{oy + rc["y"][-m + i] / P * sc:.1f}' for i in range(m))
            cause = "rectangle" if r["death_cause"] == "static_pattern_rect" else "enemy"
            color = BLUE if cause == "rectangle" else ORANGE
            s.add(f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="1.2" opacity="0.5"/>')
            s.add(f'<circle cx="{ox + rc["x"][-1] / P * sc:.1f}" cy="{oy + rc["y"][-1] / P * sc:.1f}" r="3.2" fill="{color}" stroke="var(--background)" stroke-width="1.5"><title>{esc(f"pattern {pid}: died to {cause} {d["active_pattern"]["frames_since_start"]} frames after the pattern started")}</title></circle>')
    return chart("Where the policy dies inside the worst static patterns",
                 "4-frame argmax. Shaded = the pattern's lethal rectangles at death. Lines are the last 60 frames before death, dots are where it died. Up to 45 deaths per pattern.",
                 legend([("Died to the rectangle", BLUE, "dot"), ("Died to an enemy", ORANGE, "dot")]) + s.render(),
                 "In 39 and 3 many paths run along a wall straight into a rectangle that touches that wall (wall hugging into a closing corridor). In 28 the policy circles inside the cross of four rectangles and is caught by enemies there. Pattern 4 is the transposed layout of 3 but its deaths spread out instead of piling into the corner.")


# ---------------------------------------------------------------- chart 9: where on the field
def chart_heatmap(rows, cellpx=16):
    n = FIELD // cellpx
    deaths = np.zeros((n, n))
    frames = np.zeros((n, n))
    for r in rows:
        for x, y in zip(r["trace"]["samples"]["x"], r["trace"]["samples"]["y"]):
            frames[min(n - 1, int(y / P // cellpx)), min(n - 1, int(x / P // cellpx))] += 30
        d = r["trace"]["death"]
        deaths[min(n - 1, int(d["player_y_raw"] / P // cellpx)), min(n - 1, int(d["player_x_raw"] / P // cellpx))] += 1
    rate = np.where(frames > 3000, 10000 * deaths / np.maximum(frames, 1), np.nan)
    cell = 62
    W, H = n * cell + 90, n * cell + 28
    s = Svg(W, H)
    vmax = np.nanmax(rate)
    ramp = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
    for i in range(n):
        for j in range(n):
            v = rate[i, j]
            if np.isnan(v):
                col = "none"
            else:
                col = ramp[min(len(ramp) - 1, int(v / vmax * (len(ramp) - 0.001)))]
            tip = "too little time spent here" if np.isnan(v) else f"x {j*cellpx}-{(j+1)*cellpx}, y {i*cellpx}-{(i+1)*cellpx}: {int(deaths[i,j])} deaths in {int(frames[i,j]):,} frames = {v:.1f} per 10k; {100*frames[i,j]/frames.sum():.1f}% of time"
            s.add(f'<g class="hit"><title>{esc(tip)}</title><rect x="{j*cell+1}" y="{i*cell+1}" width="{cell-2}" height="{cell-2}" rx="3" fill="{col}" stroke="{GRID}"/></g>')
            if not np.isnan(v) and v > 0:
                s.add(f'<text x="{j*cell+cell/2}" y="{i*cell+cell/2+4}" text-anchor="middle" font-size="11" style="fill:{"#fff" if v/vmax>0.4 else "#0b0b0b"}">{v:.1f}</text>')
    for k, c in enumerate(reversed(ramp)):
        s.add(f'<rect x="{n*cell+30}" y="{20+k*22}" width="20" height="20" fill="{c}"/>')
    s.text(n * cell + 56, 34, f"{vmax:.1f}", "s", 11)
    s.text(n * cell + 56, 20 + 6 * 22 + 14, "0", "s", 11)
    s.text(0, n * cell + 20, "deaths per 10k frames spent in each 16x16 px cell (top of the screen is up)", "s", 11)
    hot = sorted(((rate[i, j], i, j) for i in range(n) for j in range(n) if not np.isnan(rate[i, j])), reverse=True)[:3]
    where = ", ".join(f"x {j*cellpx}-{(j+1)*cellpx} / y {i*cellpx}-{(i+1)*cellpx} ({v:.0f})" for v, i, j in hot)
    return chart("No part of the field is safe, but a few cells are 3-4x worse than most",
                 f"4-frame argmax, {len(rows):,} games. Death rate per cell = deaths there / frames spent there (per 10k frames). Darker = deadlier.",
                 s.render(), f"Hottest cells: {where}. Death position alone does not separate wall from open field; see the paths above.")


# ---------------------------------------------------------------- page
def page(sections):
    return ("<!doctype html><html><head><meta charset='utf-8'><title>Checkpoint 420 deaths</title><style>"
            + CSS + "</style></head><body>" + "".join(sections) + "</body></html>")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report-dir", type=Path, required=True)
    ap.add_argument("--pass2-dir", type=Path, required=True, help="group files with path/gap/sample telemetry")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--split-dir", type=Path, help="also write one light-themed HTML file per chart (for screenshots)")
    args = ap.parse_args()
    d = args.report_dir
    tables = json.loads((d / "tables-fresh.json").read_text())
    records = json.loads((d / "per-game-fresh.json").read_text())
    r4 = load_pass2(args.pass2_dir, "argmax_r4")
    base = float(np.median([g / P for r in r4 for g, pid in zip(r["trace"]["samples"]["enemy_gap"], r["trace"]["samples"]["pattern_id"]) if g >= 0]))
    sections = [chart_pattern_base_rate(tables), chart_cause_split(records), chart_time_in_pattern(records),
                chart_enemy_gap_cdf(r4), chart_approach(r4, base), chart_rect_approach(r4, base),
                chart_paths(r4), chart_heatmap(r4), chart_pattern_dots(tables)]
    args.out.write_text(page(sections))
    if args.split_dir:
        args.split_dir.mkdir(parents=True, exist_ok=True)
        light = ":root{--foreground:#0b0b0b;--muted-foreground:#52514e;--background:#fcfcfb;--border:#e1e0d9}body{background:#fcfcfb;padding:12px;width:728px}"
        for i, sec in enumerate(sections, 1):
            (args.split_dir / f"chart{i}.html").write_text(page([sec]).replace("<style>", "<style>" + light, 1))


if __name__ == "__main__":
    main()
