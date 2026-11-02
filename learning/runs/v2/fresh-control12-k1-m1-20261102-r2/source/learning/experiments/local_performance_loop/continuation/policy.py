"""Prospective mean-oriented development exploitation with tail guardrails."""
import importlib.util
import math
from pathlib import Path
spec = importlib.util.spec_from_file_location('_accepted_loop_policy', Path(__file__).resolve().parents[1]/'policy.py')
legacy = importlib.util.module_from_spec(spec); spec.loader.exec_module(legacy)
summarize = legacy.summarize


def guardrails(metrics, reference, settings):
    return (metrics['Q1'] >= settings['minimum_Q1_fraction'] * reference['Q1']
            and metrics['early_deaths'] <= reference['early_deaths'] + math.ceil(settings['early_death_allowance_fraction'] * metrics['games']))


def advance(state, metrics, update, reference, settings):
    state = dict(state)
    history = list(state.get('history', []))
    best = state.get('best', dict(update=0, **reference))
    anchor = state.get('anchor', dict(reference))
    last_gain = state.get('last_gain_update', 0)
    safe = guardrails(metrics, reference, settings)
    meaningful = safe and metrics['Mean'] >= anchor['Mean'] * (1 + settings['gain_fraction']) and metrics['Mean'] > anchor['Mean']
    if meaningful:
        anchor = dict(metrics); last_gain = update
    selected = safe and metrics['Mean'] > best['Mean']
    if selected:
        best = dict(update=update, **metrics)
    history.append(dict(update=update, **metrics))
    severe = len(history) >= 3 and all(r['Mean'] < .90 * reference['Mean']
        or r['Q1'] < .80 * reference['Q1']
        or r['early_deaths'] > reference['early_deaths'] + math.ceil(.05 * r['games']) for r in history[-3:])
    stalled = update - last_gain >= settings['patience_checks'] * settings['segment_updates']
    competitive = safe and metrics['Mean'] >= .95 * best['Mean']
    recovery = (safe and metrics['Mean'] >= 1.10 * history[0]['Mean'] and metrics['Mean'] >= .95 * reference['Mean'])
    reason = None
    if update >= settings['initial_updates'] and severe: reason = 'persistently_uncompetitive_play'
    elif update >= settings['initial_updates'] and stalled: reason = 'three_checks_without_2percent_mean_gain'
    elif update >= settings['initial_updates'] and not (competitive or recovery): reason = 'not_competitive_or_recovering_with_guardrails'
    elif len(history) >= settings['max_checks']: reason = 'bounded_mean_progress_exhausted'
    state.update(history=history,best=best,anchor=anchor,last_gain_update=last_gain)
    return state,dict(update=update,selected_as_best=selected,best_update=best['update'],guardrails_passed=safe,
        continue_training=reason is None,stop_reason=reason,competitive=competitive,strong_recovery=recovery,
        last_meaningful_gain_update=last_gain,meaningful_mean_gain=meaningful)
