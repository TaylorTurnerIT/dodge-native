"""Real dummy children and pure billing faults; no cloud/native/accelerator work."""
import os
import hashlib
import json
from pathlib import Path
import sys
import threading
import time
import tarfile
from unittest.mock import patch

import pytest

from billing_guard import BillingGuard, Config
from bundle import build, extract_verified
from device_watchdog import supervise


ASSIGNMENTS = [{"endpoint": "owned", "accelerator": "T4"}]


def observe(guard, now=15, balance=99.99, rate=2, count=1, **kwargs):
    return guard.observe({"currentBalance": balance, "consumptionRateHourly": rate,
                          "assignmentsCount": count}, ASSIGNMENTS, "owned", now,
                          request_started=now-1, **kwargs)


def test_unchanged_balance_admits_and_remains_explicitly_unverified():
    guard = BillingGuard(100, 0)
    first = observe(guard, balance=100)
    assert first['fixtures_admitted'] and not first['balance_progress_seen']
    assert first['balance_freshness_proven'] is False
    for now in (90, 120, 300, 739):
        result = observe(guard, now=now, balance=100, fixtures_started=True)
        assert result['fixtures_admitted'] and result['projected_total_CU'] == pytest.approx(Config().prior_cost_upper_estimate_CU + 860 * 3 / 3600)
        assert result['accounted_cost_upper_estimate_CU'] > 0
    assert observe(guard, now=739, balance=99.5)['balance_progress_seen']


@pytest.mark.parametrize('rate', [0, -1, None, '2', float('nan'), float('inf'), 3.001])
def test_invalid_live_rate_fails_closed(rate):
    with pytest.raises(ValueError, match='rate or balance'):
        observe(BillingGuard(100, 0), rate=rate)


def test_missing_values_ownership_and_overlong_requests_are_not_defaults():
    with pytest.raises(ValueError):
        BillingGuard(100, 0).observe({}, ASSIGNMENTS, 'owned', 15, request_started=14)
    with pytest.raises(ValueError, match='Exact owned T4'):
        BillingGuard(100, 0).observe(
            {'currentBalance': 100, 'consumptionRateHourly': 2, 'assignmentsCount': 1},
            [{'endpoint': 'other', 'accelerator': 'T4'}], 'owned', 15, request_started=14)
    with pytest.raises(ValueError, match='Exactly one'):
        observe(BillingGuard(100, 0), count=2)
    with pytest.raises(ValueError, match='overlong'):
        BillingGuard(100, 0).observe({}, [], 'owned', 16, request_started=0)
    with pytest.raises(ValueError, match='discovery exceeded120s'):
        observe(BillingGuard(100, 0), now=121)


def test_cost_estimate_cuts_work_even_when_observed_debit_is_below6():
    guard = BillingGuard(100, 0); observe(guard, balance=100)
    with pytest.raises(ValueError, match='6CU'):
        observe(guard, now=739, balance=94.5, fixtures_started=True)
    with pytest.raises(ValueError, match='6CU'):
        observe(BillingGuard(100, 0), balance=94)
    with pytest.raises(ValueError, match='rose'):
        observe(BillingGuard(100, 0), balance=100.01)
    with pytest.raises(ValueError, match='not be relaxed'):
        BillingGuard(100, 0, Config(maximum_assigned_seconds=901))


def test_T4_budget_and_last_work_boundary_are_exact():
    config = Config()
    assert (config.maximum_assigned_seconds, config.teardown_reserve_seconds,
            config.maximum_rate_CU_per_hour, config.maximum_debit_CU,
            config.stop_work_debit_CU) == (860, 120, 3, 8, 6)
    with pytest.raises(ValueError, match='balance unavailable/insufficient'):
        BillingGuard(7.99, 0)
    guard = BillingGuard(100, 0); assert observe(guard, balance=100)['fixtures_admitted']
    assert observe(guard, now=739, balance=100, fixtures_started=True)['fixtures_admitted']
    with pytest.raises(ValueError, match='work deadline'):
        observe(guard, now=740, balance=100, fixtures_started=True)


def test_other_accelerators_cannot_satisfy_T4_ownership():
    for accelerator in ('A100', 'L4', 'H100', None):
        with pytest.raises(ValueError, match='Exact owned T4'):
            BillingGuard(100, 0).observe(
                {'currentBalance': 100, 'consumptionRateHourly': 2, 'assignmentsCount': 1},
                [{'endpoint': 'owned', 'accelerator': accelerator}], 'owned', 15, request_started=14)


@pytest.mark.parametrize('name', ['Tesla T4', 'NVIDIA T4'])
def test_single_T4_product_names(name):
    from remote_entry import require_single_T4
    assert require_single_T4(name + '\n') == name


@pytest.mark.parametrize('name', ['NVIDIA A100-SXM4-40GB', 'NVIDIA H100', 'Tesla T40',
    'Tesla T4\nTesla T4', 'MIG 1g.5gb', 'NVIDIA T4 MIG 1g5gb'])
def test_GPU_fallback_multiple_and_MIG_rejected(name):
    from remote_entry import require_single_T4
    with pytest.raises(ValueError, match='whole T4'):
        require_single_T4(name)


def test_bundle_deterministic_allowlist_and_corruption(tmp_path):
    left, manifest, digest = build(); right, _, other_digest = build()
    assert left == right and digest == other_digest
    assert not any(name.endswith((".so", ".pt", ".sqlite3")) for name in manifest)
    archive = tmp_path / "payload.tar"; archive.write_bytes(left)
    assert extract_verified(archive, tmp_path / "clean", digest) == manifest
    with pytest.raises(FileExistsError):
        extract_verified(archive, tmp_path / "clean", digest)
    archive.write_bytes(left + b"corruption")
    with pytest.raises(ValueError, match="hash differs"):
        extract_verified(archive, tmp_path / "bad", digest)


def live_dummy(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return {}
    return {pid: 4096}


def run_dummy(tmp_path, code, **limits):
    with patch("device_watchdog.sys.platform", "linux"):
        result = supervise([sys.executable, "-B", "-c", code], tmp_path / "result.json",
            work_seconds=limits.get("seconds", 2), rss_bytes=limits.get("rss", 1024**3),
            cuda_bytes=1024**3, require_cuda=limits.get("cuda", False),
            cancel_path=tmp_path / "cancel", resource_probe=live_dummy,
            cuda_probe=limits.get("cuda_probe", lambda _: 0), sample_seconds=.01)
    if result["child_pid"] is not None:
        with pytest.raises(ProcessLookupError):
            os.kill(result["child_pid"], 0)
    return result


def test_real_dummy_completes_once_and_duplicate_refuses(tmp_path):
    assert run_dummy(tmp_path, "print('done')")["status"] == "complete"
    with pytest.raises(FileExistsError):
        run_dummy(tmp_path, "raise AssertionError('must not launch')")


def test_mid_child_interruption_reaps_started_work(tmp_path):
    marker = tmp_path / "entered"
    def interrupt():
        until = time.monotonic() + 2
        while not marker.exists() and time.monotonic() < until:
            time.sleep(.005)
        (tmp_path / "cancel").touch()
    thread = threading.Thread(target=interrupt); thread.start()
    try:
        result = run_dummy(tmp_path,
            f"from pathlib import Path;import time;Path({str(marker)!r}).touch();time.sleep(3)")
    finally:
        thread.join(timeout=3)
    assert marker.exists() and "cancelled" in result["error"]


def test_CUDA_entry_requires_nonce_and_billing_before_device_work(tmp_path, monkeypatch):
    import compatibility
    args = ["compatibility.py", "--device", "cuda", "--checkpoint", str(tmp_path/"missing.pt"),
            "--output", str(tmp_path/"result.json")]
    monkeypatch.setattr(sys, "argv", args)
    with pytest.raises(ValueError):
        compatibility.main()
    monkeypatch.setattr(sys, "argv", args + ["--job-nonce", "00000000-0000-0000-0000-000000000057"])
    monkeypatch.delenv("DODGE060_BILLING_ADMITTED", raising=False)
    with pytest.raises(ValueError, match="billing admission absent"):
        compatibility.main()
    assert not list(tmp_path.iterdir())


def test_bootstrap_failure_download_bundle_retains_nonce_once(tmp_path, monkeypatch):
    import remote_entry
    (tmp_path / "content").mkdir()
    def mapped_path(path):
        text = str(path)
        return tmp_path / text.lstrip("/") if text.startswith("/content/") else Path(path)
    monkeypatch.setattr(remote_entry, "Path", mapped_path)
    monkeypatch.setattr(remote_entry.sys, "platform", "linux")
    monkeypatch.setenv("DODGE060_PAYLOAD_SHA256", "0" * 64)
    monkeypatch.setenv("DODGE060_BILLING_ADMITTED", "true")
    nonce = "00000000-0000-0000-0000-000000000057"
    monkeypatch.setenv("DODGE060_JOB_NONCE", nonce)
    with pytest.raises(FileNotFoundError):
        remote_entry.main()
    archive = tmp_path / "content/dodge-ray060-receipts.tar"
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    with tarfile.open(archive) as bundle:
        result = json.loads(bundle.extractfile("bootstrap-result.json").read())
        assert result["job_nonce"] == nonce and result["status"] == "failed"
        assert result["native_games"] == result["training_frames"] == 0
        assert not result["trained_weights_saved"]
        assert "bootstrap-first-failure.json" in bundle.getnames()
    with pytest.raises(FileExistsError):
        remote_entry.main()
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == digest


@pytest.mark.parametrize("fault", ["wall", "RSS", "cancel", "CUDA_probe", "child_exit"])
def test_real_dummy_failure_is_preserved_and_reaped(tmp_path, fault):
    limits = {}
    code = "import time;time.sleep(3)"
    if fault == "wall": limits["seconds"] = .03
    if fault == "RSS": limits["rss"] = 1
    if fault == "cancel": (tmp_path / "cancel").touch()
    if fault == "child_exit": code = "raise SystemExit(4)"
    if fault == "CUDA_probe":
        def fail(_): raise RuntimeError("driver probe unavailable")
        limits.update(cuda=True, cuda_probe=fail)
    result = run_dummy(tmp_path, code, **limits)
    assert result["status"] == "failed" and result["error"]
    assert (tmp_path / "result.json.claimed").is_file()
    assert (tmp_path / "result.json.first-failure.json").is_file()
    assert not (tmp_path / "result.json").exists()
