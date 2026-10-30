"""Regenerate every figure in main.tex. All numbers are copied from the
evaluation summaries cited in the paper; see data.py for provenance."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from data import *

plt.rcParams.update({
    "font.family": "serif", "font.size": 7.5, "axes.labelsize": 7.5,
    "axes.titlesize": 8, "legend.fontsize": 6.5, "xtick.labelsize": 7,
    "ytick.labelsize": 7, "axes.linewidth": 0.6, "pdf.fonttype": 42,
    "axes.spines.top": False, "axes.spines.right": False,
    "lines.linewidth": 1.2, "lines.markersize": 3.5,
})
BLUE, ORANGE, GREEN, RED, PURPLE, SKY, GRAY = (
    "#0072B2", "#E69F00", "#009E73", "#D55E00", "#CC79A7", "#56B4E9", "#555555")
FULL, COL = 7.16, 3.5


def panel(ax, tag):
    ax.text(-0.02, 1.04, tag, transform=ax.transAxes, fontweight="bold", fontsize=8)


# ---- Fig 2: progress -------------------------------------------------------
fig, (a, b) = plt.subplots(1, 2, figsize=(FULL, 2.7), gridspec_kw={"width_ratios": [1.25, 1]})
xs = list(range(len(HISTORY)))
a.plot(xs, [h[1] for h in HISTORY], color="#999999", lw=0.8, zorder=1)
for i, (lab, v, hollow) in enumerate(HISTORY):
    a.plot(i, v, "o", ms=3, mfc="white" if hollow else GRAY, mec=GRAY, mew=0.8, zorder=2)
for (name, lo, hi) in PHASES:
    a.axvspan(lo - 0.5, hi + 0.5, color="#000000", alpha=0.04 if PHASES.index((name, lo, hi)) % 2 else 0.0)
    a.text((lo + hi) / 2, -420, name, ha="center", va="top", fontsize=6)
a.set_ylim(0, 3300); a.set_xlim(-0.8, len(HISTORY) - 0.2)
a.set_xticks([]); a.set_ylabel("mean alive frames (64 dev seeds)")
a.text(15.6, 2330, "best of 24\nevals", fontsize=6, ha="left", color=GRAY)
panel(a, "(a)")

u = [r[0] for r in RETAINED]
b.plot(u, [r[1] for r in RETAINED], "o-", color=BLUE, label="mean, 64 dev seeds (selection)")
b.plot(u, [r[2] for r in RETAINED], "s-", color=ORANGE, label="mean, 1,024-seed ranking")
b.plot(u, [r[3] for r in RETAINED], "^--", color=RED, label="Q1, 1,024-seed ranking")
b.plot([324, 348], [CONFIRM_324_348[0], CONFIRM_324_348[1]], "D", color=GREEN, ms=4.5,
       label="mean, 2,048 fresh seeds")
b.axhline(3060, color=GRAY, ls=":", lw=0.8)
b.text(181, 3085, "3,060 progress gate (64-seed)", fontsize=6, color=GRAY)
b.set_xticks(u); b.set_xlabel("PPO update of retained checkpoint")
b.set_ylim(0, 3300); b.legend(frameon=False, loc="center", bbox_to_anchor=(0.5, 0.34), fontsize=6)
panel(b, "(b)")
fig.tight_layout(w_pad=1.2)
fig.savefig("figs/progress.pdf"); plt.close(fig)

# ---- Fig 3: continuation + decision frequency -----------------------------
fig, (a, b) = plt.subplots(1, 2, figsize=(FULL, 2.6), gridspec_kw={"width_ratios": [1.1, 1]})
ux = [c[0] for c in CONT]
a.plot(ux, [c[3] for c in CONT], "^-", color=PURPLE, label="Q4 (best quarter)")
a.plot(ux, [c[1] for c in CONT], "s-", color=ORANGE, label="mean")
a.plot(ux, [c[2] for c in CONT], "o--", color=RED, label="Q1 (worst quarter)")
a.set_xlabel("PPO updates after Uniform #2 (4-frame decisions)")
a.set_ylabel("alive frames (1,024 seeds)"); a.set_xticks(range(0, 601, 120))
a.legend(frameon=False, loc="center", bbox_to_anchor=(0.5, 0.60), fontsize=6)
panel(a, "(a)")

import numpy as np
conds = ["4-frame\nsampled", "1-frame\nsampled", "4-frame\nargmax", "1-frame\nargmax"]
order = ["sampled_r4", "sampled_r1", "argmax_r4", "argmax_r1"]
w = 0.26; x = np.arange(4)
for k, (key, col, lab) in enumerate([("Q1", RED, "Q1"), ("Mean", ORANGE, "mean"), ("Q4", PURPLE, "Q4")]):
    vals = [CONFIRM[c][key] for c in order]
    bars = b.bar(x + (k - 1) * w, vals, w, color=col, label=lab, edgecolor="none")
    for xi, v in zip(x + (k - 1) * w, vals):
        b.text(xi, v + 90, f"{v:,.0f}", ha="center", fontsize=5, rotation=90)
b.set_xticks(x); b.set_xticklabels(conds); b.set_ylim(0, 8600)
b.set_ylabel("alive frames (256 fresh seeds)"); b.legend(frameon=False, loc="upper left", ncol=3, fontsize=6)
panel(b, "(b)")
fig.tight_layout(w_pad=1.2)
fig.savefig("figs/continuation_decisions.pdf"); plt.close(fig)

# ---- Fig 4: survival milestones -------------------------------------------
fig, ax = plt.subplots(figsize=(COL, 2.5))
ms = list(range(13))
ax.plot(ms, ARGMAX_R1, "D-", color=GREEN, label="1-frame, argmax (mean 4,432)", ms=3)
ax.plot(ms, SAMPLED_R1, "s-", color=ORANGE, label="1-frame, sampled (mean 4,387)", ms=3)
ax.plot(ms, SAMPLED_R4, "o-", color=GRAY, label="4-frame, sampled (mean 2,626)", ms=3)
ax.axhline(50, color="#bbbbbb", lw=0.6, ls=":")
ax.set_xlabel("gameplay frames survived (thousands)"); ax.set_ylabel("games still alive (%)")
ax.set_xticks(ms); ax.set_ylim(0, 102); ax.legend(frameon=False, fontsize=6)
fig.tight_layout(); fig.savefig("figs/milestones.pdf"); plt.close(fig)

# ---- Fig 5: cause of death by window --------------------------------------
fig, ax = plt.subplots(figsize=(FULL, 2.5))
cols = [BLUE, PURPLE, SKY, ORANGE]
names = ["normal enemy", "kamikaze (body + explosion)", "static pattern rectangle", "moving pattern rectangle"]
w = 0.36
for i in range(5):
    for sg, key in ((-1, "r4"), (1, "r1")):
        d = DEATHS[key][i]; n = d[0]; acc = 0; xc = i + sg * (w / 2 + 0.02)
        for j, c in enumerate(cols):
            p = 100 * d[2 + j] / n
            ax.bar(xc, p, w, bottom=acc, color=c, edgecolor="white", lw=0.3,
                   label=names[j] if (i == 0 and sg == -1) else None)
            if p >= 9:
                ax.text(xc, acc + p / 2, f"{p:.0f}", ha="center", va="center", fontsize=5.5,
                        color="white" if c in (BLUE, PURPLE) else "black")
            acc += p
        ax.text(xc, 102, f"{d[1]:.0f}%", ha="center", fontsize=5.5)
        ax.text(xc, -9, "4f" if sg < 0 else "1f", ha="center", fontsize=5.5, color=GRAY)
ax.set_xticks(range(5)); ax.set_xticklabels(["0-1k", "1k-2k", "2k-3k", "3k-5k", "5k+"])
ax.tick_params(axis="x", pad=11)
ax.set_xlabel("gameplay frame window in which the game ended"); ax.set_ylabel("deaths in window (%)")
ax.set_ylim(0, 112); ax.legend(frameon=False, ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.30), fontsize=6)
fig.tight_layout(); fig.savefig("figs/death_causes.pdf"); plt.close(fig)

# ---- Telemetry figures (checkpoint 420, 2,048 fresh seeds, argmax) --------
import json
import numpy as np
T = json.load(open("telemetry.json"))
PH = ["0-1k", "1k-2k", "2k-3k", "3k-5k"]
PH5 = T["phases"]

# Fig 6: phase hazard and pattern exposure
fig, (a, b) = plt.subplots(1, 2, figsize=(FULL, 2.4))
x = np.arange(4)
for key, lab, c, m, off in (("argmax_r1", "1-frame", GREEN, "D", -0.06), ("argmax_r4", "4-frame", GRAY, "o", 0.06)):
    h = np.array([T[key]["hazard"][p] for p in PH]) * 100
    a.errorbar(x + off, h[:, 0], yerr=[h[:, 0] - h[:, 1], h[:, 2] - h[:, 0]], fmt=m + "-", color=c,
               capsize=1.5, elinewidth=0.7, label=lab)
a.set_xticks(x); a.set_xticklabels(PH)
a.set_xlabel("window (games alive at its start)"); a.set_ylabel("share that die in the window (%)")
a.legend(frameon=False); panel(a, "(a)")
x5 = np.arange(5)
for key, tag, c, ls in (("argmax_r1", "1f", GREEN, "-"), ("argmax_r4", "4f", GRAY, "--")):
    for state, mk, fc in (("active", "s", c), ("inactive", "o", "white")):
        v = np.array([T[key]["pattern_rate"][p][state] for p in PH5])
        b.errorbar(x5, v[:, 0], yerr=[v[:, 0] - v[:, 1], v[:, 2] - v[:, 0]], fmt=mk + ls, color=c, mfc=fc,
                   capsize=1.5, elinewidth=0.7, label=f"{tag}, pattern {state}")
b.set_yscale("log"); b.set_ylim(0.02, 40); b.set_xticks(x5); b.set_xticklabels(PH5)
b.set_xlabel("gameplay frame window"); b.set_ylabel("deaths per 10{,}000 frames".replace("{,}", ","))
b.legend(frameon=False, ncol=2, fontsize=6, loc="lower right"); panel(b, "(b)")
fig.tight_layout(w_pad=1.2); fig.savefig("figs/tele_hazard.pdf"); plt.close(fig)

# Fig 7: per-pattern lethality
rows = [r for r in T["argmax_r1"]["patterns"] if r["enc"] >= 30]
rows.sort(key=lambda r: -r["death"][0])
r4m = {r["id"]: r for r in T["argmax_r4"]["patterns"]}
fig, ax = plt.subplots(figsize=(FULL, 2.6))
for i, r in enumerate(rows):
    c = BLUE if r["type"] == "static" else ORANGE
    d = r["death"]
    ax.plot([i, i], [d[1] * 100, d[2] * 100], color=c, lw=1.0, alpha=0.55)
    ax.plot(i, d[0] * 100, "o", color=c, ms=3.4, zorder=3)
    q = r4m.get(r["id"])
    if q and q["enc"] >= 30:
        ax.plot(i, q["death"][0] * 100, "D", mfc="white", mec=GRAY, mew=0.7, ms=3.2, zorder=2)
ax.set_xticks(range(len(rows))); ax.set_xticklabels([str(r["id"]) for r in rows], fontsize=5.5)
ax.set_xlabel("pattern id (met at least 30 times at 1-frame), sorted by 1-frame lethality")
ax.set_ylabel("encounters ending in death (%)")
ax.set_xlim(-0.8, len(rows) - 0.2); ax.set_ylim(0, 104)
from matplotlib.lines import Line2D
ax.legend(handles=[Line2D([], [], marker="o", color=BLUE, ls="", ms=3.4, label="static, 1-frame (95% CI)"),
                   Line2D([], [], marker="o", color=ORANGE, ls="", ms=3.4, label="moving, 1-frame (95% CI)"),
                   Line2D([], [], marker="D", mfc="white", mec=GRAY, ls="", ms=3.2, label="4-frame")],
          frameon=False, loc="upper right", fontsize=6.5)
fig.tight_layout(); fig.savefig("figs/tele_patterns.pdf"); plt.close(fig)

# Fig 8: approach to the killing enemy
A = T["approach"]
f = np.arange(60)
nz = lambda k: np.array([np.nan if v is None else v for v in A[k]])
fig, (a, b) = plt.subplots(1, 2, figsize=(FULL, 2.3))
a.fill_between(-f, nz("gap_q1"), nz("gap_q3"), color=PURPLE, alpha=0.18, lw=0)
a.plot(-f, nz("gap_med"), color=PURPLE)
a.set_xlim(-59, 0); a.set_ylim(0, 65)
a.set_xlabel("frames before death"); a.set_ylabel("distance to killing enemy (px)")
a.text(-57, 6, f"median and quartiles, {A['n']:,} enemy-contact deaths", fontsize=6, color=GRAY)
panel(a, "(a)")
b.plot(-f, nz("killer_toward"), color=ORANGE, label="enemy toward player")
b.plot(-f, nz("player_toward"), color=BLUE, label="player toward enemy")
b.axhline(0, color="#bbbbbb", lw=0.6)
b.set_xlim(-59, 0); b.set_ylim(-1, 2)
b.set_xlabel("frames before death"); b.set_ylabel("median closing speed (px/frame)")
b.legend(frameon=False, loc="upper left"); panel(b, "(b)")
fig.tight_layout(w_pad=1.2); fig.savefig("figs/tele_approach.pdf"); plt.close(fig)

# Fig 9: where deaths happen inside four static patterns
fig, axs = plt.subplots(1, 4, figsize=(FULL, 2.0))
for ax, pid in zip(axs, ("3", "4", "28", "39")):
    d = T["paths"][pid]
    ax.set_xlim(0, 128); ax.set_ylim(128, 0); ax.set_aspect("equal")
    for rx, ry, rw, rh in d["rects"]:
        ax.add_patch(plt.Rectangle((rx, ry), rw, rh, color=BLUE, alpha=0.2, lw=0))
    for p in d["paths"]:
        c = BLUE if p["cause"] == "rect" else ORANGE
        xy = np.array(p["xy"])
        ax.plot(xy[:, 0], xy[:, 1], color=c, lw=0.5, alpha=0.45)
        ax.plot(xy[-1, 0], xy[-1, 1], "o", color=c, ms=2.2, mec="white", mew=0.3)
    ax.set_xticks([]); ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_visible(True); sp.set_linewidth(0.5)
    ax.set_title(f"pattern {pid} ({d['n']} deaths)", fontsize=6.5)
fig.tight_layout(w_pad=0.6, rect=(0, 0, 1, 0.97)); fig.savefig("figs/tele_paths.pdf"); plt.close(fig)
print("figures written")
