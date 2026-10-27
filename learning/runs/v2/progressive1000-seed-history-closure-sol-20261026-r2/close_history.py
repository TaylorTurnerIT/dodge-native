"""Finite historical seed coverage audit; stdlib only, no project imports."""
import collections
import hashlib
import json
import os
from pathlib import Path
import re
import tarfile

import discover as io
import seed_controls as controls

HERE, ROOT, R1 = io.HERE, io.ROOT, io.R1
RUNS = ROOT / 'learning/runs/v2'
LOW, HIGH = 0xD3000000, 0xD30003FF
U64 = (1 << 64) - 1
HIST = ((0xB0000000, 0xB00003E7), (0xD0000000, 0xD000007F), (0xE0000000, 0xE00003E7))

def mix64(value):
    value &= U64
    value ^= value >> 30
    value = (value * 0xBF58476D1CE4E5B9) & U64
    value ^= value >> 27
    value = (value * 0x94D049BB133111EB) & U64
    return value ^ (value >> 31)

def independent_seed(master, slot, episode, exclusions=HIST):
    """Separate implementation from the copied controls, using pinned Rust formula."""
    base = mix64(master ^ 0x444F4447455F5632)
    base ^= mix64(slot + 0x9E3779B97F4A7C15)
    base ^= mix64(episode + 0xD1B54A32D192ED03)
    for counter in range(4096):
        actual = mix64(base ^ mix64(counter + 0x94D049BB133111EB)) >> 32
        if not any(a <= actual <= b for a,b in exclusions):
            return counter, actual
    raise ValueError('finite arithmetic rejection bound exhausted')

def jload(path, purpose='original seed/counter/attempt metadata'):
    return io.load(path, purpose)

def values(obj):
    for pointer,row in io.walk(obj):
        if all(type(row.get(k)) is int for k in ('actual_seed','slot','episode','counter')):
            yield pointer,row

def rows(path):
    return [json.loads(s) for s in io.read(path, 'journal seed metadata and boundary counters').splitlines() if s.strip()]

def source(path, needles=()):
    text = io.read(path,'static source only; constructor/reset/fail-stop semantics').decode()
    lines = text.splitlines()
    return {'path':str(Path(path).relative_to(ROOT)) if Path(path).is_absolute() else str(path),
            'sha256':hashlib.sha256(text.encode()).hexdigest(),
            'evidence_lines':[[i,s] for i,s in enumerate(lines,1) if any(n in s for n in needles)]}

def add_intervals(target, master, starts, ends, exclusions=HIST):
    out = set()
    for slot,(start,end) in enumerate(zip(starts,ends)):
        assert 0 <= start <= end < 200000, (master,slot,start,end)
        for ep in range(start,end+1):
            out.add(independent_seed(master,slot,ep,exclusions)[1])
    target.update(out)
    return out

def main():
    # Pin the complete predecessor evidence, including the earlier 1,608-file audit reconciliation.
    prior = {}
    for name in ('coverage-map.json','history-reconstruction.json','coverage-inventory.json','coverage-files.json',
                 'prior-audit-input-reconciliation.json','input-manifest.json','receipt.json','observed-seeds.json',
                 'seed-vectors.json','cohort.json','future-controls.json','proposed-exclusions.json'):
        prior[name] = jload(R1/name,'R1 predecessor evidence; immutable input')
    assert hashlib.sha256(io.read(R1/'seed-vectors.json','proposal byte pin')).hexdigest() == '698557ed337cf795c1e587ca325a7a3d2645391837b0df18d8857987e634febf'
    assert hashlib.sha256(io.read(R1/'cohort.json','proposal byte pin')).hexdigest() == 'dd0d28697823eb3d3171789befb46da6f09b928f89328b3c91cb69a353104f45'
    lineage = jload(RUNS/'expanded-seed-lineage-reconstruction-deepseek-free-20261026-r3/evidence.json')
    for p in ('expanded-seed-lineage-parent-validation-20261026-r5/receipt.json',
              'expanded-evaluation-seed-coverage-reconcile-luna-20261026-r2/reconciliation.json',
              'expanded-evaluation-seed-exposure-audit-luna-20261026-r1/audit.json'):
        jload(RUNS/p,'prior lineage and explicit proof limits')
    historical_source = RUNS/'milestone3-D2-execution-r1/source-before/crates/dodge-rl-env/src/env.rs'
    sources = [source(ROOT/'crates/dodge-rl-env/src/seed.rs',('pub fn','const ','mix(', 'SeedMode::')),
               source(historical_source,('pub fn new','Slot::unstarted','slot.start','reset_all','reset_done','checked_add','return Err(self.poison')),
               source(ROOT/'python/dodge_rl/train_teacher.py',('class TrainingEnvLog','def reset_done','native_reset','except BaseException','experiment.checkpoint')),
               source(ROOT/'python/dodge_rl/ppo.py',('def collect_rollout','reset_done','for step','_guard'))]
    assert sources[0]['sha256'] == lineage['seed_source']['sha256']
    assert sources[1]['sha256'] == lineage['source_bindings']['files']['crates/dodge-rl-env/src/env.rs']['pilot_identity_pin']
    masters = sorted({x['run_master_seed'] for x in prior['history-reconstruction.json']['bounds']})
    old_envelope, tight, training_observed, unmatched = set(),set(),set(),[]
    campaigns, originals, journal_pins = [],{},{}
    for old in prior['history-reconstruction.json']['bounds']:
        name, master = old['run'],old['run_master_seed']
        directory = RUNS/name
        journal = directory/'training-episodes.jsonl'
        records = rows(journal)
        journal_pins[name] = io.PINS[str(journal.relative_to(ROOT))]
        originals[journal_pins[name]['sha256']] = str(journal.relative_to(ROOT))
        initial = next(r for r in records if r.get('kind')=='initial')
        starts = initial['batch_info']['initial_episode_indices']
        assert len(starts)==64
        last = [x-1 for x in starts]
        seedrows = 0
        for lineno,row in enumerate(records,1):
            for ptr,r in values(row):
                training_observed.add(r['actual_seed'])
                seedrows += 1
                match = [m for m in masters if independent_seed(m,r['slot'],r['episode']) == (r['counter'],r['actual_seed'])]
                if not match:
                    unmatched.append({'path':str(journal.relative_to(ROOT)),'line':lineno,'pointer':ptr,'seed_metadata':r})
                elif master in match:
                    last[r['slot']] = max(last[r['slot']],r['episode'])
        terminal_files = []
        worker = {}
        for filename in ('worker-result.json','long-worker-result.json','execution-result.json','run-result.json','launch-marker.json','worker-launch.json','inner-failure.json'):
            path = directory/filename
            if path.exists():
                obj = jload(path)
                terminal_files.append(str(path.relative_to(ROOT)))
                if filename in ('worker-result.json','long-worker-result.json'):
                    worker = obj
        final_resume = worker.get('final_resume_next_episode_indices')
        boundary_indices = [r['next_episode_indices'] for r in records if isinstance(r.get('next_episode_indices'),list)]
        if final_resume is not None:
            assert len(final_resume)==64
            last = [max(a,b-1) for a,b in zip(last,final_resume)]
            basis = 'terminal worker final_resume_next_episode_indices; fail-stop source; no reset recovery in runner'
        elif boundary_indices:
            final_resume = boundary_indices[-1]
            last = [max(a,b-1) for a,b in zip(last,final_resume)]
            basis = 'terminal checkpoint_resume_boundary plus retained terminal status/traceback; native boundary logging'
        elif name=='D2-gradient-alignment-20261025-r1':
            basis = 'failed evaluate_at(0) before first collect_rollout; initial constructors only'
        else:
            basis = 'completed fixed-count collector/probe, all returned reset metadata; no subsequent collection'
        # Keep one fail-stop reset endpoint even with a successful journal. A failed
        # native reset may consume its fresh index before Python can log a return.
        possible_end = [n+1 for n in last]
        interval_set = add_intervals(tight,master,starts,possible_end)
        add_intervals(old_envelope,master,[0]*64,old['inclusive_per_slot_bounds'])
        runner_refs=[]
        launch=directory/'worker-launch.json'
        if launch.exists():
            command=jload(launch).get('command',[])
            for token in command:
                p=Path(token)
                if p.is_absolute() and p.exists() and p.suffix=='.py':
                    runner_refs.append(source(p,('VecDodgeEnv(', 'collect_rollout(', 'for update in','except BaseException','final_resume_next_episode_indices','reset_all(')))
            if '--registration' in command:
                registration=Path(command[command.index('--registration')+1])
                reg=jload(registration,'actual worker registration master/source identity')
                expected=command[command.index('--registration-sha256')+1]
                assert io.PINS[str(registration.relative_to(ROOT))]['sha256']==expected
                assert reg.get('run_seed',master)==master
        campaigns.append({'campaign':name,'seed_mode':'training','master':master,'slots':64,
                          'initial_episode_indices':starts,'maximum_observed_own_episode_indices':last,
                          'actual_final_resume_episode_indices':final_resume,
                          'possible_inclusive_episode_end':possible_end,'unlogged_failed_reset_allowance_per_slot':1,
                          'bound_basis':basis,'terminal_status':worker.get('status',worker.get('experiment_status')),
                          'terminal_error':worker.get('error'),'terminal_update_progress':worker.get('update_progress'),
                          'terminal_counters':worker.get('counters'),'terminal_receipts':terminal_files,
                          'journal_pin':journal_pins[name],'seed_records_including_duplicates':seedrows,
                          'runner_source':runner_refs,'finite_unique_interval_seeds':len(interval_set),
                          'status':'bounded_known_campaign; not global inventory authority'})
    assert len(old_envelope)==164385
    assert len(training_observed)==70301
    io.write('campaign-closure.json',campaigns)
    io.write('source-semantics.json',{'sources':sources,'lineage_native_bindings':lineage['native_bindings'],
        'source_limit':'Historical env source recovered at exact pilot identity hash. Runner registrations and logged seed tuples bind actual streams; source reading does not certify binaries anew.',
        'constructor':'All slot seeds validate first; sequential Slot::unstarted/start stops at first error. Include every requested initial slot conservatively.',
        'reset':'Validate candidates first. Replace slot before start; a failed fresh reset consumes that index. Poison propagates; audited campaign collectors do not recover with reset_all.',
        'tail':'One extra per-slot index covers one failing reset after last retained current state. Entire buffered collections are covered by completed fixed-count receipts or explicit terminal state, not successful journals alone.'})
    # Journal copies are excluded only after byte proof. Empty files do not prove
    # their surrounding campaign did not construct anything; retain that distinction.
    nested=[]
    for path in sorted(RUNS.rglob('training-episodes.jsonl')):
        if len(path.relative_to(RUNS).parts)<=2 or HERE in path.parents: continue
        data=io.read(path,'nested journal hash proof, not execution attribution')
        pin=io.PINS[str(path.relative_to(ROOT))]
        kind='exact_ancestor_copy' if pin['sha256'] in originals else ('empty_no_seed_content' if not data else 'unresolved_nonidentical_journal')
        nested.append({**pin,'classification':kind,'identical_original':originals.get(pin['sha256']),
                       'limit':'Empty fixture/copy journal is not proof of no surrounding construction.' if not data else None})
    io.write('nested-journal-proof.json',{'paths':nested,'counts':dict(collections.Counter(x['classification'] for x in nested)),
        'r1_reported_nested_paths':843,'current_regular_paths':len(nested),
        'alias_count_difference':'Prior reported 4 symlink aliases separately; current pathlib inventory does not traverse directory symlinks.'})
    # Six explicitly requested directories.
    crit=RUNS/'critic-diagnostic-D2-20261025-r1'
    wr=jload(crit/'worker-result.json')
    obs1=RUNS/'critic-diagnostic-execution-observer-20261025-r1/worker-result.json'
    obs2=RUNS/'critic-diagnostic-execution-observer-20261025-r2/worker-result.json'
    assert io.read(crit/'worker-result.json','failed preconstructor receipt')==io.read(obs1,'observer copy byte proof')
    assert io.read(RUNS/'critic-diagnostic-D2-20261025-r2/worker-result.json','actual critic terminal receipt')==io.read(obs2,'observer copy byte proof')
    crit_source=source(RUNS/'critic-diagnostic-runner-prepare-20261025-r2/runner.py',('D1 state restoration differs','env = dodge_rl.VecDodgeEnv'))
    six=[{'directory':str(crit.relative_to(ROOT)),'classification':'failed_before_constructor','master':3192039780,
          'training_constructor_bound':0,'evidence':[str((crit/'worker-result.json').relative_to(ROOT)),crit_source],
          'reason':wr['error'],'status':'closed'},
         {'directory':str(obs1.parent.relative_to(ROOT)),'classification':'byte_identical_observer_copy_of_failed_critic_r1','new_constructor_bound':0,'status':'closed'},
         {'directory':str(obs2.parent.relative_to(ROOT)),'classification':'byte_identical_observer_copy_of_journaled_critic_r2','new_constructor_bound':0,'represented_campaign':'critic-diagnostic-D2-20261025-r2','status':'closed'}]
    m2=RUNS/'milestone2-validation-campaign-r2'
    plan=jload(m2/'registered-plan.json','seed-only plan, not native parity outcomes')
    fail=jload(RUNS/'milestone2-validation-campaign-r1/trajectory-failure.json')
    assert 'cannot be cast as' in fail['error']
    m2source=source(ROOT/'learning/scripts/v2_validate_environment.py',('def base_config','training_run_seed','def worker_trajectory','range(case[','def worker_memory','def worker_throughput','reset_done('))
    memory=jload(m2/'memory-result.json')
    throughput=jload(m2/'throughput-result.json')
    trajectory=jload(m2/'trajectory-result.json')
    m2ends=[0]*32
    for item in [memory]+throughput['measurements']:
        for slot,n in enumerate(item['batch_info']['next_episode_indices']):m2ends[slot]=max(m2ends[slot],n)
    # Trajectory has no per-slot metadata. Its exact aggregate reset count is a
    # valid all-slot maximum, tighter than the loop's per-slot decision cap.
    for case,result in zip((plan['stages'][1]['default_cap_case'],plan['stages'][1]['ragged_cap_case']),trajectory['cases']):
        for slot in range(case['batch_size']):m2ends[slot]=max(m2ends[slot],result['explicit_slot_resets']+1)
    add_intervals(tight,plan['training_run_seed'],[0]*32,m2ends)
    six.extend([{'directory':'learning/runs/v2/milestone2-validation-campaign-r1','classification':'trajectory_argument_conversion_failed_before_Rust_constructor',
                 'master':plan['training_run_seed'],'training_constructor_bound':0,'error':fail['error'],
                 'qualification_seed_metadata_only':{'B_range':[0xB0000000,0xB00003E7],'outcomes_used':False},'status':'closed'},
                {'directory':str(m2.relative_to(ROOT)),'classification':'real_training_mode_validation_not_optimizer_training',
                 'master':plan['training_run_seed'],'slots':32,'initial_episode_indices':[0]*32,'possible_inclusive_episode_end':m2ends,
                 'returned_memory_resets':memory['explicit_slot_resets'],'memory_final_resume_indices':memory['batch_info']['next_episode_indices'],
                 'trajectory_aggregate_resets':[x['explicit_slot_resets'] for x in trajectory['cases']],
                 'source':m2source,'native_parity_outcomes_used':False,'status':'closed_finite_seed_bound'}])
    action=RUNS/'postovernight-action-mode-campaign-r1'
    ar=jload(action/'run-result.json')
    command=ar['command'];runner=Path(next(x for x in command if x.endswith('/runner.py')))
    action_source=source(runner,('seeds_by_slot','eval_seeds','VecDodgeEnv','range(','run_seed','seeds='))
    six.append({'directory':str(action.relative_to(ROOT)),'classification':'real_evaluation_only_diagnostic',
                'seed_mode':'evaluation','seed_range':[0xD0000000,0xD000003F],'master':None,'worker_exit_code':ar['worker_exit_code'],
                'native_step_calls':ar['native_step_calls'],'source':action_source,'status':'closed_finite_seed_list'})
    io.write('six-directory-closure.json',six)
    # Additional concrete native constructions hidden by R1's proposal classifier.
    extras=[]
    smoke=RUNS/'milestone3-real-collector-smoke-r1'
    sp=jload(smoke/'plan.json');sr=jload(smoke/'receipt.json');ss=jload(smoke/'result.json')
    assert sr['exit_code']==0 and ss['status']=='passed'
    smoke_ends=ss['collections'][-1]['next_episode_indices']
    add_intervals(tight,sp['env']['run_seed'],[0]*2,smoke_ends)
    extras.append({'campaign':str(smoke.relative_to(ROOT)),'master':sp['env']['run_seed'],'slots':2,'initial_episode_indices':[0,0],
                   'possible_inclusive_episode_end':smoke_ends,'basis':'two eight-decision collections, terminal counters; one extra failed reset endpoint',
                   'source':source(smoke/'smoke.py',('VecDodgeEnv','collect_rollout','next_episode_indices'))})
    native=RUNS/'progressive1000-native-collector-integration-sol-20261026-r1'
    ns=source(native/'integration_driver.py',('OPTIONS =','batch_size=','run_seed=','for name','[256]','[128, 128]','reset_done','intentional_unit_guard_after_actual_native_reset'))
    add_intervals(tight,777,[0]*8,[257]*8)
    extras.append({'campaign':str(native.relative_to(ROOT)),'master':777,'slots':8,'initial_episode_indices':[0]*8,
                   'possible_inclusive_episode_end':[257]*8,'basis':'at most 256 decisions per fixed case; one reset per slot per decision; include injected post-reset guard consumption', 'source':ns})
    wrapper=RUNS/'milestone2-wrapper-r1'
    wp=jload(wrapper/'trajectory-inputs.json')
    ws=source(wrapper/'trajectory_probe.rs',('run_seed:','for decision','reset_done','for run in'))
    assert ws['sha256']==wp['source_sha256']
    archive=wrapper/'source.tar.gz'
    archive_bytes=io.read(archive,'historical seed algorithm source archive, exact member only')
    with tarfile.open(archive,'r:*') as tar:
        early=tar.extractfile('crates/dodge-rl-env/src/seed.rs').read()
    assert hashlib.sha256(early).hexdigest()=='7478aabe705fc538f806f7a14bc6ad6a9b08a77b1a3978ab5f238e2565b612eb'
    # This pre-extension source rejects B only. Formula controls replay separately.
    add_intervals(tight,0xFFFFFFFF12345678,[0]*9,[301]*9,((0xB0000000,0xB00003E7),))
    extras.append({'campaign':str(wrapper.relative_to(ROOT)),'master':0xFFFFFFFF12345678,'slots':9,'initial_episode_indices':[0]*9,
                   'possible_inclusive_episode_end':[301]*9,'exclusions':[[0xB0000000,0xB00003E7]],
                   'basis':'300-decision two-environment trajectory; seed reference arithmetic is not construction','source':ws,
                   'source_algorithm':{'archive':str(archive.relative_to(ROOT)),'archive_sha256':hashlib.sha256(archive_bytes).hexdigest(),
                     'member':'crates/dodge-rl-env/src/seed.rs','member_sha256':hashlib.sha256(early).hexdigest(),
                     'version':'dodge_slot_splitmix64_high32_reject_v1; mandatory B only'}})
    io.write('additional-construction-coverage.json',extras)
    # Full known evaluation lists bound failed startup/reset and unlogged tails.
    possible_fixed=set(range(0xD0000000,0xD0000080))|set(range(0xD1000000,0xD1000400))|set(range(0xD2000000,0xD2000800))
    possible_fixed.update(31+s+100*ep for s in range(4) for ep in range(257))
    # Outside-v2 episode constructors take explicit frozen splits; no episode hash stream.
    splits=jload(ROOT/'learning/runs/entity-teacher-bootstrap-10000/seeds.json','outside-v2 fixed episode seed metadata only')
    for key in ('train','smoke','validation','test'):possible_fixed.update(splits[key])
    possible_fixed.update((0,1,7,31,32,42,43,74,131,132))
    possible_fixed.update(range(1000,1065))
    possible_fixed.update(range(0xB0000000,0xB00003E8))
    possible_fixed.update(range(0xE0000000,0xE00003E8))
    outside_source=source(ROOT/'learning/python/dodge_learning/seeds.py',('list(range','streams ='))
    io.write('fixed-list-coverage.json',{'possible_seed_values':sorted(possible_fixed),'source':outside_source,
        'meaning':'Finite permitted fixed seed lists, not evidence that every proposed/listed episode ran. D128, D100 and D200 cover evaluation retries and failures without opening B/E outcomes.'})
    # Every R1 unresolved path receives a per-file evidence role, not a name-only
    # assertion that an entire directory never ran.
    index=jload(HERE/'provenance-index.json','owned seed/counter projection index')
    bypath={r['path']:r for r in index}
    discovery_pins={r['path']:r for r in jload(HERE/'discovery-input-pins.json','original projection input hashes')}
    # Inspect exact IPC entrypoints and the lifecycle-only discriminator calls.
    probe_proofs=[]
    for relative in ('postovernight-long-D2-IPC-close-order-probe-sonnet-r2/close_order_probe.py',
                     'postovernight-long-D2-IPC-close-order-probe-sonnet-r2/probe_wrapper.py',
                     'postovernight-long-D2-boundary-IPC-diagnosis-sonnet-r1/ipc_probe.py',
                     'postovernight-long-D2-boundary-IPC-diagnosis-sonnet-r1/starvation_model.py',
                     'postovernight-long-D2-boundary-failure-diagnosis-sonnet-r1/discriminator_acceptance.py',
                     'postovernight-long-D2-boundary-failure-diagnosis-sonnet-r1/discriminator_monitor.py',
                     'postovernight-long-D2-boundary-failure-diagnosis-sonnet-r1/discriminator_timestamp.py',
                     'postovernight-long-D2-boundary-startup-reap-diagnosis-sonnet-r1/dgram_close_probe.py',
                     'postovernight-long-D2-boundary-profile-r1/profile_once.py',
                     'postovernight-long-D2-switchinterval-probe-r1/probe_once.py'):
        probe_proofs.append(source(RUNS/relative,('import ','subprocess.Popen','__file__','Stub','def main','worker_failure(','accept_observed(','sys.modules','ML_imports')))
    # Parent audits explicitly record zero real episodes for these CPU/resource
    # calibration attempts. They are not evidence for real evaluator coverage.
    calibration_proofs=[]
    for rev in (6,7):
        path=RUNS/f'current-pair-resource-calibration-parent-audit-20261026-r{rev}/audit.json'
        data=jload(path,'retained calibration zero-game terminal receipt')
        assert data['real_game_episodes']==0
        calibration_proofs.append({'path':str(path.relative_to(ROOT)),'sha256':io.PINS[str(path.relative_to(ROOT))]['sha256'],
                                   'real_game_episodes':0,'status':data['status']})
    io.write('diagnostic-no-constructor-proofs.json',{'source_proofs':probe_proofs,'calibration_terminal_proofs':calibration_proofs,
        'limits':'IPC scripts spawn only their own stdlib roles. Lifecycle discriminators call failure/monitor/acceptance methods with stub process and guard, not worker/model/environment paths. Source proof is limited to these exact entrypoints.'})
    references={
        'D2-best180-branch-execution-observer-luna-20261026-r1':'D2-best180-branch-luna-20261026-r1',
        'D2-continuation-execution-observer-20261025-r1':'D2-continuation-20261025-r1',
        'D2-continuation-execution-observer-20261025-r2':'D2-continuation-20261025-r2',
        'D2-gradient-execution-observer-20261025-r1':'D2-gradient-alignment-20261025-r1',
        'D2-gradient-execution-observer-20261025-r2':'D2-gradient-alignment-20261025-r2',
        'D2-retained204-lr1e4-execution-observer-luna-20261026-r1':'D2-retained204-lr1e4-20261026-r1',
        'D2-retained276-continuation-execution-observer-luna-20261026-r2':'D2-retained276-continuation-20261026-r2',
        'D2-retained276-lr3em5-execution-observer-luna-20261026-r1':'pre-worker failure retained in D2-retained276-lr3em5-parent-failure-audit-20261026-r1/audit.json',
        'D2-retained276-lr3em5-execution-observer-luna-20261026-r2':'D2-retained276-lr3em5-20261026-r2',
        'D2-retained300-execution-observer-parent-20261026-r1':'D2-retained300-continuation-20261026-r1',
        'D2-retained324-execution-observer-parent-20261026-r1':'D2-retained324-continuation-20261026-r1',
        'D2-retained324-linear-execution-observer-parent-20261026-r1':'D2-retained324-linear-lr-20261026-r1',
        'D2-training-v3-execution-observer-20261025-r1':'D2-training-v3-20261025-r1',
        'milestone3-D1-execution-r1':'milestone3-D1-curriculum-r1',
        'milestone3-D2-execution-r1':'milestone3-D2-curriculum-r1',
        'milestone3-pilot-execution-r1':'milestone3-D1-pilot-r1',
        'milestone3-probe-execution-r1':'milestone3-device-probe-r1',
        'postovernight-action-mode-execution-r1':'postovernight-action-mode-campaign-r1',
        'postovernight-long-D2-execution-observer-r1':'postovernight-long-D2-campaign-r1',
        'postovernight-long-D2-execution-observer-r2':'prelaunch failure, represented by terminal-no-launch-verification.json',
        'postovernight-long-D2-execution-observer-r2b':'postovernight-long-D2-campaign-r2'}
    for relative in ('D2-retained276-lr3em5-parent-failure-audit-20261026-r1/audit.json',
                     'postovernight-long-D2-execution-observer-r2/terminal-no-launch-verification.json'):
        jload(RUNS/relative,'specific pre-worker/prelaunch failure receipt')
    unresolved=[r for r in prior['coverage-inventory.json'] if r['category']=='unresolved_execution_provenance']
    pathmap=[]
    sensitive=[]
    for row in unresolved:
        path=row['path'];entry=bypath.get(path);name=Path(path).name
        if entry is None:
            category='qualification_boundary_unopened';status='unresolved_seed_metadata_only_needed'
            reason='Recover a parent-issued seed-only range/constructor receipt for this exact path; do not open outcomes.'
            sensitive.append(path)
        elif any('/'+x+'/' in path for x in ('milestone1-r1','milestone1-r2','milestone2-core-r1','milestone2-binding-r1','milestone2-math-r1')):
            category='native_build_test_or_fixed_seed_benchmark_receipt';status='unresolved_exact_test_constructor_inventory'
            reason='Fixed 1000..1064 profile is bounded; map this exact command to its historical native test source and finite literal/hash-seed bounds. Build/test receipt alone is not a no-constructor proof.'
        elif any(x in path for x in ('postovernight-long-D2-IPC-close-order-probe','postovernight-long-D2-boundary-IPC-diagnosis','postovernight-long-D2-boundary-failure-diagnosis','postovernight-long-D2-boundary-startup-reap-diagnosis')):
            category='ipc_or_lifecycle_probe_metadata';status='closed_no_constructor_probe'
            reason='Exact stdlib IPC entrypoints and own child roles, or lifecycle discriminator stub methods, pinned in diagnostic-no-constructor-proofs.json; no call to learner/worker environment paths.'
        elif any(x in path for x in ('postovernight-long-D2-boundary-profile-r1','postovernight-long-D2-switchinterval-probe-r1')):
            category='bounded_file_hash_and_thread_probe';status='closed_metadata_role'
            reason='Pinned profile_once.py/probe_once.py calls guard/hash/thread paths only; results report no torch/numpy/dodge_rl imports. No environment construction.'
        elif any('/'+group+'/' in path for group in references):
            category='observer_or_executor_reference';status='closed_represented_campaign'
            reason='Exact command/terminal metadata refers to '+next(value for group,value in references.items() if '/'+group+'/' in path)+'. No additional constructor campaign is inferred from an observer copy.'
        elif '/current-pair-resource-calibration-' in path:
            category='synthetic_or_preload_resource_calibration';status='closed_no_real_game_calibration'
            reason='Parent terminal audits r6/r7 record real_game_episodes=0; early r1 receipt failed before representative worker load. See pinned diagnostic-no-constructor-proofs.json.'
        elif name.endswith('.jsonl') and 'resources' in name:
            category='resource_sampler_metadata';status='closed_metadata_role'
            reason='Rows contain process/resource counters; original worker campaign is covered separately. This file is not an independent environment construction receipt.'
        elif any(x in path for x in ('critic-diagnostic-execution-observer','critic-diagnostic-D2-20261025-r1')):
            category='critic_preconstructor_failure_or_observer_copy';status='closed_represented_campaign'
            reason='See six-directory-closure.json byte proofs and exact preconstructor source location.'
        elif name.startswith('state-') or name=='state.json':
            category='orchestration_state_snapshot';status='closed_metadata_role'
            reason='Snapshot references historical jobs; not an independent constructor. Referenced concrete campaigns remain in campaign-closure.json.'
        elif name in ('worker-result.json','run-result.json','execution-result.json','launch.json','worker-launch.json','command.json','command-start.json','command-terminal.json','wrapper-result.json'):
            category='command_or_terminal_reference';status='unresolved_exact_command_attribution'
            reason='Match exact command, output path, source pin and exit to a covered campaign or prove fail-before-constructor. No no-run inference from missing seed fields.'
        else:
            category='derived_audit_manifest_plan_or_lineage_metadata';status='closed_metadata_role'
            reason='This file projects an audit/manifest/plan/reference, not raw episode provenance. Its absence of seeds is not a claim about referenced or external executions.'
        pathmap.append({'path':path,'classification':category,'status':status,'reason_or_needed_action':reason,
                        'input_sha256':io.PINS.get(path,discovery_pins.get(path,{})).get('sha256'),
                        'owned_projection_pointer':next((i for i,r in enumerate(index) if r['path']==path),None)})
    io.write('r1-unresolved-path-closure.json',{'paths':pathmap,'counts':dict(collections.Counter(x['status'] for x in pathmap)),
        'meaning':'Counts refer to files, not campaigns or independent episodes; metadata-role closure does not close its referenced execution history.'})
    # D3 is a registered M3 namespace with an explicitly unstarted terminal state.
    state=jload(ROOT/'learning/runs/v2-orchestration/state.json','D3 lifecycle seed-only state projection')
    before=jload(ROOT/'learning/runs/v2-orchestration/overnight-closeout-r1/state-before-closeout.json','D3 original closeout no-attempt metadata')
    closeout=jload(ROOT/'learning/runs/v2-orchestration/overnight-closeout-r1/verification.json','original overnight lifecycle closure receipt')
    d3_current=state['M3_implementation']['D3'];d3_before=before['M3_implementation']['D3']
    assert d3_current['status'].startswith('not_started') and d3_before['status'].startswith('not_started')
    d3_mentions=[]
    for entry in index:
        for ptr,value in entry.get('metadata',[]):
            if type(value)is int and value==5562881586070242563:d3_mentions.append({'path':entry['path'],'pointer':ptr})
    d3_markers=[str(p.relative_to(ROOT)) for p in RUNS.glob('milestone3-D3-*')]
    io.write('d3-no-attempt.json',{'registered_master':5562881586070242563,'registered_campaign':'M3 D3 curriculum',
        'original_closeout_status':d3_before['status'],'current_status':d3_current['status'],
        'closeout_receipt_path':'learning/runs/v2-orchestration/overnight-closeout-r1/verification.json',
        'closeout_receipt_sha256':io.PINS['learning/runs/v2-orchestration/overnight-closeout-r1/verification.json']['sha256'],
        'matching_D3_run_freeze_execution_paths':d3_markers,'journal_replay_master_matches':0,
        'registered_seed_mentions':d3_mentions,'conclusion':'No attempt for the registered M3 D3 campaign in retained lifecycle evidence; no global proof against an unrelated unrecorded constructor.',
        'distinction':'Native baseline difficulty D3 on fixed B seeds is a different campaign/seed mode; it is not the registered M3 master stream. No D3 launched here.'})
    # Reconcile the historical unused prefix without removing it from the retained R1 envelope.
    prefix_campaign=next(x for x in campaigns if x['master']==4200000000)
    assert independent_seed(4200000000,44,48)==(0,97593849)
    assert prefix_campaign['initial_episode_indices'][44]>48
    observed_r1=set(prior['observed-seeds.json']['real_observed_sorted_unique_seeds'])
    observed=set(observed_r1)
    new_observation_files=[]
    # These are actual native controls, despite synthetic policy/certificate inputs.
    # Never infer they are synthetic environment constructions from their names.
    targeted=list(sorted((native/'results').glob('*.json')))
    # Outside-v2 files contain explicit episode seeds rather than M3 hash streams.
    targeted += [ROOT/r['path'] for r in index if not r['path'].startswith('learning/runs/v2/')
                 and not r['path'].startswith('learning/runs/v2-orchestration/')
                 and Path(r['path']).name in ('run.json','smoke-evaluation.json','neutral.json','random.json','avoidance.json','baseline-smoke-gameplay.json','relative-smoke-gameplay.json')]
    for path in targeted:
        obj=jload(path,'additional original native-control or outside-v2 episode seed metadata')
        found=set()
        for ptr,row in io.walk(obj):
            if type(row.get('actual_seed'))is int and all(type(row.get(k))is int for k in ('slot','episode','counter')):
                found.add(row['actual_seed'])
            elif type(row.get('seed'))is int and any(k in row for k in ('alive_frames','gameplay_frames','raw_frames','terminated','full_state_hash','frames')):
                found.add(row['seed'])
        if found:
            observed.update(found)
            new_observation_files.append({'path':str(path.relative_to(ROOT)),'sha256':io.PINS[str(path.relative_to(ROOT))]['sha256'],
                                           'unique_seed_values':len(found),'new_vs_R1':len(found-observed_r1)})
    io.write('additional-observed-seeds.json',{'new_sorted_unique_seed_values':sorted(observed-observed_r1),
        'new_count':len(observed-observed_r1),'merged_real_observed_count':len(observed),'source_files':new_observation_files,
        'limit':'Raw actual native-control records and explicit outside-v2 episode result records only; listed proposals and seed reference arithmetic are not observations.'})
    merged=old_envelope|tight|possible_fixed|observed
    cohort=set(range(LOW,HIGH+1))
    io.write('97593849-reconciliation.json',{'seed':97593849,'historical_tuple':{'master':4200000000,'slot':44,'episode':48,'counter':0},
        'actual_registered_construction_start_episode_slot44':prefix_campaign['initial_episode_indices'][44],
        'historical_observed':97593849 in observed,'in_tight_known_attempt_coverage':97593849 in tight,
        'in_retained_R1_zero_origin_envelope':97593849 in old_envelope,
        'future_tuple':{'replica':1,'slot':17,'episode':760,'counter':0},
        'conclusion':'Matched arithmetic streams, not historical consumption. Episode48 precedes this new master construction offset. Retain R1 envelope and report intersection; no silent filter or seed replacement.',
        'protocol':'No requirement inferred that all future training seeds avoid all prior training seeds. Cohort-versus-consumed-history freshness and six-range native exclusions are separate gates.'})
    io.write('merged-conservative-seeds.json',{'sorted_unique_seed_values':sorted(merged),'canonical_sha256':controls.digest(sorted(merged)),
        'count':len(merged),'meaning':'Union retains R1 zero-origin overapproximation; adds finite known campaign/reset allowances and permitted fixed lists. Not a global-history closure.'})
    io.write('cohort-collision-check.json',{'proposal_retained':True,'cohort_changed':False,'vectors_changed':False,
        'real_observed_seed_count_R1':len(observed_r1),'real_observed_seed_count_R2_merged':len(observed),'original_training_observed_seed_count':len(training_observed),
        'R1_conservative_envelope_count':len(old_envelope),'tight_known_attempt_seed_count':len(tight),
        'finite_fixed_list_count':len(possible_fixed),'merged_conservative_seed_count':len(merged),
        'real_observed_collisions':sorted(observed&cohort),'possible_attempt_collisions':sorted(tight&cohort),
        'merged_conservative_collisions':sorted(merged&cohort),'journal_derivation_mismatches':unmatched,
        'status':'BLOCKED_SPECIFIC_REMAINING_PROVENANCE_GAPS','freshness_approval':False,'cohort_reservation':False})
    io.write('closure-input-pins.json',list(io.PINS.values()))
    print(json.dumps({'campaigns':len(campaigns),'six_directories':len(six),'nested':len(nested),'path_statuses':dict(collections.Counter(x['status'] for x in pathmap)),
                      'merged':len(merged),'collisions':sorted(merged&cohort),'mismatches':len(unmatched)}))

if __name__=='__main__':main()
