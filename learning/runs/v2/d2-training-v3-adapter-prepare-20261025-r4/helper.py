"""Small audited helpers used by the prospective v3 worker. No v2 launcher."""
from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
import math
import os
from pathlib import Path
import resource
import signal
import sys
import time

PARENT_SHA = "ce9c03c8d476f58d5edec9f95946fa808d1d65890728528f9a44993eb0f0544f"
CONFIG_SHA = "2d8eb5626d0debdf5416d0b89610d78ddd56011c3238a82fec72efabe1bd7fe3"
ANCHOR_SHA = "4e9f12884712916e9eb957628b89b357784c79d0f1f6f8ab18e6047935197413"
VALIDATOR_SHA = "72c34ea7a3208f8ce1cba1cd144b3ba58bac7b246ce57610b70970355ac60c55"
ARCHIVE_SHA = "3b4b1e4f3337323de9938c0c86f158036d8dacc77acba645b3e150d9d2e765bd"
NEW_NATIVE_SHA = "022d41dde9bace0b4f4c4c06b9b4ed007bc2c60013cd98734086e587d7bb997e"
OLD_NATIVE_SHA = "967c7249acd52339d1818dcbe94e63ee734aea914c3497eb59a7e945a6e95583"
RANGES = [[0xB0000000, 0xB00003E7], [0xD0000000, 0xD000007F], [0xE0000000, 0xE00003E7]]
LIMITS = {"max_updates": 72, "eval_updates": [0, 72], "work_seconds": 1600,
          "total_seconds": 1800, "RSS_bytes": 6442450944, "MPS_bytes": 6442450944,
          "retries": 0}
PPO = {"gamma": .995, "gae_lambda": .95, "learning_rate": .0003, "adam_eps": .00001,
       "clip_coef": .2, "vf_coef": .5, "ent_coef": .01, "max_grad_norm": .5,
       "update_epochs": 4, "minibatch_size": 512, "target_kl": .03, "reward_scale": .1}


def need(condition, message):
    if not condition:
        raise ValueError(message)

def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1048576), b""):
            digest.update(chunk)
    return digest.hexdigest()

def read(path):
    return json.loads(Path(path).read_text())

def save(path, value):
    """New-path publication only; no replacing old receipts."""
    with Path(path).open("x") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())

def emit(stream, value):
    stream.write(json.dumps(value, sort_keys=True, allow_nan=False) + "\n")
    stream.flush()

def check_lease(reg):
    need(read(reg["state_path"]).get("active_long_campaign") == reg["expected_lease"],
         "Exact parent-owned diagnostic lease changed")

def finite_tree(value, key=""):
    if isinstance(value, dict):
        for name, item in value.items():
            finite_tree(item, name)
    elif isinstance(value, list):
        for item in value:
            finite_tree(item, key)
    elif value is None:
        need(key == "explained_variance", "Unexpected null metric")
    elif isinstance(value, float):
        need(math.isfinite(value), "Nonfinite metric")

def fingerprint(value):
    """Device-independent typed tree digest; does not consume RNG."""
    h = hashlib.sha256()
    def field(tag, payload=b""):
        tag = tag.encode("utf-8")
        h.update(len(tag).to_bytes(8, "big")); h.update(tag)
        h.update(len(payload).to_bytes(8, "big")); h.update(payload)
    def visit(v):
        if hasattr(v, "detach"):
            v = v.detach().cpu().contiguous().numpy()
        if hasattr(v, "dtype") and hasattr(v, "tobytes"):
            field("array", (str(v.dtype) + repr(tuple(v.shape))).encode())
            field("array-bytes", v.tobytes()); return
        if isinstance(v, Mapping):
            field("mapping", len(v).to_bytes(8, "big"))
            for k in sorted(v, key=lambda key: (type(key).__name__, repr(key))):
                field("entry")
                visit(k); visit(v[k])
            field("end-mapping")
        elif isinstance(v, list):
            field("list", len(v).to_bytes(8, "big"))
            for item in v:
                visit(item)
            field("end-list")
        elif isinstance(v, tuple):
            field("tuple", len(v).to_bytes(8, "big"))
            for item in v:
                visit(item)
            field("end-tuple")
        else:
            field("scalar:" + type(v).__module__ + "." + type(v).__qualname__, repr(v).encode())
    visit(value)
    return h.hexdigest()

def mismatch_paths(left, right, path="$", limit=128):
    """Return paths only; never serialize tensor, RNG, or scalar contents."""
    if fingerprint(left) == fingerprint(right):
        return []
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        if set(left) != set(right):
            return [path + ".<keys>"]
        found = []
        for key in sorted(left, key=lambda item: (type(item).__name__, repr(item))):
            found.extend(mismatch_paths(left[key], right[key], path + "." + str(key), limit))
            if len(found) >= limit:
                return found[:limit]
        return found or [path]
    if type(left) is not type(right):
        if hasattr(left, "detach") and hasattr(right, "detach"):
            try:
                if left.dtype != right.dtype: return [path + ".<dtype>"]
                if tuple(left.shape) != tuple(right.shape): return [path + ".<shape>"]
            except Exception:
                pass
        return [path + ".<type>"]
    if isinstance(left, (list, tuple)):
        if len(left) != len(right): return [path + ".<length>"]
        found = []
        for index, (a, b) in enumerate(zip(left, right)):
            found.extend(mismatch_paths(a, b, path + f"[{index}]", limit))
            if len(found) >= limit: return found[:limit]
        return found or [path]
    if hasattr(left, "detach") and hasattr(right, "detach"):
        if left.dtype != right.dtype: return [path + ".<dtype>"]
        if tuple(left.shape) != tuple(right.shape): return [path + ".<shape>"]
    return [path]

class Cancelled(BaseException):
    pass

class Guard:
    def __init__(self, reg, started, torch, stream, clock=time.monotonic):
        self.reg, self.started, self.torch, self.stream, self.clock = reg, started, torch, stream, clock
        self.last_lease = self.last_sample = -math.inf
        self.peak_rss = self.peak_mps = 0
        self.first_failure = None
        self.first_signal = None

    def signal(self, number, _frame):
        if self.first_signal is None:
            self.first_signal = number
            if self.first_failure is None:
                self.first_failure = {"monotonic": self.clock(), "kind": "cancelled", "signal": number}
            raise Cancelled("Cancellation signal " + str(number))

    def check(self, *, finalizing=False):
        now = self.clock()
        try:
            need(self.first_signal is None, "Cancellation latched")
            budget = LIMITS["total_seconds"] if finalizing else LIMITS["work_seconds"]
            need(now - self.started < budget, "Absolute diagnostic budget exhausted")
            if now - self.last_lease >= .15:
                check_lease(self.reg); self.last_lease = now
            if now - self.last_sample >= .05:
                rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                rss = int(rss if sys.platform == "darwin" else rss * 1024)
                mps = int(self.torch.mps.driver_allocated_memory())
                self.peak_rss, self.peak_mps = max(self.peak_rss, rss), max(self.peak_mps, mps)
                emit(self.stream, {"monotonic": now, "elapsed_seconds": now - self.started,
                                   "peak_rss_bytes": self.peak_rss, "mps_driver_bytes": mps})
                self.last_sample = now
                need(rss <= LIMITS["RSS_bytes"] and mps <= LIMITS["MPS_bytes"], "Resource cap exceeded")
        except BaseException as error:
            if self.first_failure is None:
                self.first_failure = {"monotonic": now, "error": repr(error)}
            raise

def performance(evaluation):
    rows = evaluation["rows"]
    need(evaluation["complete"] is True and len(rows) == 64, "Incomplete development evaluation")
    summary = {}
    for name in ("alive_frames", "score"):
        values = sorted(row[name] for row in rows)
        summary[name] = {"Q1": sum(values[:16]) / 16, "Q4": sum(values[-16:]) / 16,
                         "mean": sum(values) / 64}
    return summary

