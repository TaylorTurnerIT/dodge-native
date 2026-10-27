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
import socket
import stat
import lifecycle as life
import processes as owned
import boundary_integrity as integrity

ORIGINAL_ROOT = Path('/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79')
PREPARE_REL = 'learning/runs/v2/postovernight-long-D2-boundary-prepare-r6'
ROOT = Path(__file__).resolve().parents[4]
PROTOCOL_REL = 'learning/runs/v2-orchestration/postovernight-long-D2-r2-protocol-r5.json'
PROTOCOL_SHA256 = '2296154b2d06ae7c43eff0dd34c0c8908d90b5e5611a9e336a65dc2e37c48379'
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


Stop = life.Stop
INNER_SECONDS = 7170


def require(condition, message, outcome='identity_or_lease_failure'):
    if not condition:
        raise Stop(message, outcome)


HASH_OBSERVER = None
VERIFY_LOCAL = threading.local()


def sha(path):
    digest = hashlib.sha256()
    bytes_hashed = 0
    if HASH_OBSERVER is not None:HASH_OBSERVER()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            if HASH_OBSERVER is not None:HASH_OBSERVER()
            digest.update(block)
            bytes_hashed += len(block)
    if HASH_OBSERVER is not None:HASH_OBSERVER()
    stats = getattr(VERIFY_LOCAL, "stats", None)
    if stats is not None:
        stats["files"] += 1
        stats["bytes"] += bytes_hashed
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
    """One fresh metadata traversal per pass; no stat/content cache across passes.

    This checks declared disk state under the cooperative no-writer assumption.
    It does not attest loaded memory or defeat concurrent same-user replacement.
    """
    root = Path(root)
    canonical_root = root.resolve(strict=True)  # Exactly one canonicalization.
    require(root.is_absolute() and root == canonical_root and root != ORIGINAL_ROOT
            and manifest['version'] == 'long_d2_capsule_v1', 'Execute readonly canonical capsule only')
    # resolve() can leave a self-pointing alias lexically unchanged: inspect every
    # ancestor for symlinks as well. Ancestors outside root need not be readonly.
    for ancestor in (root, *root.parents):
        mode = ancestor.lstat().st_mode
        require(stat.S_ISDIR(mode), 'Capsule root/ancestor is not a real directory')
    expected = set(manifest['files']) | {'capsule-manifest.json'}
    for name in expected:
        require(type(name) is str and name and not Path(name).is_absolute()
                and str(Path(name)) == name and all(x not in ('', '.', '..') for x in name.split('/')),
                'Unsafe capsule member')
    require(not root.lstat().st_mode & 0o222, 'Capsule directory is writable')
    actual = set()
    def walk(directory, prefix):
        with os.scandir(directory) as entries:
            for entry in entries:
                name = prefix + entry.name
                mode = entry.stat(follow_symlinks=False).st_mode
                require(not stat.S_ISLNK(mode), 'Capsule contains symlink')
                if stat.S_ISDIR(mode):
                    require(not mode & 0o222, 'Capsule directory is writable')
                    walk(entry.path, name + '/')
                else:
                    require(stat.S_ISREG(mode), 'Capsule contains special file')
                    require(not mode & 0o222, 'Capsule file is writable')
                    require(name in expected, 'Capsule file inventory differs')
                    actual.add(name)
    walk(root, '')
    require(actual == expected, 'Capsule file inventory differs')


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


def capsule_context(root, *, require_capsule=True, verify_inputs=True):
    p = registered_protocol(root / PROTOCOL_REL)
    manifest_path = root / 'capsule-manifest.json'
    manifest = read_json(manifest_path)
    if require_capsule:
        assert_readonly_capsule(root, manifest)
    identity_path = root / PREPARE_REL / 'long-identity.json'
    identity = read_json(identity_path)
    require(identity['version'] == 'teacher_long_D2_boundary_identity_v1', 'Long identity version differs')
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
    classification_path = root / PREPARE_REL / 'classification.json'
    require(sha(classification_path) == identity['classification_sha256'], 'Classification digest differs')
    classification = read_json(classification_path)
    pins = dict(classification['B'])
    # Root envelopes form a DAG and are excluded from leaf classification.
    # External registration is anchored by parent-held invocation SHA, not itself.
    roots = {str(root/k):v for k,v in manifest['files'].items()}
    roots[str(manifest_path)] = sha(manifest_path)
    roots[str(ORIGINAL_ROOT/PREPARE_REL/'long-identity.json')] = sha(identity_path)
    roots[str(ORIGINAL_ROOT/PREPARE_REL/'classification.json')] = identity['classification_sha256']
    pins = integrity.merge_bindings(pins, roots)
    if verify_inputs:
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
    provenance = integrity.verify(context, root, endpoint='preflight')
    p, config, base, identity, pins, lease = context
    return dict(status='pure_identity_preflight_passed', protocol_document_sha256=PROTOCOL_SHA256,
                config_document_sha256=CONFIG_SHA256,
                identity_document_sha256=sha(root / PREPARE_REL / 'long-identity.json'),
                checkpoint_identity_semantic_sha256=semantic_hash(identity),
                capsule_manifest_sha256=sha(root / 'capsule-manifest.json'),
                legacy_sources=len(identity['base_registered_identity']['sources']),
                verified_pin_count=len(pins), required_lease=lease,
                project_torch_native_imported=False, campaign_output_created=False, provenance=provenance)


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


@contextmanager
def cancellation_signals():
    require(life.ACTIVE is not None, 'Subprocess lifetime latch required')
    yield life.ACTIVE  # Borrow only. Never restore handlers, masks or timer.


@contextmanager
def absolute_alarm(deadline):
    require(life.ACTIVE is not None and deadline <= life.ACTIVE.deadline,
            'Nested/new timer ownership forbidden')
    life.ACTIVE.check()
    yield
    life.ACTIVE.check()


class Guard:
    """Independent safety observer and synchronous declared byte boundaries.

    No periodic integrity thread, interval, revisit-age gate or content cache.
    Resource/lease observation remains independent during boundary file IO.
    """
    def __init__(self, deadline, lease_check, verify, stream, *, clock=time.monotonic,
                 rss=lambda: sampled_rss(os.getpid()), peak=self_peak, mps=lambda: 0):
        self.deadline, self.lease_check, self.verify, self.stream = deadline, lease_check, verify, stream
        self.clock, self.rss, self.peak, self.mps = clock, rss, peak, mps
        self.timings = []
        self.boundaries = []
        self.active_timing = None
        self.failure = None
        self.failure_at = None
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
        if not force:
            self.check()
            return
        with self.verify_lock:
            self.check()
            at = self.clock()
            row = dict(sequence=len(self.boundaries), start_monotonic=at, verdict='incomplete')
            require(len(self.boundaries) < 50000, 'Boundary evidence capacity exceeded')
            self.boundaries.append(row)
            cpu = time.thread_time()
            stats = dict(files=0, bytes=0, components={})
            VERIFY_LOCAL.stats = stats
            try:
                observation = self.verify()
                self.last_full = at
                self.check()
                row.update(verdict='passed', observation=observation)
            except BaseException as error:
                row.update(verdict='failed', error=repr(error))
                self.failure_at = self.failure_at or self.clock()
                self.failure = self.failure or (error if isinstance(error, Stop) else Stop(repr(error)))
                raise
            finally:
                row.update(end_monotonic=self.clock(), duration_seconds=self.clock()-at,
                           thread_cpu_seconds=time.thread_time()-cpu, **stats)
                VERIFY_LOCAL.stats = None
                self.timings.append(dict(row))

    def persist_timing(self, path, deadline, permission=lambda: None):
        """Main-thread IO only, after owned verifier teardown. No telemetry thread.

        Rows stay in bounded memory during verification; IO never takes either
        resource lock or runs on the independent resource monitor. A killed
        process can lose unflushed rows; partial/failure receipts retain what is
        safely available. The process lifetime deadline still owns every write.
        """
        require(all(t is None or not t.is_alive() for t in (self.thread,self.verify_thread)),
                'Timing persistence requires owned Guard thread absence')
        permission(); life.remaining(deadline)
        path = Path(path)
        path.parent.mkdir(parents=False, exist_ok=True)
        permission(); life.remaining(deadline)
        with path.open('x') as stream:
            for row in self.timings:
                permission(); life.remaining(deadline)
                emit(stream, row)
                life.remaining(deadline); permission()
        life.remaining(deadline); permission()
        manifest = dict(schema='long_d2_verification_output_v1', path=str(path),
                        sha256=sha(path), rows=len(self.timings), owned_threads_absent=True,
                        complete=all(r.get('end_monotonic') is not None for r in self.timings))
        permission(); life.remaining(deadline)
        save(path.with_suffix('.manifest.json'), manifest)
        life.remaining(deadline); permission()
        return manifest

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
        if full and force:
            self.full_check(True)
        self.check()

    def start(self):
        # Start resource sampling before full hashes; byte IO never blocks it.
        self.sample(full=False)
        def monitor():
            while not self.event.wait(0.05):
                try:
                    if self.clock() - self.last_sample >= 0.15:
                        self.sample(full=False)
                except BaseException as error:
                    self.failure_at = self.failure_at or self.clock()
                    self.failure = self.failure or (error if isinstance(error, Stop) else Stop(repr(error)))
                    return
        self.thread = threading.Thread(target=monitor, daemon=True, name='long-D2-guard')
        life.start_thread(self.thread)
        self.full_check(force=True)
    def close(self):
        self.event.set()
        for thread in (self.verify_thread, self.thread):
            if thread is not None:
                thread.join(timeout=life.remaining(life.POOL.deadline(self.deadline) if life.POOL else self.deadline, 0.5))
                require(not thread.is_alive(), 'Guard sampler did not stop')
        self.check()

    def receipt(self):
        return dict(maximum_rss_bytes=self.maximum_rss, maximum_self_peak_rss_bytes=self.maximum_peak,
                    maximum_mps_driver_bytes=self.maximum_mps,
                    maximum_sample_gap_seconds=self.maximum_sample_gap,
                    integrity_policy='declared_boundaries_no_fixed_revisit',
                    last_sample_monotonic=self.last_sample, last_full_verification_monotonic=self.last_full,
                    latched_failure=None if self.failure is None else repr(self.failure),
                    verification_pass_count=len(self.timings),
                    interrupted_verification=self.active_timing, boundary_count=len(self.boundaries),
                    boundary_verdicts=[r['verdict'] for r in self.boundaries])




def counter_report(counters, inherited, progress):
    partial = progress.get('optimizer_steps',0) if progress.get('in_update',False) else 0
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


@contextmanager
def verification_component(name):
    row = getattr(VERIFY_LOCAL, 'stats', None)
    start, cpu = time.monotonic(), time.thread_time()
    before = None if row is None else (row['files'], row['bytes'])
    status = 'failed'
    try:
        yield
        status = 'passed'
    finally:
        if row is not None:
            row['components'][name] = dict(duration_seconds=time.monotonic()-start,
                                          thread_cpu_seconds=time.thread_time()-cpu, status=status,
                                          observed_hash_files=row['files']-before[0],
                                          observed_hash_bytes=row['bytes']-before[1])


def observed_failure(error, guard=None, role='unknown'):
    if not isinstance(error, BaseException):
        error = Stop(str(error), 'safety_stop')
    candidates = []
    now = time.monotonic()
    existing = getattr(error, 'first_failure_descriptor', None)
    if existing is not None:
        candidates.append((existing['timestamp'], error, existing['kind'], existing['timing_basis'], existing.get('signal')))
    if guard is not None and guard.failure is not None and guard.failure_at is not None:
        candidates.append((guard.failure_at, guard.failure, 'safety_monitor', 'actual_guard_observation', None))
    latch = life.ACTIVE
    if latch is not None:
        if latch.first_cancel_at is not None:
            candidates.append((latch.first_cancel_at, Stop('Cancellation latched','cancelled'), 'cancel', 'signal_observed_sender_unknown', latch.requested_signal))
        if latch.first_alarm_at is not None:
            candidates.append((latch.first_alarm_at, Stop('Lifetime wall alarm','wall_guard'), 'alarm', 'signal_observed', int(signal.SIGALRM)))
        if latch.deadline is not None and now >= latch.deadline:
            candidates.append((latch.deadline, Stop('Absolute wall deadline','wall_guard'), 'deadline', 'absolute_registered_deadline', None))
    candidates.append((now, error, 'exception_observed', 'catch_observation_not_construction', None))
    at, primary, kind, basis, number = min(candidates, key=lambda item:item[0])
    descriptor = (dict(existing) if existing is not None and primary is error and at == existing['timestamp'] else
                  dict(timestamp=at, kind=kind, outcome=failure_outcome(primary), role=role, timing_basis=basis, signal=number))
    primary.first_failure_descriptor = descriptor
    return primary, descriptor


def primary_error(error, guard):
    return observed_failure(error, guard, 'worker')[0]


def record_primary_failure(result, error):
    descriptor = getattr(error, 'first_failure_descriptor', None)
    if descriptor is None:
        error, descriptor = observed_failure(error)
    if 'first_local_failure' not in result:
        result['first_local_failure'] = descriptor
    current = result.get('first_global_failure')
    if current is None or descriptor['timestamp'] < current['timestamp']:
        result['first_global_failure'] = descriptor
        primary = dict(outcome=failure_outcome(error), error=repr(error), descriptor=descriptor)
        result.update(outcome_fields(primary['outcome']), error=primary['error'], primary_failure=primary)
    else:
        result.setdefault('secondary_failures', []).append(descriptor)


def optional_timing(guard, path, deadline, permission=lambda: None):
    """Best effort once; retained partial bytes are evidence, never authority."""
    global HASH_OBSERVER
    previous = HASH_OBSERVER
    try:
        if life.POOL is not None and life.POOL.until is not None:
            HASH_OBSERVER = lambda: life.remaining(life.POOL.until)
        if Path(path).exists():
            return dict(status='existing_partial_or_complete', path=str(path))
        value = guard.persist_timing(path, deadline, permission)
        return dict(status='complete', manifest=value)
    except BaseException as error:
        if life.POOL is None or life.POOL.until is None:
            if isinstance(error,Stop) and (guard.failure is not None or time.monotonic()>=deadline or life.ACTIVE is not None and (life.ACTIVE.cancellation_requests or life.ACTIVE.alarm_seen)):
                raise
        return dict(status='partial_or_unavailable', path=str(path), error=repr(error))
    finally:
        HASH_OBSERVER = previous


def mandatory_failure(path, result, deadline):
    global HASH_OBSERVER
    previous = HASH_OBSERVER
    HASH_OBSERVER = lambda: life.remaining(deadline)
    try:
        life.remaining(deadline)
        replace_json(path, result)
        life.remaining(deadline)
        return True
    finally:
        HASH_OBSERVER = previous


def failure_publication(path, result, deadline, guard, timing_path):
    """Mandatory receipt attempted first; each optional action has its own catch."""
    try:
        mandatory_failure(path,result,deadline)
    except BaseException as error:
        result['mandatory_failure_publication_error'] = repr(error)
    try:
        if guard is not None:
            optional_timing(guard,timing_path,deadline)
    except BaseException:
        pass


def worker_failure(error, args, guard, learner, result, permission):
    """Memory-first failure latch; a failed ACK permanently forbids new writes."""
    error = primary_error(error, guard)
    record_primary_failure(result, error)
    permission['failed'] = True
    permission['acknowledged_until'] = None
    if life.ACTIVE is not None:
        life.ACTIVE.phase = 'FAILURE'
    local_until = life.POOL.fail(error)
    if learner is not None:
        learner.api.absolute_deadline = local_until
    if permission.get('ack_failed'):
        return False  # No recursive ACK retry or new cleanup allowance.
    try:
        require(life.CHANNEL is not None, 'Worker failure requires executor ACK')
        deadline = life.notify_failure(error)
        require(type(deadline) in (float, int) and math.isfinite(deadline)
                and deadline == life.POOL.until and deadline <= local_until,
                'Worker failure ACK deadline differs')
        life.remaining(deadline)
        if learner is not None:
            learner.api.absolute_deadline = deadline
        permission['acknowledged_until'] = deadline
        result['first_global_failure'] = life.POOL.first_global
        if life.POOL.first_global is not None:
            result.update(outcome_fields(life.POOL.first_global['outcome']))
        return True
    except BaseException as ack_error:
        permission['ack_failed'] = True
        if learner is not None:
            learner.api.absolute_deadline = life.POOL.until
        result['failure_ack_unavailable'] = repr(ack_error)
        return False


def worker_write_permission(args, result, permission, learner=None):
    """Check immediately before AND after each checkpoint/index/result write."""
    if result_code(result) == 1 or permission['failed']:
        require(permission['failed'] and not permission.get('ack_failed')
                and permission['acknowledged_until'] is not None
                and permission['acknowledged_until'] == life.POOL.until,
                'Unacknowledged failed-worker persistence forbidden')
        deadline = permission['acknowledged_until']
        if learner is not None:
            learner.api.absolute_deadline = deadline
    else:
        require(life.POOL.until is None, 'Failure cannot persist complete worker state')
        deadline = args.started + WORKER_SECONDS
    life.remaining(deadline)
    return deadline


def worker(args, context):
    from types import SimpleNamespace
    p,config,base,identity,pins,lease=context
    result=outcome_fields('identity_or_lease_failure')
    guard=learner=None
    permission=dict(failed=False, acknowledged_until=None, ack_failed=False)
    streams=ExitStack()
    imported={}
    final_runtime = {}
    def lease_check():
        require(os.getppid()==args.supervisor_pid,'Supervisor disappeared')
        assert_lease(args.state_path,lease)
    def verify():
        observation = integrity.verify(context, ROOT)
        if imported:
            imported['identity'].check_frozen(ORIGINAL_ROOT/p['base_identity_path'],
                 p['base_identity_sha256'],base,ORIGINAL_ROOT)
            origins = check_module_origins(identity,ROOT)
            runtime = integrity.runtime_check(identity,ORIGINAL_ROOT)
            runtime['project_origins'] = origins
            final_runtime.clear(); final_runtime.update(runtime)
            observation.update(legacy='genuine_unchanged_check_frozen', runtime=runtime)
        else:
            integrity.runtime_check(identity,ORIGINAL_ROOT)
            observation['legacy'] = 'preimport_byte_subset_only'
        return observation
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
                progress_passed=dev_eval.progress_passed,absolute_deadline=args.started+WORKER_SECONDS)
            save(args.output/'long-config.json',config)
            save(args.output/'long-identity.json',identity)
            learner=Learner(api,config,identity,parent,guard,args.output,p)
            learner.initialize()
            schedule=streams.enter_context((args.output/'schedule.jsonl').open('x'))
            result=run_schedule(learner,guard,schedule)
            guard.check(force=True)
        except BaseException as error:
            worker_failure(error, args, guard, learner, result, permission)
            result['traceback'] = traceback.format_exc()
        finally:
            cancel()  # Every later signal is still latched.
            if learner is not None and learner.model is not None and result_code(result)==1:
                try:
                    tag=('interrupted_mid_update' if learner.progress.get('in_update',False)
                         else 'timeout' if result['outcome']=='wall_guard' else 'failure')
                    worker_write_permission(args,result,permission,learner)
                    result['failure_checkpoint']=learner.checkpoint(tag,emergency=True)
                    worker_write_permission(args,result,permission,learner)
                except BaseException as error:
                    result['failure_checkpoint_unavailable']=repr(error)
            try:
                if learner is not None:
                    learner.close()
                    result['counters']=learner.report()
                if guard is not None:
                    guard.close()
                if result_code(result) != 1:
                    verify()
                require(time.monotonic()<life.POOL.deadline(args.started+WORKER_SECONDS),'Worker finalization crossed absolute deadline','wall_guard')
            except BaseException as error:
                worker_failure(error, args, guard, learner, result, permission)
                result['final_verification_error'] = repr(error)
            try:
                streams.close()
            except BaseException as error:
                worker_failure(error, args, guard, learner, result, permission)
                result['stream_close_error'] = repr(error)
            if guard:
                result['worker_resources']=guard.receipt()
    if cancel.cancellation_requests:
        worker_failure(Stop('Cancellation latched','cancelled'),args,guard,learner,result,permission)
        result.update(cancellation_requests=cancel.cancellation_requests,
                      cancellation_signal=signal.Signals(cancel.requested_signal).name,
                      cancellation_secondary=result['outcome'] != 'cancelled')
    if result_code(result) != 1:
        result['integrity_summary'] = integrity.worker_summary(identity,guard,final_runtime,lease)
    result.update(run_id=p['run_id'],protocol_sha256=PROTOCOL_SHA256,
                  config_document_sha256=CONFIG_SHA256,identity_document_sha256=lease['identity_sha256'],
                  checkpoint_identity_semantic_sha256=semantic_hash(identity),
                  actual_import_origins=(check_module_origins(identity,ROOT) if result_code(result)!=1 else {}),
                  inherited_consumed_wall_scope='D1 historical context only; long budget uses supervisor T0',
                  worker_wall_seconds_lower_bound=time.monotonic()-args.started,
                  worker_result_write_and_process_exit_not_timed=True)
    if time.monotonic()>=life.POOL.deadline(args.started+WORKER_SECONDS):
        record_primary_failure(result, Stop('Worker deadline expired','wall_guard'))
        result['deadline_expired'] = True
    if result_code(result)==1 and not permission['failed']:
        worker_failure(Stop(result['outcome']),args,guard,learner,result,permission)
    if permission.get('ack_failed'):
        return 1
    try:
        if guard is not None:
            result['optional_timing'] = optional_timing(guard,args.output/'worker-verification.jsonl',
                life.POOL.deadline(args.started+WORKER_SECONDS),
                lambda: worker_write_permission(args,result,permission,learner))
        if learner is not None:
            worker_write_permission(args,result,permission,learner)
            save(args.output/'checkpoint-index.json',learner.checkpoints)
            worker_write_permission(args,result,permission,learner)
        worker_write_permission(args,result,permission,learner)
        save(args.output/'long-worker-result.json',result)
        worker_write_permission(args,result,permission,learner)
    except BaseException as error:
        worker_failure(error,args,guard,learner,result,permission)
        return 1  # Never recursively retry persistence or ACK after a write error.
    return result_code(result)


def provisional(result):
    return dict(authoritative=False, acceptance_authority='outer-executor-receipt',
                internal_decision=('complete_pending_outer_acceptance' if result_code(result) in (0,2) else 'failed'))


def publish_terminal(output, result, started, deadline, stable, *, authority):
    require(stable,'Owned worker group absence unproven','publication_failure')
    result.update(provisional(result), terminal_status_authority='outer-executor-receipt',
                  completion_requires_terminal_receipt=True,
                  wall_timing_scope='provisional lower bound; parent observes outer raw exit and wall')
    authority(True)
    replace_json(output/'long-run-result.json', result)
    authority(True)
    artifacts={}
    for path in sorted(output.rglob('*')):
        require(not path.is_symlink() and path.resolve().is_relative_to(output), 'Escaped/symlink output')
        if path.is_file():
            require(path.name not in ('artifact-manifest.json','finalization-result.json')
                    and not path.name.startswith('.'), 'Existing or pending publication')
            authority(False)
            artifacts[str(path.relative_to(output))]=sha(path)
            authority(False)
    replace_json(output/'artifact-manifest.json',artifacts)
    authority(True)
    receipt={**outcome_fields(result['outcome'],True),**provisional(result),
             'artifact_manifest_sha256':sha(output/'artifact-manifest.json'),
             'run_result_sha256':artifacts['long-run-result.json'],
             'absolute_deadline_monotonic':deadline,'stable_owned_group':True,
             'wall_seconds_lower_bound':time.monotonic()-started}
    authority(False)
    replace_json(output/'finalization-result.json',receipt)
    authority(True)
    return result_code(result)


def owned_handoff(args):
    require(args.executor_pid is not None and args.executor_pid==os.getppid(), 'Executor parent required')
    require(os.getsid(0)==os.getpid()==os.getpgrp(), 'Supervisor new session required')
    channel=life.Channel.inherited(args.executor_fd)
    value,fds=channel.receive(LAUNCH_MONOTONIC+1,args.executor_pid)
    require(value.get('kind')=='start' and len(fds)==1, 'Private directed worker endpoint required')
    t0=float.fromhex(value['t0_monotonic_hex'])
    require(math.isfinite(t0) and t0<=LAUNCH_MONOTONIC<=time.monotonic(), 'Shared executor clock invalid')
    require(value.get('clock_schema')=='long_d2_owned_start_v1'
            and value.get('executor_pid')==args.executor_pid
            and value.get('protocol_sha256')==PROTOCOL_SHA256, 'Owned handoff identity/schema differs')
    life.POOL=life.FailurePool(t0)
    life.CHANNEL=channel
    latch=life.ProcessLatch();latch.install(t0+INNER_SECONDS)
    signal.pthread_sigmask(signal.SIG_UNBLOCK,life.OWNED)
    return t0,value,socket.socket(fileno=fds[0])


def worker_gate(args):
    require(args.supervisor_pid==os.getppid() and args.supervisor_pid>1
            and os.getsid(0)==os.getpid()==os.getpgrp(), 'Worker ownership/session differs')
    require(args.started is not None and math.isfinite(args.started)
            and args.started<=LAUNCH_MONOTONIC<args.started+WORKER_SECONDS, 'Invalid inherited worker clock')
    channel=life.Channel.inherited(args.executor_fd)
    life.POOL=life.FailurePool(args.started);life.CHANNEL=channel
    latch=life.ProcessLatch();latch.install(args.started+WORKER_SECONDS)
    channel.send(dict(kind='worker_ready',supervisor_pid=args.supervisor_pid,
                      executor_pid=args.executor_pid,t0_monotonic_hex=args.started.hex(),
                      protocol_sha256=PROTOCOL_SHA256),args.started+WORKER_SECONDS)
    value,fds=channel.receive(args.started+WORKER_SECONDS,args.executor_pid)
    require(not fds and value.get('kind')=='start_ack' and value.get('worker_pid')==os.getpid()
            and value.get('t0_monotonic_hex')==args.started.hex()
            and value.get('protocol_sha256')==PROTOCOL_SHA256, 'Worker start ACK differs')
    context=capsule_context(ROOT,verify_inputs=False)
    require(value.get('identity_sha256')==context[-1]['identity_sha256']
            and value.get('capsule_manifest_sha256')==context[-1]['capsule_manifest_sha256'],
            'Worker gate frozen identity differs')
    signal.pthread_sigmask(signal.SIG_UNBLOCK,life.OWNED)
    return context


def supervise_owned(args, started, handoff, gate, *, context_provider=capsule_context,
                    command_factory=None, guard_factory=Guard):
    deadline=started+INNER_SECONDS
    process=child=guard=None
    stream=io.StringIO()
    result=outcome_fields('identity_or_lease_failure')
    try:
        p,config,base,identity,pins,lease=context_provider(ROOT,verify_inputs=False)
        require(handoff['identity_sha256']==lease['identity_sha256']
                and handoff['capsule_manifest_sha256']==lease['capsule_manifest_sha256'], 'Supervisor identity handoff differs')
        require(args.output.resolve()==ORIGINAL_ROOT/p['output']
                and args.state_path.resolve()==STATE_PATH, 'Noncanonical output/lease')
        assert_lease(args.state_path,lease)
        args.output.mkdir(parents=False,exist_ok=False)
        def lease_check():
            assert_lease(args.state_path,lease)
        def verify():
            return integrity.verify((p,config,base,identity,pins,lease), ROOT)
        guard=guard_factory(deadline,lease_check,verify,stream)
        guard.start()
        def authority(force=False):
            life.ACTIVE.check()
            guard.check()
            lease_check()
            if force:
                guard.full_check(True)
            guard.sample(full=False)
            life.ACTIVE.check()
            lease_check()
            require(time.monotonic()-guard.last_sample<=.5, 'Final resource observation age exceeded','resource_stop')
        command=([sys.executable,'-B',str(Path(__file__).resolve()),'worker',
                  '--output',str(args.output),'--state-path',str(args.state_path),
                  '--started',str(started),'--supervisor-pid',str(os.getpid()),
                  '--executor-fd',str(gate.fileno()),'--executor-pid',str(args.executor_pid)]
                 if command_factory is None else command_factory(args,started,gate.fileno()))
        result.update(run_id=p['run_id'],protocol_sha256=PROTOCOL_SHA256,required_lease=lease,
                      command=command,supervisor_started_monotonic=started,
                      absolute_deadline_monotonic=deadline,worker_deadline_monotonic=started+WORKER_SECONDS)
        with (args.output/'worker.stdout.log').open('x') as stdout, (args.output/'worker.stderr.log').open('x') as stderr:
            mask=signal.pthread_sigmask(signal.SIG_BLOCK,life.OWNED)
            try:
                require(not os.environ.get('PYTORCH_ENABLE_MPS_FALLBACK'), 'MPS fallback forbidden')
                process=subprocess.Popen(command,stdout=stdout,stderr=stderr,cwd=ROOT,
                    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'),start_new_session=True,pass_fds=(gate.fileno(),))
                child=owned.Child(process)
                life.CHANNEL.send(dict(kind='register_worker',worker_pid=process.pid,worker_pgid=process.pid,
                    command=command,t0_monotonic_hex=started.hex()),deadline)
                ack,fds=life.CHANNEL.receive(deadline,args.executor_pid)
                require(not fds and ack.get('kind')=='registered' and ack.get('worker_pid')==process.pid,
                        'Worker registration ACK missing')
                gate.close()
            finally:
                signal.pthread_sigmask(signal.SIG_SETMASK,mask)
            guard.rss=lambda:owned.group_rss([os.getpgrp(),process.pid],life.POOL.deadline(deadline))
            while child.poll() is None:
                authority(False)
                require(time.monotonic()<started+WORKER_SECONDS, 'Worker raw exit cutoff reached','wall_guard')
                time.sleep(life.remaining(started+WORKER_SECONDS,.02))
            report=child.report
            life.CHANNEL.send(dict(kind='worker_wait',report=report,t0_monotonic_hex=started.hex()),deadline)
            require(report['observed_monotonic']<started+WORKER_SECONDS, 'Worker exit late','wall_guard')
            require(owned.absent(process.pid,deadline), 'Worker descendant/group still live','publication_failure')
            wr=read_json(args.output/'long-worker-result.json')
            code=result_code(wr)
            require(report['returncode']==code and code in (0,2), 'Worker raw/outcome failure','publication_failure')
            require(wr['expected_exit_code']==code and wr['teacher_qualified'] is False
                    and wr['training_parent_eligible'] is False, 'Worker outcome/qualification invalid')
            result.update(outcome_fields(wr['outcome'],True),worker_result=wr,worker_exit_code=code,
                          worker_wait_report=report,owned_process_stop=dict(reaped=True,group_empty=True,
                            owned_pid=process.pid,owned_pgid=process.pid,termination_owner='executor',errors=[]))
        authority(True)
        with guard.lock:
            snapshot=stream.getvalue()
            guard.stream=None
        with (args.output/'supervisor-guard.jsonl').open('x') as snapshot_file:
            snapshot_file.write(snapshot)
        authority(True)
        result['supervisor_observation_log_scope']='closed prepublication snapshot; later monitor memory-only'
        code=publish_terminal(args.output,result,started,deadline,True,authority=authority)
        authority(True)
        life.ACTIVE()
        guard.close()
        guard.stream=None
        stream.close()
        authority(False)
        terminal=read_json(args.output/'finalization-result.json')
        terminal.update(supervisor_resources_final=guard.receipt(),owned_guard_handles_absent=True,
                        owned_writers_absent=True,final_authority_check_after_monitor_and_stream_close=True,
                        inherited_consumed_wall_scope='D1 historical context only; long budget uses executor T0')
        replace_json(args.output/'finalization-result.json',terminal)
        authority(False)
        life.CHANNEL.send(dict(kind='inner_ready',t0_monotonic_hex=started.hex(),expected_exit_code=code,
                               owned_guard_handles_absent=True,owned_writers_absent=True),deadline)
        def final_hash_observer():
            guard.check()
            if time.monotonic()-guard.last_sample>=.15:guard.sample(full=False)
        global HASH_OBSERVER
        HASH_OBSERVER=final_hash_observer
        authority(True)
        optional_timing(guard,ORIGINAL_ROOT/Path(p['terminal_lifecycle']['acceptance_receipt']).parent/'inner-verification.jsonl',
                             deadline,lambda: authority(False))
        return code,guard
    except BaseException as error:
        # No ordinary verification or artifact hash after first failure.
        try:
            error, descriptor=observed_failure(error,guard,'inner')
            at=descriptor['timestamp']
            until=life.notify_failure(error,at)
        except BaseException as notify_error:
            until=life.POOL.fail(error)
            result['failure_ack_unavailable']=repr(notify_error)
        life.ACTIVE.phase='FAILURE'
        result.update(outcome_fields(failure_outcome(error)),**provisional(outcome_fields('failed')),
                      error=repr(error),first_failure_monotonic=life.POOL.first,
                      cleanup_until_monotonic=until,first_local_failure=life.POOL.first_local,first_global_failure=life.POOL.first_global)
        # Publish before guard joins, stream/gate closure, or optional telemetry.
        # Unproven handles/children remain explicit; this is never acceptance.
        result.update(cleanup_complete=False, experiment_status='failed_partial',
                      owned_guard_handles_absent=False,
                      owned_worker_reaped=child is not None and child.report is not None,
                      worker_wait=None if child is None else child.report)
        try:
            if args.output.is_dir():
                mandatory_failure(args.output/'inner-failure.json',result,until)
        except BaseException as publication_error:
            result['mandatory_failure_publication_error']=repr(publication_error)
        for action in (
            lambda: guard.event.set() if guard is not None else None,
            lambda: setattr(guard,'stream',None) if guard is not None else None,
            stream.close, gate.close):
            try: action()
            except BaseException: pass
        try:
            if guard is not None:
                for thread in (guard.thread,guard.verify_thread):
                    if thread is not None:thread.join(timeout=life.remaining(until,.5))
        except BaseException: pass
        try:
            if guard is not None:
                optional_timing(guard,args.output.parent/'inner-verification.jsonl',until)
        except BaseException: pass
        try: life.CHANNEL.sock.close()
        except BaseException: pass
        return 1,guard


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('preflight','run','worker'))
    parser.add_argument('--output',type=Path)
    parser.add_argument('--state-path',type=Path,default=STATE_PATH)
    parser.add_argument('--started',type=float,help=argparse.SUPPRESS)
    parser.add_argument('--supervisor-pid',type=int,help=argparse.SUPPRESS)
    parser.add_argument('--executor-fd',type=int,help=argparse.SUPPRESS)
    parser.add_argument('--executor-pid',type=int,help=argparse.SUPPRESS)
    args=parser.parse_args()
    if args.command=='preflight':
        require(args.output is None,'Pure preflight creates no output')
        print(json.dumps(pure_preflight(ROOT),indent=2,sort_keys=True))
        return
    require(args.output is not None,'Registered output required')
    if args.command=='run':
        require(args.started is None and args.supervisor_pid is None,'Executor owns shared T0')
        t0,handoff,gate=owned_handoff(args)
        code,guard=supervise_owned(args,t0,handoff,gate)
        deadline=life.POOL.until if code==1 and life.POOL.until is not None else t0+INNER_SECONDS
        life.final_exit(code,life.ACTIVE,deadline,lambda:guard is not None and guard.failure is not None)
    else:
        context=worker_gate(args)
        try:
            require(args.output.resolve()==ORIGINAL_ROOT/context[0]['output'] and args.state_path.resolve()==STATE_PATH,
                    'Noncanonical worker output/lease')
            code=worker(args,context)
        except BaseException as error:
            try:life.notify_failure(error)
            except BaseException:pass
            code=1
        try:
            if code in (0,2):
                life.CHANNEL.send(dict(kind='worker_done',t0_monotonic_hex=args.started.hex(),expected_exit_code=code),
                                  args.started+WORKER_SECONDS)
            life.CHANNEL.sock.close()
        except BaseException as error:
            life.POOL.fail(error)  # Memory only; no recursive failure ACK or persistence.
            life.ACTIVE.phase='FAILURE'
            code=1
        deadline=life.POOL.until if code==1 and life.POOL.until is not None else args.started+WORKER_SECONDS
        life.final_exit(code,life.ACTIVE,deadline)


if __name__=='__main__':
    main()
