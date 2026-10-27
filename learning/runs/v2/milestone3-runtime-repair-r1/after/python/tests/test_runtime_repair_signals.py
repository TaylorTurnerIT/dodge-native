"""Synthetic cancellation and exact owned-process cleanup regressions."""
from __future__ import annotations

import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import threading
from types import SimpleNamespace

import pytest

from dodge_rl import supervision as s


@pytest.mark.parametrize("number", [signal.SIGTERM, signal.SIGINT])
def test_cancellation_signal_raises_once_and_restores_handlers(number):
    previous = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)}
    with s.cancellation_signals() as cancellation:
        with pytest.raises(s.SignalCancellation) as caught:
            signal.raise_signal(number)
        assert caught.value.signal_number == number
        assert cancellation.signal_number == number
        signal.raise_signal(number)  # A repeated signal cannot interrupt receipts.
    assert {sig: signal.getsignal(sig) for sig in previous} == previous


def test_cancellation_deferred_until_owned_pid_assignment_finishes():
    with s.cancellation_signals() as cancellation:
        cancellation.defer()
        signal.raise_signal(signal.SIGTERM)
        owned_pid = 123456
        with pytest.raises(s.SignalCancellation) as caught:
            cancellation.resume()
        assert owned_pid == 123456 and caught.value.signal_number == signal.SIGTERM
        signal.raise_signal(signal.SIGINT)


def test_cancellation_handlers_restore_after_base_exception():
    previous = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)}
    with pytest.raises(KeyboardInterrupt):
        with s.cancellation_signals():
            raise KeyboardInterrupt("synthetic caller cancellation")
    assert {sig: signal.getsignal(sig) for sig in previous} == previous


def test_cancellation_rejects_background_thread_before_handler_mutation(monkeypatch):
    calls = []
    monkeypatch.setattr(s.signal, "signal", lambda *args: calls.append(args))
    failures = []

    def background():
        try:
            with s.cancellation_signals():
                pytest.fail("Background thread obtained process signal ownership")
        except ValueError as error:
            failures.append(str(error))

    thread = threading.Thread(target=background)
    thread.start()
    thread.join(timeout=2)
    assert not thread.is_alive()
    assert failures == ["Teacher signal supervision requires the main thread"]
    assert calls == []


def test_cleanup_terminates_group_even_after_worker_leader_exited(monkeypatch):
    """Frozen r1 skips both signals because the worker leader already exited."""
    sent, waited = [], []
    group = SimpleNamespace(alive=True)
    process = SimpleNamespace(pid=740004, poll=lambda: 0,
                              wait=lambda timeout: waited.append(timeout) or 0)

    def killpg(pid, number):
        assert pid == process.pid
        if not group.alive:
            raise ProcessLookupError("group gone")
        if number:
            sent.append(number)
        if number == signal.SIGKILL:
            group.alive = False

    monkeypatch.setattr(s.os, "killpg", killpg)
    monkeypatch.setattr(s.time, "sleep", lambda seconds: None)
    result = s.stop_owned(process)
    assert sent == [signal.SIGTERM, signal.SIGKILL]
    assert waited == [5, 5]
    assert result["reaped"] and result["exit_code"] == 0 and not group.alive


def test_cleanup_real_worker_gets_graceful_signal_and_is_reaped(tmp_path):
    """A plain Python process writes a cancellation diagnostic, with no rollout."""
    diagnostic = tmp_path / "worker-cancelled.txt"
    program = """
import pathlib, signal, sys, time
def cancelled(number, frame):
    pathlib.Path(sys.argv[1]).write_text('diagnostic retained')
    raise SystemExit(0)
signal.signal(signal.SIGTERM, cancelled)
print('ready', flush=True)
while True:
    time.sleep(.1)
"""
    process = subprocess.Popen([sys.executable, "-B", "-c", program, str(diagnostic)],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, start_new_session=True)
    try:
        ready, _, _ = select.select([process.stdout], [], [], 5)
        assert ready and process.stdout.readline().strip() == "ready"
        result = s.stop_owned(process)
        assert result["reaped"] and result["exit_code"] == 0
        assert result["SIGTERM"] and "SIGKILL" not in result
        assert diagnostic.read_text() == "diagnostic retained"
        with pytest.raises(ChildProcessError):
            os.waitpid(process.pid, os.WNOHANG)
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)
        process.stdout.close()
        process.stderr.close()
