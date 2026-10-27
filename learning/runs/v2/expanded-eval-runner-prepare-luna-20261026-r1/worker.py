"""Inert Layer A worker. Never imports torch/native modules until launched by parent."""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, os, sys, time
from pathlib import Path


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''): h.update(chunk)
    return h.hexdigest()


def run(registration_path: Path, evaluator_path: Path, output_path: Path, stage: str, candidate_update: int, cohort_name: str, guard_path: Path | None = None, deadline: float | None = None):
    reg = json.loads(registration_path.read_text())
    if reg.get('schema') != 'expanded_D2_evaluation_registration_v1' or reg.get('mode') != stage:
        raise RuntimeError('registration schema/mode mismatch')
    pin = reg.get('source', {})
    expected = pin.get('evaluator_sha256')
    if not expected or len(expected) != 64 or sha256(evaluator_path) != expected:
        raise RuntimeError('evaluator source pin absent or mismatch')
    # Check digest again after import to close path replacement window.
    spec = importlib.util.spec_from_file_location('_pinned_expanded_evaluator', evaluator_path)
    if spec is None or spec.loader is None: raise RuntimeError('cannot load pinned evaluator')
    module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module; spec.loader.exec_module(module)
    if sha256(evaluator_path) != expected: raise RuntimeError('evaluator source changed during import')
    evaluate = getattr(module, 'evaluate_registered', None)
    if not callable(evaluate): raise RuntimeError('evaluator canonical API missing')
    def check_guard():
        if deadline is not None and time.monotonic() >= deadline: raise RuntimeError('worker wall deadline reached')
        cancel=reg.get('cancel_path')
        if cancel and Path(cancel).exists(): raise RuntimeError('parent cancellation requested')
        if guard_path is not None and not guard_path.exists(): raise RuntimeError('parent guard lost')
        return True
    calls = [(candidate_update, cohort_name, output_path)]
    if stage == 'benchmark':
        calls = [(candidate_update, 'benchmark_dev64', output_path.with_name(output_path.stem + f'-repeat-{i}' + output_path.suffix)) for i in (1, 2)]
    elif stage == 'ranking':
        calls = [(int(k), 'ranking', output_path.with_name(output_path.stem + f'-candidate-{k}' + output_path.suffix)) for k in sorted(reg['candidates'], key=int)]
    elif stage == 'confirmation':
        record=reg.get('selection_record') or {}
        winner=record.get('winner_update')
        if not winner or winner == 348: raise RuntimeError('confirmation requires pinned non-348 winner')
        winner_cp=reg.get('candidates',{}).get(str(winner),{}).get('checkpoint_sha256')
        incumbent_cp=reg.get('candidates',{}).get('348',{}).get('checkpoint_sha256')
        if record.get('winner_checkpoint_sha256') != winner_cp or record.get('incumbent_checkpoint_sha256') != incumbent_cp:
            raise RuntimeError('confirmation selection checkpoint pins mismatch')
        calls = [(int(record['winner_update']), 'confirmation', output_path.with_name(output_path.stem + '-winner' + output_path.suffix)), (348, 'confirmation', output_path.with_name(output_path.stem + '-incumbent-348' + output_path.suffix))]
    results=[]
    for update, cohort, dest in calls:
        check_guard()
        result=evaluate(registration_path=str(registration_path), registration_sha256=sha256(registration_path), candidate_update=update, cohort_name=cohort, output_path=str(dest), check_guard=check_guard)
        if not isinstance(result,dict) or result.get('complete') is not True: raise RuntimeError('incomplete evaluator result; partial receipts preserved')
        dest.parent.mkdir(parents=True,exist_ok=True); tmp=dest.with_name(dest.name+'.partial'); tmp.write_text(json.dumps(result,sort_keys=True,separators=(',',':'))+'\n'); os.replace(tmp,dest)
        results.append(result)
    if stage == 'benchmark':
        a,b=results
        for key in ('candidate_update','cohort_name','cohort_sha256','checkpoint_sha256','episodes','rows','performance','death_causes','caps'):
            if a.get(key)!=b.get(key): raise RuntimeError(f'old-dev64 determinism mismatch at {key}')
    if stage == 'ranking':
        if len(results)!=6 or {r.get('candidate_update') for r in results}!={180,204,276,300,324,348}: raise RuntimeError('ranking incomplete candidate set')
        ranked=sorted(results,key=lambda r:(-r['performance']['mean'],r['candidate_update']))
        results={'schema':'expanded_D2_ranking_selection_v1','selection_only':True,'winner_update':ranked[0]['candidate_update'],'ordered_updates':[r['candidate_update'] for r in ranked],'candidate_results':results}
    else: results={'schema':'expanded_D2_stage_bundle_v1','stage':stage,'results':results}
    output_path.parent.mkdir(parents=True,exist_ok=True); tmp=output_path.with_name(output_path.name+'.partial'); tmp.write_text(json.dumps(results,sort_keys=True,separators=(',',':'))+'\n'); os.replace(tmp,output_path)
    return results

if __name__ == '__main__':
    p=argparse.ArgumentParser(); p.add_argument('--registration',type=Path,required=True); p.add_argument('--evaluator',type=Path,required=True); p.add_argument('--output',type=Path,required=True); p.add_argument('--stage',choices=['benchmark','ranking','confirmation'],required=True); p.add_argument('--candidate-update',type=int,required=True); p.add_argument('--cohort',required=True); p.add_argument('--guard',type=Path); p.add_argument('--deadline',type=float)
    a=p.parse_args(); run(a.registration,a.evaluator,a.output,a.stage,a.candidate_update,a.cohort,a.guard,a.deadline)
