"""Independent CPU preparation replay, with no live-candidate audit."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SOURCE = ROOT / "learning/runs/v2/D2-retained276-all-candidate-auditor-luna-20261026-r3"

def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1048576), b""):
            h.update(block)
    return h.hexdigest()

def verify():
    expected = {"audit_candidates.py": "98a58d8300eebd4630eb5d8ba66cf4880b49fc0526253d3bb8fe4b9d485ab707",
                "wrapper.py": "fbc3e71532b4db918042c962efa61172848a40626ec065c78838d4d858d8f854",
                "source-manifest.json": "b5212792c2338543a5c4fe70818ece658e02e83d5006f7b8199d34a8c9f93437",
                "receipt.json": "9b39b02a542838dbdfd5924f9a5dfd015d0cb63b31cdfa1d285ca8880791e610"}
    for name, digest in expected.items():
        assert sha(SOURCE / name) == digest, name
    manifest = json.loads((SOURCE / "source-manifest.json").read_text())
    for name, digest in manifest["owned_files_sha256"].items():
        assert sha(SOURCE / name) == digest, name
    return {"source_hashes": expected, "manifest_files": len(manifest["owned_files_sha256"])}

def main():
    started = time.monotonic()
    report = {"actual_audit_called": False, "MPS_used": False,
              "game_environment_instances": 0, "game_weight_optimizer_steps": 0, "runs": []}
    try:
        report["before"] = verify()
        reg = json.loads((ROOT / "learning/runs/v2/D2-retained276-continuation-prepare-luna-20261026-r2/registration.json").read_text())
        cache = Path(reg["import_policy"]["pycache_prefix"])
        assert cache.is_dir() and not any(cache.iterdir())
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONPYCACHEPREFIX=str(cache),
                   OMP_NUM_THREADS="4", MKL_NUM_THREADS="4", OPENBLAS_NUM_THREADS="4")
        env.pop("PYTHONPATH", None)
        for name, count in (("test_audit_candidates.py", 55), ("test_terminal_wrapper.py", 25)):
            command = [reg["interpreter"], "-B", str(SOURCE / name)]
            log = HERE / (name + ".log")
            with log.open("x") as stream:
                result = subprocess.run(command, cwd=SOURCE, env=env, stdout=stream,
                                        stderr=subprocess.STDOUT, timeout=120)
            match = re.search(r"Ran (\d+) tests?", log.read_text())
            actual = int(match.group(1)) if match else None
            report["runs"].append({"command": command, "exit": result.returncode,
                                   "test_count": actual, "log": log.name, "sha256": sha(log)})
            assert result.returncode == 0 and actual == count, (name, result.returncode, actual)
        report["after"] = verify()
        assert not any(cache.iterdir())
        report["registered_cache_empty_after"] = True
        report["status"] = "passed_80_CPU_controls_only_pending_review_and_actual_terminal_audit"
    except BaseException as error:
        report.update(status="failed", error=repr(error))
        raise
    finally:
        report["elapsed_seconds"] = time.monotonic() - started
        (HERE / "validation.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps({"status": report["status"], "elapsed_seconds": report["elapsed_seconds"],
                          "tests": [item["test_count"] for item in report["runs"]]}))

if __name__ == "__main__":
    main()
