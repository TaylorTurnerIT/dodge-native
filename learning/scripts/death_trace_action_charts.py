"""Render the per-decision action metrics (death_trace_actions.py output) as SVG charts."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from death_trace_charts import (AQUA, BLUE, MAGENTA, MUTED, ORANGE, VIOLET, Svg, chart, legend,  # noqa: E402
                                nice_max, page, table_view)

ACTION_LABELS = ["neutral", "left", "right", "up", "down", "up-left", "up-right", "down-left", "down-right"]
RESPONSE_COLORS = {"toward": ORANGE, "away": BLUE, "sideways": MUTED, "neutral": "#d4d2c8"}
# Sequential single-hue ramp, low to high confidence.
RAMP = ["#dbe6f6", "#a9c4ec", "#6f9ddf", "#2a78d6", "#1a4c8f"]


def metric(m, name):
    return m["metrics"][name]


def est(entry, key):
    stat = entry[key]
    return (stat["est"], stat["lo"], stat["hi"]) if stat else (0.0, 0.0, 0.0)


def axis_y(s, W, H, L, R, T, B, ymax, fmt):
    for k in range(5):
        v = ymax * k / 4
        y = H - B - (H - T - B) * v / ymax
        s.line(L, y, W - R, y)
        s.text(L - 6, y + 4, fmt(v), "s", anchor="end")


def whisker(s, x, lo_y, hi_y):
    s.line(x, lo_y, x, hi_y, "var(--foreground)", 1.2)
    s.line(x - 3, lo_y, x + 3, lo_y, "var(--foreground)", 1.2)
    s.line(x - 3, hi_y, x + 3, hi_y, "var(--foreground)", 1.2)


def chart_histogram(m):
    plain, pat = metric(m, "histogram_by_pattern")
    overall = metric(m, "histogram_overall")[0]
    actions = m["actions"]
    W, H, L, R, T, B = 700, 270, 44, 10, 18, 40
    ymax = nice_max(max(est(e, a)[2] for e in (plain, pat) for a in actions))
    s = Svg(W, H)
    axis_y(s, W, H, L, R, T, B, ymax, lambda v: f"{100*v:.0f}%")
    band = (W - L - R) / len(actions)
    bw = 20
    for i, a in enumerate(actions):
        cx = L + band * (i + 0.5)
        for j, (e, color, lab) in enumerate(((plain, "#898781", "no pattern"), (pat, BLUE, "pattern visible"))):
            v, lo, hi = est(e, a)
            x = cx - bw - 1 + j * (bw + 2)
            y = H - B - (H - T - B) * v / ymax
            tip = f"{ACTION_LABELS[i]}, {lab}: {100*v:.1f}% of decisions [{100*lo:.1f}, {100*hi:.1f}]"
            s.add(f'<g class="hit"><title>{tip}</title><rect x="{x}" y="{y:.1f}" width="{bw}" height="{H-B-y:.1f}" fill="{color}" rx="3"/></g>')
            whisker(s, x + bw / 2, H - B - (H - T - B) * lo / ymax, H - B - (H - T - B) * hi / ymax)
        s.text(cx, H - B + 16, ACTION_LABELS[i], "s", 11, "middle")
    s.line(L, H - B, W - R, H - B, "#c3c2b7")
    rows = [[ACTION_LABELS[i], f"{100*est(overall, a)[0]:.1f}%", f"{100*est(plain, a)[0]:.1f}%", f"{100*est(pat, a)[0]:.1f}%"]
            for i, a in enumerate(actions)]
    lr = sum(est(overall, a)[0] for a in ("right", "up_right", "down_right")) / max(
        sum(est(overall, a)[0] for a in ("left", "up_left", "down_left")), 1e-9)
    ud = sum(est(overall, a)[0] for a in ("down", "down_left", "down_right")) / max(
        sum(est(overall, a)[0] for a in ("up", "up_left", "up_right")), 1e-9)
    return chart(
        "Which way the policy pushes",
        f"{m['metrics']['decisions']:,} decisions in {m['metrics']['games']:,} games. Whiskers are 95% intervals from resampling whole games.",
        legend([("No pattern visible", "#898781", "dot"), ("Pattern visible", BLUE, "dot")]) + s.render(),
        f"Rightward actions outnumber leftward {lr:.2f} to 1 and downward outnumber upward {ud:.2f} to 1. Neutral is {100*est(overall, 'neutral')[0]:.1f}% of decisions.",
        table_view(["action", "all", "no pattern", "pattern"], rows))


def stacked_bars(s, entries, keys, colors, L, R, T, rowh, W, labels, fmt_tip, minw=0.04):
    inner = W - L - R
    for r, e in enumerate(entries):
        y = T + r * rowh
        s.text(L - 8, y + rowh * 0.45 + 4, labels[r], "s", 11.5, "end")
        x = L
        for key, color in zip(keys, colors):
            v, lo, hi = est(e, key)
            w = inner * v
            tip = fmt_tip(labels[r], key, v, lo, hi, e["decisions"])
            s.add(f'<g class="hit"><title>{tip}</title><rect x="{x:.1f}" y="{y}" width="{max(w-1, 0):.1f}" height="{rowh*0.7:.1f}" fill="{color}"/></g>')
            if v >= minw:
                dark = color in (BLUE, ORANGE, "#1a4c8f", "#2a78d6")
                s.text(x + w / 2, y + rowh * 0.45 + 4, f"{100*v:.0f}", "m", 10.5, "middle",
                       extra=f'style="fill:{"#fff" if dark else "#0b0b0b"}"')
            x += w


def chart_response(m):
    entries = metric(m, "response_by_enemy_gap")
    labels = [e["bin"] for e in entries]
    base = metric(m, "baseline_response_when_enemy_near")[0]
    W, rowh, L, R, T = 700, 34, 90, 10, 26
    H = T + rowh * len(entries) + 28
    s = Svg(W, H)
    s.text(L, 12, "share of decisions, by distance to the nearest lethal enemy (edge to edge)", "s", 11)
    keys = ["toward", "away", "sideways", "neutral"]
    stacked_bars(s, entries, keys, [RESPONSE_COLORS[k] for k in keys], L, R, T, rowh, W, labels,
                 lambda lab, k, v, lo, hi, n: f"{lab}, {k}: {100*v:.1f}% [{100*lo:.1f}, {100*hi:.1f}] of {n:,} decisions")
    rows = [[e["bin"], f'{e["decisions"]:,}'] + [f"{100*est(e, k)[0]:.1f}%" for k in keys] for e in entries]
    close = entries[0]
    return chart(
        "How the policy moves relative to the nearest enemy",
        "Toward / away are within 67 degrees of the bearing to the enemy's centre; sideways is the rest; neutral is no key. Numbers are percent.",
        legend([(k, RESPONSE_COLORS[k], "dot") for k in keys]) + s.render(),
        f"Within 6 px the policy moves toward the enemy in {100*est(close, 'toward')[0]:.0f}% of decisions and away in {100*est(close, 'away')[0]:.0f}%. "
        f"Across all decisions with an enemy within 20 px: {100*est(base, 'toward')[0]:.0f}% toward, {100*est(base, 'away')[0]:.0f}% away.",
        table_view(["gap", "decisions"] + keys, rows))


def chart_confidence(m):
    entries = metric(m, "confidence_by_enemy_gap")
    labels = [e["bin"] for e in entries]
    keys = [k for k in entries[0] if k not in ("bin", "decisions")]
    W, rowh, L, R, T = 700, 34, 90, 10, 26
    H = T + rowh * len(entries) + 28
    s = Svg(W, H)
    s.text(L, 12, "share of decisions by the probability the policy gave its chosen action", "s", 11)
    stacked_bars(s, entries, keys, RAMP, L, R, T, rowh, W, labels,
                 lambda lab, k, v, lo, hi, n: f"{lab}, probability {k}: {100*v:.1f}% [{100*lo:.1f}, {100*hi:.1f}] of {n:,} decisions")
    overall = metric(m, "confidence_overall")[0]
    rows = [[e["bin"], f'{e["decisions"]:,}'] + [f"{100*est(e, k)[0]:.1f}%" for k in keys] for e in entries]
    low = est(overall, keys[0])[0] + est(overall, keys[1])[0]
    return chart(
        "How sure the policy is when it picks an action",
        "Probability of the chosen action under the policy's softmax; one decision of a 9-way choice, so 0.11 is a coin toss among all nine.",
        legend([(f"p {k}", c, "dot") for k, c in zip(keys, RAMP)]) + s.render(),
        f"{100*low:.0f}% of all decisions go to an action the policy gave under 60%.",
        table_view(["enemy gap", "decisions"] + keys, rows))


def chart_switching(m):
    sw = metric(m, "switch_by_enemy_gap")
    rev = metric(m, "reversal_by_enemy_gap")
    W, H, L, R, T, B = 700, 250, 44, 10, 20, 40
    s = Svg(W, H)
    axis_y(s, W, H, L, R, T, B, 1.0, lambda v: f"{100*v:.0f}%")
    band = (W - L - R) / len(sw)
    bw = 24
    for i, (a, b) in enumerate(zip(sw, rev)):
        cx = L + band * (i + 0.5)
        for j, (e, color, lab) in enumerate(((a, BLUE, "changes action"), (b, ORANGE, "reverses direction"))):
            v, lo, hi = est(e, "rate")
            x = cx - bw - 1 + j * (bw + 2)
            y = H - B - (H - T - B) * v
            s.add(f'<g class="hit"><title>{a["bin"]}, {lab}: {100*v:.1f}% [{100*lo:.1f}, {100*hi:.1f}] of {e["decisions"]:,} decisions</title><rect x="{x}" y="{y:.1f}" width="{bw}" height="{H-B-y:.1f}" fill="{color}" rx="3"/></g>')
            whisker(s, x + bw / 2, H - B - (H - T - B) * lo, H - B - (H - T - B) * hi)
            s.text(x + bw / 2, y - 7 if hi - v < 0.03 else y + 14, f"{100*v:.0f}", "m", 10.5, "middle",
                   extra='style="fill:var(--foreground)"' if hi - v < 0.03 else 'style="fill:#fff"')
        s.text(cx, H - B + 16, a["bin"], "s", 11, "middle")
    s.line(L, H - B, W - R, H - B, "#c3c2b7")
    rows = [[a["bin"], f'{a["decisions"]:,}', f'{100*est(a, "rate")[0]:.1f}%', f'{100*est(b, "rate")[0]:.1f}%']
            for a, b in zip(sw, rev)]
    overall = est(metric(m, "switch_overall")[0], "rate")[0]
    return chart(
        "Does the policy hold a heading?",
        "Share of decisions that differ from the previous decision; reversal is the share of consecutive moves pointing in opposite directions.",
        legend([("Changes action", BLUE, "dot"), ("Reverses direction", ORANGE, "dot")]) + s.render(),
        f"The chosen action changes at {100*overall:.0f}% of all decisions.",
        table_view(["enemy gap", "decisions", "changes", "reverses"], rows))


def chart_pre_death(m):
    entries = metric(m, "pre_death_response_enemy_deaths")
    base = metric(m, "baseline_response_when_enemy_near")[0]
    W, H, L, R, T, B = 700, 270, 44, 10, 14, 40
    n = len(entries)
    s = Svg(W, H)
    axis_y(s, W, H, L, R, T, B, 0.6, lambda v: f"{100*v:.0f}%")
    X = lambda k: L + (W - L - R) * (n - 1 - k) / (n - 1)  # fatal decision at the right edge
    Y = lambda v: H - B - (H - T - B) * v / 0.6
    for k in range(0, n, 5):
        s.text(X(k), H - B + 15, f"-{k}" if k else "death", "s", 11, "middle")
    s.text(L + (W - L - R) / 2, H - 4, "decisions before the fatal one (4 frames each)", "s", 11, "middle")
    for key, color in (("toward", ORANGE), ("away", BLUE)):
        pts = " ".join(f"{X(k):.1f},{Y(min(est(e, key)[0], 0.6)):.1f}" for k, e in enumerate(entries))
        s.add(f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2" stroke-linejoin="round"/>')
        s.line(L, Y(est(base, key)[0]), W - R, Y(est(base, key)[0]), color, 1, 'stroke-dasharray="4 4" opacity=".6"')
        for k in (0, 2, 5, 10):
            v, lo, hi = est(entries[k], key)
            s.add(f'<circle cx="{X(k):.1f}" cy="{Y(min(v, 0.6)):.1f}" r="4.5" fill="{color}" stroke="var(--background)" stroke-width="2"><title>{k} decisions before death, {key}: {100*v:.1f}% [{100*lo:.1f}, {100*hi:.1f}]</title></circle>')
    rows = [[f"-{k}" if k else "fatal", f'{e["decisions"]:,}', f'{100*est(e, "toward")[0]:.1f}%', f'{100*est(e, "away")[0]:.1f}%']
            for k, e in enumerate(entries)]
    t0, a0 = est(entries[0], "toward")[0], est(entries[0], "away")[0]
    tb, ab = est(base, "toward")[0], est(base, "away")[0]
    return chart(
        "What the policy does in its last moves before an enemy kills it",
        "Share of decisions moving toward or away from the nearest enemy, counted back from the fatal decision, in enemy-contact deaths. Dashed = all decisions with an enemy within 20 px.",
        legend([("Toward the enemy", ORANGE, "line"), ("Away from the enemy", BLUE, "line")]) + s.render(),
        f"At the fatal decision {100*t0:.0f}% move toward and {100*a0:.0f}% away; the baseline is {100*tb:.0f}% toward and {100*ab:.0f}% away.",
        table_view(["decisions before death", "decisions", "toward", "away"], rows))


def chart_walls(m):
    entries = metric(m, "into_wall_within_10px")
    anywhere = m["metrics"]["into_wall_anywhere"]
    names = ["left", "right", "top", "bottom"]
    W, H, L, R, T, B = 700, 230, 44, 10, 20, 40
    s = Svg(W, H)
    axis_y(s, W, H, L, R, T, B, 0.6, lambda v: f"{100*v:.0f}%")
    band = (W - L - R) / 4
    bw = 40
    for i, (name, e) in enumerate(zip(names, entries)):
        cx = L + band * (i + 0.5)
        v, lo, hi = est(e, "into_wall")
        y = H - B - (H - T - B) * v / 0.6
        s.add(f'<g class="hit"><title>{name} wall zone: {100*v:.1f}% of {e["decisions"]:,} decisions push into it [{100*lo:.1f}, {100*hi:.1f}]; {100*anywhere[name]:.1f}% anywhere</title><rect x="{cx-bw/2}" y="{y:.1f}" width="{bw}" height="{H-B-y:.1f}" fill="{BLUE}" rx="3"/></g>')
        whisker(s, cx, H - B - (H - T - B) * lo / 0.6, H - B - (H - T - B) * hi / 0.6)
        yb = H - B - (H - T - B) * anywhere[name] / 0.6
        s.line(cx - bw, yb, cx + bw, yb, ORANGE, 2)
        s.text(cx, H - B + 16, f"{name} ({e['decisions']:,})", "s", 11, "middle")
    s.line(L, H - B, W - R, H - B, "#c3c2b7")
    rows = [[n, f'{e["decisions"]:,}', f'{100*est(e, "into_wall")[0]:.1f}%', f'{100*anywhere[n]:.1f}%']
            for n, e in zip(names, entries)]
    return chart(
        "Does the policy lean on walls?",
        "Share of decisions with the player within 10 px of a wall that push toward that wall (the player is clamped, so they achieve nothing). Orange line = the same push anywhere on the field.",
        legend([("Within 10 px of the wall", BLUE, "dot"), ("Anywhere", ORANGE, "line")]) + s.render(),
        table_view(["wall", "decisions in zone", "pushes into wall", "anywhere"], rows))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--metrics", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--split-dir", type=Path)
    args = ap.parse_args()
    m = json.loads(args.metrics.read_text())
    sections = [chart_histogram(m), chart_response(m), chart_pre_death(m), chart_confidence(m),
                chart_switching(m), chart_walls(m)]
    args.out.write_text(page(sections))
    if args.split_dir:
        args.split_dir.mkdir(parents=True, exist_ok=True)
        light = ":root{--foreground:#0b0b0b;--muted-foreground:#52514e;--background:#fcfcfb;--border:#e1e0d9}body{background:#fcfcfb;padding:12px;width:728px}"
        for i, sec in enumerate(sections, 1):
            (args.split_dir / f"action{i}.html").write_text(page([sec]).replace("<style>", "<style>" + light, 1))


if __name__ == "__main__":
    main()
