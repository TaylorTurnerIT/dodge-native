"""Render death_trace_analysis.py tables as Markdown (counts, percentages, 95% intervals)."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

CAUSE_SHORT = {"normal_enemy": "normal", "kamikaze_enemy": "kami body", "kamikaze_explosion": "kami blast",
               "static_pattern_rect": "static rect", "moving_pattern_rect": "moving rect", "unknown": "unknown"}


def pct(stat, digits=1):
    if stat is None or not math.isfinite(stat["est"]):
        return "n/a"
    return f"{100 * stat['est']:.{digits}f}% [{100 * stat['lo']:.{digits}f}, {100 * stat['hi']:.{digits}f}]"


def num(stat, digits=2):
    if stat is None or not math.isfinite(stat["est"]):
        return "n/a"
    return f"{stat['est']:.{digits}f} [{stat['lo']:.{digits}f}, {stat['hi']:.{digits}f}]"


def pp(stat, digits=1):
    """Difference of proportions, in percentage points."""
    return f"{100 * stat['est']:+.{digits}f} [{100 * stat['lo']:+.{digits}f}, {100 * stat['hi']:+.{digits}f}]"


def md(header, rows):
    out = ["| " + " | ".join(header) + " |", "|" + "|".join(["---"] * len(header)) + "|"]
    out += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return "\n".join(out) + "\n"


def i(x):
    return f"{int(round(x)):,}"


def render_setting(name, block, top_patterns=8, min_encounters=30):
    t = block["tables"]
    lines = [f"### {name}: {i(block['n_games'])} games over {i(block['n_seeds'])} seeds\n"]
    lines.append("**Phase hazard.** Deaths among games alive at the phase start, and deaths per 1,000 frames lived.\n")
    lines.append(md(["phase", "alive at start", "deaths", "P(die in phase)", "deaths / 10k frames"],
                    [[r["phase"], i(r["at_risk"]), i(r["deaths"]), pct(r["hazard"]), num(r["rate_per_10k_frames"])]
                     for r in t["phase_overview"]]))
    lines.append("**Cause share of deaths.**\n")
    causes = list(t["cause_share"][0]["shares"])
    lines.append(md(["phase", "deaths"] + [CAUSE_SHORT[c] for c in causes],
                    [[r["phase"], i(r["deaths"])] + [pct(r["shares"][c], 0) for c in causes] for r in t["cause_share"]]))
    lines.append("**fyou before death.** Share of each phase's deaths preceded by a fyou trigger, and by one within "
                 "the last 100/300/600 frames; plus killer provenance.\n")
    lines.append(md(["phase", "deaths", "any trigger", "<=100f", "<=300f", "<=600f", "mean triggers",
                     "killer fyou-spawned (of enemy kills)", "fyou-spawned enemy on screen"],
                    [[r["phase"], i(r["deaths"]), pct(r["fy_any"], 0), pct(r["fy_w100"], 0), pct(r["fy_w300"], 0),
                      pct(r["fy_w600"], 0), num(r["mean_triggers_before_death"], 1),
                      f"{pct(r['killer_fyou_of_enemy_kills'], 0)} (n={i(r['enemy_kills'])})",
                      pct(r["fyou_enemy_alive_any"], 0)] for r in t["fyou_in_deaths"]]))
    lines.append("**Hazard split by fyou status at phase start.** P(die in phase | alive at start).\n")
    lines.append(md(["phase", "split", "n yes / no", "hazard yes", "hazard no", "difference (pp)"],
                    [[r["phase"], r["split"].replace("_", " "), f"{i(r['at_risk_yes'])} / {i(r['at_risk_no'])}",
                      pct(r["hazard_yes"]), pct(r["hazard_no"]), pp(r["difference"])]
                     for r in t["hazard_by_fyou_at_phase_start"]]))
    lines.append("**Death rate by time since the last fyou trigger** (frames lived in each bucket; deaths / 10k frames).\n")
    lines.append(md(["phase", "since last fyou", "deaths", "frames", "deaths / 10k frames"],
                    [[r["phase"], r["since_last_fyou"], i(r["deaths"]), i(r["frames"]), num(r["deaths_per_10k_frames"])]
                     for r in t["hazard_by_time_since_fyou"]]))
    lines.append("**Pattern state base rate.** Share of frames with a pattern active, and deaths per 10k frames "
                 "lived with a pattern active / inactive (by class of the active pattern).\n")
    lines.append(md(["phase", "frames pattern active", "deaths active", "per 10k active", "deaths inactive",
                     "per 10k inactive", "per 10k static", "per 10k moving"],
                    [[r["phase"], pct(r["share_of_frames_pattern_active"], 0), i(r["deaths_active"]),
                      num(r["per_10k_active"]), i(r["deaths_inactive"]), num(r["per_10k_inactive"]),
                      num(r["per_10k_static"]), num(r["per_10k_moving"])] for r in t["hazard_by_pattern_state"]]))
    lines.append("**Pattern active at death.**\n")
    lines.append(md(["phase", "deaths", "pattern active", "moving", "static", "no pattern", "<=60f", "61-180f",
                     "181-600f", "601f+"],
                    [[r["phase"], i(r["deaths"]), pct(r["pattern_active"], 0), pct(r["type"]["moving"], 0),
                      pct(r["type"]["static"], 0), pct(r["no_pattern"], 0)]
                     + [pct(r["frames_since_pattern_start"][b], 0) for b in ("<=60", "61-180", "181-600", "601+")]
                     for r in t["pattern_at_death"]]))
    lines.append("(`<=60f`.. columns: frames since the active pattern started, as a share of deaths with a pattern "
                 "active.)\n")
    # Top patterns by deaths.
    by_id = t["encounter_rates_by_pattern_id"]
    ranked = sorted(by_id, key=lambda r: -r["by_start_phase"]["all"]["deaths_during"])
    lines.append(f"**Per-pattern deaths and rates** (top {top_patterns} by deaths during the encounter; "
                 f"encounter = one activation; rates are deaths / encounters started; observed / expected divides "
                 f"deaths by those expected if every encounter died at its start phase's overall rate, which "
                 f"removes the late-game confound).\n")
    rows = []
    for r in ranked[:top_patterns]:
        a = r["by_start_phase"]["all"]
        rows.append([r["id"], r["pattern_type"], r["family"], i(a["encounters"]), i(a["deaths_during"]),
                     i(a["rect_deaths"]), pct(a["death_per_encounter"]), pct(a["rect_death_per_encounter"]),
                     num(a["deaths_per_10k_active_frames"]), num(r["observed_over_expected"])])
    lines.append(md(["id", "type", "family", "encounters", "deaths during", "rect deaths", "death / encounter",
                     "rect death / encounter", "deaths / 10k active frames", "observed / expected"], rows))
    eligible = [r for r in by_id if r["by_start_phase"]["all"]["encounters"] >= min_encounters]
    eligible.sort(key=lambda r: -r["by_start_phase"]["all"]["death_per_encounter"]["est"])
    lines.append(f"**Highest death-per-encounter among patterns with >= {min_encounters} encounters.**\n")
    rows = []
    for r in eligible[:top_patterns]:
        a = r["by_start_phase"]["all"]
        rows.append([r["id"], r["pattern_type"], i(a["encounters"]), i(a["deaths_during"]),
                     pct(a["death_per_encounter"]), pct(a["rect_death_per_encounter"]),
                     num(r["observed_over_expected"])])
    lines.append(md(["id", "type", "encounters", "deaths during", "death / encounter", "rect death / encounter",
                     "observed / expected"], rows))
    lines.append("**Pattern class and phase of encounter start.**\n")
    rows = []
    for r in t["encounter_rates_by_scope"]:
        if r["scope"] not in ("all", "type|static", "type|moving"):
            continue
        for ph in ("all", "0-1k", "1k-2k", "2k-3k", "3k-5k", "5k+"):
            a = r["by_start_phase"][ph]
            rows.append([r["scope"].replace("type|", ""), ph, i(a["encounters"]), i(a["deaths_during"]),
                         pct(a["death_per_encounter"]), pct(a["rect_death_per_encounter"])])
    lines.append(md(["class", "encounter started in", "encounters", "deaths during", "death / encounter",
                     "rect death / encounter"], rows))
    lines.append("**Death scenarios** (shares of each phase's deaths).\n")
    lines.append(md(["phase", "deaths", "in center box (dwell>=1)", "dwell 51+", "mean dwell", "mean other enemies",
                     "<5 others", "15+ others", "corner", "edge", "interior", "freeze active"],
                    [[r["phase"], i(r["deaths"]), pct(r["dwell_positive"], 0),
                      pct(r["dwell"]["51+"], 0), num(r["mean_center_dwell"], 1), num(r["mean_other_enemies"], 1),
                      pct(r["enemies_on_screen_excluding_killer"]["0-4"], 0),
                      pct(r["enemies_on_screen_excluding_killer"]["15+"], 0),
                      pct(r["location"]["corner"], 0), pct(r["location"]["edge"], 0),
                      pct(r["location"]["interior"], 0), pct(r["freeze_active"], 0)]
                     for r in t["scenarios"]]))
    lines.append("**Killer age** (frames from the killer enemy's birth to the fatal frame, enemy kills only).\n")
    ages = ["<=30", "31-100", "101-300", "301-600", "601+"]
    rows = []
    for r in t["scenarios"]:
        rows.append([r["phase"], "fyou-spawned", i(r["killer_fyou_n"])] + [pct(r["killer_age_fyou"][a], 0) for a in ages])
        rows.append([r["phase"], "other spawn", i(r["killer_other_n"])] + [pct(r["killer_age_other"][a], 0) for a in ages])
    lines.append(md(["phase", "killer", "n"] + ages, rows))
    return "\n".join(lines)


def render_contrasts(contrasts):
    lines = []
    for name, block in contrasts.items():
        lines.append(f"### {name} (paired by seed)\n")
        rows = []
        for phase, stats in block.items():
            rows.append([phase,
                         pp(stats["hazard"]), num({k: v * 1 for k, v in stats["rate_per_10k"].items()
                                                   if k in ("est", "lo", "hi")}),
                         pp(stats["fy_any"]), pp(stats["fy_w300"]), pp(stats["killer_fyou_of_enemy_kills"]),
                         pp(stats["pattern_active"])]
                        + [pp(stats[f"cause_{c}"]) for c in ("normal_enemy", "moving_pattern_rect", "static_pattern_rect")])
        lines.append(md(["phase", "P(die in phase) pp", "deaths/10k frames", "any fyou pp", "fyou<=300f pp",
                         "killer fyou pp", "pattern active pp", "normal pp", "moving rect pp", "static rect pp"], rows))
    return "\n".join(lines)


def render_full_patterns(name, block, info):
    t = block["tables"]
    dd = {r["id"]: r for r in t["deaths_by_pattern_id"]}
    phases = ["0-1k", "1k-2k", "2k-3k", "3k-5k", "5k+"]
    rows = []
    for r in t["encounter_rates_by_pattern_id"]:
        a = r["by_start_phase"]["all"]
        meta = info[str(r["id"])]
        gate = f"{meta['mins']:g}-{meta['maxs']:g}" if meta["maxs"] < 30000 else f">={meta['mins']:g}"
        by_phase = "/".join(str(int(dd[r["id"]]["by_phase"][p]["deaths"])) for p in phases)
        rows.append([r["id"], r["pattern_type"], r["family"], gate, i(a["encounters"]), i(a["deaths_during"]),
                     pct(a["death_per_encounter"], 0), pct(a["rect_death_per_encounter"], 0),
                     num(r["observed_over_expected"]) if a["encounters"] else "n/a", by_phase])
    return (f"### {name}: all patterns\n\n" + md(
        ["id", "type", "family", "score gate", "encounters", "deaths during", "death / encounter",
         "rect death / encounter", "observed / expected", "deaths at death-phase 0-1k/1k-2k/2k-3k/3k-5k/5k+"], rows))


def render_post_fyou(block):
    rows = []
    for label, v in block.items():
        o = v["observed_over_expected"]
        rows.append([label, i(v["observed_deaths"]), f"{v['expected_deaths']:.1f}", i(v["frames"]), num(o)])
    return md(["setting", "deaths in 1-300 frames after a trigger", "expected at never-triggered rate",
               "frames", "observed / expected"], rows)


def render_headline(data, left="argmax_r1", right="argmax_r4"):
    """Side-by-side 1-frame (left) versus 4-frame (right) headline tables."""
    a, b = data["settings"][left]["tables"], data["settings"][right]["tables"]
    out = []
    out.append("**Phase hazard.** Games alive at the phase start, P(die in the phase), and deaths per 10k frames lived. "
               "No game reached the 18,000-frame cap, so every game ends in a death and P(die) in `5k+` is 100% by "
               "construction; use the per-frame rate there.\n")
    out.append(md(["phase", "1-frame alive", "1-frame P(die)", "1-frame / 10k frames", "4-frame alive", "4-frame P(die)",
                   "4-frame / 10k frames"],
                  [[x["phase"], i(x["at_risk"]), pct(x["hazard"]), num(x["rate_per_10k_frames"]), i(y["at_risk"]),
                    pct(y["hazard"]), num(y["rate_per_10k_frames"])]
                   for x, y in zip(a["phase_overview"], b["phase_overview"])]))
    for title, tb in (("1-frame decisions", a), ("4-frame decisions", b)):
        causes = list(tb["cause_share"][0]["shares"])[:5]
        out.append(f"**Cause share of deaths, {title}.**\n")
        out.append(md(["phase", "deaths"] + [CAUSE_SHORT[c] for c in causes],
                      [[r["phase"], i(r["deaths"])] + [pct(r["shares"][c], 0) for c in causes] for r in tb["cause_share"]]))
    out.append("**fyou before death.** Share of each phase's deaths preceded by any fyou trigger (n triggered / deaths), "
               "and killer enemy spawned by fyou (n / enemy-kill deaths).\n")
    rows = []
    for x, y in zip(a["fyou_in_deaths"], b["fyou_in_deaths"]):
        rows.append([x["phase"],
                     f"{pct(x['fy_any'])} ({i(x['fy_any']['num'])}/{i(x['deaths'])})",
                     f"{i(x['killer_fyou_of_enemy_kills']['num'])}/{i(x['killer_fyou_of_enemy_kills']['den'])}",
                     f"{pct(y['fy_any'])} ({i(y['fy_any']['num'])}/{i(y['deaths'])})",
                     f"{i(y['killer_fyou_of_enemy_kills']['num'])}/{i(y['killer_fyou_of_enemy_kills']['den'])}"])
    out.append(md(["phase", "1-frame any trigger", "1-frame fyou killer", "4-frame any trigger", "4-frame fyou killer"], rows))
    out.append("**Pattern base rate.** Share of frames with a pattern active, share of deaths with a pattern active, "
               "and death rate per 10k frames lived with a pattern active versus inactive.\n")
    rows = []
    for tb, label in ((a, "1-frame"), (b, "4-frame")):
        for r, d in zip(tb["hazard_by_pattern_state"], tb["pattern_at_death"]):
            rows.append([label, r["phase"], pct(r["share_of_frames_pattern_active"], 0), pct(d["pattern_active"], 0),
                         num(r["per_10k_active"]), num(r["per_10k_inactive"])])
    out.append(md(["decisions", "phase", "frames pattern active", "deaths with pattern active", "deaths / 10k active",
                   "deaths / 10k inactive"], rows))
    for title, tb in (("1-frame decisions", a), ("4-frame decisions", b)):
        out.append(f"**Patterns that kill in each phase, {title}.** Top five pattern ids by deaths with that pattern "
                   f"active; share of the phase's deaths.\n")
        rows = []
        for phase in ("0-1k", "1k-2k", "2k-3k", "3k-5k", "5k+"):
            top = sorted(tb["deaths_by_pattern_id"], key=lambda r: -r["by_phase"][phase]["deaths"])[:5]
            rows.append([phase] + [f"{r['id']} ({r['pattern_type'][:3]}): {i(r['by_phase'][phase]['deaths'])} "
                                   f"({pct(r['by_phase'][phase]['share_of_phase_deaths'], 0).split(' ')[0]})"
                                   for r in top])
        out.append(md(["phase", "1st", "2nd", "3rd", "4th", "5th"], rows))
    return "\n".join(out)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("tables", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--setting", action="append", help="restrict/ordering of settings to render")
    parser.add_argument("--headline-out", type=Path, help="write the compact 1-frame versus 4-frame tables")
    args = parser.parse_args()
    data = json.loads(args.tables.read_text())
    names = args.setting or list(data["settings"])
    parts = [render_setting(n, data["settings"][n]) for n in names]
    parts.append("## fyou: deaths shortly after a trigger (phase-standardized)\n\n"
                 + render_post_fyou(data["post_fyou_standardized"]))
    for n in names:
        if n.startswith("argmax"):
            parts.append(render_full_patterns(n, data["settings"][n], data["pattern_info"]))
    if data["contrasts"]:
        parts.append("## 1-frame minus 4-frame contrasts\n\n" + render_contrasts(data["contrasts"]))
    args.out.write_text("\n\n".join(parts))
    if args.headline_out:
        args.headline_out.write_text(render_headline(data))


if __name__ == "__main__":
    main()
