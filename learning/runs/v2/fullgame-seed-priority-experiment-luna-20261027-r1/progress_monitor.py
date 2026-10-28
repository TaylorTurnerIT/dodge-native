"""Side-effect-free progress estimates and exact-content lease parsing cache."""
import json
from pathlib import Path
import time


class LeaseReader:
    """Read ledger bytes on every guard; reparse only when bytes change.

    Changed or malformed bytes fail immediately. No mtime shortcut, stale lease
    fallback, write, or relaxed polling interval is used.
    """
    def __init__(self, path, parser):
        self.path, self.parser = Path(path), parser
        self.raw = self.value = None

    def read(self):
        raw = self.path.read_bytes()
        if raw != self.raw:
            value = self.parser(raw)
            self.raw, self.value = raw, value
        return self.value


def parse_lease(raw):
    def unique(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate JSON field: ' + key)
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value))).get('active_long_campaign')


class ProgressMonitor:
    def __init__(self, started, work_seconds, total_updates=60, window=5, clock=time.monotonic):
        self.started, self.work_seconds = started, work_seconds
        self.total_updates, self.window, self.clock = total_updates, window, clock
        self.completed = 0
        self.phase = 'startup'
        self.phase_started = clock()
        self.phase_seconds = {}
        self.durations = []
        self.update_started = self.phase_started
        self.last_payload = None

    def enter(self, phase):
        now = self.clock()
        self.phase_seconds[self.phase] = self.phase_seconds.get(self.phase, 0.0) + now-self.phase_started
        self.phase, self.phase_started = phase, now

    def begin_update(self, update):
        if update != self.completed+1:
            raise ValueError('progress update sequence differs')
        self.update_started = self.clock()
        self.phase_seconds = {}
        self.phase, self.phase_started = 'collection', self.update_started

    def finish_update(self, update):
        if update != self.completed+1:
            raise ValueError('completed progress sequence differs')
        self.enter('between_updates')
        now = self.clock()
        self.durations.append(now-self.update_started)
        self.completed = update
        return self.payload(now)

    def payload(self, now=None):
        now = self.clock() if now is None else now
        elapsed = now-self.started
        remaining = self.total_updates-self.completed
        recent = self.durations[-self.window:]
        recent_mean = sum(recent)/len(recent) if recent else None
        all_mean = sum(self.durations)/len(self.durations) if self.durations else None
        # Use the slower observed mean. Include time already spent in an active
        # update instead of pretending no progress occurred since last boundary.
        mean = max(recent_mean, all_mean) if recent else None
        in_update = self.phase not in ('startup', 'between_updates')
        active_seconds = now-self.update_started if in_update else 0.0
        outstanding = max(0, mean*remaining-min(mean, active_seconds)) if mean is not None else None
        projected = elapsed+outstanding if outstanding is not None else None
        phases = dict(self.phase_seconds)
        phases[self.phase] = phases.get(self.phase, 0.0)+now-self.phase_started
        return dict(schema='progressive1000_progress_v1', completed_updates=self.completed,
            total_updates=self.total_updates, phase=self.phase, elapsed_seconds=elapsed,
            recent_seconds_per_update=recent_mean, average_seconds_per_update=all_mean,
            projected_total_seconds=projected, work_limit_seconds=self.work_seconds,
            projected_work_deadline_miss=projected is not None and projected > self.work_seconds,
            phase_seconds=phases,
            estimate_scope='Observed means; warning only. Does not change learning, limits, or launch authorization.')
