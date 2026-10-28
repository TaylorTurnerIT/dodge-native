"""Successor of frozen expanded_eval.py; sampled full-run terminal evaluation.

Production calls are reachable only through evaluator_cli and independent parent
registration. Summary/comparison functions accept synthetic rows without imports.
"""
from __future__ import annotations
import math
from pathlib import Path
import statistics
import contracts as c

DEATH_CAUSES = ("normal_enemy", "kamikaze_enemy", "kamikaze_explosion",
                "static_pattern_rect", "moving_pattern_rect", "unknown", "unavailable")
MILESTONES = tuple(range(1000,18001,1000))
POLICY_IDS = tuple(f"replica-{replica}-{arm}" for replica in range(1,4) for arm in c.ARMS) + ("parent324",)

class ValidationError(ValueError):
    pass


def _require(ok: bool, message: str) -> None:
    if not ok:
        raise ValidationError(message)

def _validate_rows(rows: list[dict], seeds: list[int], *, cap=18000) -> list[dict]:
    _require(type(rows) is list and type(seeds) is list and len(seeds) > 0 and len(seeds) % 4 == 0
             and len(rows) == len(seeds), "evaluation row count must be positive, divisible by four, and match manifest")
    _require([row.get("seed") for row in rows] == seeds, "rows missing, reordered, duplicated, or outside manifest")
    for index, row in enumerate(rows):
        _require(type(row) is dict, "row must be an object")
        for key in ("episode_index", "seed", "score_raw_fixed", "score_delta_sum_raw_fixed",
                    "alive_frames", "gameplay_frames", "startup_frames"):
            _require(type(row.get(key)) is int and row[key] >= 0, f"{key} must be a nonnegative integer")
        _require(row["episode_index"] == index and row["startup_frames"] == 13, "row identity/startup differs")
        _require(row["score_delta_sum_raw_fixed"] == row["score_raw_fixed"], "fixed score accumulation differs")
        _require(type(row.get("terminated")) is bool and type(row.get("truncated")) is bool
                 and row["terminated"] != row["truncated"], "episode boundary flags invalid")
        _require(row["alive_frames"] <= row["gameplay_frames"] <= cap, "raw frame bound exceeded")
        if row["terminated"]:
            _require(row["alive_frames"] + 1 == row["gameplay_frames"], "fatal-frame conservation differs")
            cause = row.get("death_cause")
            _require(cause in DEATH_CAUSES, "terminated row cause missing/invalid")
            if cause == "unavailable":
                _require(row.get("fatal_gameplay_frame") is None and row.get("death_observed_lethal_contacts") is None,
                         "unavailable telemetry cannot infer fatal contacts")
            else:
                contacts = row.get("death_observed_lethal_contacts")
                _require(row.get("fatal_gameplay_frame") == row["gameplay_frames"]
                         and type(contacts) is dict and set(contacts) == set(DEATH_CAUSES[:-1])
                         and all(type(v) is int and v >= 0 for v in contacts.values())
                         and (cause == "unknown" or contacts[cause] >= 1), "native death telemetry differs")
        else:
            _require(row["gameplay_frames"] == row["alive_frames"] == cap
                     and row.get("death_cause") is None and row.get("fatal_gameplay_frame") is None
                     and row.get("death_observed_lethal_contacts") is None, "truncation telemetry/frame cap differs")
        _require(type(row.get("score")) in (int, float) and math.isfinite(row["score"])
                 and row["score"] == row["score_raw_fixed"] / 65536, "score identity differs")
        expected = row["score_raw_fixed"] / 65536 + row["alive_frames"] / 100 - 5 * row["terminated"]
        _require(type(row.get("objective_return")) in (int, float) and math.isfinite(row["objective_return"])
                 and math.isclose(row["objective_return"], expected, rel_tol=0, abs_tol=1e-9),
                 "raw objective identity differs")
    return rows

def _production_rows(model, env_factory, observations_keys, death_fields, seeds, excluded_ranges, guard,
                     *, batch_size=64, event_sink=None) -> list[dict]:
    import numpy as np
    import torch
    rows = []
    for offset in range(0, len(seeds), batch_size):
        chunk = seeds[offset:offset + batch_size]
        envs, obs, completed = {}, {}, {}
        for local, seed in enumerate(chunk):
            guard()
            env = env_factory(batch_size=1, action_repeat=4, difficulty=2, patterns_enabled=True,
                powerups_enabled=True, raw_frame_cap=18000, num_threads=1, chunk_size=1,
                render_pixels=False, auxiliary_targets=False, seeds_by_slot=[[seed]],
                excluded_seed_ranges=excluded_ranges)
            info = env.episode_info()[0]
            if event_sink is not None:
                event_sink(dict(kind="evaluation_constructor",episode_index=offset+local,info=info))
            _require(info["seed"]["evaluation"] is True and info["seed"]["actual_seed"] == seed
                     and info["startup_frames"] == 13 and info["gameplay_frames"] == 0,
                     "D2 constructor seed/startup differs")
            envs[local] = env; obs[local] = env.observations()
        while envs:
            guard()
            active = sorted(envs)
            tensors = {name: torch.from_numpy(np.concatenate([obs[i][name] for i in active], axis=0))
                       .to(model._expanded_eval_device) for name in observations_keys}
            with torch.no_grad():
                output = model(*(tensors[name] for name in observations_keys))
            logits = output.logits
            _require(tuple(logits.shape) == (len(envs), 9) and bool(torch.isfinite(logits).all()),
                     "nonfinite or malformed D2 policy output")
            actions = torch.distributions.Categorical(logits=logits).sample().cpu().numpy()
            del tensors, output, logits
            for position, i in enumerate(active):
                guard()
                result = envs[i].step(np.array([actions[position]], dtype=np.int64)); info = result["info"][0]
                if event_sink is not None:
                    event_sink(dict(kind="evaluation_step",episode_index=offset+i,
                        elapsed_raw_frames=int(result["elapsed_raw_frames"][0]),info=info))
                terminated, truncated = bool(result["terminated"][0]), bool(result["truncated"][0])
                _require(info["seed"]["actual_seed"] == chunk[i] and not (terminated and truncated)
                         and info["bootstrap"] == (not terminated), "D2 seed/boundary differs")
                _require(info["score_raw_fixed"] == info["score_delta_sum_raw_fixed"], "fixed score identity differs")
                if terminated or truncated:
                    completed[i] = {"episode_index": offset + i, "seed": chunk[i],
                        "score_raw_fixed": info["score_raw_fixed"], "score": info["score_raw_fixed"] / 65536,
                        "alive_frames": info["alive_frames"], "gameplay_frames": info["gameplay_frames"],
                        "startup_frames": info["startup_frames"], "objective_return": info["objective_return"],
                        "score_delta_sum_raw_fixed": info["score_delta_sum_raw_fixed"],
                        "terminated": terminated, "truncated": truncated,
                        **death_fields(info, terminated, truncated)}
                    if event_sink is not None:
                        event_sink(dict(kind="evaluation_completed",row=completed[i]))
                    del envs[i], obs[i]
                else:
                    obs[i] = result["observations"]
            guard()
        rows.extend(completed[i] for i in range(len(chunk)))
    return rows


def validate_full_rows(rows,seeds):
    _require(type(seeds)is list and len(seeds)==1024 and len(set(seeds))==1024
             and all(type(seed)is int and 0<=seed<2**32 for seed in seeds),'exact 1024 unique seed rows required')
    return _validate_rows(rows,seeds)


def summarize(rows,seeds):
    rows=validate_full_rows(rows,seeds)
    ordered=sorted(row['alive_frames'] for row in rows)
    deaths={cause:sum(row['terminated'] and row['death_cause']==cause for row in rows) for cause in DEATH_CAUSES}
    caps=sum(row['truncated'] for row in rows)
    _require(sum(deaths.values())+caps==1024,'death/cap conservation differs')
    return dict(complete=True,episodes=1024,missing_rows=0,invalid_rows=0,
        performance=dict(Worst=ordered[0],Q1=sum(ordered[:256])/256,Mean=sum(ordered)/1024,
                         Q4=sum(ordered[768:])/256,Best=ordered[-1]),
        milestones={str(h):dict(numerator=sum(row['alive_frames']>=h for row in rows),denominator=1024) for h in MILESTONES},
        death_causes=deaths,caps=caps)


def incomplete_accounting(rows,seeds):
    """Diagnostics for partial/invalid outputs; never emit a complete comparison."""
    valid={};invalid=duplicates=0
    for row in rows:
        try:
            index=row['episode_index']
            _require(type(index)is int and 0<=index<1024 and row['seed']==seeds[index],'row identity invalid')
            # The frozen validator requires quarter-compatible batches; validate
            # one row in a four-row synthetic-independent identity remapping.
            sample=[dict(row,episode_index=i) for i in range(4)]
            _validate_rows(sample,[row['seed']]*4)
            if index in valid:duplicates+=1
            else:valid[index]=row
        except (ValueError,KeyError,TypeError):invalid+=1
    deaths={cause:sum(row['terminated'] and row['death_cause']==cause for row in valid.values()) for cause in DEATH_CAUSES}
    caps=sum(row['truncated'] for row in valid.values())
    _require(sum(deaths.values())+caps==len(valid),'partial outcome conservation differs')
    return dict(complete=False,valid_rows=len(valid),missing_rows=1024-len(valid),invalid_rows=invalid,
                duplicate_rows=duplicates,death_causes=deaths,caps=caps)


def compare(policy_rows,seeds):
    _require(type(policy_rows)is dict and set(policy_rows)==set(POLICY_IDS),'incomplete pair or shared parent; seven endpoints required')
    summaries={name:summarize(rows,seeds) for name,rows in policy_rows.items()}
    parent=policy_rows['parent324']; pairs=[]
    for replica in range(1,4):
        control,curriculum=(f'replica-{replica}-{arm}' for arm in c.ARMS)
        comparisons={}
        for label,left,right in [('curriculum_minus_control',curriculum,control),
                                 ('control_minus_parent',control,'parent324'),
                                 ('curriculum_minus_parent',curriculum,'parent324')]:
            a,b=policy_rows[left],policy_rows[right]
            metrics={key:summaries[left]['performance'][key]-summaries[right]['performance'][key]
                     for key in ('Worst','Q1','Mean','Q4','Best')}
            milestone_differences={str(h):summaries[left]['milestones'][str(h)]['numerator']-summaries[right]['milestones'][str(h)]['numerator'] for h in MILESTONES}
            comparisons[label]=dict(metric_differences=metrics,milestone_numerator_differences=milestone_differences,
                per_seed=[dict(seed=seed,alive_frames=a[i]['alive_frames']-b[i]['alive_frames'],
                    milestones={str(h):int(a[i]['alive_frames']>=h)-int(b[i]['alive_frames']>=h) for h in MILESTONES})
                    for i,seed in enumerate(seeds)])
        pairs.append(dict(replica=replica,comparisons=comparisons))
    across={}
    for label in pairs[0]['comparisons']:
        across[label]={}
        fields={**pairs[0]['comparisons'][label]['metric_differences'],
                **{'milestone_'+h:v for h,v in pairs[0]['comparisons'][label]['milestone_numerator_differences'].items()}}
        for metric in fields:
            values=[pair['comparisons'][label]['milestone_numerator_differences'][metric.removeprefix('milestone_')]
                    if metric.startswith('milestone_') else pair['comparisons'][label]['metric_differences'][metric] for pair in pairs]
            across[label][metric]=dict(values=values,mean=statistics.mean(values),min=min(values),max=max(values),sample_stddev=statistics.stdev(values))
    return dict(schema='progressive1000_terminal_paired_comparison_v1',complete=True,planned_episodes=7168,
        policies=summaries,paired_replicas=pairs,across_three_descriptive=across,parent_evaluations=1,
        parent_independent_samples=1,automatic_selection=False,promoted=False,
        interpretation='descriptive three-pair pilot; shared parent baseline; no method superiority or acceptance claim')


def evaluate_full_run(model, *, registration, endpoint, check_guard, event_sink=None):
    """Curriculum hook for the existing trusted parent evaluator/launch path.

    The caller owns its registered endpoint load, launch marker and supervision.
    This hook adds no loader, launcher, probe, or candidate selection. It reuses
    the frozen full-run loop and row audit, with the new design's sampled actions.
    """
    import inspect
    import random
    import sys
    reg=registration
    _require(callable(check_guard),'existing parent resource/lease guard required')
    _require(reg.get('study_id')==c.STUDY and reg.get('status')=='parent_registered'
             and reg.get('cohort_state')=='reserved_parent_approved'
             and reg.get('history_state')=='freshness_parent_approved'
             and reg.get('reservation_state')=='parent_reserved','parent evaluation registration/cohort gates pending')
    _require(reg.get('action_mode')=='sampled_categorical' and reg.get('cutoff_enabled') is False
             and reg.get('normal_start') is True and reg.get('row_count')==1024,'full-run semantics differ')
    _require(reg.get('seeds')==list(range(0xD3000000,0xD3000400)),'new shared cohort differs')
    _require(endpoint.get('id') in POLICY_IDS and
             (endpoint['id']=='parent324' or endpoint.get('global_update')==60),'only fixed terminal60 and shared parent allowed')
    _require(reg.get('backend') in {'cpu','mps'} and type(reg.get('evaluation_rng_seed'))is int
             and 0<reg['evaluation_rng_seed']<2**63,'registered sampling stream/backend missing')
    c.validate_union(reg['exclusion_union'])
    c.verify_manifest(c.HERE/'source-manifest.json',reg['source_manifest_sha256'],c.HERE)
    runtime=c.verify_manifest(c.HERE/'runtime-manifest.json',reg['runtime_manifest_sha256'],c.HERE/'runtime',exact=True)
    _require(Path(inspect.getfile(type(model))).resolve()==c.HERE/'runtime/dodge_rl/models/teacher.py','shared model origin differs')
    for name,module in tuple(sys.modules.items()):
        if name=='dodge_rl' or name.startswith('dodge_rl.'):
            path=Path(module.__file__).resolve()
            _require(path.is_relative_to(c.HERE/'runtime') and
                     c.sha(path)==runtime['files'].get(str(path.relative_to(c.HERE/'runtime'))),'loaded evaluation module/native pin differs')
    import numpy as np
    import torch
    from dodge_rl import VecDodgeEnv
    from dodge_rl.checkpoints import capture_rng, restore_rng
    from death_telemetry import death_fields
    from fingerprints import fingerprint
    from successor_identity import NEURAL_INPUTS
    _require(dict(python=sys.version.split()[0],numpy=str(np.__version__),torch=str(torch.__version__))==reg['runtime_versions'],
             'evaluation dependencies differ')
    _require(all(p.device.type==reg['backend'] for p in model.parameters()),'evaluation device differs')
    check_guard()
    rng=capture_rng(reg['backend']);before=fingerprint(model.state_dict())
    modes=[(module,module.training) for module in model.modules()]
    had_device=hasattr(model,'_expanded_eval_device');old_device=getattr(model,'_expanded_eval_device',None)
    try:
        model.eval();model._expanded_eval_device=reg['backend']
        random.seed(reg['evaluation_rng_seed']);np.random.seed(reg['evaluation_rng_seed']%(2**32))
        torch.manual_seed(reg['evaluation_rng_seed'])
        if reg['backend']=='mps':torch.mps.manual_seed(reg['evaluation_rng_seed'])
        # Remove only the shared evaluation cohort from the training union.
        excluded=[]
        for low,high in reg['exclusion_union']:
            if low<0xD3000000:excluded.append((low,min(high,0xD3000000-1)))
            if high>0xD30003FF:excluded.append((max(low,0xD3000400),high))
        rows=_production_rows(model,VecDodgeEnv,NEURAL_INPUTS,death_fields,reg['seeds'],excluded,
                              check_guard,batch_size=64,event_sink=event_sink)
        result=summarize(rows,reg['seeds'])
        _require(fingerprint(model.state_dict())==before,'evaluation changed model')
        check_guard()
        return dict(endpoint=endpoint,summary=result,rows=rows,backend=reg['backend'],
                    action_mode='sampled_categorical',normal_start=True,cutoff_enabled=False,
                    runtime_manifest_sha256=reg['runtime_manifest_sha256'],automatic_selection=False,promoted=False)
    finally:
        restore_rng(rng,reg['backend'])
        for module,mode in modes:module.training=mode
        if had_device:model._expanded_eval_device=old_device
        else:del model._expanded_eval_device
        _require(fingerprint(capture_rng(reg['backend']))==fingerprint(rng),'evaluation failed to restore caller RNG')
