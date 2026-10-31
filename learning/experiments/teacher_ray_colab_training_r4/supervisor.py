"""Remote direct-child supervision; never allocation, retries or ledger writes."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import common as c
from receipts import write_stage


def group_resources(group):
    members = {}
    for path in Path('/proc').iterdir():
        if not path.name.isdigit(): continue
        try:
            stat = (path/'stat').read_text().rsplit(')', 1)[1].split()
            if int(stat[2]) == group and stat[0] != 'Z':
                members[int(path.name)] = int((path/'statm').read_text().split()[1])*os.sysconf('SC_PAGE_SIZE')
        except FileNotFoundError: continue
    return members


def driver_bytes(members):
    result = subprocess.run(['nvidia-smi', '--query-compute-apps=pid,used_gpu_memory', '--format=csv,noheader,nounits'],
                            capture_output=True, text=True, check=True, timeout=3)
    total = 0
    for line in result.stdout.splitlines():
        if not line.strip(): continue
        fields = [value.strip() for value in line.split(',')]
        c.need(len(fields) == 2 and all(value.isdigit() for value in fields), 'CUDA driver meter unavailable')
        if int(fields[0]) in members: total += int(fields[1])*1024**2
    return total


def exited_without_reaping(child):
    # Linux keeps the leader PID owned until group cleanup and the direct reap.
    return os.waitid(os.P_PID, child.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT) is not None


def supervise(command, out, reg, job, *, check_control, sample_seconds=.25,
              resource_probe=group_resources, GPU_probe=driver_bytes,
              exit_probe=exited_without_reaping, qualified_linux=True):
    c.need(not qualified_linux or sys.platform == 'linux', 'Linux supervisor ABI required')
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    c.save(out/'supervisor.claimed', dict(record='DODGE-065', job_nonce=reg['job_nonce'], command=command))
    child = None; error = None; peak_rss = peak_gpu = 0; group_absent = False
    cancelled = False
    def cancel(*_):
        nonlocal cancelled
        cancelled = True
    handlers = {sig: signal.signal(sig, cancel) for sig in (signal.SIGTERM, signal.SIGINT)}
    began = time.monotonic()
    try:
        check_control()
        with (out/'worker.stdout').open('xb') as stdout, (out/'worker.stderr').open('xb') as stderr:
            child = subprocess.Popen(command, stdout=stdout, stderr=stderr, start_new_session=True)
            c.save(out/'dispatch.json', dict(worker_expected_job=job['id'], parent_pid=os.getpid(),
                worker_pid=child.pid, registration_sha256=reg['registration_sha256'],
                campaign_started_monotonic=reg['campaign_started_monotonic'], job_index=reg['jobs'].index(job)))
            # Worker waits for this dispatch receipt before any device/constructor work.
            while not exit_probe(child):
                check_control()
                c.need(not cancelled, 'Remote supervisor cancellation')
                c.need(time.monotonic()-began < reg['work_seconds'], 'Worker work cap reached')
                members = resource_probe(child.pid)
                rss, GPU = sum(members.values()), GPU_probe(members)
                peak_rss, peak_gpu = max(peak_rss, rss), max(peak_gpu, GPU)
                c.need(rss < reg['rss_bytes'] and GPU < reg['cuda_driver_bytes'], 'Separate6GiB RSS/CUDA driver ceiling')
                time.sleep(sample_seconds)
    except BaseException as failure:
        error = repr(failure)
    finally:
        if child is not None:
            # Send only while the unreaped direct leader anchors the process group.
            try:
                try: os.killpg(child.pid, signal.SIGTERM)
                except ProcessLookupError: pass
                until = min(began+reg['work_seconds']+reg['receipt_seconds'],time.monotonic()+reg['receipt_seconds'])
                while time.monotonic() < until and resource_probe(child.pid):
                    members=resource_probe(child.pid)
                    if sum(members.values()) >= reg['rss_bytes']:
                        break
                    time.sleep(.02)
                if resource_probe(child.pid):
                    try: os.killpg(child.pid, signal.SIGKILL)
                    except ProcessLookupError: pass
            except BaseException as cleanup_error:
                error=error or 'Owned cleanup error: '+repr(cleanup_error)
            try:
                child.wait(timeout=2)
                group_absent = not resource_probe(child.pid)
            except BaseException as reap_error:
                error=error or 'Direct reap error: '+repr(reap_error)
            if child.returncode != 0: error = error or 'Worker nonzero exit '+str(child.returncode)
            if not group_absent: error = error or 'Owned group still present'
        for sig, handler in handlers.items(): signal.signal(sig, handler)
    worker_path = out/'worker-result.json'
    if not worker_path.exists(): worker_path=out/'worker-first-failure.json'
    body=None
    if worker_path.exists():
        try:
            body=c.read(worker_path)
            for key in ('trained_weights_saved','training_frames','native_games','status'):
                c.need(key in body,'Worker receipt missing field: '+key)
        except BaseException as malformed:
            error=error or 'Worker receipt unreadable: '+repr(malformed)
            body=None
    if body is None or body.get('status') != 'complete': error = error or 'Complete worker receipt absent'
    result = write_stage(out/('supervisor-result.json' if error is None else 'supervisor-first-failure.json'),
        reg, 'supervisor', 'complete' if error is None else 'failed', job=job['id'],
        trained_weights_saved=None if body is None else body['trained_weights_saved'],
        training_frames=None if body is None else body['training_frames'],
        native_games=None if body is None else body['native_games'], worker_report_present=worker_path.exists(),
        worker_result_sha256=c.sha(worker_path) if worker_path.exists() else None,
        child_returncode=None if child is None else child.returncode, owned_group_absent=group_absent,
        peak_group_RSS_bytes=peak_rss, peak_CUDA_driver_process_bytes=peak_gpu,
        elapsed_seconds=time.monotonic()-began, error=error,
        memory_limits='Sampled RSS and nvidia-smi process memory; Torch allocator peaks are worker-owned.')
    return result
