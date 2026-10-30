"""Action-distribution metrics from per-decision death-trace groups (`--decisions` runs).

Input: one group file written by death_trace_eval.py with `--decisions`. Output: one JSON of
metrics with seed-cluster bootstrap 95% intervals (whole games are resampled, so decisions from
one game are never treated as independent).

Every share is a ratio of sums over games: sum of decisions in a class / sum of decisions in the
bin, recomputed on each bootstrap draw.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

ACTIONS = ["neutral", "left", "right", "up", "down", "up_left", "up_right", "down_left", "down_right"]
# Unit direction of each action in screen coordinates (y grows downward; `up` is -y).
_D = 1 / np.sqrt(2)
VECTOR = np.array([[0, 0], [-1, 0], [1, 0], [0, -1], [0, 1], [-_D, -_D], [_D, -_D], [-_D, _D], [_D, _D]])
PHASES = [(0, 1000, "0-1k"), (1000, 2000, "1k-2k"), (2000, 3000, "2k-3k"), (3000, 5000, "3k-5k"), (5000, 10**9, "5k+")]
ENEMY_BINS = [(0, 60, "<6 px"), (60, 120, "6-12"), (120, 200, "12-20"), (200, 400, "20-40"), (400, 10**9, "40+")]
CONFIDENCE_BINS = [(0, 400, "<0.4"), (400, 600, "0.4-0.6"), (600, 800, "0.6-0.8"), (800, 950, "0.8-0.95"), (950, 1001, ">=0.95")]
ENEMY_CAUSES = ["normal_enemy", "kamikaze_enemy", "kamikaze_explosion"]
RESPONSES = ["toward", "away", "sideways", "neutral"]
WALL_ZONE = 100  # tenths of a pixel: within 10 px of a wall
FIELD_MIN, FIELD_MAX = 20, 1250  # playfield clamp [2, 125] px, in tenths
TOWARD_COS = 0.38  # within 67.5 degrees of the bearing counts as toward (or away) for 8-way moves
BEFORE = 30  # decisions before the end shown in the pre-death view
BOOTSTRAP_DRAWS = 2000


def stack(rows):
    """Concatenate every game's decision columns into flat arrays plus bookkeeping."""
    cols = {}
    sizes = [len(r["decisions"]["a"]) for r in rows]
    for name in rows[0]["decisions"]:
        cols[name] = np.concatenate([np.asarray(r["decisions"][name], dtype=np.int64) for r in rows])
    cols["game"] = np.repeat(np.arange(len(rows)), sizes)
    cols["index"] = np.concatenate([np.arange(n) for n in sizes])
    cols["before"] = np.concatenate([np.arange(n)[::-1] for n in sizes])
    repeat = np.array([r["action_repeat"] for r in rows])
    cols["frame"] = cols["index"] * repeat[cols["game"]]
    cols["prev"] = np.concatenate([[-1], cols["a"][:-1]])
    cols["prev"][cols["index"] == 0] = -1
    cols["cause"] = np.array([r["death_cause"] for r in rows])[cols["game"]]
    return cols


def bearing_class(a, edx, edy, has_enemy):
    """Toward / away / sideways / neutral relative to the nearest enemy; 4 when no enemy."""
    u = VECTOR[a]
    norm = np.hypot(edx, edy)
    cos = np.divide((u[:, 0] * edx + u[:, 1] * edy), norm, out=np.zeros(len(a)), where=norm > 0)
    out = np.where(cos >= TOWARD_COS, 0, np.where(cos <= -TOWARD_COS, 1, 2))
    out = np.where(a == 0, 3, out)
    return np.where(has_enemy, out, 4)


def derive(c):
    c["has_enemy"] = c["eg"] >= 0
    c["response"] = bearing_class(c["a"], c["edx"], c["edy"], c["has_enemy"])
    same_game = (c["prev"] >= 0)
    c["switch"] = same_game & (c["a"] != c["prev"])
    pu, cu = VECTOR[np.maximum(c["prev"], 0)], VECTOR[c["a"]]
    dot = (pu * cu).sum(axis=1)
    c["moving_pair"] = same_game & (c["a"] != 0) & (c["prev"] != 0)
    c["reversal"] = c["moving_pair"] & (dot <= -0.7)
    return c


def mean_or_none(values, scale=1, fn=np.mean):
    return float(fn(values) / scale) if len(values) else None


def bin_of(values, bins):
    out = np.full(len(values), -1)
    for i, (lo, hi, _) in enumerate(bins):
        out[(values >= lo) & (values < hi)] = i
    return out


def counts(game, nbins, noutcomes, bin_, outcome, G):
    """Per-game count matrix [G, nbins, noutcomes] for decisions with bin_ >= 0 and outcome >= 0."""
    keep = (bin_ >= 0) & (outcome >= 0)
    idx = (game[keep] * nbins + bin_[keep]) * noutcomes + outcome[keep]
    return np.bincount(idx, minlength=G * nbins * noutcomes).reshape(G, nbins, noutcomes)


def bootstrap_weights(G, draws=BOOTSTRAP_DRAWS, seed=20261030):
    rng = np.random.default_rng(seed)
    return rng.multinomial(G, np.full(G, 1.0 / G), size=draws).astype(np.float64)


def shares(cnt, weights):
    """Share of each outcome within each bin: estimate and 95% interval, shape [bins, outcomes, 3]."""
    def ratio(total):
        denom = total.sum(axis=-1, keepdims=True)
        return np.divide(total, denom, out=np.full(total.shape, np.nan), where=denom > 0)

    point = ratio(cnt.sum(axis=0))
    boot = np.einsum("dg,gbo->dbo", weights, cnt.astype(np.float64))
    boot = ratio(boot)
    lo, hi = np.nanpercentile(boot, [2.5, 97.5], axis=0)
    return np.stack([point, lo, hi], axis=2), cnt.sum(axis=(0, 2))


def pack(table, support, row_labels, col_labels):
    out = []
    for i, label in enumerate(row_labels):
        entry = {"bin": label, "decisions": int(support[i])}
        for j, col in enumerate(col_labels):
            est, lo, hi = table[i, j]
            entry[col] = None if np.isnan(est) else {"est": float(est), "lo": float(lo), "hi": float(hi)}
        out.append(entry)
    return out


def rate_table(c, G, weights, bin_, flag, labels, pool=None):
    """P(flag | bin) for a boolean per-decision flag; `pool` restricts the denominator."""
    outcome = flag.astype(np.int64)
    if pool is not None:
        outcome = np.where(pool, outcome, -1)
    cnt = counts(c["game"], len(labels), 2, bin_, outcome, G)
    table, support = shares(cnt, weights)
    return pack(table[:, 1:2], support, labels, ["rate"])


def categorical(c, G, weights, bin_, outcome, labels, outcome_labels):
    cnt = counts(c["game"], len(labels), len(outcome_labels), bin_, outcome, G)
    table, support = shares(cnt, weights)
    return pack(table, support, labels, outcome_labels)


def all_metrics(rows):
    c = derive(stack(rows))
    G = len(rows)
    w = bootstrap_weights(G)
    one = np.zeros(len(c["a"]), dtype=np.int64)
    phase = bin_of(c["frame"], PHASES)
    pattern = c["pv"]
    egap = np.where(c["has_enemy"], bin_of(c["eg"], ENEMY_BINS), len(ENEMY_BINS))
    egap_labels = [b[2] for b in ENEMY_BINS] + ["no enemy"]
    conf = bin_of(c["pa"], CONFIDENCE_BINS)
    near = c["has_enemy"] & (c["eg"] < 200)
    pattern_labels = ["no pattern", "pattern visible"]
    out = dict(games=G, decisions=int(len(c["a"])), bootstrap_draws=BOOTSTRAP_DRAWS)

    out["histogram_overall"] = categorical(c, G, w, one, c["a"], ["all decisions"], ACTIONS)
    out["histogram_by_phase"] = categorical(c, G, w, phase, c["a"], [p[2] for p in PHASES], ACTIONS)
    out["histogram_by_pattern"] = categorical(c, G, w, pattern, c["a"], pattern_labels, ACTIONS)
    out["histogram_by_enemy_gap"] = categorical(c, G, w, egap, c["a"], egap_labels, ACTIONS)

    out["confidence_overall"] = categorical(c, G, w, one, conf, ["all decisions"], [b[2] for b in CONFIDENCE_BINS])
    out["confidence_by_enemy_gap"] = categorical(c, G, w, egap, conf, egap_labels, [b[2] for b in CONFIDENCE_BINS])
    out["confidence_by_pattern"] = categorical(c, G, w, pattern, conf, pattern_labels, [b[2] for b in CONFIDENCE_BINS])
    out["entropy_mean_centinats_by_enemy_gap"] = [
        {"bin": label, "mean": mean_or_none(c["ent"][egap == i])}
        for i, label in enumerate(egap_labels)]

    moving = c["prev"] >= 0
    out["switch_overall"] = rate_table(c, G, w, np.where(moving, 0, -1), c["switch"], ["all decisions"])
    out["switch_by_enemy_gap"] = rate_table(c, G, w, np.where(moving, egap, -1), c["switch"], egap_labels)
    out["switch_by_pattern"] = rate_table(c, G, w, np.where(moving, pattern, -1), c["switch"], pattern_labels)
    out["reversal_by_enemy_gap"] = rate_table(
        c, G, w, np.where(c["moving_pair"], egap, -1), c["reversal"], egap_labels)

    resp = c["response"]
    out["response_by_enemy_gap"] = categorical(
        c, G, w, np.where(c["has_enemy"], egap, -1), resp, egap_labels, RESPONSES)
    out["response_by_enemy_gap_pattern"] = categorical(
        c, G, w, np.where(c["has_enemy"] & (c["eg"] < 200), pattern, -1), resp, pattern_labels, RESPONSES)

    # Pre-death view: decisions counted back from the fatal one, enemy deaths versus the baseline.
    enemy_death = np.isin(c["cause"], ENEMY_CAUSES)
    window = np.where(c["before"] < BEFORE, c["before"], -1)
    labels = [f"{k}" for k in range(BEFORE)]
    out["pre_death_response_enemy_deaths"] = categorical(
        c, G, w, np.where(enemy_death & c["has_enemy"], window, -1), resp, labels, RESPONSES)
    out["pre_death_response_other_deaths"] = categorical(
        c, G, w, np.where(~enemy_death & c["has_enemy"], window, -1), resp, labels, RESPONSES)
    out["pre_death_switch_enemy_deaths"] = rate_table(
        c, G, w, np.where(enemy_death & moving, window, -1), c["switch"], labels)
    out["pre_death_confidence_enemy_deaths"] = [
        {"bin": f"{k}", "mean_probability": mean_or_none(c["pa"][enemy_death & (c["before"] == k)], 1000)}
        for k in range(BEFORE)]
    out["pre_death_enemy_gap_enemy_deaths"] = [
        {"bin": f"{k}", "median_gap_px": mean_or_none(
            c["eg"][enemy_death & (c["before"] == k) & c["has_enemy"]], 10, np.median)}
        for k in range(BEFORE)]
    out["baseline_response_when_enemy_near"] = categorical(
        c, G, w, np.where(near, 0, -1), resp, ["enemy within 20 px"], RESPONSES)

    # Walls: does the action push into the wall the player is next to?
    zone = [("left", c["x"] < FIELD_MIN + WALL_ZONE), ("right", c["x"] > FIELD_MAX - WALL_ZONE),
            ("top", c["y"] < FIELD_MIN + WALL_ZONE), ("bottom", c["y"] > FIELD_MAX - WALL_ZONE)]
    inward = {"left": VECTOR[c["a"]][:, 0] < -0.1, "right": VECTOR[c["a"]][:, 0] > 0.1,
              "top": VECTOR[c["a"]][:, 1] < -0.1, "bottom": VECTOR[c["a"]][:, 1] > 0.1}
    wall_rows = []
    for name, inside in zone:
        flag = inward[name]
        cnt = counts(c["game"], 1, 2, np.where(inside, 0, -1), flag.astype(np.int64), G)
        table, support = shares(cnt, w)
        wall_rows += pack(table[:, 1:2], support, [name], ["into_wall"])
    out["into_wall_within_10px"] = wall_rows
    # Reference: the same flag for the whole field, per wall.
    ref = {}
    for name in inward:
        ref[name] = float(inward[name].mean())
    out["into_wall_anywhere"] = ref

    # Position-specific drift: mean heading over the whole run (net lean).
    out["mean_heading"] = dict(
        dx=float(VECTOR[c["a"]][:, 0].mean()), dy=float(VECTOR[c["a"]][:, 1].mean()))
    return out


def load_rows(path: Path):
    data = json.loads(path.read_text())
    if not data.get("decisions"):
        raise SystemExit(f"{path} has no per-decision columns (run death_trace_eval.py with --decisions)")
    rows = data["rows"]
    # Normalise the cause to a string so the analysis does not depend on the saved encoding.
    for r in rows:
        r["death_cause"] = str(r["death_cause"]).lower()
    return data, rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--group", type=Path, required=True, help="group file written with --decisions")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    if args.out.exists():
        raise SystemExit(f"refusing to overwrite {args.out}")
    data, rows = load_rows(args.group)
    result = dict(schema="death_trace_actions_v1", source=args.group.name, mode=data["mode"],
                  action_repeat=data["action_repeat"], checkpoint_sha256=data["checkpoint_sha256"],
                  actions=ACTIONS, metrics=all_metrics(rows))
    args.out.write_text(json.dumps(result, separators=(",", ":"), allow_nan=False))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
