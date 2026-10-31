"""Explicit device operations for the new cloud candidate, never old packets."""
from __future__ import annotations

import sys

import torch


def peak_rss_bytes(raw_peak: int, platform: str = sys.platform) -> int:
    if platform == "darwin":
        return int(raw_peak)
    if platform.startswith("linux"):
        return int(raw_peak) * 1024
    raise ValueError("Unqualified RSS units: " + platform)


def synchronize(device):
    device = torch.device(device)
    if device.type == "cuda":
        torch.cuda.synchronize(device)
    elif device.type == "mps":
        torch.mps.synchronize()
    elif device.type != "cpu":
        raise ValueError("Unsupported learner device")


def accelerator_bytes(device) -> int:
    device = torch.device(device)
    if device.type == "cuda":
        # Reserved, rather than allocated, includes the process caching pool.
        return int(torch.cuda.memory_reserved(device))
    if device.type == "mps":
        return int(torch.mps.driver_allocated_memory())
    if device.type == "cpu":
        return 0
    raise ValueError("Unsupported learner device")


def seed_accelerator(device, seed):
    device = torch.device(device)
    if device.type == "cuda":
        with torch.cuda.device(device):
            torch.cuda.manual_seed(seed)
    elif device.type == "mps":
        torch.mps.manual_seed(seed)
    elif device.type != "cpu":
        raise ValueError("Unsupported learner device")


def accelerator_rng(device):
    device = torch.device(device)
    if device.type == "cuda":
        return torch.cuda.get_rng_state(device).clone()
    if device.type == "mps":
        return torch.mps.get_rng_state().clone()
    if device.type == "cpu":
        return None
    raise ValueError("Unsupported learner device")


def restore_accelerator_rng(device, state):
    device = torch.device(device)
    if device.type == "cuda":
        if state is None:
            raise ValueError("CUDA RNG state missing")
        torch.cuda.set_rng_state(state.cpu(), device)
    elif device.type == "mps":
        if state is None:
            raise ValueError("MPS RNG state missing")
        torch.mps.set_rng_state(state.cpu())
    elif device.type != "cpu":
        raise ValueError("Unsupported learner device")
