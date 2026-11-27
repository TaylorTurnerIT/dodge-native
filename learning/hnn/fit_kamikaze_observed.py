"""Fit a distance threshold and speed step from observer-only probe records."""
import collections
import sys

path = sys.argv[1]
groups = collections.defaultdict(dict)
episode = 0
for line in open(path):
    fields = line.split()
    if not fields:
        continue
    if fields[0] == "probe-reset":
        episode += 1
    if fields[0] != "probe" or len(fields) != 7:
        continue
    _, frame, ident, age, distance, rate, global_rate = fields
    if float(global_rate) > 0:
        groups[episode, ident][int(frame)] = (int(age), float(distance), float(rate) / float(global_rate))
traces = []
for track in groups.values():
    rows = sorted(track.items())
    if len(rows) >= 5 and rows[0][1][0] <= 12:
        traces.append([(frame, distance, rate) for frame, (_, distance, rate) in rows])
best = []
for radius in range(15, 36):
    for millistep in range(3, 26, 2):
        step = millistep / 1000
        loss = count = 0
        for track in traces:
            speed, previous = 1.0, track[0][0]
            for frame, distance, rate in track:
                speed = min(1.0, speed + (frame - previous) * step * (-1 if distance <= radius else 1))
                previous = frame
                if 0.1 < rate < 2.0 and distance < 50:
                    loss += min((speed - rate) ** 2, 0.25)
                    count += 1
        if count:
            best.append((loss / count, radius, step, count))
if not best:
    raise SystemExit("No usable tracks")
print("tracks", len(traces), "best", sorted(best)[:8])
