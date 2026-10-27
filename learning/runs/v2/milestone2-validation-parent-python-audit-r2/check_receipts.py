"""Independent stdlib-only retained Python-campaign evidence audit. No project imports."""
from collections import Counter
from datetime import datetime, timezone
import ast
import hashlib
import json
import math
from pathlib import Path
import statistics
import struct
import traceback

ROOT = Path(__file__).resolve().parents[4]
OWN = Path(__file__).resolve().parent
DATA = ROOT / 'learning/runs/v2/milestone2-validation-campaign-r2'
CAP = ROOT / 'learning/.cache/v2-m2-campaign-review-r4'
IDENTITY = 'eb72ae7efec29f6def72940715ad6ff09e43d09140f0c348f095bdbbf2727448'
LIMIT = 6 * 1024**3
REPORT = ROOT / 'learning/runs/v2/milestone2-validation-execution-r2/report.json'


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def save_new(p, v):
    with p.open('x') as f:
        json.dump(v, f, indent=2, sort_keys=True, allow_nan=False)
        f.write('\n')


def read(p):
    return json.loads(p.read_text())


def rows(p):
    return [json.loads(line) for line in p.read_text().splitlines()]


def ensure(condition, detail):
    if not condition:
        raise AssertionError(detail)


checks = []
inputs = [p for p in DATA.iterdir() if p.is_file()] + [REPORT]
source_names = ['learning/scripts/v2_validate_environment.py', 'crates/dodge-rl-env/src/python.rs', 'crates/dodge-rl-env/src/seed.rs']
inputs += [CAP / name for name in source_names]
inputs += [CAP / 'manifest.json']
before = {str(p.relative_to(ROOT)): sha(p) for p in inputs}
save_new(OWN / 'input-pins-before.json', before)
audit = {'schema': 'independent_m2_python_retained_evidence_audit_v1',
         'created_at_utc': datetime.now(timezone.utc).isoformat(),
         'scope': 'Python trajectory, memory, throughput retained evidence; no project import or execution.',
         'frozen_identity_sha256': IDENTITY, 'checks': checks, 'failures': [], 'findings': [],
         'limitations': [
             'No project, NumPy, extension, game, test, native binary, network operation, or subagent was executed.',
             'Trajectory summaries and pinned successful checking code support equality/ownership; intermediate arrays are not serialized for independent replay.',
             'Memory stream serializes completed episodes and resets, not every step tensor. Completed-episode objectives and aggregate frames are independently checked; per-call reward/array assertions rely on pinned executed checking code.',
             'The 101-point memory plateau is empirical under this random short-episode workload, not mathematical zero-leak proof or mature-pattern coverage.',
             'Throughput action/work/final-neural hashes agree across configurations; raw actions/per-call work/final arrays are not serialized, so their hashes cannot be independently reconstructed here.',
             'RSS samples and ru_maxrss are separate cooperative observations, not proof of an unsampled hard OS ceiling. No MPS or PPO throughput is measured.',
             'Parent must reconcile this audit with the separate native/build audit before complete M2 acceptance. No teacher learning or qualification evidence is established.'
         ]}

try:
    manifest = read(DATA / 'artifact-sha256.json')
    ensure(len(manifest) == 34, 'Unexpected declared campaign artifact count')
    actual = {str(p.relative_to(DATA)) for p in DATA.iterdir() if p.is_file() and p != DATA / 'artifact-sha256.json'}
    ensure(set(manifest) == actual, 'Manifest is not exact top-level campaign-file coverage')
    for name, expected in manifest.items():
        ensure(sha(DATA / name) == expected, f'Artifact hash mismatch: {name}')
    campaign = read(DATA / 'campaign-result.json')
    plan = read(DATA / 'registered-plan.json')
    identity = read(DATA / 'identity.json')
    ensure(sha(DATA / 'identity.json') == IDENTITY, 'Identity document mismatch')
    ensure(sha(DATA / 'registered-plan.json') == campaign['registered_plan_sha256'], 'Plan hash mismatch')
    ensure(campaign['status'] == 'passed' and campaign['identity_sha256'] == IDENTITY, 'Overall pass/identity mismatch')
    ensure(campaign['automatic_retries'] == 0 and not campaign['resource_limits_relaxed'], 'Retry/limit policy differs')
    ensure(campaign['elapsed_seconds'] < 1800 and campaign['rss_limit_bytes'] == LIMIT, 'Overall resource limit differs')
    ensure(datetime.fromisoformat(campaign['finished_at_utc']) < datetime(2026, 10, 24, 13, tzinfo=timezone.utc), 'Campaign exceeded cutoff')
    outer = read(REPORT)
    ensure(outer['execution']['campaign_invocations'] == 1 and outer['execution']['exit_code'] == 0, 'Outer invocation/exit mismatch')
    ensure(outer['boundaries']['automatic_retries'] == 0 and not outer['boundaries']['source_edits_performed'], 'Outer mutation/retry claim differs')
    for name in source_names:
        ensure(sha(CAP / name) == identity['source_sha256'][name], f'Examined frozen source mismatch: {name}')
    source = (CAP / source_names[0]).read_text()
    functions = {node.name: ast.get_source_segment(source, node) for node in ast.parse(source).body if isinstance(node, ast.FunctionDef)}
    ensure('[tuple(pair) for pair in plan["effective_reserved_ranges"]]' in functions['base_config'], 'Tuple adapter missing')
    ensure('excluded_seed_ranges: Option<Vec<(u32, u32)>>' in (CAP / source_names[1]).read_text(), 'Strict binding signature differs')
    checks.append({'check': 'exact_artifacts_identity_plan_and_examined_source', 'passed': True,
                   'artifact_hashes': 34, 'examined_frozen_sources': len(source_names), 'outer_campaign_invocations': 1})

    # Check each Python phase's exit, worker hash, external RSS, self peak, and bounds.
    phases = {p['name']: p for p in campaign['phases']}
    worker_results = {}
    resource_results = {}
    for name, budget in [('trajectory', 120), ('memory', 600), ('throughput', 120)]:
        phase = phases[name]
        result = read(DATA / f'{name}-result.json')
        ensure(phase['status'] == result['status'] == 'passed' and phase['exit_code'] == 0, f'{name} failed')
        ensure(sha(DATA / f'{name}-result.json') == phase['worker_result_sha256'], f'{name} worker-result hash differs')
        ensure(result['identity_sha256'] == IDENTITY and result['phase'] == name, f'{name} identity/phase differs')
        ensure(phase['wall_limit_seconds'] == budget and 0 < result['elapsed_seconds'] <= phase['elapsed_seconds'] < budget, f'{name} wall guards differ')
        rss = rows(DATA / f'{name}.rss.jsonl')
        ensure(len(rss) == phase['rss_samples'] and rss, f'{name} external RSS sample count differs')
        ensure(all(0 < x['rss_bytes'] <= LIMIT and x['pid'] == phase['owned_pid'] and x['wall_seconds'] < budget for x in rss), f'{name} external RSS guard differs')
        ensure(max(x['rss_bytes'] for x in rss) == phase['observed_peak_worker_rss_bytes'], f'{name} external RSS peak differs')
        ensure(phase['observed_peak_worker_rss_bytes'] <= result['observed_peak_self_rss_bytes'] <= LIMIT, f'{name} self/external peak inconsistent')
        resource_results[name] = {'phase_wall_seconds': phase['elapsed_seconds'], 'worker_wall_seconds': result['elapsed_seconds'],
                                 'external_samples': len(rss), 'external_peak_RSS_bytes': phase['observed_peak_worker_rss_bytes'],
                                 'self_ru_maxrss_bytes': result['observed_peak_self_rss_bytes']}
        worker_results[name] = result
    audit['resources'] = resource_results
    checks.append({'check': 'Python_phase_receipts_time_and_separate_RSS_observations', 'passed': True, 'phases': 3})

    trajectory = worker_results['trajectory']
    expected_cases = [(9, 400, 18000, 14344, 48, 0, 48, 30), (5, 40, 17, 680, 0, 40, 40, 40)]
    ensure(len(trajectory['cases']) == 2, 'Trajectory case count differs')
    for case, expected in zip(trajectory['cases'], expected_cases):
        batch, decisions, cap, raw, deaths, caps, resets, ragged = expected
        ensure(case['config'] == {'batch_size': batch, 'decisions': decisions, 'raw_frame_cap': cap, 'thread_chunk_pairs': [[1, 1], [4, 3]]}, 'Trajectory configuration differs')
        ensure([case[k] for k in ['raw_frames_per_path', 'deaths', 'caps', 'explicit_slot_resets', 'ragged_K_endings']] == [raw, deaths, caps, resets, ragged], 'Trajectory summary differs')
        ensure(batch * decisions <= raw <= 4 * batch * decisions, 'Trajectory elapsed K count impossible')
        ensure(len(case['final_observation_sha256']) == 64 and resets == deaths + caps, 'Trajectory hash/reset counts invalid')
        if cap == 17:
            ensure(raw == 5 * 8 * 17 and caps == 5 * 8 and ragged == caps, 'Cap17 trajectory arithmetic differs')
    for anchor in ['compare_tree(np, a, b)', 'audit_step(np, a, plan, cap)', 'not np.shares_memory', 'np.array_equal(value, sentinels[key])', 'ended[::-1]', 'Subset reset row order differs']:
        ensure(anchor in functions['worker_trajectory'], f'Trajectory executed assertion missing: {anchor}')
    audit['trajectory'] = {'status': 'passed_retained_evidence', 'raw_frames_per_path': 15024, 'deaths': 48, 'caps': 40, 'explicit_slot_resets': 88, 'cases': trajectory['cases'],
                           'evidence_limit': 'Summaries plus exact pinned successful assertion code; no intermediate-array archive.'}
    checks.append({'check': 'trajectory_configuration_arithmetic_and_pinned_equality_ownership_assertions', 'passed': True})

    memory = worker_results['memory']
    ensure(memory['warmup_step_calls'] == 5000 and memory['measured_step_calls'] == 100000, 'Memory call counts differ')
    ensure(memory['config']['batch_size'] == 8 and memory['config']['num_threads'] == 4 and memory['config']['chunk_size'] == 2, 'Memory batch/thread/chunk differs')
    ensure(memory['config']['render_pixels'] and memory['config']['auxiliary_targets'] and memory['config']['action_repeat'] == 4, 'Memory image/target/K differs')
    samples = rows(DATA / 'memory-rss.jsonl')
    ensure([r['measured_step_calls'] for r in samples] == list(range(0, 100001, 1000)), 'Memory RSS indices differ')
    ensure(all(0 < r['rss_bytes'] <= LIMIT for r in samples), 'Memory sampled RSS exceeded limit')
    count = math.ceil(len(samples) * 0.1)
    first = statistics.median(r['rss_bytes'] for r in samples[:count]); last = statistics.median(r['rss_bytes'] for r in samples[-count:])
    growth = last - first
    xs = [r['measured_step_calls'] for r in samples]; ys = [r['rss_bytes'] for r in samples]
    mx = statistics.mean(xs); my = statistics.mean(ys)
    slope = sum((x-mx)*(y-my) for x,y in zip(xs,ys)) / sum((x-mx)**2 for x in xs)
    plate = memory['post_warmup_samples']
    ensure(count == 11 and first == plate['first_median_rss_bytes'] and last == plate['last_median_rss_bytes'], 'Memory endpoint medians differ')
    ensure(growth == plate['median_growth_bytes'] == 3014656 and growth <= plate['median_growth_limit_bytes'] == 67108864, 'Memory plateau differs')
    ensure(plate['sample_count'] == len(samples) == 101 and plate['passed'], 'Memory plateau pass/sample count differs')
    ensure(math.isclose(slope, plate['ols_rss_bytes_per_step_call'], rel_tol=1e-12), 'Memory OLS differs')
    ensure(samples[0]['raw_frames_including_warmup'] == memory['warmup_raw_frames'] == 159023, 'Memory warmup raw frames differ')
    ensure(samples[-1]['raw_frames_including_warmup'] == memory['raw_frames_including_warmup'] == 3339854, 'Memory final raw frames differ')
    ensure(memory['measured_raw_frames'] == memory['raw_frames_including_warmup'] - memory['warmup_raw_frames'] == 3180831, 'Memory measured raw frames differ')

    # Independently reproduce the documented SplitMix64 tuple hash using Python integers.
    mask = 2**64 - 1
    reserved = plan['effective_reserved_ranges']
    ensure(reserved == [[0xB0000000, 0xB00003E7], [0xD0000000, 0xD000007F], [0xE0000000, 0xE00003E7]], 'Reserved B/D/E ranges differ')
    ensure(memory['batch_info']['effective_excluded_seed_ranges'] == memory['config']['excluded_seed_ranges'] == reserved, 'Memory exclusion metadata differs')
    def mix(z):
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & mask
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & mask
        return z ^ (z >> 31)
    def expected_seed(slot, episode):
        base = mix(plan['training_run_seed'] ^ 0x444F4447455F5632) ^ mix((slot + 0x9E3779B97F4A7C15) & mask) ^ mix((episode + 0xD1B54A32D192ED03) & mask)
        counter = 0
        while True:
            value = mix(base ^ mix((counter + 0x94D049BB133111EB) & mask)) >> 32
            if all(not lo <= value <= hi for lo,hi in reserved): return counter, value
            counter += 1
    def check_seed(seed):
        ensure(type(seed['actual_seed']) is int and 0 <= seed['actual_seed'] <= 2**32-1 and not seed.get('evaluation',False), 'Seed type/range/mode differs')
        ensure((seed['counter'], seed['actual_seed']) == expected_seed(seed['slot'], seed['episode']), 'Independent seed tuple hash differs')
    def check_info(info, initial):
        check_seed(info['seed'])
        g,a = info['gameplay_frames'], info['alive_frames']
        ensure(info['startup_frames'] == 13 and 0 <= a <= g <= 18000, 'Episode startup/raw/alive bounds differ')
        ensure(not (info['terminated'] and info['truncated']) and info['bootstrap'] == (not info['terminated']), 'Episode boundary flags differ')
        ensure(info['score_raw_fixed'] == info['score_delta_sum_raw_fixed'] >= 0 and info['score'] == info['score_raw_fixed']/65536, 'Episode fixed score accounting differs')
        ensure(info['objective_return'] == info['score_raw_fixed']/65536 + a/100 - 5*info['terminated'], 'Episode objective differs')
        if initial: ensure(g == a == 0 and info['objective_return'] == 0 and not info['terminated'] and not info['truncated'], 'Reset episode not fresh')
        else: ensure(info['terminated'] or info['truncated'], 'Ended stream includes non-ended episode')
    stream = rows(DATA / 'memory-episodes.jsonl')
    ensure(stream[0]['kind'] == 'initial' and len(stream[0]['info']) == 8, 'Memory initial stream differs')
    current = {}; last_reset = {}; completed = Counter(); completed_frames = Counter(); completed_alive = Counter(); seen_tuples = set(); seed_values = []
    ended_total = deaths = caps = 0
    for info in stream[0]['info']:
        check_info(info, True); slot=info['seed']['slot'];ensure(slot not in current and info['seed']['episode']==0, 'Duplicate/missing initial slot')
        current[slot]=info['seed'];last_reset[slot]=0;seen_tuples.add((slot,0));seed_values.append(info['seed']['actual_seed'])
    ensure(set(current)==set(range(8)), 'Memory slot set differs')
    pending = None; previous_call=0; warmup_reconstructed = None
    for record in stream[1:]:
        call=record['step_call'];ensure(previous_call <= call <= 105000, 'Memory stream call order differs')
        if warmup_reconstructed is None and call > 5000:
            warmup_reconstructed = sum(completed_frames.values()) + sum((5000-last_reset[i])*4 for i in current)
        previous_call=call
        if record['kind']=='ended':
            ensure(pending is None and record['info'], 'Unpaired ended/reset records')
            pending=[]
            for info in record['info']:
                check_info(info, False);seed=info['seed'];slot=seed['slot'];ensure(seed==current[slot], 'Ended episode identity differs')
                ensure(slot not in pending and 1 <= call-last_reset[slot], 'Duplicate ended slot or empty episode')
                g=info['gameplay_frames'];ensure(0 <= (call-last_reset[slot])*4-g <=3, 'Raw episode frames not consistent with K4 calls')
                if info['terminated']: ensure(info['alive_frames']==g-1, 'Death-frame survival credit differs')
                if info['truncated']: ensure(g==18000 and info['alive_frames']==g, 'Truncation count differs')
                pending.append(slot);completed[slot]+=1;completed_frames[slot]+=g;completed_alive[slot]+=info['alive_frames'];ended_total+=1;deaths+=info['terminated'];caps+=info['truncated']
        elif record['kind']=='reset':
            ensure(pending==[i['seed']['slot'] for i in record['info']], 'Reset row order or paired slots differs')
            for info in record['info']:
                check_info(info, True);seed=info['seed'];slot=seed['slot'];ensure(seed['episode']==current[slot]['episode']+1, 'Episode counter did not advance')
                ensure((slot,seed['episode']) not in seen_tuples,'Seed tuple reused');seen_tuples.add((slot,seed['episode']));seed_values.append(seed['actual_seed']);current[slot]=seed;last_reset[slot]=call
            pending=None
        else: raise AssertionError('Unknown memory stream record kind')
    ensure(pending is None, 'Unpaired final ended record')
    final_frames=sum(completed_frames.values())+sum((105000-last_reset[i])*4 for i in current)
    ensure(warmup_reconstructed==159023 and final_frames==3339854, 'Independent episode+active-slot raw-frame reconstruction differs')
    ensure(ended_total==deaths==memory['explicit_slot_resets']==memory['deaths_including_warmup']==13155 and caps==memory['caps_including_warmup']==0, 'Memory reset/death/cap totals differ')
    ensure([current[i]['episode']+1 for i in range(8)]==memory['batch_info']['next_episode_indices'], 'Memory next episode indices differ')
    for anchor in ['range(stage["warmup_step_calls"] + stage["measured_step_calls"])', 'audit_step(np, result, plan', 'not np.shares_memory', 'np.array_equal(value, frozen[key])']:
        ensure(anchor in functions['worker_memory'], f'Memory executed checking code missing: {anchor}')
    audit['memory']={'status':'passed_retained_evidence','warmup_calls':5000,'measured_calls':100000,'samples':len(samples),'endpoint_samples_each':count,
                     'first_median_RSS_bytes':first,'last_median_RSS_bytes':last,'median_growth_bytes':growth,'limit_bytes':67108864,'OLS_bytes_per_call':slope,
                     'stream_records':len(stream),'completed_episodes':ended_total,'seed_assignments_checked':len(seed_values),'distinct_actual_seeds':len(set(seed_values)),
                     'independently_reconstructed_warmup_raw_frames':warmup_reconstructed,'independently_reconstructed_total_raw_frames':final_frames,'measured_raw_frames':final_frames-warmup_reconstructed,
                     'deaths':deaths,'caps':caps,'empirical_plateau_only':True}
    checks.append({'check':'memory_RSS_plateau_episode_objectives_seed_stream_and_raw_frame_reconstruction','passed':True})

    throughput=worker_results['throughput'];measurements=throughput['measurements'];ensure(len(measurements)==4,'Throughput config count differs')
    ensure([(m['config']['render_pixels'],m['config']['num_threads'],m['config']['chunk_size']) for m in measurements]==[(False,1,1),(False,4,8),(True,1,1),(True,4,8)],'Throughput configuration order differs')
    seed_logs=[];timings=[]
    for measurement in measurements:
        m=measurement;ensure(m['config']['batch_size']==32 and not m['config']['auxiliary_targets'] and m['config']['action_repeat']==4,'Throughput B/aux/K differs')
        ensure(m['batch_info']['effective_excluded_seed_ranges']==reserved,'Throughput exclusions differ')
        ensure(m['warmup_step_calls']==200 and m['measured_step_calls']==2000 and m['environment_decisions']==64000,'Throughput call/work counts differ')
        wall=m['wall_seconds'];ensure(0<wall<=60,'Throughput config exceeded time guard')
        for key,numerator in [('public_step_calls_per_second',2000),('environment_decisions_per_second',64000),('raw_gameplay_frames_per_second',m['raw_gameplay_frames'])]:
            ensure(math.isclose(m[key],numerator/wall,rel_tol=1e-12),f'Throughput rate differs: {key}')
        ensure(64000<=m['raw_gameplay_frames']<=256000,'Throughput raw-frame count outside K bounds')
        seedpath=DATA/m['actual_seed_log'];ensure(sha(seedpath)==m['actual_seed_log_sha256'],'Throughput raw seed-log hash differs')
        log=rows(seedpath);ensure(len(log)==m['actual_seed_assignments']==1112,'Throughput seed assignment count differs')
        digest=hashlib.sha256();episodes={};counts=Counter();previous_position=(-1,-1)
        for row in log:
            phase=row['phase'];position=({'initial':0,'warmup_reset':1,'timed_reset':2}[phase],row['step_call']);ensure(position>=previous_position,'Throughput seed log reordered');previous_position=position
            slot=row['slot'];ensure(0<=slot<32,'Throughput slot outside batch');ensure(row['episode']==episodes.get(slot,-1)+1,'Throughput episode assignment not fresh/sequential');episodes[slot]=row['episode'];check_seed(row)
            if phase=='initial': ensure(row['step_call']==row['episode']==0,'Throughput initial assignment differs')
            elif phase=='warmup_reset': ensure(1<=row['step_call']<=200,'Throughput warmup call outside bounds')
            else: ensure(1<=row['step_call']<=2000,'Throughput timed reset outside bounds')
            counts[phase]+=1;digest.update(struct.pack('<QQQI',row['slot'],row['episode'],row['counter'],row['actual_seed']))
        ensure(counts=={'initial':32,'warmup_reset':85,'timed_reset':995} and counts['timed_reset']==m['explicit_slot_resets'],'Throughput reset phases differ')
        ensure(digest.hexdigest()==m['actual_reset_seed_schedule_sha256'],'Independent binary seed schedule hash differs')
        ensure([episodes[i]+1 for i in range(32)]==m['batch_info']['next_episode_indices'],'Throughput final seed counters differ')
        seed_logs.append(log);timings.append({'render_pixels':m['config']['render_pixels'],'threads':m['config']['num_threads'],'chunk_size':m['config']['chunk_size'],'wall_seconds':wall,'public_calls_per_second':m['public_step_calls_per_second'],'environment_decisions_per_second':m['environment_decisions_per_second'],'raw_frames_per_second':m['raw_gameplay_frames_per_second']})
    ensure(all(log==seed_logs[0] for log in seed_logs[1:]),'Throughput actual seed schedules differ')
    for key in ['action_schedule_sha256','work_schedule_sha256','final_neural_arrays_sha256','actual_reset_seed_schedule_sha256','raw_gameplay_frames','explicit_slot_resets']:
        ensure(len({m[key] for m in measurements})==1,f'Paired throughput evidence differs: {key}')
    ensure(sum(m['wall_seconds'] for m in measurements)<=throughput['elapsed_seconds'],'Timed config loops exceed worker time')
    ensure('require(elapsed <= stage["per_config_wall_seconds"]' in functions['worker_throughput'],'Post-loop throughput guard missing')
    audit['throughput']={'status':'passed_retained_evidence','measurements':timings,'raw_frames_per_config':254497,'timed_slot_resets_per_config':995,'seed_assignments_per_config':1112,
                         'independently_recomputed_seed_schedule_sha256':measurements[0]['actual_reset_seed_schedule_sha256'],'same_actual_seed_rows_all4':True,'hash_equality_for_action_work_final_neural_arrays':True,'public_API_workload_only':True}
    checks.append({'check':'throughput_paired_seed_streams_hash_equality_rates_and_bounds','passed':True})

    after={str(p.relative_to(ROOT)):sha(p) for p in inputs}
    ensure(after==before,'Audited inputs changed during independent audit')
    checks.append({'check':'input_preservation','passed':True,'files':len(before)})
    audit['status']='passed_python_retained_evidence_scope;parent_full_M2_acceptance_required'
except Exception as error:
    audit['status']='failed_audit'
    audit['failures'].append({'error':repr(error),'traceback':traceback.format_exc()})
finally:
    audit['checker_sha256']=sha(Path(__file__))
    save_new(OWN/'audit.json',audit)
    print(json.dumps({'status':audit['status'],'failures':audit['failures'],'checks':len(checks),'audit_sha256':sha(OWN/'audit.json')},sort_keys=True))
    if audit['failures']: raise SystemExit(1)
