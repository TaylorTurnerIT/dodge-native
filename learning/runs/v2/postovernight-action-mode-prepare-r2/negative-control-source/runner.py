#!/usr/bin/env python3
"""Paired action-mode diagnostic. Preparation/tests never enter main's worker path.

Production execution requires a parent-reviewed, read-only source capsule and an
exact diagnostic lease. This does not use or alter the overnight training guard.
All model/native imports are lazy and exclusive to the supervised worker.
"""
from __future__ import annotations

import time
LAUNCH_MONOTONIC = time.monotonic()

import argparse
from contextlib import contextmanager
import hashlib
import io
import json
import math
import os
from pathlib import Path
import platform
import resource
import signal
import subprocess
import sys
import threading
import time
import traceback

ORIGINAL_ROOT = Path('/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79')
ROOT = Path(__file__).resolve().parents[4]
PROTOCOL_REL = 'learning/runs/v2-orchestration/postovernight-action-mode-r1-protocol.json'
PROTOCOL_SHA256 = '4e8ee5fb6141f9112e16190f2436f43f6c9127fcedbf51e3b3696523f47fe8db'
STATE_PATH = ORIGINAL_ROOT / 'learning/runs/v2-orchestration/state.json'
SEEDS = tuple(range(3489660928, 3489660992))
CONTROLLER_SEEDS = (64001, 64002, 64003)
LABELS = ('entry', 'phase96', 'phase104')
OBSERVATION_KEYS = ('global_feats', 'entity_feats', 'entity_types', 'entity_mask')
ROW_KEYS = ('episode_index', 'seed', 'score_raw_fixed', 'score', 'alive_frames',
            'gameplay_frames', 'terminated', 'truncated', 'objective_return')
LIMIT = 6 * 1024**3
SAMPLE_SECONDS = 0.25


class Stop(RuntimeError):
    pass


def require(ok, message):
    if not ok:
        raise Stop(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def emit(stream, value):
    stream.write(json.dumps(value, sort_keys=True, allow_nan=False) + '\n')
    stream.flush()


def save(path, value):
    # Exclusive creation retains earlier receipts and prevents an accidental retry.
    with Path(path).open('x') as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')


def verify_files(pins):
    for path, digest in pins.items():
        require(Path(path).is_file() and sha(path) == digest, f'Input hash mismatch: {path}')


def assert_lease(state_path, protocol, protocol_hash, harness_hash, capsule_hash):
    lease = json.loads(Path(state_path).read_text()).get('active_long_campaign')
    expected = {'kind': 'M3_action_mode_diagnostic',
                'authorization': 'new_postovernight_inference_only',
                'run_id': protocol['run_id'], 'protocol_sha256': protocol_hash,
                'harness_sha256': harness_hash,
                'frozen_capsule_manifest_sha256': capsule_hash,
                'frozen_capsule_path': str(ROOT)}
    require(isinstance(lease, dict) and all(lease.get(k) == v for k, v in expected.items()),
            'Exact parent-owned diagnostic lease missing or changed')
    require(lease.get('cancel_requested', False) is False, 'Parent requested cancellation')
    return lease


def registered_protocol(path):
    require(sha(path) == PROTOCOL_SHA256, 'Parent protocol hash mismatch')
    p = json.loads(Path(path).read_text())
    require(p['wall_budget_seconds'] == 600 and p['cleanup_reserve_seconds'] == 10
            and p['episodes_expected'] == 768 and len(p['foundation_sources']) == 75,
            'Registered diagnostic bounds differ')
    require(p['order'] == [f'{label}_argmax' for label in LABELS] +
            [f'{label}_sample{seed}' for seed in CONTROLLER_SEEDS for label in LABELS],
            'Registered order differs')
    require(p['device'] == 'mps' and p['dtype'] == 'float32' and p['torch_num_threads'] == 4,
            'Original inference settings required')
    require(p['development_seeds']['first'] == SEEDS[0]
            and p['development_seeds']['last'] == SEEDS[-1]
            and p['development_seeds']['count'] == 64, 'Only D cohort is authorized')
    return p


def input_pins(p, protocol_path, capsule_manifest):
    files = dict(p['foundation_sources'])
    files[p['foundation_identity_path']] = p['foundation_identity_sha256']
    files[PROTOCOL_REL] = PROTOCOL_SHA256
    for item in p['checkpoints']:
        files[item['path']] = item['sha256']
        if item['control']:
            files[item['control']] = item['control_sha256']
    require(all(capsule_manifest['files'].get(k) == v for k, v in files.items()),
            'Capsule lacks exact protocol/foundation/checkpoints/controls')
    pins = {str(ROOT / k): v for k, v in capsule_manifest['files'].items()}
    for name, value in files.items():
        pins[str(ORIGINAL_ROOT / name)] = value
    pins[str(protocol_path)] = PROTOCOL_SHA256
    pins[p['foundation_runtime']['interpreter']] = p['foundation_runtime']['interpreter_sha256']
    foundation = json.loads((ROOT / p['foundation_identity_path']).read_text())
    pins.update(foundation['foundation']['binary_and_receipt_sha256'])
    return pins, foundation


def assert_readonly_capsule(manifest):
    require(ROOT != ORIGINAL_ROOT, 'Execute the reviewed runner inside its read-only capsule')
    require(manifest.get('version') == 'action_mode_capsule_v1', 'Unknown capsule manifest')
    for name in manifest['files']:
        relative = Path(name)
        require(not relative.is_absolute() and '..' not in relative.parts, 'Unsafe capsule member')
        path = ROOT / relative
        require(path.resolve().is_relative_to(ROOT) and not path.is_symlink(), 'Capsule member escaped root')
        require(path.is_file() and not path.stat().st_mode & 0o222, 'Capsule file is writable')
        for parent in (path.parent, *path.parents):
            if not parent.is_relative_to(ROOT):
                break
            require(not parent.stat().st_mode & 0o222, 'Capsule directory is writable')
    require(not (ROOT / 'capsule-manifest.json').stat().st_mode & 0o222,
            'Capsule manifest is writable')


def sampled_rss(pid):
    r = subprocess.run(['ps', '-o', 'rss=', '-p', str(pid)], capture_output=True,
                       text=True, timeout=0.2)
    require(r.returncode == 0 and r.stdout.strip().isdigit(), 'RSS probe failed')
    return int(r.stdout.strip()) * 1024


def self_peak():
    n = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(n if sys.platform == 'darwin' else n * 1024)


class DiagnosticGuard:
    """Cutoff-independent guard; sampling thread plus every inference/step boundary.

    Identity/resource failures are latched. The supervisor separately enforces
    the absolute wall deadline even if Python imports or a native call block.
    """
    def __init__(self, deadline, verify, stream, *, clock=time.monotonic,
                 rss=lambda: sampled_rss(os.getpid()), peak=self_peak, mps=lambda: 0):
        self.deadline, self.verify, self.stream = deadline, verify, stream
        self.clock, self.rss, self.peak, self.mps = clock, rss, peak, mps
        self.maximum_sampled_rss = self.maximum_self_peak = self.maximum_mps = 0
        self.failure = None
        self.last_sample = None
        self.maximum_sample_gap = 0.0
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.thread = None

    def check(self):
        if self.failure is not None:
            raise Stop(f'Latched guard failure: {self.failure}')
        require(self.clock() < self.deadline, '600-second diagnostic deadline reached')

    def sample(self):
        with self.lock:
            self.check()
            at = self.clock()
            self.verify()
            rss, peak, mps = self.rss(), self.peak(), self.mps()
            require(all(type(v) is int and v >= 0 for v in (rss, peak, mps)), 'Invalid resource probe')
            self.maximum_sampled_rss = max(self.maximum_sampled_rss, rss)
            self.maximum_self_peak = max(self.maximum_self_peak, peak)
            self.maximum_mps = max(self.maximum_mps, mps)
            gap = 0 if self.last_sample is None else at - self.last_sample
            self.maximum_sample_gap = max(self.maximum_sample_gap, gap)
            self.last_sample = at
            emit(self.stream, {'monotonic': at, 'pid': os.getpid(), 'sampled_rss_bytes': rss,
                               'self_peak_rss_bytes': peak, 'mps_driver_bytes': mps,
                               'sample_gap_seconds': gap})
            require(gap <= 0.5, 'Guard sample interval exceeded 0.5 seconds')
            require(max(rss, peak) <= LIMIT, 'RSS limit exceeded')
            require(mps <= LIMIT, 'MPS driver limit exceeded')
            self.check()

    def start(self):
        self.sample()
        def monitor():
            while not self.stop_event.wait(SAMPLE_SECONDS):
                try:
                    self.sample()
                except BaseException as error:
                    self.failure = repr(error)
                    return
        self.thread = threading.Thread(target=monitor, name='diagnostic-guard', daemon=True)
        self.thread.start()

    def close(self):
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=0.5)
            require(not self.thread.is_alive(), 'Guard sampler did not stop')

    def receipt(self):
        return {'maximum_sampled_rss_bytes': self.maximum_sampled_rss,
                'maximum_self_peak_rss_bytes': self.maximum_self_peak,
                'maximum_mps_driver_bytes': self.maximum_mps,
                'maximum_sample_gap_seconds': self.maximum_sample_gap,
                'latched_failure': self.failure}


@contextmanager
def cancellation_signals():
    previous, cancelling = {}, [False]
    def handle(number, frame):
        if not cancelling[0]:
            cancelling[0] = True
            raise KeyboardInterrupt(f'Cancellation signal {signal.Signals(number).name}')
    try:
        for sig in (signal.SIGINT, signal.SIGTERM):
            previous[sig] = signal.getsignal(sig)
            signal.signal(sig, handle)
        yield lambda: cancelling.__setitem__(0, True)
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def stop_owned(process):
    """Terminate/reap only the exact new-session group created by the supervisor.

    macOS can report EPERM for a just-disappeared group; retain that probe and
    independently check the process table before concluding that it is absent.
    """
    require(process.pid > 1 and process.pid != os.getpgrp(), 'Unsafe owned process group')
    start = time.monotonic()
    receipt = {'owned_pid': process.pid, 'owned_pgid': process.pid, 'errors': [], 'probe_notes': []}
    def group_exists():
        try:
            os.killpg(process.pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError as error:
            receipt['probe_notes'].append(repr(error))
            probe = subprocess.run(['ps', '-axo', 'pgid='], capture_output=True, text=True, timeout=0.2)
            require(probe.returncode == 0, 'Cannot prove owned group absence')
            return process.pid in [int(x) for x in probe.stdout.split()]
    for sig, allowance in ((signal.SIGTERM, 5.0), (signal.SIGKILL, 5.0)):
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            pass
        except PermissionError as error:
            # A pre-exec/session race or permission failure is retained. Never
            # target an inherited process group or another process instead.
            receipt['errors'].append(repr(error))
        end = min(start + 9.5, time.monotonic() + allowance)
        while time.monotonic() < end:
            process.poll()
            try:
                if not group_exists():
                    break
            except BaseException as error:
                receipt['errors'].append(repr(error))
                break
            time.sleep(min(0.02, max(0, end - time.monotonic())))
        try:
            process.wait(timeout=max(0.001, end - time.monotonic()))
        except subprocess.TimeoutExpired:
            continue
        if sig == signal.SIGTERM:
            try:
                if not group_exists():
                    break
            except BaseException as error:
                receipt['errors'].append(repr(error))
    try:
        group_empty = not group_exists()
    except BaseException as error:
        receipt['errors'].append(repr(error))
        group_empty = False
    receipt.update(reaped=process.poll() is not None, group_empty=group_empty,
                   exit_code=process.returncode, cleanup_seconds=time.monotonic() - start)
    return receipt


def validate_checkpoint(state, item, identity):
    require(state.get('version') == 'teacher_checkpoint_v1' and state.get('resume_mode') == 'fresh_env',
            'Unknown checkpoint format')
    expected_tag = 'periodic' if item['label'] == 'phase104' else 'candidate'
    progress = state.get('update_progress', {})
    require(state.get('tag') == expected_tag and not progress.get('in_update', False)
            and (not progress or progress.get('complete') is True), 'Incomplete checkpoint rejected')
    require(state.get('identity') == identity
            and state.get('identity_sha256') == hashlib.sha256(canonical(identity)).hexdigest(),
            'Checkpoint semantic identity mismatch')
    counters = state.get('counters', {})
    require(set(counters) == {'updates', 'phase_updates', 'optimizer_steps', 'environment_decisions',
                              'raw_frames', 'checkpoint_index'}
            and all(type(v) is int and v >= 0 for v in counters.values()), 'Invalid checkpoint counters')
    require(counters['phase_updates'] == item['phase_updates']
            and counters['checkpoint_index'] == {'entry': 10, 'phase96': 22, 'phase104': 23}[item['label']]
            and counters['updates'] == 48 + item['phase_updates'], 'Complete checkpoint update counters differ')
    require(state.get('parent_checkpoint_sha256') == identity['config']['parent_checkpoint_sha256'],
            'Checkpoint parent identity differs')


def load_diagnostic_model(torch, np, teacher_class, item, p, identity, guard):
    # The three exact protocol paths/hashes are the only accepted deserialization inputs.
    require(item in p['checkpoints'], 'Unpinned checkpoint requested')
    path = ROOT / item['path']
    guard.check()
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == item['sha256'], 'Checkpoint changed before load')
    safe = [np._core.multiarray._reconstruct, np.ndarray, np.dtype,
            *(type(np.dtype(n)) for n in ('uint32', 'int64', 'float64', 'uint64', 'bool', 'float32', 'int32'))]
    with torch.serialization.safe_globals(safe):
        state = torch.load(io.BytesIO(raw), map_location='cpu', weights_only=True)
    validate_checkpoint(state, item, identity)
    model = teacher_class()
    require(model.architecture_description() == p['architecture'], 'Teacher architecture changed')
    expected, actual = model.state_dict(), state['model']
    require(set(actual) == set(expected) and all(actual[k].shape == v.shape
            and actual[k].dtype == torch.float32 and bool(torch.isfinite(actual[k]).all())
            for k, v in expected.items()), 'Strict checkpoint shapes/dtypes/finite values differ')
    model.load_state_dict(actual, strict=True)
    # Never restore optimizer, RNG, episode state, or transition eligibility.
    del state, raw, actual, expected
    model.to(device='mps', dtype=torch.float32).eval()
    require(all(param.grad is None for param in model.parameters()), 'Unexpected parameter gradients')
    guard.check()
    return model


def validate_row(row):
    require(set(row) == set(ROW_KEYS), 'Original development row fields differ')
    require(type(row['episode_index']) is int and 0 <= row['episode_index'] < 64
            and row['seed'] == SEEDS[row['episode_index']], 'Wrong D seed/index')
    a, g, s = row['alive_frames'], row['gameplay_frames'], row['score_raw_fixed']
    require(type(a) is int and type(g) is int and 0 <= a <= g <= 18000, 'Frame bounds differ')
    require(type(s) is int and s >= 0 and math.isfinite(row['score'])
            and row['score'] == s / 65536, 'Score identity differs')
    t, c = row['terminated'], row['truncated']
    require(type(t) is bool and type(c) is bool and t != c, 'Endpoint flags differ')
    require((t and g == a + 1) or (c and g == a == 18000), 'Endpoint frame identity differs')
    require(math.isfinite(row['objective_return']) and math.isclose(row['objective_return'],
            s / 65536 + a / 100 - 5 * t, rel_tol=0, abs_tol=1e-9), 'Objective identity differs')


def indexed_rows(rows):
    require(len(rows) == 64, 'Expected all 64 game seeds exactly once')
    for row in rows:
        validate_row(row)
    result = {r['seed']: r for r in rows}
    require(len(result) == 64 and set(result) == set(SEEDS), 'Incomplete/duplicate D seeds')
    return result


def compare_control(rows, saved):
    actual, expected = indexed_rows(rows), indexed_rows(saved)
    for seed in SEEDS:
        require(actual[seed] == expected[seed], f'Exact historical control mismatch at seed {seed}')
    return {'matched': True, 'seeds': 64, 'fields': list(ROW_KEYS), 'comparison': 'field_for_field'}


def context(info, prior=None):
    d = info['diagnostics']
    counts = {k: d[k] for k in ('admitted_enemies', 'admitted_rectangles', 'onscreen_warnings')}
    require(all(type(v) is int and v >= 0 for v in counts.values()), 'Invalid observation diagnostics')
    pattern = counts['admitted_rectangles'] > 0 or counts['onscreen_warnings'] > 0
    prior = prior or {'observations': 0, 'enemy_presence_observations': 0,
                      'pattern_presence_observations': 0, 'rectangle_presence_observations': 0,
                      'warning_presence_observations': 0, 'first_observed_pattern_gameplay_frame': None}
    prior['observations'] += 1
    prior['enemy_presence_observations'] += int(counts['admitted_enemies'] > 0)
    prior['pattern_presence_observations'] += int(pattern)
    prior['rectangle_presence_observations'] += int(counts['admitted_rectangles'] > 0)
    prior['warning_presence_observations'] += int(counts['onscreen_warnings'] > 0)
    if pattern and prior['first_observed_pattern_gameplay_frame'] is None:
        prior['first_observed_pattern_gameplay_frame'] = info['gameplay_frames']
    return {**prior, 'terminal_observation_counts': counts, 'context_presence_only': True,
            'death_cause': 'UNKNOWN', 'startup_native_updates': 7,
            'timing_note': '420 is a native schedule counter; first visibility is observed at K4 boundaries'}


def evaluate(model, mode, controller_seed, checkpoint, guard, episode_stream, trace_stream,
             counters, *, torch, np, env_factory, config_factory, device='mps'):
    """Mirror dev_eval.evaluate: 64 B1 environments, sorted shrinking active batch.

    Only action selection and streamed diagnostics are added. No reset/filler.
    Synthetic tests inject tiny CPU policies and fake environments directly;
    production has no CLI device override and always supplies original helpers.
    """
    require(mode in {'argmax', 'sample'}, 'Invalid action mode')
    require((mode == 'argmax' and controller_seed is None)
            or (mode == 'sample' and controller_seed in CONTROLLER_SEEDS), 'Invalid controller seed')
    environments, observations, contexts, decisions, frames, rows = {}, {}, {}, {}, {}, {}
    provenance = {'checkpoint': checkpoint, 'mode': mode, 'controller_seed': controller_seed}
    model.eval()
    with torch.no_grad():
        if mode == 'sample':
            torch.manual_seed(controller_seed)
            if device == 'mps':
                torch.mps.manual_seed(controller_seed)
        for index, seed in enumerate(SEEDS):
            guard.check()
            config = config_factory(seed, 'D2')
            expected = {'batch_size': 1, 'action_repeat': 4, 'difficulty': 2,
                        'patterns_enabled': True, 'powerups_enabled': True, 'raw_frame_cap': 18000,
                        'num_threads': 1, 'chunk_size': 1, 'render_pixels': False,
                        'auxiliary_targets': False, 'seeds_by_slot': [[seed]]}
            require(all(config.get(k) == v for k, v in expected.items()), 'D2 configuration changed')
            env = env_factory(**config)
            counters['environments_created'] += 1
            info = env.episode_info()[0]
            require(info['seed']['evaluation'] is True and info['seed']['actual_seed'] == seed
                    and info['seed']['episode'] == 0 and info['startup_frames'] == 13
                    and info['gameplay_frames'] == info['alive_frames'] == 0
                    and info['score_raw_fixed'] == 0 and not info['terminated'] and not info['truncated'],
                    'Fresh D seed/startup assertion failed')
            environments[index], observations[index] = env, env.observations()
            contexts[index], decisions[index], frames[index] = context(info), 0, 0
            guard.check()
        while environments:
            guard.check()
            active = sorted(environments)
            tensors = {name: torch.from_numpy(np.concatenate([observations[i][name] for i in active],
                        axis=0)).to(device) for name in OBSERVATION_KEYS}
            guard.check()
            output = model(*(tensors[name] for name in OBSERVATION_KEYS))
            counters['inference_calls'] += 1
            guard.check()
            logits = output.logits
            require(logits.shape == (len(active), 9) and bool(torch.isfinite(logits).all()),
                    'Nonfinite development policy')
            distribution = torch.distributions.Categorical(logits=logits)
            argmax = logits.argmax(dim=-1)
            chosen = distribution.sample() if mode == 'sample' else argmax
            probabilities = distribution.probs
            top = probabilities.topk(2, dim=-1).values
            packed = torch.cat((probabilities, distribution.entropy()[:, None], top[:, :1],
                                (top[:, 0] - top[:, 1])[:, None]), dim=1).cpu().numpy()
            actions, maxima = chosen.cpu().numpy(), argmax.cpu().numpy()
            require(bool(np.isfinite(packed).all()), 'Nonfinite probabilities/entropy')
            del distribution, output, tensors, logits, probabilities, top, chosen, argmax
            guard.check()
            for position, index in enumerate(active):
                guard.check()
                values = packed[position]
                emit(trace_stream, {**provenance, 'episode_index': index, 'episode_seed': SEEDS[index],
                     'decision_index': decisions[index], 'gameplay_frames_before_step': frames[index],
                     'argmax_action': int(maxima[position]), 'chosen_action': int(actions[position]),
                     'probabilities9': values[:9].tolist(), 'entropy': float(values[9]),
                     'top1_probability': float(values[10]), 'top1_top2_margin': float(values[11])})
                counters['decisions_logged'] += 1
                guard.check()
                result = environments[index].step(np.array([actions[position]], dtype=np.int64))
                counters['native_step_calls'] += 1
                guard.check()
                info = result['info'][0]
                require(info['seed']['actual_seed'] == SEEDS[index]
                        and info['seed']['evaluation'] is True and info['seed']['episode'] == 0
                        and info['startup_frames'] == 13, 'Development seed/startup changed')
                terminated, truncated = bool(result['terminated'][0]), bool(result['truncated'][0])
                require(not (terminated and truncated) and info['bootstrap'] == (not terminated)
                        and info['terminated'] == terminated and info['truncated'] == truncated,
                        'Development boundary flags differ')
                require(info['score_raw_fixed'] == info['score_delta_sum_raw_fixed']
                        and info['score'] == info['score_raw_fixed'] / 65536, 'Development score identity failed')
                require(math.isfinite(info['objective_return']) and math.isclose(info['objective_return'],
                        info['score_raw_fixed'] / 65536 + info['alive_frames'] / 100 - 5 * terminated,
                        rel_tol=0, abs_tol=1e-9), 'Development objective identity failed')
                require(frames[index] < info['gameplay_frames'] <= min(frames[index] + 4, 18000),
                        'K4 frame progression failed')
                decisions[index] += 1
                frames[index] = info['gameplay_frames']
                contexts[index] = context(info, contexts[index])
                if terminated or truncated:
                    row = {'episode_index': index, 'seed': info['seed']['actual_seed'],
                           'score_raw_fixed': info['score_raw_fixed'], 'score': info['score_raw_fixed'] / 65536,
                           'alive_frames': info['alive_frames'], 'gameplay_frames': info['gameplay_frames'],
                           'terminated': terminated, 'truncated': truncated,
                           'objective_return': info['objective_return']}
                    validate_row(row)
                    rows[index] = row
                    emit(episode_stream, {**provenance, 'row': row, 'context': contexts[index],
                                          'decisions': decisions[index]})
                    counters['episodes_completed'] += 1
                    del environments[index], observations[index], contexts[index]
                else:
                    observations[index] = result['observations']
            guard.check()
    result = [rows[i] for i in range(64)]
    indexed_rows(result)
    return result


def execute_order(p, evaluate_one, controls, guard, event_stream, matches=None):
    results = {}
    matches = {} if matches is None else matches
    for name in p['order']:
        guard.check()
        label, suffix = name.split('_')
        mode = 'argmax' if suffix == 'argmax' else 'sample'
        if mode == 'sample':
            require(set(matches) == {'entry', 'phase96'} and all(x['matched'] for x in matches.values()),
                    'Historical controls must match before sampling')
        rows = evaluate_one(label, mode, None if mode == 'argmax' else int(suffix[6:]))
        results[name] = rows
        emit(event_stream, {'event': 'evaluation_complete', 'evaluation': name, 'rows': rows})
        if label in controls and mode == 'argmax':
            matches[label] = compare_control(rows, controls[label])
            emit(event_stream, {'event': 'historical_control', 'checkpoint': label, **matches[label]})
        guard.check()
    return results, matches


def paired_statistics(results, np, check=lambda: None):
    require(set(results) == {f'{l}_argmax' for l in LABELS} |
            {f'{l}_sample{s}' for s in CONTROLLER_SEEDS for l in LABELS}, 'Incomplete diagnostic matrix')
    # One set of resampled seed indices for every metric and checkpoint.
    rng = np.random.default_rng(764002)
    indices = rng.integers(0, 64, size=(10000, 64))
    output = {}
    for label in LABELS:
        check()
        base = indexed_rows(results[f'{label}_argmax'])
        sampled = [indexed_rows(results[f'{label}_sample{s}']) for s in CONTROLLER_SEEDS]
        delta, metrics, clusters = [], {}, []
        for seed in SEEDS:
            check()
            b = [float(base[seed][m]) for m in ('alive_frames', 'score')]
            a = [sum(r[seed][m] for r in sampled) / 3 for m in ('alive_frames', 'score')]
            delta.append([a[j] - b[j] for j in range(2)])
            clusters.append({'seed': seed, 'argmax_alive_score': b, 'sampled_replicate_mean_alive_score': a,
                             'paired_delta_alive_score': delta[-1]})
        d = np.asarray(delta, dtype=np.float64)
        boot = d[indices].mean(axis=1)
        check()
        ci = np.percentile(boot, [2.5, 97.5], axis=0)
        for j, (metric, margin) in enumerate((('alive_frames', 100), ('score', 1))):
            metrics[metric] = {'argmax_mean': sum(base[s][metric] for s in SEEDS) / 64,
                              'sampled_mean': sum(sum(r[s][metric] for r in sampled) / 3 for s in SEEDS) / 64,
                              'paired_mean_delta': float(d[:, j].mean()),
                              'ci95': ci[:, j].tolist(), 'practical_margin': margin}
        if all(v['ci95'][0] > -v['practical_margin'] and v['ci95'][1] < v['practical_margin'] for v in metrics.values()):
            decision = 'practical_similarity'
        elif all(v['ci95'][0] > v['practical_margin'] for v in metrics.values()):
            decision = 'meaningful_stochastic_advantage'
        elif all(v['ci95'][1] < -v['practical_margin'] for v in metrics.values()):
            decision = 'meaningful_argmax_advantage'
        else:
            decision = 'mixed_or_inconclusive'
        output[label] = {'role': 'primary' if label == 'phase104' else 'secondary',
                         'seed_clusters': 64, 'argmax_episodes': 64, 'sampled_episodes': 192,
                         'replicates_per_seed': 3, 'bootstrap_draws': 10000, 'bootstrap_seed': 764002,
                         'shared_resampled_indices': True, 'metrics': metrics, 'decision': decision,
                         'paired_clusters': clusters}
    return output


def baseline_result():
    return {'status': 'failed', 'diagnostic_only': True, 'qualification': False,
            'training_eligibility_changed': False, 'automatic_retries': 0,
            'B_opened': False, 'E_opened': False, 'gradient_updates': 0,
            'optimizer_instantiations': 0, 'checkpoint_writes': 0,
            'inference_calls': 0, 'native_step_calls': 0, 'environments_created': 0,
            'decisions_logged': 0, 'episodes_completed': 0, 'evaluations_completed': 0,
            'death_cause': 'UNKNOWN', 'checkpoint_selection': None,
            'control_matches': {}, 'gradients_observed': False,
            'wall_budget_includes': 'imports, load, evaluation, streamed logging, controls, statistics, worker receipts',
            'resource_semantics': 'Sampled RSS, self peak RSS and sampled MPS driver allocation; no hard OS memory cap.'}


def worker(args, p, pins, identity, verify):
    result = baseline_result()
    started = args.started
    with (args.output / 'worker-guard.jsonl').open('x') as stream:
        guard = DiagnosticGuard(args.deadline, verify, stream)
        try:
            guard.start()
            # Imports and model loading consume the same supervisor-started 600 seconds.
            sys.path.insert(0, str(ROOT / 'python'))
            import numpy as np
            import torch
            from dodge_rl import VecDodgeEnv
            from dodge_rl.dev_eval import development_environment_config, development_seeds
            from dodge_rl.models.teacher import OmniscientEntityTeacher
            import dodge_rl._native as native
            guard.mps = lambda: int(torch.mps.driver_allocated_memory())
            def runtime_identity():
                return {'python': sys.version, 'interpreter': str(Path(sys.executable).resolve()),
                       'interpreter_sha256': sha(Path(sys.executable).resolve()),
                       'torch': str(torch.__version__), 'numpy': np.__version__,
                       'platform': platform.platform(), 'machine': platform.machine(),
                       'mps_available': bool(torch.backends.mps.is_available())}
            runtime = runtime_identity()
            require(runtime == p['foundation_runtime'], 'Installed runtime differs from foundation')
            def runtime_verify():
                verify()
                require(runtime_identity() == p['foundation_runtime'], 'Runtime changed during diagnostic')
            guard.verify = runtime_verify
            require(Path(native.__file__).resolve() == (ROOT / 'python/dodge_rl/_native.cpython-312-darwin.so').resolve(),
                    'Installed extension import escaped capsule')
            require(tuple(development_seeds()) == SEEDS, 'Original D seeds changed')
            torch.set_num_threads(4)
            require(torch.get_num_threads() == 4 and not os.environ.get('PYTORCH_ENABLE_MPS_FALLBACK'),
                    'Original MPS threads/no-fallback settings required')
            controls = {item['label']: [json.loads(line) for line in (ROOT / item['control']).read_text().splitlines()]
                        for item in p['checkpoints'] if item['control']}
            with (args.output / 'episodes.jsonl').open('x') as episodes, \
                 (args.output / 'decisions.jsonl').open('x') as traces, \
                 (args.output / 'evaluations.jsonl').open('x') as events:
                def one(label, mode, seed):
                    guard.check()
                    item = next(x for x in p['checkpoints'] if x['label'] == label)
                    model = load_diagnostic_model(torch, np, OmniscientEntityTeacher, item, p, identity, guard)
                    try:
                        rows = evaluate(model, mode, seed, label, guard, episodes, traces, result,
                                        torch=torch, np=np, env_factory=VecDodgeEnv,
                                        config_factory=development_environment_config)
                        require(all(param.grad is None for param in model.parameters()), 'Gradient observed')
                        result['evaluations_completed'] += 1
                        return rows
                    finally:
                        del model
                evaluations, matches = execute_order(p, one, controls, guard, events, result['control_matches'])
                result['control_matches'] = matches
                result['statistics'] = paired_statistics(evaluations, np, guard.check)
            guard.sample()
            require(result['episodes_completed'] == 768 and result['evaluations_completed'] == 12,
                    'Observed evaluation/episode total differs')
            result['status'] = 'complete'
        except BaseException as error:
            result.update(error=repr(error), traceback=traceback.format_exc(), partial=True)
        finally:
            try:
                guard.close()
                verify()
            except BaseException as error:
                result.update(status='failed', final_verification_error=repr(error), partial=True)
            result.update(guard.receipt(), elapsed_seconds=time.monotonic() - started,
                          checkpoint_hashes={i['label']: i['sha256'] for i in p['checkpoints']},
                          foundation_sources=p['foundation_sources'], protocol_sha256=PROTOCOL_SHA256,
                          harness_sha256=sha(__file__), partial=result['status'] != 'complete')
            if guard.failure is not None:
                result.update(status='failed', partial=True, guard_failure=guard.failure)
            if time.monotonic() >= args.deadline:
                result.update(status='failed', partial=True, deadline_expired=True)
            save(args.output / 'worker-result.json', result)
    return 0 if result['status'] == 'complete' else 1


def supervise(args):
    result = baseline_result()
    process = guard = None
    started = LAUNCH_MONOTONIC
    deadline = started + 600
    args.output = args.output.resolve()
    # Output is the one registered future campaign directory. Refuse reuse.
    p = registered_protocol(args.protocol)
    require(args.output == ORIGINAL_ROOT / p['output'], 'Unregistered campaign output')
    args.output.mkdir(parents=False, exist_ok=False)
    with cancellation_signals() as defer, (args.output / 'supervisor-guard.jsonl').open('x') as stream:
        try:
            manifest_path = ROOT / 'capsule-manifest.json'
            manifest_hash = sha(manifest_path)
            manifest = json.loads(manifest_path.read_text())
            assert_readonly_capsule(manifest)
            harness_hash = sha(__file__)
            require(manifest['files'].get(p['runner']) == harness_hash, 'Harness not pinned in capsule')
            pins, identity = input_pins(p, args.protocol, manifest)
            pins[str(manifest_path)] = manifest_hash
            def verify():
                assert_lease(args.state_path, p, PROTOCOL_SHA256, harness_hash, manifest_hash)
                verify_files(pins)
                assert_readonly_capsule(manifest)
            # Exact lease and every identity input are checked before worker spawn.
            verify()
            guard = DiagnosticGuard(deadline, verify, stream)
            guard.start()
            command = [sys.executable, '-B', str(Path(__file__).resolve()), '--worker',
                       '--protocol', str(args.protocol.resolve()), '--output', str(args.output),
                       '--state-path', str(args.state_path.resolve()), '--started', str(started),
                       '--deadline', str(deadline), '--supervisor-pid', str(os.getpid())]
            result.update(run_id=p['run_id'], command=command, protocol_sha256=PROTOCOL_SHA256,
                          harness_sha256=harness_hash, frozen_capsule_manifest_sha256=manifest_hash,
                          input_hashes=pins)
            with (args.output / 'worker.stdout.log').open('x') as stdout, \
                 (args.output / 'worker.stderr.log').open('x') as stderr:
                # Signals are blocked across creation/assignment to prevent an orphan race.
                blocked = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT, signal.SIGTERM})
                try:
                    require(not os.environ.get('PYTORCH_ENABLE_MPS_FALLBACK'),
                            'MPS fallback environment setting is not authorized')
                    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
                    process = subprocess.Popen(command, stdout=stdout, stderr=stderr, cwd=ROOT,
                                               env=environment, start_new_session=True)
                finally:
                    signal.pthread_sigmask(signal.SIG_SETMASK, blocked)
                guard.rss = lambda: max(sampled_rss(os.getpid()), sampled_rss(process.pid)) if process.poll() is None else sampled_rss(os.getpid())
                while process.poll() is None:
                    guard.check()
                    time.sleep(min(0.025, max(0, deadline - time.monotonic())))
                guard.check()
                result['worker_exit_code'] = process.returncode
                wr = json.loads((args.output / 'worker-result.json').read_text())
                result['worker_result'] = wr
                require(process.returncode == 0 and wr['status'] == 'complete', 'Worker failed; no retry')
                guard.sample()
                result.update(status='complete', partial=False)
        except BaseException as error:
            result.update(status='failed', partial=True, error=repr(error), traceback=traceback.format_exc())
        finally:
            defer()
            execution_end = time.monotonic()
            if process is not None:
                try:
                    result['owned_process_stop'] = stop_owned(process)
                except BaseException as error:
                    result['owned_process_stop'] = {'reaped': process.poll() is not None,
                                                    'group_empty': False, 'error': repr(error)}
            result['cleanup_seconds'] = time.monotonic() - execution_end
            result['inference_budget_elapsed_seconds'] = min(execution_end - started, 600)
            result['actual_execution_wall_seconds'] = execution_end - started
            if guard is not None:
                try:
                    guard.close()
                    verify()
                except BaseException as error:
                    result.update(status='failed', partial=True, final_verification_error=repr(error))
                result['supervisor_resources'] = guard.receipt()
            if process is not None and (not result['owned_process_stop']['reaped']
                    or not result['owned_process_stop'].get('group_empty', False)
                    or result['owned_process_stop'].get('errors')):
                result.update(status='failed', partial=True, cleanup_failure=True)
            if execution_end >= deadline:
                result.update(status='failed', partial=True, deadline_expired=True)
            # A timed-out/killed worker may still have produced a failure receipt.
            if process is not None and process.poll() is not None and 'worker_result' not in result:
                try:
                    result['worker_result'] = json.loads((args.output / 'worker-result.json').read_text())
                except (FileNotFoundError, json.JSONDecodeError):
                    for key in ('inference_calls', 'native_step_calls', 'environments_created'):
                        result[key] = None
                    result['worker_counts_unavailable'] = True
            if guard is not None and guard.failure is not None:
                result.update(status='failed', partial=True, guard_failure=guard.failure)
            if result.get('worker_counts_unavailable') and process.poll() is not None:
                for filename, key in (('episodes.jsonl', 'episodes_completed'),
                                      ('decisions.jsonl', 'decisions_logged'),
                                      ('evaluations.jsonl', 'evaluations_completed')):
                    count = 0
                    path = args.output / filename
                    if path.exists():
                        with path.open() as records:
                            for line in records:
                                try:
                                    record = json.loads(line)
                                    if filename != 'evaluations.jsonl' or record.get('event') == 'evaluation_complete':
                                        count += 1
                                    if record.get('event') == 'historical_control':
                                        result['control_matches'][record['checkpoint']] = record
                                except json.JSONDecodeError:
                                    result['partial_final_log_record'] = True
                    result[key] = count
            # Stable receipts/manifests are published only after owned worker exit.
            for key in ('inference_calls', 'native_step_calls', 'environments_created', 'decisions_logged',
                        'episodes_completed', 'evaluations_completed', 'control_matches'):
                if 'worker_result' in result and key in result['worker_result']:
                    result[key] = result['worker_result'][key]
            result['actual_total_wall_seconds'] = time.monotonic() - started
            save(args.output / 'run-result.json', result)
    # Include closed streams and retained partial logs; never hash mutable logs as inputs.
    if process is not None and process.poll() is None:
        save(args.output / 'artifact-manifest-unavailable.json',
             {'stable': False, 'reason': 'Owned worker has not exited; mutable logs were not hashed'})
        return 1
    save(args.output / 'artifact-manifest.json', {str(x.relative_to(args.output)): sha(x)
         for x in sorted(args.output.rglob('*')) if x.is_file()})
    return 0 if result['status'] == 'complete' else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--protocol', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--state-path', type=Path, default=STATE_PATH)
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--started', type=float, help=argparse.SUPPRESS)
    parser.add_argument('--deadline', type=float, help=argparse.SUPPRESS)
    parser.add_argument('--supervisor-pid', type=int, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not args.worker:
        return supervise(args)
    # A worker cannot be launched as an independent inference entry point.
    require(args.supervisor_pid == os.getppid() and args.supervisor_pid > 1
            and os.getsid(0) == os.getpid() and os.getpgrp() == os.getpid(), 'Worker is not supervisor-owned')
    signal.pthread_sigmask(signal.SIG_SETMASK, set())
    require(args.started is not None and args.deadline == args.started + 600
            and time.monotonic() < args.deadline, 'Invalid inherited diagnostic deadline')
    p = registered_protocol(args.protocol)
    require(args.output.resolve() == ORIGINAL_ROOT / p['output'], 'Unregistered worker output')
    manifest_path = ROOT / 'capsule-manifest.json'
    manifest = json.loads(manifest_path.read_text())
    manifest_hash, harness_hash = sha(manifest_path), sha(__file__)
    assert_readonly_capsule(manifest)
    pins, identity = input_pins(p, args.protocol, manifest)
    pins[str(manifest_path)] = manifest_hash
    def verify():
        require(os.getppid() == args.supervisor_pid, 'Supervisor disappeared')
        assert_lease(args.state_path, p, PROTOCOL_SHA256, harness_hash, manifest_hash)
        verify_files(pins)
        assert_readonly_capsule(manifest)
    with cancellation_signals():
        return worker(args, p, pins, identity, verify)


if __name__ == '__main__':
    raise SystemExit(main())
