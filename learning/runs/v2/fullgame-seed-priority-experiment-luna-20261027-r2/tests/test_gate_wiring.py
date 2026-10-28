"""Stdlib checks for launch-approval and direct-observer receipt wiring."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE))
import binding
import contracts
from audit import validate_observer_receipts
from successor_identity import matched_pair


class GateWiringTests(unittest.TestCase):
    def test_worker_command_passes_contract_approval_path(self):
        with tempfile.TemporaryDirectory() as directory:
            approval_path=Path(directory)/"launch-approval.json"
            reg={"run_id":"test-run","interpreter":"/usr/bin/python3",
                "source_manifest_sha256":"a"*64,
                "runtime_manifest_sha256":"b"*64}
            registration_sha="c"*64
            env={"registration":"/parent/registration.json",
                "registration_sha256":registration_sha,
                "launch_approval":str(approval_path),"launch_approval_sha256":"d"*64,
                "source_acceptance":"/parent/source-acceptance.json",
                "source_acceptance_sha256":"e"*64,"started":1.0}
            expected=contracts.launch_approval_document(registration_sha,reg)
            approval_path.write_text(json.dumps(expected))
            command=binding.worker_command(env,reg)
            approval_index=command.index("--launch-approval")
            self.assertEqual(command[approval_index+1],env["launch_approval"])
            self.assertEqual(command[approval_index+2],"--launch-approval-sha256")
            self.assertEqual(command[approval_index+3],env["launch_approval_sha256"])
            passed=contracts.read(command[approval_index+1])
            self.assertEqual(contracts.validate_launch_approval(passed,registration_sha,reg),expected)
            self.assertEqual(tuple(expected["gates"]),contracts.GATES)
            self.assertFalse(hasattr(binding,"GATES"))
            self.assertNotIn("--source-acceptance",command)

    def test_observer_fixture_uses_emitted_actual_exit_fields(self):
        envelope_sha="f"*64;registration_sha="1"*64
        parent={"observer_pid":31001,"observer_pgid":31001,
            "registration_sha256":registration_sha,"envelope_sha256":envelope_sha}
        exit_record={"raw_observer_exit_code":0,"observer_directly_reaped":True,
            "registration_sha256":registration_sha}
        observer={"status":"completed_pending_parent_audit","observed_worker_raw_exit":0,
            "directly_reaped":True,"first_event":None,"owned_group_absent":True,
            "worker_group_absent":True,"postflight_inputs_unchanged":True,
            "registration_sha256":registration_sha,"envelope_sha256":envelope_sha,"owned_pgid":31002}
        execution_result=dict(observer)
        self.assertTrue(validate_observer_receipts(envelope_sha,registration_sha,parent,
            exit_record,observer,execution_result))
        bad=dict(observer,observed_worker_raw_exit=1)
        with self.assertRaisesRegex(ValueError,"observer execution/observation receipts differ"):
            validate_observer_receipts(envelope_sha,registration_sha,parent,exit_record,bad,execution_result)

    def test_matched_pair_allows_only_declared_arm_stream_differences(self):
        left={"replica":1,"arm":"uniform","run_id":"u","output":"u-out",
            "attempt_claim_path":"u-claim","launch_marker_path":"u-marker",
            "slot_stream_sha256":["a"],"slot_component_sha256":["b"],"fixed":"same"}
        right=dict(left,arm="opening_priority",run_id="p",output="p-out",
            attempt_claim_path="p-claim",launch_marker_path="p-marker",
            slot_stream_sha256=["c"],slot_component_sha256=["d"])
        self.assertEqual(matched_pair(left,right),[
            "arm","attempt_claim_path","launch_marker_path","output","run_id",
            "slot_component_sha256","slot_stream_sha256"])


if __name__=="__main__":unittest.main()
