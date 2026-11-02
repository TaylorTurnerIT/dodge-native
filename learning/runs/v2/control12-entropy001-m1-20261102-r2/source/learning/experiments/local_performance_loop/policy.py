"""Practical development selection. No significance or replication gate."""
import math


def summarize(rows):
    v=sorted(r['alive_frames'] for r in rows);n=len(v)
    if not n or n%4:raise ValueError('Whole quartiles required')
    return dict(games=n,Mean=sum(v)/n,Q1=sum(v[:n//4])/(n//4),
        early_deaths=sum(r['terminated'] and r['alive_frames']<=600 for r in rows),
        mean_score=sum(r['score_raw_fixed']/65536 for r in rows)/n)


def advance(state,metrics,update,reference,settings):
    """All decisions use measured play, never EV/KL or elapsed time."""
    state=dict(state);history=list(state.get('history',[]));anchor=state.get('anchor')
    if anchor is None:
        anchor=dict(metrics);state['last_gain_update']=None
    elif (metrics['Q1']>anchor['Q1'] and metrics['Q1']>=anchor['Q1']*(1+settings['gain_fraction']) and metrics['Mean']>=anchor['Mean']*.98):
        anchor=dict(metrics);state['last_gain_update']=update
    history.append(dict(update=update,**metrics));state['history']=history;state['anchor']=anchor
    best=state.get('best',dict(update=0,**reference))
    selected=metrics['Q1']>best['Q1'] and metrics['Mean']>=reference['Mean']*.95 and metrics['early_deaths']<=reference['early_deaths']+math.ceil(.02*metrics['games'])
    if selected:best=dict(update=update,**metrics)
    state['best']=best
    severely_bad=len(history)>=3 and all(r['Q1']<.8*reference['Q1'] and r['Mean']<.9*reference['Mean'] for r in history[-3:])
    stalled=state['last_gain_update'] is None or update-state['last_gain_update']>=settings['patience_checks']*settings['segment_updates']
    competitive=metrics['Q1']>=reference['Q1']*.95 and metrics['Mean']>=reference['Mean']*.95
    recovery=metrics['Q1']>=history[0]['Q1']*1.10 and metrics['Q1']>=reference['Q1']*.85 and metrics['Mean']>=reference['Mean']*.90
    reason=None
    if update>=settings['initial_updates'] and severely_bad:reason='persistently_uncompetitive_play'
    elif update>=settings['initial_updates'] and stalled:reason='three_checks_without_meaningful_play_gain'
    elif update>=settings['initial_updates'] and not (competitive or recovery):reason='not_competitive_or_recovering'
    elif len(history)>=settings['max_checks']:reason='bounded_performance_progress_exhausted'
    return state,dict(update=update,selected_as_best=selected,best_update=best['update'],
        continue_training=reason is None,stop_reason=reason,competitive=competitive,strong_recovery=recovery,
        last_meaningful_gain_update=state['last_gain_update'])
