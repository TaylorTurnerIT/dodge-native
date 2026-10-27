"""Final evidence inventory, JSON CLI checks and immutable handoff; stdlib only."""
from pathlib import Path
import json,os,subprocess,sys,time
import long_d2 as c
H=Path(__file__).resolve().parent

def main():
    unit=c.read_json(H/'attempts/units-05/unit-result.json')
    c.require(unit['successful'] and not unit['ML_imports'],'Final unit failure')
    reg=c.read_json(H/'registration.json');inventory=c.read_json(H/'expanded-inventory.json')
    stress=c.read_json(H/'attempts/stress-01/stress-result.json')
    matrix=c.read_json(H/'attempts/matrix-01-cases/summary.json')
    c.require(c.read_json(c.STATE_PATH).get('active_long_campaign') is None,'Unexpected active production lease')
    p=c.registered_protocol(c.ORIGINAL_ROOT/c.PROTOCOL_REL)
    c.require(not (c.ORIGINAL_ROOT/p['output']).exists(),'Campaign output exists')
    c.require(not (c.ORIGINAL_ROOT/Path(p['terminal_lifecycle']['acceptance_receipt']).parent).exists(),'Production execution directory exists')
    context=c.capsule_context(H/'capsule-final');c.verify_files(context[4])
    mirrors={k:c.sha(H/'capsule-final'/k)==v for k,v in p['base_identity']['sources'].items()}
    c.require(len(mirrors)==75 and all(mirrors.values()),'Legacy mirror drift')
    c.save(H/'legacy-mirror-equality.json',dict(count=75,exact=mirrors))
    sources={x.name:c.sha(x) for x in sorted(H.iterdir()) if x.is_file() and x.suffix in ('.py','.md','.txt')}
    c.save(H/'source-manifest.json',sources)
    c.require(sources=={Path(k).name:v for k,v in inventory['source_inventory'].items()},'Post-freeze source drift')
    result=dict(version='long_D2_guard_r2_preparation_result_v1',status='blocked_stress_requires_fresh_design' if stress['status']!='bounded_synthetic_pass' else 'prepared_for_fresh_frozen_parent_review',
        ready_for_campaign=False,ready_for_frozen_parent_review=True,stress_launch_blocker=stress['status']!='bounded_synthetic_pass',
        controller_sha256=c.sha(H/'long_d2.py'),executor_sha256=c.sha(H/'long_d2_executor.py'),identity_raw_sha256=reg['identity_sha256'],
        identity_semantic_sha256=c.semantic_hash(c.read_json(H/'long-identity.json')),capsule_manifest_sha256=reg['capsule_manifest_sha256'],
        registration_sha256=c.sha(H/'registration.json'),protocol_sha256=c.PROTOCOL_SHA256,config_sha256=c.CONFIG_SHA256,
        new_full_pin_count=len(context[4]),retained_r4_full_pins=9870,retained_older_union=9675,legacy_sources_and_mirrors=75,
        frozen_source_files=len(sources),capsule_files=inventory['capsule_files'],fresh_final_unit_methods=unit['methods_run'],
        fresh_OS_lifecycle_subprocesses=matrix['OS_subprocesses'],unit_OS_latch_subprocesses=6,counts_distinct_not_added=True,
        stress=dict(status=stress['status'],samples=stress['samples'],background_samples=stress['background_samples'],successful_samples=stress['successful_samples'],
            elapsed_seconds=stress['elapsed_seconds'],maximum_duration_seconds=stress['maximum_duration_seconds'],maximum_full_gap_seconds=stress['maximum_full_gap_seconds'],
            first_failure=stress['first_failure'],close_error=stress['close_error'],owned_threads_absent=stress['owned_threads_absent'],attempts=1),
        prior_attempts=['units-01 environment annotation incompatibility','units-02 inherited minimal Guard stub missing failure','units-03 actual worker residual primary overwrite','units-04 87 methods passed before timing permission audit'],
        fresh_final_unit_attempt='attempts/units-05',raw_stress='attempts/stress-01/stress-result.json',full_matrix='attempts/matrix-01-cases/summary.json',
        source_equality='source-equality.json',source_manifest='source-manifest.json',artifact_inventory='artifact-inventory.json',
        frozen_capsule_readonly=True,required_lease='required-lease.json',lease_published=False,invocation='invocation.json',
        ML_native_import_checkpoint_deserialization_inference_gradient_gameplay_training=False,production_launch=False,
        scheduler_commit_PR_deploy_external_messages_delegation=False,mutable_parent_state_frozen=False,
        limitations=stress['limitations']+['No runtime teacher or production ML qualification','Telemetry buffers can be lost on abrupt process death',
            'Inner and outer timing hash manifests are separate execution outputs; parent must inventory them',
            'Kernel scheduling/uninterruptibility and post-scan/transient observation limits remain',
            'Historical R3 aggregate stdout loss remains unrecoverable; old40 supervisor controls are not fresh passes here'])
    c.save(H/'implementation-result.json',result)
    # Actual json.tool on every JSON evidence file, excluding huge capsule duplicates
    # already byte-verified; include the identity, source manifests and receipts.
    paths=[x for x in H.rglob('*.json') if 'capsule-final' not in x.relative_to(H).parts]
    checks=[]
    for x in sorted(paths):
        t=time.monotonic();r=subprocess.run([sys.executable,'-B','-m','json.tool',str(x)],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)
        checks.append(dict(path=str(x.relative_to(H)),raw_exit=r.returncode,wall_seconds=time.monotonic()-t,stderr=r.stderr))
        c.require(r.returncode==0,'json.tool failed: '+str(x))
    c.save(H/'json-tool-validation.json',dict(commands=checks,count=len(checks),successful=True))
    # Immutable inventory excludes itself only, contains all actual bytes/sizes.
    files={str(x.relative_to(H)):dict(sha256=c.sha(x),bytes=x.stat().st_size) for x in sorted(H.rglob('*')) if x.is_file()}
    c.save(H/'artifact-inventory.json',dict(schema='guard_preparation_immutable_inventory_v1',excludes=['artifact-inventory.json'],files=files,count=len(files)))
    for x in H.rglob('*'):
        if x.is_file():x.chmod(0o444)
    for x in sorted((x for x in H.rglob('*') if x.is_dir()),key=lambda x:len(x.parts),reverse=True):x.chmod(0o555)
    H.chmod(0o555)
    print(json.dumps(result,sort_keys=True,indent=2))

if __name__=='__main__':main()
