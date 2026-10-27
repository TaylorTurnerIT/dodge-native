#!/usr/bin/env python3
"""One separately authorized long-D2 experiment. No resume or device override.

The stdlib-only preflight/freeze path never imports the project, Torch, or native
code. Only the supervisor-owned worker may import the ORIGINAL_ROOT package.
Legacy proof validates the old D1->D2 contract; it never authorizes this run.
"""
from __future__ import annotations
import time
LAUNCH_MONOTONIC = time.monotonic()  # Includes all subsequent normal imports.

import argparse
import copy
from contextlib import contextmanager, ExitStack
import hashlib
import io
import json
import math
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import threading
import traceback

ORIGINAL_ROOT = Path('/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79')
PREPARE_REL = 'learning/runs/v2/postovernight-long-D2-prepare-r2'
ROOT = Path(__file__).resolve().parents[4]
PROTOCOL_REL = 'learning/runs/v2-orchestration/postovernight-long-D2-r1-protocol-r2.json'
PROTOCOL_SHA256 = 'f662a4aba18e144098faeb01d398b67f489aea7549a9ebe4a5959f993e1cff09'
CONFIG_SHA256 = '2ac814d3842228017d09669364a8391344722da56ad19f41ad9030dbb930c2db'
STATE_PATH = ORIGINAL_ROOT / 'learning/runs/v2-orchestration/state.json'
LIMIT = 6442450944
BUDGET = 7200
WORKER_SECONDS = 7140
CLEANUP_SECONDS = 10
SEEDS = tuple(range(3489660928, 3489660992))
ROW_KEYS = ('episode_index', 'seed', 'score_raw_fixed', 'score', 'alive_frames',
            'gameplay_frames', 'terminated', 'truncated', 'objective_return')
PARENT_COUNTERS = dict(updates=48, phase_updates=32, optimizer_steps=6144,
                       environment_decisions=786432, raw_frames=3139552, checkpoint_index=9)
LEASE_KEYS = {'kind', 'authorization', 'run_id', 'protocol_sha256', 'controller_sha256',
              'capsule_manifest_sha256', 'capsule_path', 'config_sha256', 'identity_sha256',
              'parent_checkpoint_sha256', 'parent_terminal_receipt', 'budget_seconds',
              'cleanup_reserve_seconds', 'output', 'cancel_requested'}


class Stop(RuntimeError):
    def __init__(self, message, outcome='identity_or_lease_failure'):
        self.outcome = outcome
        super().__init__(message)


def require(condition, message, outcome='identity_or_lease_failure'):
    if not condition:
        raise Stop(message, outcome)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def semantic_hash(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def read_json(path):
    # Repeated or nonfinite JSON keys/values cannot silently redefine authority.
    def pairs(items):
        value = {}
        for key, item in items:
            require(key not in value, 'Duplicate JSON field: ' + key)
            value[key] = item
        return value
    return json.loads(Path(path).read_bytes(), object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(Stop('Nonfinite JSON: ' + value)))


def save(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def replace_json(path, value):
    pending = path.with_name('.' + path.name + '.pending')
    save(pending, value)
    os.replace(pending, path)


def emit(stream, value):
    stream.write(json.dumps(value, sort_keys=True, allow_nan=False) + '\n')
    stream.flush()


def verify_files(pins):
    for path, digest in pins.items():
        require(Path(path).is_file() and sha(path) == digest, 'Input hash mismatch: ' + str(path))


def registered_protocol(path):
    require(sha(path) == PROTOCOL_SHA256, 'Parent protocol document hash mismatch')
    p = read_json(path)
    require(p['budget_seconds'] == BUDGET and p['cleanup_reserve_seconds'] == CLEANUP_SECONDS
            and p['guard']['worker_deadline_seconds'] == WORKER_SECONDS, 'Registered bounds differ')
    require(p['config_sha256'] == CONFIG_SHA256 and len(p['base_identity']['sources']) == 75,
            'Registered config/base inventory differs')
    return p


def validate_long_config(config, base, protocol, legacy_protocol):
    require(canonical(config) == canonical(protocol['config']), 'Exact long config differs (extra/missing/value/type)')
    changed = {'version', 'phase', 'phase_settings'}
    extra = {'evaluation_stage', 'base_config_sha256', 'long_settings'}
    require(set(config) == set(base) | extra, 'Long config key set differs')
    require(canonical({k:v for k,v in config.items() if k not in changed | extra})
            == canonical({k:v for k,v in base.items() if k not in changed}), 'Learner/environment fields differ')
    seed = config['phase_settings']['run_seed']
    reserved = {row[k] for row in legacy_protocol['seed_namespace_table'].values()
                for k in ('run_seed', 'initialization_seed') if k in row}
    require(type(seed) is int and seed == 5562873868232098305 and seed not in reserved,
            'Run seed is wrong or collides with registered run/initialization seed')
    require(config['phase'] == 'long_D2' and config['evaluation_stage'] == 'D2'
            and config['phase_settings']['budget_seconds'] == BUDGET, 'Wrong experiment phase/budget')
    return config


def expected_lease(protocol, controller_hash, capsule_hash, capsule_path, identity_document_hash):
    return dict(kind='M3_long_D2_experiment', authorization=protocol['authorization'],
                run_id=protocol['run_id'], protocol_sha256=PROTOCOL_SHA256,
                controller_sha256=controller_hash, capsule_manifest_sha256=capsule_hash,
                capsule_path=str(capsule_path), config_sha256=CONFIG_SHA256,
                identity_sha256=identity_document_hash,
                parent_checkpoint_sha256=protocol['parent_checkpoint_sha256'],
                parent_terminal_receipt=protocol['parent_terminal_receipt'], budget_seconds=BUDGET,
                cleanup_reserve_seconds=CLEANUP_SECONDS, output=protocol['output'], cancel_requested=False)


def assert_lease(path, expected):
    lease = read_json(path).get('active_long_campaign')
    require(isinstance(lease, dict) and set(lease) == LEASE_KEYS, 'Exact lease key set missing/changed')
    require(lease['cancel_requested'] is False, 'Parent requested cancellation', 'cancelled')
    require(canonical(lease) == canonical(expected), 'Exact parent-owned long-D2 lease changed')
    return lease


def safe_member(root, name):
    part = Path(name)
    require(not part.is_absolute() and '..' not in part.parts, 'Unsafe capsule member')
    path = root / part
    require(path.resolve().is_relative_to(root) and not path.is_symlink(), 'Capsule member escaped root')
    return path


def assert_readonly_capsule(root, manifest):
    require(root != ORIGINAL_ROOT and manifest['version'] == 'long_d2_capsule_v1', 'Execute readonly capsule only')
    for name in list(manifest['files']) + ['capsule-manifest.json']:
        path = safe_member(root, name)
        require(path.is_file() and not path.stat().st_mode & 0o222, 'Capsule file is writable')
        for parent in (path.parent, *path.parents):
            if not parent.is_relative_to(root):
                break
            require(not parent.stat().st_mode & 0o222, 'Capsule directory is writable')
    actual = {str(x.relative_to(root)) for x in root.rglob('*') if x.is_file()}
    require(actual == set(manifest['files']) | {'capsule-manifest.json'}, 'Capsule file inventory differs')


def check_module_origins(identity, capsule_root, modules=None):
    modules = sys.modules if modules is None else modules
    expected = identity['legacy_module_origins']
    observed = {}
    for name, module in tuple(modules.items()):
        if name != 'dodge_rl' and not name.startswith('dodge_rl.'):
            continue
        origin = getattr(module, '__file__', None)
        require(origin is not None, 'Loaded package module has no file: ' + name)
        path = Path(origin).resolve()
        require(str(path) in expected, 'Unexpected legacy module origin: ' + str(path))
        pin = expected[str(path)]
        require(sha(path) == pin['sha256'] == sha(capsule_root / pin['mirror']),
                'Loaded legacy module/mirror hash differs: ' + name)
        observed[name] = dict(origin=str(path), sha256=pin['sha256'], mirror=pin['mirror'])
    return observed


def capsule_context(root, *, require_capsule=True):
    p = registered_protocol(root / PROTOCOL_REL)
    manifest_path = root / 'capsule-manifest.json'
    manifest = read_json(manifest_path)
    if require_capsule:
        assert_readonly_capsule(root, manifest)
    identity_path = root / PREPARE_REL / 'long-identity.json'
    identity = read_json(identity_path)
    require(identity['version'] == 'teacher_long_D2_identity_v1', 'Long identity version differs')
    require(identity['protocol_sha256'] == PROTOCOL_SHA256, 'Identity protocol differs')
    require(identity['base_registered_identity'] == p['base_identity']
            and identity['base_registered_identity_sha256'] == p['base_identity_sha256']
            and identity['parent_terminal_receipt'] == p['parent_terminal_receipt']
            and identity['parent_checkpoint_sha256'] == p['parent_checkpoint_sha256'], 'Identity lineage differs')
    require(sha(root / p['config_path']) == CONFIG_SHA256, 'Config document hash differs')
    config = read_json(root / p['config_path'])
    base = read_json(root / p['base_config_path'])
    validate_long_config(config, base, p, read_json(root / 'docs/v2-m3-run-protocol.json'))
    require(identity['config'] == config and identity['config_sha256'] == CONFIG_SHA256,
            'Long identity config document binding differs')
    sources = {str(ORIGINAL_ROOT / k):v for k,v in identity['controller_sources'].items()}
    require(sources and sources[str(ORIGINAL_ROOT / p['controller'])] == sha(root / p['controller']),
            'Controller source binding differs')
    pins = {str(root / k):v for k,v in manifest['files'].items()}
    pins.update(identity['original_input_pins'])
    pins.update(sources)
    pins[str(manifest_path)] = sha(manifest_path)
    verify_files(pins)
    require(sha(ORIGINAL_ROOT / p['base_identity_path']) == p['base_identity_sha256']
            and sha(ORIGINAL_ROOT / p['base_config_path']) == p['base_config_sha256'],
            'Historical identity/config document binding differs')
    require(read_json(ORIGINAL_ROOT / p['base_identity_path']) == p['base_identity'],
            'Full historical identity differs')
    for name, digest in identity['controller_sources'].items():
        require(manifest['files'].get(name) == digest, 'Helper/test missing from capsule sources')
    for path, pin in identity['legacy_module_origins'].items():
        require(Path(path) == ORIGINAL_ROOT / pin['mirror']
                and identity['base_registered_identity']['sources'].get(pin['mirror']) == pin['sha256'],
                'Legacy module origin policy differs from original 75 inputs')
    require(manifest['files'][str(Path(PREPARE_REL) / 'long-identity.json')] == sha(identity_path),
            'Identity document not bound to capsule')
    lease = expected_lease(p, sha(root / p['controller']), sha(manifest_path), root, sha(identity_path))
    return p, config, base, identity, pins, lease


def pure_preflight(root):
    require(not any(name in {'torch','numpy','dodge_rl'} or name.startswith(('torch.','numpy.','dodge_rl.'))
                    for name in sys.modules), 'Pure preflight imported ML/project code')
    context = capsule_context(root)
    p, config, base, identity, pins, lease = context
    return dict(status='pure_identity_preflight_passed', protocol_document_sha256=PROTOCOL_SHA256,
                config_document_sha256=CONFIG_SHA256,
                identity_document_sha256=sha(root / PREPARE_REL / 'long-identity.json'),
                checkpoint_identity_semantic_sha256=semantic_hash(identity),
                capsule_manifest_sha256=sha(root / 'capsule-manifest.json'),
                legacy_sources=len(identity['base_registered_identity']['sources']),
                verified_pin_count=len(pins), required_lease=lease,
                project_torch_native_imported=False, campaign_output_created=False)


class Schedule:
    def __init__(self):
        self.U, self.E, self.C, self.F = 25.0, 150.0, 15.0, 30.0

    def update_wall(self, wall):
        require(math.isfinite(wall) and wall >= 0, 'Invalid update timing')
        self.U = max(self.U, 1.25 * wall)

    def evaluation_wall(self, wall):
        require(math.isfinite(wall) and wall >= 0, 'Invalid evaluation timing')
        self.E = max(self.E, 3.0 * wall)

    def block_cost(self):
        return 16 * self.U + self.E + 2 * self.C + self.F

    def remaining_cost(self, phase_updates):
        done = phase_updates % 16
        remaining = 16 - done
        checkpoints = 2 if done < 8 else 1
        return remaining * self.U + self.E + checkpoints * self.C + self.F

    def evaluation_cost(self):
        return self.C + self.E + self.F

    def receipt(self):
        return dict(U=self.U, E=self.E, C=self.C, F=self.F)


def outcome_fields(outcome, complete=False):
    passed = complete and outcome == 'D2_progress_gate_passed'
    return dict(experiment_status='complete' if complete else 'failed', outcome=outcome,
                progression_gate_passed=passed, teacher_qualified=False, training_parent_eligible=False,
                D3_parent_candidate_pending_separate_parent_audit=passed,
                B_E_student_D3_opened=False, automatic_retries=0, same_phase_resume=False,
                expected_exit_code=(0 if passed else 2) if complete else 1)


def result_code(result):
    good = result.get('experiment_status') == 'complete'
    if good and result.get('outcome') == 'D2_progress_gate_passed' and result.get('progression_gate_passed') is True:
        return 0
    if good and result.get('outcome') == 'budget_closed_below_gate' and result.get('progression_gate_passed') is False:
        return 2
    return 1


def failure_outcome(error):
    if isinstance(error, Stop):
        return error.outcome
    if isinstance(error, KeyboardInterrupt):
        return 'cancelled'
    return 'safety_stop'


def require_finite(value):
    if isinstance(value, dict):
        for item in value.values():
            require_finite(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            require_finite(item)
    elif type(value) is float:
        require(math.isfinite(value), 'Nonfinite update metric', 'safety_stop')


def compare_control(rows, saved):
    def index(items):
        require(len(items) == 64, 'Entry needs exactly 64 rows', 'entry_control_mismatch')
        found = {}
        for row in items:
            require(set(row) == set(ROW_KEYS) and type(row['episode_index']) is int
                    and 0 <= row['episode_index'] < 64 and row['seed'] == SEEDS[row['episode_index']],
                    'Entry row fields/seed/index differ', 'entry_control_mismatch')
            require(row['seed'] not in found, 'Duplicate entry seed', 'entry_control_mismatch')
            found[row['seed']] = row
        return found
    actual, expected = index(rows), index(saved)
    require(canonical(actual) == canonical(expected), 'Exact historical entry control mismatch', 'entry_control_mismatch')
    require(sum(row['score'] for row in rows)/64 == 1.4765625
            and sum(row['alive_frames'] for row in rows)/64 == 295.25,
            'Historical entry control means differ', 'entry_control_mismatch')
    return dict(matched=True, rows=64, fields=list(ROW_KEYS), comparison='seed_and_index_all_nine_fields')


def tree_fingerprint(value):
    """Bitwise CPU representation, including dtype/shape/container/scalar types.

    Duck typing permits synthetic objects without importing Torch on pure paths.
    NumPy global RNG arrays and CPU/MPS tensors are hashed as raw bytes.
    """
    if hasattr(value, 'detach'):
        tensor = value.detach().cpu().contiguous()
        return dict(kind='tensor', dtype=str(tensor.dtype), shape=list(tensor.shape),
                    bytes_sha256=hashlib.sha256(tensor.numpy().tobytes()).hexdigest())
    if hasattr(value, 'tobytes') and hasattr(value, 'dtype'):
        return dict(kind='array', dtype=str(value.dtype), shape=list(value.shape),
                    bytes_sha256=hashlib.sha256(value.tobytes()).hexdigest())
    if isinstance(value, dict):
        return ['dict', sorted(([tree_fingerprint(k), tree_fingerprint(v)] for k,v in value.items()),
                               key=lambda pair: canonical(pair[0]))]
    if isinstance(value, (list, tuple)):
        return [type(value).__name__, [tree_fingerprint(v) for v in value]]
    if isinstance(value, bytes):
        return ['bytes', value.hex()]
    require(value is None or type(value) in (bool, int, float, str), 'Unsupported equality object')
    return [type(value).__name__, value]


def assert_equal_tree(actual, expected, label):
    a, b = semantic_hash(tree_fingerprint(actual)), semantic_hash(tree_fingerprint(expected))
    require(a == b, label + ' bitwise state mismatch', 'entry_control_mismatch')
    return a


def environment_kwargs(base_kwargs, config):
    expected = dict(batch_size=64, action_repeat=4, difficulty=2, patterns_enabled=True,
                    powerups_enabled=True, raw_frame_cap=18000, num_threads=4, chunk_size=8,
                    render_pixels=False, auxiliary_targets=False,
                    excluded_seed_ranges=[tuple(x) for x in config['excluded_seed_ranges']],
                    initial_episode_indices=[0]*64)
    require(set(base_kwargs) == set(expected) | {'run_seed'}
            and {k:v for k,v in base_kwargs.items() if k != 'run_seed'} == expected,
            'Legacy environment kwargs differ')
    require(base_kwargs['run_seed'] == 5562881586070242562, 'Wrong historical training namespace')
    result = copy.deepcopy(base_kwargs)
    result['run_seed'] = config['phase_settings']['run_seed']
    require([k for k in result if result[k] != base_kwargs[k]] == ['run_seed'], 'Environment must change only run_seed')
    return result


def sampled_rss(pid):
    r = subprocess.run(['ps', '-o', 'rss=', '-p', str(pid)], capture_output=True,
                       text=True, timeout=0.2)
    require(r.returncode == 0 and r.stdout.strip().isdigit(), 'RSS probe failed')
    return int(r.stdout.strip()) * 1024


def self_peak():
    n = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(n if sys.platform == 'darwin' else n * 1024)


_ACTIVE_CANCELLATION = None


@contextmanager
def cancellation_signals():
    # Nested publication borrows the outer latch. It must never restore the
    # process handlers or reset request counts while the supervisor still owns IO.
    global _ACTIVE_CANCELLATION
    if _ACTIVE_CANCELLATION is not None:
        yield _ACTIVE_CANCELLATION
        return
    previous, cancelling = {}, [False]
    def defer():
        cancelling[0] = True
    defer.requested_signal = None
    defer.cancellation_requests = 0
    def handle(number, frame):
        defer.cancellation_requests += 1
        if defer.requested_signal is None:
            defer.requested_signal = number
        if not cancelling[0]:
            cancelling[0] = True
            raise KeyboardInterrupt(f'Cancellation signal {signal.Signals(number).name}')
    try:
        for sig in (signal.SIGINT, signal.SIGTERM):
            previous[sig] = signal.getsignal(sig)
            signal.signal(sig, handle)
        _ACTIVE_CANCELLATION = defer
        yield defer
    finally:
        # Restore both handlers under one signal mask. Requests arriving during
        # restoration are consumed into the same latch before unmasking, rather
        # than being delivered to a restored SIG_DFL handler.
        mask=signal.pthread_sigmask(signal.SIG_BLOCK,set(previous))
        try:
            for sig, handler in previous.items():
                signal.signal(sig, handler)
            pending=signal.sigpending() & set(previous)
            while pending:
                number=signal.sigwait(pending)
                defer()
                handle(number,None)
                pending=signal.sigpending() & set(previous)
        finally:
            _ACTIVE_CANCELLATION = None
            signal.pthread_sigmask(signal.SIG_SETMASK,mask)


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


class Guard:
    """Independent resource/lease and full-byte monitors, with latched failures.

    Full verification never holds the resource lock. Slow byte IO therefore
    cannot suppress <=0.5s observations. Full checks retain the <=5s bound,
    including verification duration. Supervisor observations use memory only;
    its one disk snapshot is closed before any artifact hashing starts.
    """
    def __init__(self, deadline, lease_check, verify, stream, *, clock=time.monotonic,
                 rss=lambda: sampled_rss(os.getpid()), peak=self_peak, mps=lambda: 0):
        self.deadline, self.lease_check, self.verify, self.stream = deadline, lease_check, verify, stream
        self.clock, self.rss, self.peak, self.mps = clock, rss, peak, mps
        self.failure = None
        self.maximum_rss = self.maximum_peak = self.maximum_mps = 0
        self.last_sample = self.last_full = None
        self.maximum_sample_gap = self.maximum_full_gap = 0.0
        self.lock = threading.RLock()
        self.verify_lock = threading.RLock()
        self.event = threading.Event()
        self.thread = self.verify_thread = None

    def check(self, force=False):
        if self.failure is not None:
            raise self.failure
        require(self.clock() < self.deadline, 'Absolute wall guard reached', 'wall_guard')
        if force:
            self.sample(force=True)

    def full_check(self, force=False):
        with self.verify_lock:
            self.check()
            at = self.clock()
            if not force and self.last_full is not None and at - self.last_full < 4:
                return
            gap = 0 if self.last_full is None else at - self.last_full
            require(gap <= 5, 'Full input verification gap exceeded 5s')
            self.verify()
            end = self.clock()
            # Use consecutive verification starts and include this check's IO.
            # This conservatively bounds every pinned byte's revisit interval.
            gap = max(gap, end-at if self.last_full is None else end-self.last_full)
            self.maximum_full_gap = max(self.maximum_full_gap, gap)
            require(gap <= 5, 'Full input verification gap exceeded 5s')
            self.last_full = at
            self.check()

    def sample(self, force=False, *, full=True):
        with self.lock:
            self.check()
            at = self.clock()
            self.lease_check()
            gap = 0 if self.last_sample is None else at - self.last_sample
            self.maximum_sample_gap = max(self.maximum_sample_gap, gap)
            require(gap <= 0.5, 'Resource/lease sampling gap exceeded 0.5s', 'resource_stop')
            rss, peak, mps = self.rss(), self.peak(), self.mps()
            require(all(type(x) is int and x >= 0 for x in (rss,peak,mps)), 'Invalid resource probe', 'resource_stop')
            self.maximum_rss = max(self.maximum_rss, rss)
            self.maximum_peak = max(self.maximum_peak, peak)
            self.maximum_mps = max(self.maximum_mps, mps)
            self.last_sample = at
            if self.stream is not None:
                emit(self.stream, dict(monotonic=at, rss_bytes=rss, self_peak_rss_bytes=peak,
                                       mps_driver_bytes=mps, sample_gap_seconds=gap, pid=os.getpid()))
            require(max(rss,peak) <= LIMIT and mps <= LIMIT, 'RSS or MPS resource limit exceeded', 'resource_stop')
            require(self.clock()-at <= 0.5, 'Resource probe exceeded 0.5s', 'resource_stop')
        if full:
            self.full_check(force)
        self.check()

    def start(self):
        # Start resource sampling before full hashes; byte IO never blocks it.
        self.sample(full=False)
        def monitor():
            while not self.event.wait(0.05):
                try:
                    if self.clock() - self.last_sample >= 0.15:
                        self.sample(full=False)
                    if self.last_full is not None:
                        require(self.clock()-self.last_full <= 5, 'Full input verification gap exceeded 5s')
                except BaseException as error:
                    self.failure = error if isinstance(error, Stop) else Stop(repr(error))
                    return
        self.thread = threading.Thread(target=monitor, daemon=True, name='long-D2-guard')
        self.thread.start()
        self.full_check(force=True)
        def verify_monitor():
            while not self.event.wait(0.05):
                try:
                    self.full_check()
                except BaseException as error:
                    self.failure = error if isinstance(error, Stop) else Stop(repr(error))
                    return
        self.verify_thread = threading.Thread(target=verify_monitor, daemon=True, name='long-D2-inputs')
        self.verify_thread.start()

    def close(self):
        self.event.set()
        for thread in (self.verify_thread, self.thread):
            if thread is not None:
                thread.join(timeout=0.5)
                require(not thread.is_alive(), 'Guard sampler did not stop')
        self.check()

    def receipt(self):
        return dict(maximum_rss_bytes=self.maximum_rss, maximum_self_peak_rss_bytes=self.maximum_peak,
                    maximum_mps_driver_bytes=self.maximum_mps,
                    maximum_sample_gap_seconds=self.maximum_sample_gap,
                    maximum_full_input_gap_seconds=self.maximum_full_gap,
                    last_sample_monotonic=self.last_sample, last_full_verification_monotonic=self.last_full,
                    latched_failure=None if self.failure is None else repr(self.failure))


@contextmanager
def absolute_alarm(deadline):
    """Interrupt normal supervisor publication/IO at the inclusive deadline.

    After this fires, only failure persistence and bounded owned cleanup remain.
    The worker has no authority to alter this independent parent alarm.
    """
    def expired(number, frame):
        raise Stop('Supervisor absolute 7200s alarm', 'wall_guard')
    old = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, max(0.000001, deadline-time.monotonic()))
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old)


def counter_report(counters, inherited, progress):
    partial = 0
    return dict(cumulative=copy.deepcopy(counters), inherited=copy.deepcopy(inherited),
                phase={k:counters[k]-inherited[k] for k in
                       ('updates','optimizer_steps','environment_decisions','raw_frames')},
                phase_updates=counters['phase_updates'], partial_optimizer_steps=partial,
                actual_optimizer_steps_including_partial=counters['optimizer_steps']+partial)


class Learner:
    """Only necessary orchestration; never instantiates or fabricates Experiment."""
    def __init__(self, api, config, identity, parent, guard, output, protocol, *, clock=time.monotonic):
        self.api, self.config, self.identity, self.guard = api,config,identity,guard
        self.output,self.protocol,self.clock = output,protocol,clock
        self.env = self.observation = self.model = self.optimizer = None
        self.progress = {}
        self.checkpoints = []
        self.counters = copy.deepcopy(parent['counters'])
        require(self.counters == PARENT_COUNTERS, 'Exact D1 counters differ')
        self.inherited = copy.deepcopy(self.counters)
        self.counters['phase_updates'] = 0
        self.origin = copy.deepcopy(self.counters)
        self.context = copy.deepcopy(parent.get('run_context',{}))
        self.context['D1_competence_demonstrated'] = True
        for key in ('pilot_before','pilot_initial_checkpoint','pilot_initial_checkpoint_sha256'):
            self.context.pop(key,None)
        self.last_metrics = self.context.get('last_metrics')
        self.kl_count = self.context.get('large_kl_iterations',0)
        self.actor_gradient_seen = self.context.get('actor_gradient_seen',False)
        self.critic_gradient_seen = self.context.get('critic_gradient_seen',False)
        self.episodes = self.metrics = None
        self.parent = parent

    def initialize(self):
        a = self.api
        a.seed_initialization(0)
        self.model = a.teacher().to(device='mps',dtype=a.torch.float32)
        require(self.model.architecture_description() == self.protocol['base_identity']['architecture'],
                'Full teacher architecture differs')
        require(sum(p.numel() for p in self.model.parameters()) == 321290, 'Parameter count differs')
        self.optimizer = a.make_optimizer(self.model,self.config)
        self.ppo = a.PPOConfig(**self.config['ppo'])
        a.ckpt.restore_learner(self.parent,self.model,self.optimizer,'mps')
        receipt = dict(model=assert_equal_tree(self.model.state_dict(),self.parent['model'],'D1 model'),
                       Adam=assert_equal_tree(self.optimizer.state_dict(),self.parent['optimizer'],'D1 Adam'),
                       RNG=assert_equal_tree(a.ckpt.capture_rng('mps'),self.parent['rng'],'D1 RNG'))
        # No environment may precede all three equality checks.
        save(self.output/'entry-restoration.json',dict(matched=True,bitwise_sha256=receipt,
                                                     before_any_environment_or_gradient=True))
        self.episodes = (self.output/'training-episodes.jsonl').open('x')
        self.metrics = (self.output/'training-metrics.jsonl').open('x')
        require(len(self.parent['abandoned_episodes']) == 64, 'D1 abandoned episode count differs')
        for item in self.parent['abandoned_episodes']:
            emit(self.episodes,{**item,'reason':'long_D2_namespace_transition'})
        kwargs = environment_kwargs(a.training_env_config(a.base,[0]*64),self.config)
        self.guard.check(force=True)
        self.env = a.TrainingEnvLog(a.env_factory(**kwargs),self.counters,self.episodes)
        metadata = a.verify_training_env(self.env,self.config,[0]*64)
        emit(self.episodes,dict(kind='initial',info=self.env.episode_info(),batch_info=metadata,kwargs=kwargs))
        self.observation = self.env.observations()
        save(self.output/'parent-lineage.json',dict(parent_checkpoint=self.protocol['parent_checkpoint'],
             parent_checkpoint_sha256=self.protocol['parent_checkpoint_sha256'],
             parent_terminal_receipt=self.protocol['parent_terminal_receipt'],
             inherited_counters=self.inherited,phase_origin_counters=self.origin,
             failed_D2_experience_inherited=False,abandoned_parent_episodes=64,
             historical_old_D1_to_D2_proof=True,new_authority_is_separate=True))
        self.guard.check(force=True)

    def report(self):
        return counter_report(self.counters,self.inherited,self.progress)

    def checkpoint(self,tag,*,emergency=False):
        if not emergency:
            self.guard.check(force=True)
        require(self.clock() < self.api.absolute_deadline, 'No checkpoint after absolute deadline', 'wall_guard')
        self.counters['checkpoint_index'] += 1
        path = self.output/f"checkpoint-{self.counters['checkpoint_index']:06d}-{tag}.pt"
        state = self.api.ckpt.make_state(self.model,self.optimizer,self.identity,self.counters,
                env=self.env,tag=tag,progress=self.progress,device='mps',
                parent_sha256=self.config['parent_checkpoint_sha256'])
        self.context.update(large_kl_iterations=self.kl_count,last_metrics=copy.deepcopy(self.last_metrics),
                            actor_gradient_seen=self.actor_gradient_seen,critic_gradient_seen=self.critic_gradient_seen)
        state.update(run_context=copy.deepcopy(self.context),phase_origin_counters=self.origin,
                     long_counter_report=self.report(),training_parent_eligible=False,
                     teacher_qualified=False,same_phase_resume=False)
        adam_steps=[]
        for item in state.get('optimizer',{}).get('state',{}).values():
            if 'step' in item:
                step=item['step']
                adam_steps.append(float(step.item() if hasattr(step,'item') else step))
        state['actual_Adam_parameter_step_values']=sorted(set(adam_steps))
        digest = self.api.ckpt.save_checkpoint(path,state)
        record = dict(checkpoint=path.name,sha256=digest,tag=tag,counters=self.report(),
                      update_progress=copy.deepcopy(self.progress),complete_update=not self.progress.get('in_update',False),
                      evaluated=False,progression_gate_passed=False,training_parent_eligible=False)
        record['actual_Adam_parameter_step_values']=state['actual_Adam_parameter_step_values']
        self.checkpoints.append(record)
        if self.episodes:
            emit(self.episodes,dict(kind='checkpoint_resume_boundary',checkpoint_sha256=digest,
                 next_episode_indices=state['next_episode_indices'],abandoned_on_resume=state['abandoned_episodes'],
                 live_environment_reset=False))
        require(self.clock() < self.api.absolute_deadline, 'Checkpoint crossed absolute deadline', 'wall_guard')
        if not emergency:
            self.guard.check(force=True)
        return record

    def evaluate_checkpoint(self,*,entry=False):
        a = self.api
        self.guard.check(force=True)
        # Snapshot before BOTH checkpoint and evaluation, preserving training RNG/live state.
        before_rng = a.ckpt.capture_rng('mps')
        before_model = tree_fingerprint(self.model.state_dict())
        before_adam = tree_fingerprint(self.optimizer.state_dict())
        before_env = copy.deepcopy((self.env.episode_info(),self.env.batch_info()))
        record = self.checkpoint('long_evaluated')
        started = self.clock()
        with (self.output/(record['checkpoint']+'.D2-development.jsonl')).open('x') as stream:
            evaluation = a.evaluate(self.model,'D2','mps',check_guard=self.guard.check,episode_stream=stream)
        elapsed = self.clock()-started
        self.guard.check(force=True)
        a.validate_summary(evaluation)
        assert_equal_tree(a.ckpt.capture_rng('mps'),before_rng,'Evaluation training RNG')
        require(tree_fingerprint(self.model.state_dict()) == before_model
                and tree_fingerprint(self.optimizer.state_dict()) == before_adam,
                'Checkpoint/evaluation changed model or Adam','entry_control_mismatch')
        require((self.env.episode_info(),self.env.batch_info()) == before_env,
                'Checkpoint/evaluation changed live training environments')
        if entry:
            control = read_json(ORIGINAL_ROOT/self.protocol['entry_control'])['evaluations']['D2']
            receipt = compare_control(evaluation['rows'],control['rows'])
            save(self.output/'entry-control.json',{**receipt,'control_document_sha256':self.protocol['entry_control_sha256'],
                 'RNG_unchanged':True,'model_Adam_unchanged':True,'zero_gradients_before_control':True})
        passed = bool(a.progress_passed('D2',{'D2':evaluation}))
        require(sha(self.output/record['checkpoint']) == record['sha256'], 'Evaluated checkpoint changed')
        certificate = dict(phase='long_D2',evaluation_stage='D2',checkpoint_sha256=record['sha256'],
                           complete=True,evaluations={'D2':evaluation},progression_gate_passed=passed,
                           training_parent_eligible=False,teacher_qualified=False,
                           D3_parent_candidate_pending_separate_parent_audit=passed)
        save(self.output/(record['checkpoint']+'.long-evaluation.json'),certificate)
        record.update(evaluated=True,progression_gate_passed=passed,
                      evaluation_sha256=sha(self.output/(record['checkpoint']+'.long-evaluation.json')))
        self.guard.check(force=True)
        return record,passed,elapsed

    def update_once(self):
        self.guard.check(force=True)
        # Discard stale complete-update progress before collecting the next rollout.
        self.progress = {}
        a = self.api
        collection = a.collect_rollout(self.model,self.env,self.config['rollout_steps'],'mps',
                   observation=self.observation,config=self.ppo,check_guard=self.guard.check)
        a.require_raw_diagnostics(collection.batch)
        self.observation = collection.observations
        emit(self.episodes,dict(kind='collection_accepted',counters=self.report(),
             completed_episodes=len(collection.completed_episodes),reset_events=len(collection.reset_info),
             transitions=collection.batch.transitions,
             returned_raw_frames=int(collection.batch.elapsed_raw_frames.sum().item())))
        metrics = a.ppo_update(self.model,self.optimizer,collection.batch,self.ppo,
                              check_guard=self.guard.check,progress=self.progress)
        # Complete counters move only after ppo_update returns successfully.
        require(self.progress.get('complete') is True and not self.progress.get('in_update',True),
                'PPO returned incomplete progress','safety_stop')
        self.counters['updates'] += 1
        self.counters['phase_updates'] += 1
        self.counters['optimizer_steps'] += metrics['optimizer_steps']
        self.last_metrics = metrics
        require_finite(metrics)
        require(metrics['optimizer_steps'] == self.progress['optimizer_steps'], 'Adam step accounting differs','safety_stop')
        self.actor_gradient_seen |= metrics['actor_grad_norm'] > 0
        self.critic_gradient_seen |= metrics['critic_grad_norm'] > 0
        self.kl_count = self.kl_count+1 if metrics['approx_kl'] > 0.1 else 0
        emit(self.metrics,dict(monotonic=self.clock(),counters=self.report(),metrics=metrics,
                               update_progress=self.progress))
        require(self.kl_count < 3,'Approximate KL exceeded 0.1 on three consecutive iterations','safety_stop')
        self.guard.check(force=True)

    def close(self):
        for stream in (self.episodes,self.metrics):
            if stream:
                stream.close()


def run_schedule(learner, guard, stream, *, clock=time.monotonic):
    schedule = Schedule()
    final = None
    def remaining():
        return guard.deadline-clock()
    def record(event, **extra):
        emit(stream,dict(event=event,phase_updates=learner.counters['phase_updates'],
                         remaining_worker_seconds=remaining(),reserves=schedule.receipt(),**extra))
    def closure(unevaluated=False):
        nonlocal final
        if unevaluated:
            final=learner.checkpoint('long_closure_unevaluated')
        require(final is not None,'No complete closure checkpoint','wall_guard')
        record('budget_closure',final_checkpoint=final)
        return {**outcome_fields('budget_closed_below_gate',True),
                'final_checkpoint':final,'final_checkpoint_evaluated':final['evaluated'],
                'counters':learner.report(),'schedule':schedule.receipt()}
    require(remaining() >= schedule.evaluation_cost(),'Entry evaluation reserve unavailable','wall_guard')
    final,passed,wall = learner.evaluate_checkpoint(entry=True)
    schedule.evaluation_wall(wall)
    record('cadence_evaluation',gate_passed=passed)
    while True:
        guard.check(force=True)
        if passed:
            record('gate_pass')
            return {**outcome_fields('D2_progress_gate_passed',True),'final_checkpoint':final,
                    'final_checkpoint_evaluated':True,'counters':learner.report(),'schedule':schedule.receipt()}
        if remaining() < schedule.block_cost():
            return closure()
        record('block_admitted',required_seconds=schedule.block_cost())
        for _ in range(16):
            guard.check(force=True)
            required = schedule.remaining_cost(learner.counters['phase_updates'])
            if remaining() < required:
                return closure(True)
            record('update_admitted',required_seconds=required)
            started = clock()
            learner.update_once()
            phase = learner.counters['phase_updates']
            if phase % 8 == 0 and phase % 16:
                learner.checkpoint('long_periodic')
            schedule.update_wall(clock()-started)  # Includes periodic checkpoint.
            record('update_complete')
        if remaining() < schedule.evaluation_cost():
            return closure(True)
        final,passed,wall=learner.evaluate_checkpoint()
        schedule.evaluation_wall(wall)
        record('cadence_evaluation',gate_passed=passed)


def worker(args, context):
    from types import SimpleNamespace
    p,config,base,identity,pins,lease=context
    result=outcome_fields('identity_or_lease_failure')
    guard=learner=None
    streams=ExitStack()
    imported={}
    def lease_check():
        require(os.getppid()==args.supervisor_pid,'Supervisor disappeared')
        assert_lease(args.state_path,lease)
    def verify():
        verify_files(pins)
        assert_readonly_capsule(ROOT,read_json(ROOT/'capsule-manifest.json'))
        if imported:
            imported['identity'].check_frozen(ORIGINAL_ROOT/p['base_identity_path'],
                 p['base_identity_sha256'],base,ORIGINAL_ROOT)
            check_module_origins(identity,ROOT)
    with cancellation_signals() as cancel:
        try:
            resources=streams.enter_context((args.output/'worker-resources.jsonl').open('x'))
            guard=Guard(args.started+WORKER_SECONDS,lease_check,verify,resources)
            guard.start()
            # No project import is permitted before worker ownership, capsule,
            # authority and input checks. Preserve original extension origin.
            require(not any(n=='dodge_rl' or n.startswith('dodge_rl.') for n in sys.modules),
                    'Project package imported before explicit original-root policy')
            sys.path.insert(0,str(ORIGINAL_ROOT/'python'))
            import torch
            import numpy as np
            import dodge_rl
            from dodge_rl import checkpoints as ckpt, identity as old_identity, dev_eval
            from dodge_rl.models.teacher import OmniscientEntityTeacher
            from dodge_rl.ppo import PPOConfig, collect_rollout, ppo_update
            from dodge_rl.train_teacher import (seed_initialization, make_optimizer, TrainingEnvLog,
                                                require_raw_diagnostics)
            imported.update(identity=old_identity)
            require(not os.environ.get('PYTORCH_ENABLE_MPS_FALLBACK'),'MPS fallback forbidden')
            require(torch.backends.mps.is_available(),'MPS is unavailable')
            torch.set_num_threads(4)
            require(torch.get_num_threads()==4,'Torch thread count differs')
            guard.mps=lambda:int(torch.mps.driver_allocated_memory())
            guard.check(force=True)
            historical=old_identity.check_frozen(ORIGINAL_ROOT/p['base_identity_path'],
                                      p['base_identity_sha256'],base,ORIGINAL_ROOT)
            require(historical==p['base_identity'],'Historical D2 identity differs')
            # Genuine unchanged historical terminal and transition validators.
            # They authorize neither the long seed nor 7200 seconds.
            ckpt.validate_terminal_receipt((ORIGINAL_ROOT/p['parent_checkpoint']).parent,p['parent_terminal_receipt'])
            parent,certificate=ckpt.validate_transition(ORIGINAL_ROOT/p['parent_checkpoint'],historical,
                                                       terminal_anchor=p['parent_terminal_receipt'])
            require(parent['identity']['config']['phase']=='D1' and parent['tag']=='candidate',
                    'Only exact successful D1 candidate can initialize this run')
            require(parent['counters']==PARENT_COUNTERS,'Parent counters differ')
            origins=check_module_origins(identity,ROOT)
            save(args.output/'actual-import-origins.json',origins)
            api=SimpleNamespace(torch=torch,ckpt=ckpt,teacher=OmniscientEntityTeacher,
                seed_initialization=seed_initialization,make_optimizer=make_optimizer,
                PPOConfig=PPOConfig,TrainingEnvLog=TrainingEnvLog,env_factory=dodge_rl.VecDodgeEnv,
                base=base,training_env_config=old_identity.training_env_config,
                verify_training_env=old_identity.verify_training_env,collect_rollout=collect_rollout,
                ppo_update=ppo_update,require_raw_diagnostics=require_raw_diagnostics,
                evaluate=dev_eval.evaluate,validate_summary=dev_eval.validate_summary,
                progress_passed=dev_eval.progress_passed,absolute_deadline=args.started+BUDGET)
            save(args.output/'long-config.json',config)
            save(args.output/'long-identity.json',identity)
            learner=Learner(api,config,identity,parent,guard,args.output,p)
            learner.initialize()
            schedule=streams.enter_context((args.output/'schedule.jsonl').open('x'))
            result=run_schedule(learner,guard,schedule)
            guard.check(force=True)
        except BaseException as error:
            result.update(outcome_fields(failure_outcome(error)),error=repr(error),traceback=traceback.format_exc())
        finally:
            cancel()  # Every later signal is still latched.
            if learner is not None and learner.model is not None and result_code(result)==1:
                try:
                    tag=('interrupted_mid_update' if learner.progress.get('in_update',False)
                         else 'timeout' if result['outcome']=='wall_guard' else 'failure')
                    result['failure_checkpoint']=learner.checkpoint(tag,emergency=True)
                except BaseException as error:
                    result['failure_checkpoint_unavailable']=repr(error)
            try:
                if learner is not None:
                    learner.close()
                    result['counters']=learner.report()
                    save(args.output/'checkpoint-index.json',learner.checkpoints)
                if guard is not None:
                    guard.close()
                verify()
                require(time.monotonic()<args.started+BUDGET,'Worker finalization crossed absolute deadline','wall_guard')
            except BaseException as error:
                result.update(outcome_fields(failure_outcome(error)),final_verification_error=repr(error))
            try:
                streams.close()
            except BaseException as error:
                result.update(outcome_fields('publication_failure'),stream_close_error=repr(error))
            if guard:
                result['worker_resources']=guard.receipt()
    if cancel.cancellation_requests:
        result.update(outcome_fields('cancelled'),cancellation_requests=cancel.cancellation_requests,
                      cancellation_signal=signal.Signals(cancel.requested_signal).name)
    result.update(run_id=p['run_id'],protocol_sha256=PROTOCOL_SHA256,
                  config_document_sha256=CONFIG_SHA256,identity_document_sha256=lease['identity_sha256'],
                  checkpoint_identity_semantic_sha256=semantic_hash(identity),
                  actual_import_origins=check_module_origins(identity,ROOT),
                  inherited_consumed_wall_scope='D1 historical context only; long budget uses supervisor T0',
                  worker_wall_seconds_lower_bound=time.monotonic()-args.started,
                  worker_result_write_and_process_exit_not_timed=True)
    if time.monotonic()>=args.started+BUDGET:
        result.update(outcome_fields('wall_guard'),deadline_expired=True)
    save(args.output/'long-worker-result.json',result)
    return result_code(result) if time.monotonic()<args.started+BUDGET else 1


def revoke_terminal(output,result,started,stable,error,*,clock=time.monotonic):
    manifest=output/'artifact-manifest.json'
    terminal=output/'finalization-result.json'
    run=output/'long-run-result.json'
    result.setdefault('wall_timing_scope','lower bound before terminal own write and process exit')
    manifest.unlink(missing_ok=True)
    terminal.unlink(missing_ok=True)
    for path in (run,manifest,terminal):
        pending=path.with_name('.'+path.name+'.pending')
        if pending.exists():
            os.replace(pending,path.with_name('.'+path.name+'.failed-publication'))
    result.update(outcome_fields(failure_outcome(error) if isinstance(error,Stop) else 'publication_failure'),
                  publication_error=repr(error),actual_wall_seconds_lower_bound=clock()-started)
    # No mutable output is hashed, even to decorate a failure receipt.
    replace_json(output/'artifact-manifest-unavailable.json',dict(stable=False,reason=repr(error),
                 partial_outputs_retained=True,artifacts_not_hashed=True))
    replace_json(run,result)
    replace_json(terminal,dict(**outcome_fields(result['outcome']),artifact_manifest_available=False,
                 stable_owned_group=stable,error=repr(error),
                 wall_seconds_lower_bound=clock()-started,
                 wall_timing_scope=result['wall_timing_scope'],
                 failure_receipt_persistence_may_exceed_deadline=True,
                 cleanup_seconds=result.get('cleanup_seconds'),
                 run_result_binding_unavailable=True))


def publish_terminal(output,result,started,deadline,stable,*,clock=time.monotonic,authority=lambda force=False:None):
    """Hash only closed/reaped artifacts. No success survives late writes/cancel.

    Failure-only persistence can exceed the deadline; it grants no inference,
    evaluation, checkpoint, hashing, or training time. Parent measures real exit.
    """
    manifest=output/'artifact-manifest.json'
    terminal=output/'finalization-result.json'
    run=output/'long-run-result.json'
    stages=result.setdefault('finalization_stages',[])
    result.update(terminal_status_authority='finalization-result.json',
                  completion_requires_terminal_receipt=True,
                  wall_timing_scope='lower bound before terminal own write and process exit')
    def check(stage):
        stages.append(dict(stage=stage,wall_seconds=clock()-started))
        require(clock()<deadline,'7200s deadline reached during '+stage,'wall_guard')
        authority(force=stage in ('before_terminal_authority','terminal_receipt_publication'))
        if cancel.cancellation_requests:
            raise Stop('Cancellation latched during terminal publication','cancelled')
        require(clock()<deadline,'7200s deadline reached during '+stage,'wall_guard')
    def revoke(error):
        revoke_terminal(output,result,started,stable,error,clock=clock)
    with cancellation_signals() as cancel:
        try:
            require(stable,'Owned leader/group absence unproven; artifacts were not hashed','publication_failure')
            check('closed_streams')
            replace_json(run,result)
            check('run_result_publication')
            artifacts={}
            for path in sorted(output.rglob('*')):
                if path.is_file() and path not in (manifest,terminal):
                    check('before_artifact_hash:'+str(path.relative_to(output)))
                    artifacts[str(path.relative_to(output))]=sha(path)
                    check('after_artifact_hash:'+str(path.relative_to(output)))
            replace_json(manifest,artifacts)
            check('manifest_publication')
            manifest_hash=sha(manifest)
            check('manifest_hash')
            check('before_terminal_authority')
            receipt=dict(**outcome_fields(result['outcome'],result['experiment_status']=='complete'),
                     artifact_manifest_sha256=manifest_hash,run_result_sha256=artifacts[run.name],
                     wall_seconds_lower_bound=clock()-started,wall_timing_scope=result['wall_timing_scope'],
                     finalization_stages=stages,absolute_deadline_monotonic=deadline,
                     cleanup_seconds=result.get('cleanup_seconds'),stable_owned_group=True)
            replace_json(terminal,receipt)
            check('terminal_receipt_publication')
        except BaseException as error:
            cancel()
            revoke(error)
    # Includes signals raised/deferred through context restoration and own writes.
    if cancel.cancellation_requests:
        result.update(cancellation_requests=cancel.cancellation_requests)
        revoke(Stop('Cancellation latched during terminal publication','cancelled'))
    if clock()>=deadline and result['experiment_status']=='complete':
        revoke(Stop('Deadline crossed after terminal publication','wall_guard'))
    return result_code(result)


def _supervise(args,cancel,*,context_provider=capsule_context,command_factory=None,
              guard_factory=Guard,alarm_factory=absolute_alarm,started=None):
    """Injection points are Python-only synthetic fixtures; CLI exposes none."""
    started=LAUNCH_MONOTONIC if started is None else started
    deadline=started+BUDGET
    process=guard=None
    stable=True
    result=outcome_fields('identity_or_lease_failure')
    args.output=args.output.resolve()
    # Inspect authority before creating the unique output, then recheck in guards.
    with alarm_factory(deadline):
        p,config,base,identity,pins,lease=context_provider(ROOT)
    require(args.output==ORIGINAL_ROOT/p['output'],'Unregistered campaign output')
    require(Path(args.state_path).resolve()==STATE_PATH,'Noncanonical parent lease path')
    assert_lease(args.state_path,lease)
    args.output.mkdir(parents=False,exist_ok=False)
    def lease_check():
        assert_lease(args.state_path,lease)
    def verify():
        verify_files(pins)
        assert_readonly_capsule(ROOT,read_json(ROOT/'capsule-manifest.json'))
        if 'legacy_module_origins' in identity:
            check_module_origins(identity,ROOT)
    stream=io.StringIO()
    try:
        try:
            with alarm_factory(deadline):
                guard=guard_factory(deadline,lease_check,verify,stream)
                guard.start()
                command=([sys.executable,'-B',str(Path(__file__).resolve()),'worker',
                          '--output',str(args.output),'--state-path',str(args.state_path),
                          '--started',str(started),'--supervisor-pid',str(os.getpid())]
                         if command_factory is None else command_factory(args,context_provider(ROOT)))
                result.update(run_id=p['run_id'],protocol_sha256=PROTOCOL_SHA256,required_lease=lease,
                              command=command,supervisor_started_monotonic=started,
                              absolute_deadline_monotonic=deadline,worker_deadline_monotonic=started+WORKER_SECONDS)
                with (args.output/'worker.stdout.log').open('x') as stdout, \
                     (args.output/'worker.stderr.log').open('x') as stderr:
                    blocked=signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGINT,signal.SIGTERM,signal.SIGALRM})
                    try:
                        require(not os.environ.get('PYTORCH_ENABLE_MPS_FALLBACK'),'MPS fallback forbidden')
                        process=subprocess.Popen(command,stdout=stdout,stderr=stderr,cwd=ROOT,
                            env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'),start_new_session=True)
                    finally:
                        signal.pthread_sigmask(signal.SIG_SETMASK,blocked)
                    guard.rss=lambda:(max(sampled_rss(os.getpid()),sampled_rss(process.pid))
                                      if process.poll() is None else sampled_rss(os.getpid()))
                    while process.poll() is None:
                        guard.check()
                        time.sleep(min(0.025,max(0,deadline-time.monotonic())))
                    guard.check()
                    wr=read_json(args.output/'long-worker-result.json')
                    result['worker_exit_code']=process.returncode
                    result['worker_result']=wr
                    code=result_code(wr)
                    failure=(wr.get('outcome','safety_stop') if wr.get('experiment_status')=='failed'
                             else 'publication_failure')
                    require(process.returncode==code and code in (0,2),'Worker failed; no retry',failure)
                    require(wr.get('expected_exit_code')==code,'Worker outcome/exit mismatch','publication_failure')
                    require(wr.get('teacher_qualified') is False and wr.get('training_parent_eligible') is False,
                            'Worker claimed forbidden qualification/eligibility','publication_failure')
                    result.update(outcome_fields(wr['outcome'],True))
                    guard.sample(force=True)
        except BaseException as error:
            result.update(outcome_fields(failure_outcome(error)),error=repr(error),traceback=traceback.format_exc())
        finally:
            cancel()
            cleanup_start=time.monotonic()
            if process is not None:
                try:
                    result['owned_process_stop']=stop_owned(process)
                except BaseException as error:
                    result['owned_process_stop']=dict(reaped=process.poll() is not None,group_empty=False,error=repr(error))
            result['cleanup_seconds']=time.monotonic()-cleanup_start
            stop=result.get('owned_process_stop',{})
            stable=process is None or (process.poll() is not None and stop.get('reaped') is True
                    and stop.get('group_empty') is True and not stop.get('errors') and not stop.get('error'))
            if not stable or result['cleanup_seconds']>CLEANUP_SECONDS:
                result.update(outcome_fields('publication_failure'),cleanup_failure=True)
            try:
                if guard:
                    result['supervisor_resources_before_publication']=guard.receipt()
                require(time.monotonic()<deadline,'Deadline crossed during guard close','wall_guard')
                with alarm_factory(deadline):
                    lease_check()
                    verify()
                require(time.monotonic()<deadline,'Deadline crossed during final verification','wall_guard')
            except BaseException as error:
                result.update(outcome_fields(failure_outcome(error)),final_verification_error=repr(error))
            if process is not None and process.poll() is not None and 'worker_result' not in result:
                try:
                    result['worker_result']=read_json(args.output/'long-worker-result.json')
                except (FileNotFoundError,ValueError):
                    result['worker_result_unavailable']=True
        # This disk snapshot has no live writer. All later samples remain in
        # memory and are explicitly excluded from the stable artifact inventory.
        with (args.output/'supervisor-guard.jsonl').open('x') as snapshot:
            if guard is not None and hasattr(guard,'lock'):
                with guard.lock:
                    text=stream.getvalue()
            else:
                text=stream.getvalue()
            snapshot.write(text)
        result['supervisor_observation_log_scope']='closed prepublication snapshot; later monitor is memory-only'
    except BaseException as error:
        result.update(outcome_fields(failure_outcome(error)),snapshot_error=repr(error))
    def authority(force=False):
        if cancel.cancellation_requests:
            raise Stop('Cancellation latched through final authority decision','cancelled')
        require(time.monotonic()<deadline,'Deadline crossed during final authority decision','wall_guard')
        lease_check()
        if guard is not None:
            guard.sample(force=force)
        elif force:
            verify()
        # Full hashing/probes may have allowed a request; recheck on return.
        lease_check()
        if cancel.cancellation_requests:
            raise Stop('Cancellation latched through final authority decision','cancelled')
        require(time.monotonic()<deadline,'Deadline crossed during final authority decision','wall_guard')
    if cancel.cancellation_requests:
        result.update(outcome_fields('cancelled'),cancellation_requests=cancel.cancellation_requests,
                      cancellation_signal=signal.Signals(cancel.requested_signal).name)
    if time.monotonic()>=deadline:
        result.update(outcome_fields('wall_guard'),deadline_expired=True)
    try:
        if time.monotonic() < deadline:
            with alarm_factory(deadline):
                code=publish_terminal(args.output,result,started,deadline,stable,authority=authority)
        else:
            code=publish_terminal(args.output,result,started,deadline,stable,authority=authority)
    except BaseException as error:
        # An alarm can arrive as the publication context exits. Re-enter the
        # failure/revocation path after its one-shot alarm has been disarmed.
        result.update(outcome_fields(failure_outcome(error)),publication_context_error=repr(error))
        revoke_terminal(args.output,result,started,False,error)
        code=1
    closed=False
    try:
        with alarm_factory(deadline):
            authority(force=True)
            if guard is not None:
                guard.close()
                guard.stream=None
            closed=True
            stream.close()
        # Publication alarm restoration, guard joins and stream closure all
        # precede this full check. No background writer owns an output file.
        with absolute_alarm(deadline):
            authority(force=True)
            receipt=read_json(args.output/'finalization-result.json')
            receipt.update(supervisor_resources_final=guard.receipt() if guard else {},
                           observation_log_scope=result['supervisor_observation_log_scope'],
                           inherited_consumed_wall_scope='D1 historical context only; long budget uses supervisor T0',
                           final_authority_check_after_monitor_and_stream_close=True)
            replace_json(args.output/'finalization-result.json',receipt)
            authority(force=True)  # Revalidate after our last terminal write.
        # No normal writes or contexts remain. This checks lease/resources and
        # every deferred request after the last alarm restored its handler.
        authority(force=False)
    except BaseException as error:
        cancel()
        result.update(publication_context_error=repr(error))
        revoke_terminal(args.output,result,started,stable,error)
        code=1
    finally:
        if not closed:
            # Failure-only shutdown; never hashes a buffer while its monitor runs.
            if guard is not None:
                try:
                    guard.close()
                except BaseException as error:
                    result['monitor_close_error']=repr(error)
                guard.stream=None
            stream.close()
    if cancel.cancellation_requests:
        result.update(cancellation_requests=cancel.cancellation_requests,
                      cancellation_signal=signal.Signals(cancel.requested_signal).name)
        revoke_terminal(args.output,result,started,stable,Stop('Final cancellation latch','cancelled'))
        code=1
    if time.monotonic()>=deadline and code!=1:
        revoke_terminal(args.output,result,started,stable,Stop('Final deadline check','wall_guard'))
        code=1
    return code


def supervise(args,**kwargs):
    """One effective SIGINT/SIGTERM latch through every publication/close phase."""
    with cancellation_signals() as cancel:
        code=_supervise(args,cancel,**kwargs)
    # Include the outer latch's own handler restoration, as well as every
    # borrowed inner context. Only failure persistence can occur after this.
    if cancel.cancellation_requests:
        result=read_json(args.output/'long-run-result.json')
        result.update(cancellation_requests=cancel.cancellation_requests,
                      cancellation_signal=signal.Signals(cancel.requested_signal).name)
        started=kwargs.get('started')
        started=LAUNCH_MONOTONIC if started is None else started
        stop=result.get('owned_process_stop',{})
        stable=not stop or (stop.get('reaped') is True and stop.get('group_empty') is True
                            and not stop.get('errors') and not stop.get('error'))
        revoke_terminal(args.output,result,started,stable,Stop('Outer cancellation restoration latch','cancelled'))
        code=1
    return code


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('preflight','run','worker'))
    parser.add_argument('--output',type=Path)
    parser.add_argument('--state-path',type=Path,default=STATE_PATH)
    parser.add_argument('--started',type=float,help=argparse.SUPPRESS)
    parser.add_argument('--supervisor-pid',type=int,help=argparse.SUPPRESS)
    args=parser.parse_args()
    if args.command=='preflight':
        require(args.output is None,'Pure preflight must not create campaign output')
        print(json.dumps(pure_preflight(ROOT),indent=2,sort_keys=True))
        return 0
    require(args.output is not None,'Registered output required')
    if args.command=='run':
        require(args.started is None and args.supervisor_pid is None,'Supervisor owns T0/PID')
        return supervise(args)
    require(args.supervisor_pid==os.getppid() and args.supervisor_pid>1
            and os.getsid(0)==os.getpid() and os.getpgrp()==os.getpid(),'Worker is not supervisor-owned')
    signal.pthread_sigmask(signal.SIG_SETMASK,set())
    require(args.started is not None and math.isfinite(args.started)
            and args.started<=time.monotonic()<args.started+WORKER_SECONDS,'Invalid inherited worker deadline')
    context=capsule_context(ROOT)
    require(args.output.resolve()==ORIGINAL_ROOT/context[0]['output']
            and args.state_path.resolve()==STATE_PATH,'Noncanonical worker output/lease')
    return worker(args,context)


if __name__=='__main__':
    raise SystemExit(main())
