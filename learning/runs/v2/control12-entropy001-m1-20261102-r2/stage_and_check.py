"""Extract the hash-bound DODGE-075 packet and run read-only host gates."""
from pathlib import Path, PurePosixPath
import argparse, hashlib, json, os, sys, tarfile
from datetime import datetime
from zoneinfo import ZoneInfo

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()

def verify_artifacts(contract, archive_path, script_path):
    archive_spec=contract['archive']; script_spec=contract['script']
    archive=Path(archive_path); script=Path(script_path)
    if archive.name != archive_spec['filename']:
        raise ValueError('archive filename mismatch')
    if archive.stat().st_size != archive_spec['bytes'] or sha(archive) != archive_spec['sha256']:
        raise ValueError('archive size/hash mismatch')
    if script.name != script_spec['filename']:
        raise ValueError('stale stage script filename')
    if script.stat().st_size != script_spec['bytes'] or sha(script) != script_spec['sha256']:
        raise ValueError('stale stage script readback')

def save_new(path, value):
    path=Path(path)
    with path.open('x') as stream:
        json.dump(value,stream,indent=2,sort_keys=True);stream.write('\n');stream.flush();os.fsync(stream.fileno())
    fd=os.open(path.parent,os.O_RDONLY)
    try: os.fsync(fd)
    finally: os.close(fd)

def extract_into_empty_root(archive, root, expected_files):
    root=Path(root)
    if not root.is_dir() or any(root.iterdir()):
        raise ValueError('extraction root is not the fresh empty directory created by this invocation')
    with tarfile.open(archive,'r:gz') as bundle:
        members=bundle.getmembers();names=[]
        for member in members:
            relative=PurePosixPath(member.name)
            if relative.is_absolute() or '..' in relative.parts or not member.isfile():
                raise ValueError('unsafe archive member')
            names.append(relative.as_posix())
        if sorted(names) != sorted(expected_files):
            raise ValueError('archive member set differs from contract')
        for member in members:
            target=root.joinpath(*PurePosixPath(member.name).parts)
            target.parent.mkdir(parents=True,exist_ok=True)
            with target.open('xb') as stream:
                stream.write(bundle.extractfile(member).read());stream.flush();os.fsync(stream.fileno())
    return len(members)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--contract',required=True);parser.add_argument('--archive',required=True);parser.add_argument('--run-root',required=True)
    args=parser.parse_args(); contract_path=Path(args.contract); contract=json.loads(contract_path.read_text())
    root=Path(args.run_root); owns_root=False
    try:
        verify_artifacts(contract,args.archive,Path(__file__).resolve())
        if root.exists() or root.is_symlink():
            raise ValueError('075 destination exists; preserve first state, never retry')
        with tarfile.open(args.archive,'r:gz') as bundle:
            embedded=json.load(bundle.extractfile('config.json'))
        if str(root) != contract['run_root'] or str(root) != embedded['run_dir']:
            raise ValueError('extraction root differs from registered run_dir')
        root.mkdir(parents=True);owns_root=True
        extracted=extract_into_empty_root(args.archive,root,contract['payload_files'])
        sys.path.insert(0,str(root))
        from directory_contract import create_layout,check_layout,check_source_commit,check_ledger
        create_layout(root);directories=check_layout(root)
        sys.path.insert(0,str(root/'source/learning/experiments/local_performance_loop/fresh'))
        import common as c
        from ssh_route_guard import verify_preflight
        config=root/'config.json';reg=c.load_registration(config,contract['registration_sha256'])
        review_sha=c.review_gate(reg,contract['registration_sha256']);c.verify_environment(reg)
        source_commit=check_source_commit(root,dict(registration_sha256=contract['registration_sha256'],host_driver_sha256=c.sha(root/'host_driver.py'),source_manifest_sha256=c.sha(root/'source-manifest.json'),review_sha256=review_sha))
        ledger=check_ledger(reg['state_path'],reg['machine']);route=verify_preflight(reg['launch_context'])
        state=c.read(reg['state_path']);ledger_hash=c.sha(reg['state_path']);c.machine_state(reg,state)
        c.need(state['active_long_campaign'] is None and state['active_inference_diagnostic'] is None,'M1 busy; never clear a lease')
        c.need(not any(name=='torch' or name=='dodge_rl' or name.startswith('dodge_rl.') for name in sys.modules),'model/native import occurred during staging')
        c.need(c.sha(reg['state_path'])==ledger_hash,'read-only stage gate changed machine ledger')
        receipt={'status':'staged_full_packet_readonly_gates_passed_no_runtime','record':'DODGE-075','run_id':reg['run_id'],'registration_sha256':contract['registration_sha256'],'archive_sha256':contract['archive']['sha256'],'stage_script_sha256':contract['script']['sha256'],'files_extracted':extracted,'source_pins_checked':len(reg['source_pins']),'input_pins_checked':len(reg['input_pins']),'runtime_members_checked':len(reg['runtime_members']),'directory_contract':directories,'source_commit':source_commit,'read_only_ledger':ledger,'actual_host_route':route,'scope':'read-only staging; no host driver invoked by this script','recorded_at_Central':datetime.now(ZoneInfo('America/Chicago')).isoformat()}
        save_new(root/'staging-preflight.json',receipt);print(json.dumps(receipt,sort_keys=True))
    except BaseException as error:
        if owns_root and root.exists() and not (root/'stage-first-failure.json').exists():
            save_new(root/'stage-first-failure.json',{'status':'first_stage_failure_preserved_no_runtime','error_class':type(error).__name__,'reason':str(error)})
        raise

if __name__=='__main__': main()
