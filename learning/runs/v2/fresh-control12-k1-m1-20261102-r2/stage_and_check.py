"""One private artifact staging/readback; no native/model import or lease."""
from pathlib import Path
import hashlib
import json
import os
import sys
import tarfile
from datetime import datetime
from zoneinfo import ZoneInfo

root=Path('/Users/taylor/Projects/dodge-native/learning/runs/v2/fresh-control12-k1-m1-20261102-r2')
archive=root/'stage-bundle.tar.gz'
expected='316146ec096b36b910b7648f617e3599394c7fc1c881c655ab75c38dd6f7b2fc'
digest=lambda path:hashlib.sha256(Path(path).read_bytes()).hexdigest()

def save(path,value):
    with path.open('x') as stream:
        json.dump(value,stream,indent=2,sort_keys=True);stream.write('\n');stream.flush();os.fsync(stream.fileno())
    descriptor=os.open(path.parent,os.O_RDONLY)
    try:os.fsync(descriptor)
    finally:os.close(descriptor)

try:
    if digest(archive)!=expected:raise ValueError('Private staging archive differs')
    count=0
    with tarfile.open(archive,'r:gz') as bundle:
        for member in bundle.getmembers():
            relative=Path(member.name)
            if relative.is_absolute() or '..' in relative.parts or not member.isfile():
                raise ValueError('Staging member path/type differs')
            target=root/relative;target.parent.mkdir(parents=True,exist_ok=True)
            with target.open('xb') as stream:
                stream.write(bundle.extractfile(member).read());stream.flush();os.fsync(stream.fileno())
            count+=1
    sys.path.insert(0,str(root))
    from directory_contract import create_layout,check_layout,check_source_commit,check_ledger
    create_layout(root)
    directories=check_layout(root)
    sys.path.insert(0,str(root/'source/learning/experiments/local_performance_loop/fresh'))
    import common as c
    sys.path.insert(1,str(root))
    from ssh_route_guard import verify_preflight
    config=root/'config.json'
    reg=c.load_registration(config,'f1b943135f7407cc476985473c245f957b6ccb592afe2865a1ffd65a05ef7ba1')
    review=c.review_gate(reg,c.sha(config));c.verify_environment(reg)
    source=check_source_commit(root,dict(registration_sha256=c.sha(config),host_driver_sha256=c.sha(root/'host_driver.py'),
        source_manifest_sha256=c.sha(root/'source-manifest.json'),review_sha256=review))
    ledger=check_ledger(reg['state_path'],reg['machine'])
    route=verify_preflight(reg['launch_context'])
    state=c.read(reg['state_path']);state_hash=c.sha(reg['state_path']);c.machine_state(reg,state)
    c.need(state['active_long_campaign'] is None and state['active_inference_diagnostic'] is None,
           'Per-M1 admission not free; never clear a lease')
    protected=c.protected_identities()
    c.need(not any(m=='torch' or m=='dodge_rl' or m.startswith('dodge_rl.') for m in sys.modules),
           'Staging imported a model/native module')
    c.need(not list((root/'empty-pycache').rglob('*')) and not list((root/'output').rglob('*.claimed')),
           'Prelaunch cache/claims differ')
    c.need(c.sha(reg['state_path'])==state_hash,'Read-only preparation changed ledger bytes')
    receipt=dict(status='staged_exact_source_venv_runtime_baseline_pins_host_context_checked_no_native_work',
        recorded_at_Central=datetime.now(ZoneInfo('America/Chicago')).isoformat(),
        registration_sha256=c.sha(config),review_sha256=review,host_driver_sha256=c.sha(root/'host_driver.py'),
        archive_sha256=expected,staged_files=count,source_pins_checked=len(reg['source_pins']),
        input_pins_checked=len(reg['input_pins']),runtime_members_checked=len(reg['runtime_members']),
        original_control12_sha256=c.sha(reg['warmstart']['path']),fallback420_sha256=c.sha(reg['checkpoint_path']),
        cached_baseline_episode_hashes={label:c.sha(v['episodes_path']) for label,v in reg['baseline_sources'].items()},
        machine=reg['machine'],route=route,interpreter=sys.executable,protected_process_identities=protected,
        directory_contract=directories,source_commit=source,preclaim_ledger=ledger,
        memory_pressure=c.subprocess.check_output(['/usr/bin/memory_pressure','-Q'],text=True).strip(),
        load_average=os.getloadavg(),
        ledger_path=reg['state_path'],ledger_sha256=state_hash,lease_operations=0,active_long_campaign=None,
        production_seed_lookups=0,checkpoint_loads=0,native_games=0,optimizer_steps=0,MPS_work=False,
        runtime_invocations=0,first_two_counted_training_updates='Pending inside ONE actual authorized invocation')
    save(root/'prelaunch-check.json',receipt)
    print(json.dumps(receipt,sort_keys=True),flush=True)
except BaseException as error:
    save(root/'prelaunch-first-failure.json',dict(status='first_prelaunch_failure_preserved_no_runtime_invocation',
        error_class=type(error).__name__,reason=str(error)))
    raise
