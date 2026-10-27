"""One real-binding integration preflight, separate from M2 qualification."""
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import resource
import sys
import time
import traceback

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
CURRENT = ROOT / 'learning/scripts/v2_validate_environment.py'
BEFORE = HERE.parent / 'runner-before.py'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


started = time.monotonic()
record = {'at_utc': datetime.now(timezone.utc).isoformat(),
    'purpose': 'Bounded real API integration preflight; no M2 qualification',
    'selected_executed_source': str(CURRENT), 'selected_executed_source_sha256': digest(CURRENT),
    'old_executed_source': str(BEFORE), 'old_executed_source_sha256': digest(BEFORE),
    'native_execution': True, 'campaign_executed': False, 'wall_limit_seconds': 120,
    'observed_peak_rss_limit_bytes': 6442450944, 'status': 'running'}
exit_code = 0
try:
    assert record['selected_executed_source_sha256'] == '2a542c52413fd3ef9529688e6f7ea34652ae102c89481d8b593690664adf3303'
    assert record['old_executed_source_sha256'] == 'a7e4fd87ca0c606d42cab7e8d03fe3437a29e502d04cde8ddcd62db9afcbd35f'
    import numpy as np
    import dodge_rl._native as native
    from dodge_rl import VecDodgeEnv
    record['extension_path'] = native.__file__
    record['extension_sha256'] = digest(Path(native.__file__))
    assert record['extension_sha256'] == '967c7249acd52339d1818dcbe94e63ee734aea914c3497eb59a7e945a6e95583'
    h = load('current_supervisor', CURRENT)
    before = load('before_supervisor', BEFORE)
    plan = h.read_plan()
    try:
        VecDodgeEnv(**before.base_config(plan))
    except TypeError as error:
        assert str(error) == "argument 'excluded_seed_ranges': 'list' object cannot be cast as 'tuple'"
        record['old_constructor_negative_control'] = {'status': 'expected_TypeError', 'error': str(error)}
    else:
        raise AssertionError('Original list-based constructor unexpectedly succeeded')
    env = VecDodgeEnv(**h.base_config(plan))
    metadata = env.batch_info()
    expected = [tuple(pair) for pair in plan['effective_reserved_ranges']]
    assert metadata['additional_excluded_seed_ranges'] == expected
    assert metadata['effective_excluded_seed_ranges'] == expected
    infos = env.episode_info()
    assert len(infos) == 8
    for info in infos:
        h.audit_info(info, plan, 18000)
    observation = env.observations()
    h.validate_observation(np, observation, 8, True, True)
    record['repaired_constructor'] = {'status': 'passed', 'batch_info': metadata, 'initial_info': infos,
        'shapes': {key: list(value.shape) for key, value in observation.items() if isinstance(value, np.ndarray)}}
    del observation, env
    output = HERE / 'full-original-trajectory'
    output.mkdir(exist_ok=False)
    record['trajectory'] = h.worker_trajectory(np, VecDodgeEnv, plan, output)
    assert record['trajectory']['status'] == 'passed'
    record['status'] = 'passed'
except Exception as error:
    record.update(status='failed', error=repr(error), traceback=traceback.format_exc())
    traceback.print_exc()
    exit_code = 1
finally:
    record['elapsed_seconds'] = time.monotonic() - started
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    record['observed_peak_self_rss_bytes'] = int(peak if sys.platform == 'darwin' else peak * 1024)
    if record['observed_peak_self_rss_bytes'] > record['observed_peak_rss_limit_bytes']:
        record.update(status='failed', resource_error='Observed peak RSS limit exceeded')
        exit_code = 1
    with (HERE / 'real-api-smoke-result.json').open('x') as stream:
        json.dump(record, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')
    print(json.dumps(record, sort_keys=True), flush=True)
sys.exit(exit_code)
