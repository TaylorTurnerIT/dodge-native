"""Exact source/AST boundaries; no learner/native execution."""
from pathlib import Path
import ast,difflib,json
import long_d2 as c
H=Path(__file__).resolve().parent;R=H.parent/'postovernight-long-D2-prepare-r4'

def blocks(path):
    text=path.read_text();lines=text.splitlines(True)
    return {n.name:''.join(lines[n.lineno-1:n.end_lineno]) for n in ast.parse(text).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}

def check():
    old,new=blocks(R/'long_d2.py'),blocks(H/'long_d2.py')
    changed={k for k in old if old[k]!=new.get(k)}
    allowed={'sha','Guard','worker_failure','worker','supervise_owned'}
    c.require(changed<=allowed,'Undeclared controller function change: '+repr(changed-allowed))
    added=set(new)-set(old)
    c.require(added=={'verification_component','primary_error','record_primary_failure'},'Unexpected helper function')
    protected=('Learner','Schedule','run_schedule','environment_kwargs','counter_report','compare_control','tree_fingerprint','assert_equal_tree',
        'validate_long_config','expected_lease','assert_lease','check_module_origins','outcome_fields','result_code')
    equal={k:old[k]==new[k] for k in protected};c.require(all(equal.values()),'Protected source drift')
    def worker_body(path):
        s=path.read_text();lines=s.splitlines(True);t=ast.parse(s)
        w=next(n for n in t.body if isinstance(n,ast.FunctionDef) and n.name=='worker')
        t=next(n for n in w.body if isinstance(n,ast.With)).body[0]
        return ''.join(lines[t.body[0].lineno-1:t.body[-1].end_lineno])
    bodyeq=worker_body(R/'long_d2.py')==worker_body(H/'long_d2.py');c.require(bodyeq,'Worker ML try changed')
    a,b=blocks(R/'long_d2_executor.py'),blocks(H/'long_d2_executor.py')
    executor_changes={k for k in a if a[k]!=b.get(k)}
    c.require(executor_changes<={'Execution','validate_artifacts'} and set(a)==set(b),'Unexpected executor change')
    helpers={k:c.sha(R/k)==c.sha(H/k) for k in ('lifecycle.py','processes.py')};c.require(all(helpers.values()),'Lifetime/process drift')
    p=c.registered_protocol(c.ORIGINAL_ROOT/c.PROTOCOL_REL)
    sourcepins={str(c.ORIGINAL_ROOT/k):v for k,v in p['base_identity']['sources'].items()};c.verify_files(sourcepins)
    config_equal=(c.ORIGINAL_ROOT/p['config_path']).read_bytes()==(c.ORIGINAL_ROOT/'learning/runs/v2-orchestration/postovernight-long-D2-r1-config.json').read_bytes()
    c.require(config_equal,'Controlled replication config differs')
    result=dict(protected_source_equal=equal,worker_ML_try_byte_equal=bodyeq,changed_controller_blocks=sorted(changed),added_controller_blocks=sorted(added),
        changed_executor_blocks=sorted(executor_changes),helper_byte_equal=helpers,legacy_original_sources_verified=len(sourcepins),legacy75_pins=sourcepins,
        config_r1_r2_byte_equal=config_equal,allowed_registration_constants=['PREPARE_REL','PROTOCOL_REL','PROTOCOL_SHA256'],new_timing_state='VERIFY_LOCAL',
        note='Function source and AST retained; complete diffs expose module-level changes for review')
    c.save(H/'source-equality.json',result)
    for name in ('long_d2.py','long_d2_executor.py'):
        with (H/(name+'.diff')).open('x') as f:f.writelines(difflib.unified_diff((R/name).read_text().splitlines(True),(H/name).read_text().splitlines(True),fromfile='R4/'+name,tofile='guard-r1/'+name))
    print(json.dumps(dict(protected=len(equal),legacy_sources=len(sourcepins),worker_ML_try_equal=bodyeq,changed=sorted(changed))))

if __name__=='__main__':check()
