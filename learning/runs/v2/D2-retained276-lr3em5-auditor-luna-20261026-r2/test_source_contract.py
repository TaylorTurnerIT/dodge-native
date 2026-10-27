"""Static source-boundary controls for the independent auditor."""
import hashlib
import json
from pathlib import Path
import unittest
import audit_candidates as a
import wrapper as w

class SourceBoundary(unittest.TestCase):
    def test_registered_r2_inputs_and_schema_origin_are_exact(self):
        self.assertEqual(a.REG_SHA, "8e17e1188253f091b62a8b60397663a530c4a865166f9568978dd009148308e7")
        self.assertEqual(a.RUNNER_SHA, "013ef0b526bfbce89588a429ec01766aece59e3553d08047d0616b3744607267")
        self.assertEqual(a.LAUNCHER_SHA, "fd7298a8d6a7885a341c2f5c5d1eb4c5e407654a579f15403f9f342fffc8aa2d")
        self.assertEqual(a.REGISTRATION_SCHEMA_SHA, "f8956515024db261902e541a29d48f8b30e96f9efd05ee618e3759af95f1af9b")
        reg=json.loads(a.REG_PATH.read_text())
        w.bind_interpreter(reg)
        w.bind_bytecode()
        self.assertEqual(str(a.PREP/"registration_schema.py"),reg["registration_schema_module_path"])
        self.assertEqual(a.REGISTRATION_SCHEMA_SHA,reg["registration_schema_module_sha256"])
        self.assertIn("PYTHONPATH must be unset",Path(a.__file__).read_text())

    def test_terminal_observer_and_closed_receipt_negative_controls(self):
        observation={"outer_raw_exit":0,"worker_raw_exit":0,"first_event":None,"launch_count":1,
          "outer_limit_seconds":1800,"outer_inclusive_wall_seconds":100,"max_aggregate_rss_bytes":1,
          "aggregate_rss_limit_bytes":6442450944,"mps_limit_bytes":6442450944,"outer_process_absent":True,
          "worker_process_absent":True,"worker_group_absent":True,
          "postflight":{"pins":{"failures":[]},"cache_empty_after":True}}
        execution={"actual_worker_launch_count":1,"observed_worker_raw_exit":0,"status":"passed"}
        worker={"status":"completed","first_failure":None,"peak_rss_bytes":1,"peak_mps_driver_bytes":1}
        w.terminal_gates(observation,execution,worker)
        for key,value in (("outer_raw_exit",1),("worker_raw_exit",1),("launch_count",2),("first_event","signal"),
                          ("worker_process_absent",False)):
            bad=dict(observation); bad[key]=value
            with self.assertRaises(w.WrapperError): w.terminal_gates(bad,execution,worker)
        bad=dict(execution); bad["observed_worker_raw_exit"]=1
        with self.assertRaises(w.WrapperError): w.terminal_gates(observation,bad,worker)
        bad=dict(worker); bad["first_failure"]={"error":"synthetic"}
        with self.assertRaises(w.WrapperError): w.terminal_gates(observation,execution,bad)

    def test_wrapper_pins_this_auditor_and_cli_refuses_full_mode(self):
        raw=w.AUD_PATH.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),w.AUD_SHA)
        self.assertEqual(w.OBSERVER_SHA,"a52fe93c1f4705d2c5d9042bf8bb7b765fd6d63420c3e935a33bf03f9fd6da54")
        self.assertIn("full mode is parent-only",Path(w.__file__).read_text())

if __name__ == "__main__": unittest.main()
