"""CPU mocks verify device routing without touching any accelerator API."""
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import torch

from dodge_rl import device_runtime as d


def test_RSS_units_are_explicit():
    assert d.peak_rss_bytes(123, "darwin") == 123
    assert d.peak_rss_bytes(123, "linux") == 123 * 1024
    with pytest.raises(ValueError, match="Unqualified RSS"):
        d.peak_rss_bytes(123, "win32")


def test_CPU_never_calls_accelerator():
    with patch.object(torch.cuda, "synchronize", side_effect=AssertionError), \
         patch.object(torch.mps, "synchronize", side_effect=AssertionError):
        d.synchronize("cpu")
        d.seed_accelerator("cpu", 1)
        assert d.accelerator_bytes("cpu") == 0
        assert d.accelerator_rng("cpu") is None
        d.restore_accelerator_rng("cpu", None)


def test_CUDA_uses_reserved_memory_and_specific_device():
    with patch.object(torch.cuda, "memory_reserved", return_value=123) as memory, \
         patch.object(torch.cuda, "synchronize") as sync:
        assert d.accelerator_bytes("cuda:1") == 123
        d.synchronize("cuda:1")
        memory.assert_called_once_with(torch.device("cuda:1"))
        sync.assert_called_once_with(torch.device("cuda:1"))


def test_CUDA_RNG_is_owned_and_cloned():
    rng = torch.tensor([1, 2, 3], dtype=torch.uint8)
    with patch.object(torch.cuda, "get_rng_state", return_value=rng), \
         patch.object(torch.cuda, "set_rng_state") as restore:
        saved = d.accelerator_rng("cuda:0")
        assert torch.equal(saved, rng) and saved.data_ptr() != rng.data_ptr()
        d.restore_accelerator_rng("cuda:0", saved)
        restore.assert_called_once()
        assert restore.call_args.args[1] == torch.device("cuda:0")
    with pytest.raises(ValueError, match="CUDA RNG state missing"):
        d.restore_accelerator_rng("cuda:0", None)


def test_unknown_device_rejected():
    for operation in (d.synchronize, d.accelerator_bytes, d.accelerator_rng):
        with pytest.raises(ValueError, match="Unsupported"):
            operation("meta")


def test_checkpoint_CUDA_RNG_capture_restore_is_explicit():
    from dodge_rl.checkpoints import capture_rng, restore_rng
    rng = torch.tensor([1, 7], dtype=torch.uint8)
    with patch.object(torch.cuda, "get_rng_state", return_value=rng), \
         patch.object(torch.cuda, "set_rng_state") as restore:
        saved = capture_rng("cuda:1")
        assert saved["sampling_backend"] == "torch_global_cuda"
        assert torch.equal(saved["torch_cuda"], rng)
        assert saved["torch_cuda"].data_ptr() != rng.data_ptr()
        restore_rng(saved, "cuda:1")
        assert restore.call_args.args[1] == torch.device("cuda:1")
