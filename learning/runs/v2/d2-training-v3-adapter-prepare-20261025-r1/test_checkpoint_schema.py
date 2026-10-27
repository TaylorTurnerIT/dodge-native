import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]
RUNTIME = ROOT / "learning/runs/v2/critic-diagnostic-parent-prepare-20261025-r1/runtime"
sys.path.insert(0, str(RUNTIME))

from dodge_rl import checkpoints


class ProspectiveCheckpointSchemaTests(unittest.TestCase):
    def test_standard_loader_accepts_normal_v3_candidate_schema(self):
        identity = {"version": "teacher_identity_v3", "run_id": "D2-training-v3-20261025-r1",
                    "phase": "D2", "policy_sha256": "a" * 64}
        state = {"version": "teacher_checkpoint_v1", "resume_mode": "fresh_env", "tag": "candidate",
                 "schema": "d2_training_v3_checkpoint_v1", "identity": identity,
                 "identity_sha256": checkpoints.identity_hash(identity),
                 "model": {"w": [1.0]}, "optimizer": {"state": {}, "param_groups": []},
                 "rng": {"python": (), "numpy_global": (), "numpy_generator": None,
                         "torch_cpu": b"cpu", "torch_mps": b"mps", "sampling_backend": "torch_global_mps"},
                 "update_progress": {"complete": True, "in_update": False},
                 "eligibility_status": "provisional_pending_parent_terminal_receipt"}
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as temp:
            path = Path(temp) / "candidate.pt"
            checkpoints.save_checkpoint(path, state)
            loaded = checkpoints.load_checkpoint(path, expected_sha256=checkpoints.file_hash(path))
            checkpoints.require_complete_update(loaded)
        self.assertEqual(loaded["version"], "teacher_checkpoint_v1")
        self.assertEqual(loaded["schema"], "d2_training_v3_checkpoint_v1")
        self.assertEqual(loaded["eligibility_status"], "provisional_pending_parent_terminal_receipt")


if __name__ == "__main__":
    unittest.main()
