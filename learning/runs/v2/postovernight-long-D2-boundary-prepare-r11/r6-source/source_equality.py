"""Byte equality of protected blocks, with complete review diffs."""
from pathlib import Path
import ast
import difflib
import hashlib
H=Path(__file__).resolve().parent


def blocks(path):
    text=path.read_text();lines=text.splitlines(True)
    return {n.name:''.join(lines[n.lineno-1:n.end_lineno]) for n in ast.parse(text).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}


def body(path):
    text=path.read_text();lines=text.splitlines(True)
    node=next(n for n in ast.parse(text).body if isinstance(n,ast.FunctionDef) and n.name=='worker')
    node=next(n for n in node.body if isinstance(n,ast.With)).body[0]
    return ''.join(lines[node.body[0].lineno-1:node.body[-1].end_lineno])


def check(output):
    import long_d2 as c
    protected=('Learner','Schedule','run_schedule','environment_kwargs','counter_report','compare_control',
               'tree_fingerprint','assert_equal_tree','validate_long_config','expected_lease','assert_lease',
               'check_module_origins','outcome_fields','result_code')
    current=blocks(H/'long_d2.py');result={}
    for label in ('postovernight-long-D2-guard-prepare-r1','postovernight-long-D2-prepare-r4'):
        base=H.parent/label;old=blocks(base/'long_d2.py')
        result[label]=dict(protected={k:current[k]==old[k] for k in protected},worker_ML_try_byte_equal=body(H/'long_d2.py')==body(base/'long_d2.py'),
                           changed_blocks=sorted(k for k in old if old[k]!=current.get(k)),added_blocks=sorted(set(current)-set(old)))
        assert all(result[label]['protected'].values()) and result[label]['worker_ML_try_byte_equal'],result[label]
        for name in ('long_d2.py','long_d2_executor.py','lifecycle.py','processes.py'):
            (output/(label+'-'+name+'.diff')).write_text(''.join(difflib.unified_diff((base/name).read_text().splitlines(True),(H/name).read_text().splitlines(True),fromfile=label+'/'+name,tofile='boundary-r1/'+name)))
    frozen=H.parent/'postovernight-long-D2-boundary-prepare-r3'
    current=blocks(H/'long_d2.py');old=blocks(frozen/'long_d2.py')
    result['r3']=dict(protected={k:current[k]==old[k] for k in protected},
                      worker_ML_try_byte_equal=body(H/'long_d2.py')==body(frozen/'long_d2.py'))
    assert all(result['r3']['protected'].values()) and result['r3']['worker_ML_try_byte_equal']
    p=c.read_json(c.ORIGINAL_ROOT/'learning/runs/v2-orchestration/postovernight-long-D2-r2-protocol-r4.json')
    pins={str(c.ORIGINAL_ROOT/k):v for k,v in p['base_identity']['sources'].items()}
    c.verify_files(pins)
    assert len(pins)==75
    assert (H/'processes.py').read_bytes()==(frozen/'processes.py').read_bytes()
    assert c.sha(c.ORIGINAL_ROOT/p['config_path'])==c.CONFIG_SHA256
    result.update(legacy75_verified=pins,process_ownership_helper_equal=True,config_exact=True,
                  fixed_5s_integrity_predicates=False,periodic_verifier_threads=False,
                  protocol_used='historical r4 for source identity only; no r5 registration')
    c.save(output/'source-equality.json',result)
    return result
