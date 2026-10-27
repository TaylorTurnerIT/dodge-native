"""Exact typed digests and explicit PyInit__native loading for CPU unit children."""
from pathlib import Path
import hashlib
import importlib.util
import json
import sys

import numpy as np

OUT = Path(__file__).resolve().parent
INPUTS = json.loads((OUT / 'inputs.json').read_text())

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def canonical(value):
    if isinstance(value, np.ndarray):
        return ['ndarray', value.dtype.str, list(value.shape),
                hashlib.sha256(value.tobytes(order='C')).hexdigest()]
    if isinstance(value, np.generic):
        return ['numpy_scalar', value.dtype.str, value.tobytes().hex()]
    if isinstance(value, dict):
        return ['dict', [[key, canonical(value[key])] for key in sorted(value)]]
    if isinstance(value, (tuple, list)):
        return [type(value).__name__, [canonical(x) for x in value]]
    if isinstance(value, float):
        return ['float', value.hex()]
    if value is None or type(value) in (bool, int, str):
        return [type(value).__name__, value]
    raise TypeError(type(value))

def digest(value):
    encoded = json.dumps(canonical(value), separators=(',', ':'), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(encoded.encode()).hexdigest()

def write(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n')

def load_native(which):
    assert sys.version_info[:3] == (3, 12, 15), sys.version
    assert not any(x == 'dodge_rl' or x.startswith('dodge_rl.') for x in sys.modules)
    path = Path(INPUTS['native_' + which])
    assert sha(path) == INPUTS['pins'][str(path)]
    spec = importlib.util.spec_from_file_location('_native', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert Path(module.__file__).resolve() == path.resolve()
    return module
