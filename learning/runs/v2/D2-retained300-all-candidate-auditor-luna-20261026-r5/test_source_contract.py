"""Pinned source and terminal boundary controls."""
import hashlib
import json
from pathlib import Path
import unittest
import audit_candidates as a
import wrapper as w

class SourceBoundary(unittest.TestCase):
    def test_registered_sources_and_own_bytecode_prefix(self):
        self.assertEqual(a.REG_SHA, "8a60dc80f1ebe03c43bf18eebf75199e14f207b677570ac2d6d4368ddfcb0f79")
        self.assertEqual(a.RUNNER_SHA, "108ba55ad78aa26166acb14f67cc6466da6293ccee3d272e1fe6e775ebf2ac60")
        self.assertEqual(a.LAUNCHER_SHA, "7215ae6628c364fe74bafba68e66cb1c688000a3b7d648dba9248fc2d812310e")
        self.assertEqual(a.REGISTRATION_SCHEMA_SHA, "eae76ec910b232b2cf6accbb6107a35b8cfedb5db162a6328e02bcee3367c088")
        self.assertEqual(a.UPDATES, (300,312,324,336,348,360))
        self.assertEqual(a.PARENT_TOTAL_UPDATES, 348)
        self.assertEqual(a.LR_ARM, 3e-5)
        reg=json.loads(a.REG_PATH.read_text())
        self.assertEqual(reg["parent"]["sha256"], a.PARENT_SHA)
        self.assertEqual(reg["expected_outputs"], a.expected_outputs())
        self.assertIn("lr-transition.json", reg["forbidden_outputs"])
        self.assertEqual(w.PYCACHE_PREFIX, w.OUT / "empty-pycache")
        with self.assertRaises(w.WrapperError): w.bind_observer_directory(w.OUT)
        self.assertIn("PYTHONPATH must be unset",Path(a.__file__).read_text())

    def test_terminal_observer_negative_controls(self):
        observation={"outer_raw_exit":0,"worker_raw_exit":0,"first_event":None,"launch_count":1,
          "outer_limit_seconds":1800,"outer_inclusive_wall_seconds":100,"max_aggregate_rss_bytes":1,
          "aggregate_rss_limit_bytes":6442450944,"mps_limit_bytes":6442450944,"outer_process_absent":True,
          "worker_process_absent":True,"worker_group_absent":True,
          "success_authoritative":True,"postflight":{"lease":{"active_long_campaign_exact":True,
          "active_inference_campaign":None,"active_inference_lease":None,"active_inference_diagnostic":None},
          "pins":{"checked":13827,"failures":[]},"cache_empty_after":True,"publication_failure_absent":True}}
        execution={"actual_worker_launch_count":1,"observed_worker_raw_exit":0,"status":"passed","worker_pid":99999999,"owned_pgid":99999998}
        worker={"status":"completed","first_failure":None,"peak_rss_bytes":1,"peak_mps_driver_bytes":1}
        w.terminal_gates(observation,execution,worker)
        for key,value in (("outer_raw_exit",1),("worker_raw_exit",1),("launch_count",2),("first_event","signal"),("worker_process_absent",False)):
            bad=dict(observation); bad[key]=value
            with self.assertRaises(w.WrapperError): w.terminal_gates(bad,execution,worker)
        bad=dict(execution); bad["observed_worker_raw_exit"]=1
        with self.assertRaises(w.WrapperError): w.terminal_gates(observation,bad,worker)
        bad=dict(observation); bad["postflight"]={**observation["postflight"],"publication_failure_absent":False}
        with self.assertRaises(w.WrapperError): w.terminal_gates(bad,execution,worker)
        bad=dict(observation); bad["postflight"]={**observation["postflight"],"pins":{"checked":13826,"failures":[]}}
        with self.assertRaises(w.WrapperError): w.terminal_gates(bad,execution,worker)
        bad=dict(worker); bad["first_failure"]={"error":"synthetic"}
        with self.assertRaises(w.WrapperError): w.terminal_gates(observation,execution,bad)

    def test_wrapper_hash_and_cli_refuses_full_mode(self):
        self.assertEqual(hashlib.sha256(w.AUD_PATH.read_bytes()).hexdigest(),w.AUD_SHA)
        self.assertEqual(w.OBSERVER_SHA,"37713a27cb8166dde21d672d4347bb919e3bd2f30f0cc2dd03a12cdfb4b7fae1")
        with self.assertRaises(SystemExit): w.main([])
        self.assertIn("full mode is parent-only",Path(w.__file__).read_text())

if __name__ == "__main__": unittest.main()
