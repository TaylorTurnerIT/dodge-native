"""Prepare one constant-entropy successor from a completed replay source."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path,value):
    Path(path).write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--predecessor',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--record',required=True)
    args=parser.parse_args()
    prior_dir=args.predecessor;root=args.output
    prior=json.loads((prior_dir/'config.json').read_text())
    root.mkdir()
    remote=str(Path(prior['project_root'])/'learning/runs/v2'/root.name)
    old=prior['run_dir']
    authority=dict(record=args.record,run_id=root.name,training_execution_authorized=True,fresh_games_authorized=True,
        existing_Taylor_mandate='Act autonomously I have already given the direction. Go forth and prosper',
        latest_direct_Taylor_instruction='discard all earlier stops on Dodge AI, including no-retry and no-successor rules and old memory notes like DODGE-055; only new stops from Taylor count. Keep earlier results and do not delete them. Machine limits, spending limits and publication limits still apply. Keep working.',
        authority_interpretation='Continue the performance-first local loop under the latest human mandate. This is not a new Taylor quote approving a named entropy value. The accountable owner selects the existing DODGE-037 lever after accepted073 regressed.',
        scope='One original control12 plus complete original Adam at LR3e-5; only constant entropy coefficient changes from0.01 to0.001 relative to073. Deliberately replay the bound073 exposed training stream; no globally fresh claim, heldout, replica, ray, cloud or public promotion.',
        no_cloud=True,public_promotion=False,one_invocation=True,no_wall_clock_cancellation=True,
        first_failure='Preserve evidence and exact lease on genuine runtime failure. Do not silently restart this invocation.',
        review_roster=['codex/gpt-6-luna','claudeAgent/claude-haiku-5-5; Luna alone if unavailable'],
        completion='M4 SSH execution-task completion -> accountable M4 owner -> department callback; no polling schedules or reverse pairing.')
    save(root/'authority.json',authority)
    for name in ['host_driver.py','directory_contract.py','ssh_route_guard.py']:
        shutil.copyfile(prior_dir/name,root/name)
    reg=json.loads(json.dumps(prior))
    reg.update(record=args.record,run_id=root.name,run_dir=remote,runner=remote+'/source/learning/experiments/local_performance_loop/fresh',
        cache=remote+'/empty-pycache',authority_path=remote+'/authority.json',authority_sha256=sha(root/'authority.json'),
        objective_delta=dict(parameter='ent_coef',before=.01,after=.001,schedule='constant'),
        preparation_status='new_entropy_replay_successor_pending_exact_delta_review',
        required_execution_disposition='Latest Taylor autonomous performance mandate; exact reviewed local entropy intervention, separate attempt.',
        source_rng_policy='Restore original control12 RNG and full original Adam at LR3e-5. Start a new simulator segment on the explicit exposed073 training-stream replay.',
        prior_results_preserved='All073 and earlier results/source/checkpoints/claims/leases remain unchanged. This starts from original control12, not a regressed endpoint.')
    reg['ppo']['ent_coef']=.001
    reg['expected_lease'].update(kind='local_control12_entropy_replay_continuation',record=args.record,owner_token=root.name,package=remote)
    reg['launch_context']['entrypoint']=remote+'/host_driver.py'
    reg['fresh_stream']['role']='exposed_training_replay_unique_within_trajectory'
    reg['fresh_stream']['replay']=dict(campaign_run_id=prior['run_id'],config_path=old+'/config.json',
        config_sha256=sha(prior_dir/'config.json'),audit_path=old+'/output/parent-terminal-audit.json',
        release_path=old+'/output/lease-release.json',
        exposure='Seeds are unique within this trajectory but deliberately overlap073. Prior exclusions and heldouts stay identical. Changed episode boundaries can consume different ordinal prefixes; this is not matched-action trajectory identity.')
    reg['callback']['request_id']=root.name+'-terminal-call-home-v1'
    reg['callback']['accountable_owner_thread']='mcp:d02bb35a-f159-4dd3-a71a-d28b6ce4dda0'
    for name in ['config.json','output/parent-terminal-audit.json','output/lease-release.json','output/host-driver-complete.json']:
        local=prior_dir/name if name=='config.json' else prior_dir/'terminal-evidence'/name
        reg['input_pins'][old+'/'+name]=sha(local)
    reg['input_pins'][reg['authority_path']]=reg['authority_sha256']
    reg['route_source_pins']={remote+'/'+name:sha(root/name) for name in ['directory_contract.py','ssh_route_guard.py']}
    reg['input_pins'].update(reg['route_source_pins'])
    # Snapshot inherited components and the actual changed reusable source only.
    repo=Path(__file__).resolve().parents[4]
    paths=[Path(p).relative_to(Path(old)/'source') for p in prior['source_pins']]
    paths.append(Path('learning/experiments/local_performance_loop/fresh/test_entropy_delta.py'))
    manifest={}
    for path in sorted(set(paths)):
        destination=root/'source'/path;destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(repo/path,destination)
        manifest[remote+'/source/'+str(path)]=sha(destination)
    reg['source_pins']=manifest
    save(root/'source-manifest.json',manifest)
    save(root/'config.json',reg)
    caller=root/'host_driver.py'
    caller.write_text(caller.read_text().replace(sha(prior_dir/'config.json'),sha(root/'config.json')))
    save(root/'identity-before-review.json',dict(record=args.record,registration_sha256=sha(root/'config.json'),
        host_driver_sha256=sha(caller),source_manifest_sha256=sha(root/'source-manifest.json'),
        authority_sha256=sha(root/'authority.json'),algorithm_source_count=len(manifest),route_source_pins=reg['route_source_pins']))
    print(json.dumps(json.loads((root/'identity-before-review.json').read_text()),sort_keys=True))


if __name__=='__main__':main()
