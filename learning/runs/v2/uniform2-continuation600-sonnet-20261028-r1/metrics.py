"""Evaluation summaries and the worst-quarter (Q1) selection rule; stdlib only."""
from __future__ import annotations

MILESTONES = (1000, 2000, 4000, 8000, 12000, 18000)
DEATH_CAUSES = ('normal_enemy', 'kamikaze_enemy', 'kamikaze_explosion', 'static_pattern_rect',
                'moving_pattern_rect', 'unknown', 'unavailable')
EPISODES = 1024
QUARTER = EPISODES//4


def summarize(rows):
    """Rows are already validated (1024 exact seeds, full normal-start episodes)."""
    if len(rows) != EPISODES:
        raise ValueError('1024 complete rows required')
    ordered = sorted(row['alive_frames'] for row in rows)
    deaths = {cause: sum(bool(row['terminated']) and row['death_cause'] == cause for row in rows) for cause in DEATH_CAUSES}
    caps = sum(bool(row['truncated']) for row in rows)
    if sum(deaths.values())+caps != EPISODES:
        raise ValueError('death/cap conservation differs')
    return dict(complete=True, episodes=EPISODES, missing_rows=0, invalid_rows=0,
        performance=dict(Worst=ordered[0], Q1=sum(ordered[:QUARTER])/QUARTER, Mean=sum(ordered)/EPISODES,
                         Q4=sum(ordered[-QUARTER:])/QUARTER, Best=ordered[-1]),
        milestones={str(h): dict(numerator=sum(row['alive_frames'] >= h for row in rows), denominator=EPISODES)
                    for h in MILESTONES},
        death_causes=deaths, caps=caps)


def rank_key(summary):
    performance = summary['performance']
    return (performance['Q1'], performance['Mean'])


class Selection:
    """Largest Q1, then largest Mean; an exact tie keeps the earlier checkpoint. Order is evaluation order."""
    def __init__(self):
        self.entries, self.best = [], None

    def add(self, global_update, summary, checkpoint_sha256):
        if self.entries and global_update <= self.entries[-1]['global_update']:
            raise ValueError('evaluations must arrive in increasing update order')
        entry = dict(global_update=global_update, checkpoint_sha256=checkpoint_sha256, Q1=summary['performance']['Q1'],
                     Mean=summary['performance']['Mean'])
        self.entries.append(entry)
        if self.best is None or (entry['Q1'], entry['Mean']) > (self.best['Q1'], self.best['Mean']):
            self.best = entry
        return dict(self.best)

    def report(self):
        trained = [e for e in self.entries if e['global_update'] > 0]
        best_trained = None
        for entry in trained:
            if best_trained is None or (entry['Q1'], entry['Mean']) > (best_trained['Q1'], best_trained['Mean']):
                best_trained = entry
        return dict(rule='largest Q1 (bottom-256 mean of 1024), then largest Mean, exact tie keeps the earlier checkpoint',
            candidates=list(self.entries), selected=self.best, best_trained_only=best_trained,
            selected_is_starting_model=bool(self.best and self.best['global_update'] == 0))
