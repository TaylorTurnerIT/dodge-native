"""Replay frozen R6 CPU controls with all test scratch redirected to parent ownership."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SOURCE = ROOT / "learning/runs/v2/current-pair-resource-calibration-prepare-luna-20261026-r6"

def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1048576), b""):
            h.update(block)
    return h.hexdigest()

def frozen():
    expected = {"calibration-plan.json": "a1c49bc5674f0dc15d54d8516f9c5d399d54316ef52b3ed8f65e23b90c9acac1",
                "source-pins.json": "23c50cf81ad71fb7d0f325fafa0dbd661aff065d15dd305059d42238d9e08ad6",
                "freeze-manifest.json": "d2d537de5b5acccf786650bc39fd8e9580cf0d7b46de8574139da28da6d55c05"}
    for name, digest in expected.items():
        assert sha(SOURCE / name) == digest, name
    return {str(path.relative_to(SOURCE)): sha(path) for path in SOURCE.rglob("*") if path.is_file()}

def main():
    started = time.monotonic()
    report = {"actual_probe": False, "actual_training": False, "MPS_operations": 0,
              "scratch_redirection": "tempfile.mkdtemp directory only; production modules unchanged"}
    try:
        before = frozen()
        (HERE / "scratch").mkdir(exist_ok=True)
        (HERE / "empty-cache").mkdir(exist_ok=True)
        script = """import runpy,sys,tempfile
from pathlib import Path
from unittest.mock import patch
source=Path(sys.argv[1]);scratch=Path(sys.argv[2]);original=tempfile.mkdtemp
def owned_mkdtemp(suffix=None,prefix=None,dir=None):
    if dir is not None and Path(dir).resolve()==source.resolve():
        dir=scratch
    return original(suffix=suffix,prefix=prefix,dir=dir)
sys.path.insert(0,str(source));sys.argv=[str(source/'test_calibration_cpu.py'),'-v']
with patch.object(tempfile,'mkdtemp',owned_mkdtemp):
    runpy.run_path(str(source/'test_calibration_cpu.py'),run_name='__main__')
"""
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONPYCACHEPREFIX=str(HERE / "empty-cache"),
                   OMP_NUM_THREADS="4", MKL_NUM_THREADS="4", OPENBLAS_NUM_THREADS="4", VECLIB_MAXIMUM_THREADS="4")
        env.pop("PYTHONPATH", None)
        command = [str(ROOT / "python/.venv/bin/python"), "-B", "-c", script, str(SOURCE), str(HERE / "scratch")]
        with (HERE / "cpu-tests.log").open("x") as stream:
            result = subprocess.run(command, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT, timeout=180)
        report.update(command=command, raw_exit=result.returncode, log_sha256=sha(HERE / "cpu-tests.log"))
        assert result.returncode == 0, "CPU suite failed; inspect retained log"
        assert "Ran 16 tests" in (HERE / "cpu-tests.log").read_text()
        after = frozen()
        assert before == after, "Frozen R6 directory membership or bytes changed"
        assert not any((HERE / "empty-cache").rglob("*"))
        report.update(status="passed_16_CPU_controls_only_pending_source_review_and_actual_probe", tests=16,
                      frozen_file_count=len(before), frozen_directory_unchanged=True, empty_cache_after=True)
    except BaseException as error:
        report.update(status="failed", error=repr(error))
        raise
    finally:
        report["elapsed_seconds"] = time.monotonic() - started
        (HERE / "validation.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps({key: report[key] for key in ("status", "elapsed_seconds")}))

if __name__ == "__main__":
    main()
