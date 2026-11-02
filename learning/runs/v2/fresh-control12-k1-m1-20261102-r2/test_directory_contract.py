"""Target only the missing-directory failure and fresh-layout lifecycle contract."""
from pathlib import Path
import os
import sys
import tempfile
import unittest
import json
from unittest.mock import patch
from directory_contract import create_layout,check_layout,check_source_commit,check_ledger,CHILD_DIRECTORIES


class DirectoryTests(unittest.TestCase):
    def test_complete_fresh_layout_is_writable_and_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);create_layout(root);result=check_layout(root)
            self.assertEqual(len(result['directories']),6)
            self.assertFalse((root/'output/host-coordinator').exists())
            self.assertTrue(all(not list((root/'output'/name).iterdir()) for name in CHILD_DIRECTORIES))
            self.assertFalse(list((root/'empty-pycache').iterdir()))

    def test_missing_owner_rejected_without_repair_or_spawn(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);create_layout(root);(root/'output/owner').rmdir()
            with patch('subprocess.Popen',side_effect=AssertionError('No spawn allowed')):
                with self.assertRaisesRegex(ValueError,'owner'):check_layout(root)
            self.assertFalse((root/'output/owner').exists())
            self.assertFalse(list(root.rglob('*.claimed')))

    def test_missing_acceptance_detected_before_training(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);create_layout(root);(root/'output/acceptance').rmdir()
            with self.assertRaisesRegex(ValueError,'acceptance'):check_layout(root)

    def test_file_and_symlink_are_not_directories(self):
        for kind in ['file','symlink']:
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);create_layout(root);target=root/'output/owner';target.rmdir()
                if kind=='file':target.write_bytes(b'protected')
                else:target.symlink_to(root/'output/worker',target_is_directory=True)
                with self.assertRaisesRegex(ValueError,'unsafe'):check_layout(root)
                self.assertTrue(target.is_symlink() if kind=='symlink' else target.read_bytes()==b'protected')

    def test_prior_log_claim_or_coordinator_blocks_prelaunch(self):
        for name in ['worker/worker.log','coordinator.claimed','host-coordinator']:
            with self.subTest(name=name),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);create_layout(root);target=root/'output'/name
                target.write_bytes(b'preserved')
                with self.assertRaises(ValueError):check_layout(root)
                self.assertEqual(target.read_bytes(),b'preserved')

    def test_real_cpu_children_reap_in_all_required_directories(self):
        source=Path(__file__).resolve().parent/'source/learning/experiments/local_performance_loop/fresh'
        sys.path.insert(0,str(source))
        import common
        from lifecycle import run_child
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);create_layout(root);check_layout(root)
            for name in CHILD_DIRECTORIES:
                receipt=run_child([sys.executable,'-B','-c','pass'],root/'output'/name,
                    dict(os.environ,PYTHONDONTWRITEBYTECODE='1'),lambda members:None,None)
                self.assertEqual(receipt['raw_exit_code'],0)
                self.assertTrue(receipt['directly_reaped'] and receipt['group_absent'])

    def test_missing_source_commit_fails_without_claim_or_child(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);create_layout(root)
            with patch('subprocess.Popen',side_effect=AssertionError('No child allowed')):
                with self.assertRaisesRegex(ValueError,'SOURCE_COMMIT'):check_source_commit(root,{})
            self.assertFalse(list(root.rglob('*.claimed')))
            self.assertFalse((root/'SOURCE_COMMIT.json').exists())

    def test_source_commit_binds_current_config_caller_manifest_and_review(self):
        expected={key:str(index)*64 for index,key in enumerate(
            ['registration_sha256','host_driver_sha256','source_manifest_sha256','review_sha256'],1)}
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=root/'SOURCE_COMMIT.json'
            receipt=dict(commit='a'*40,**expected);path.write_text(json.dumps(receipt))
            self.assertEqual(check_source_commit(root,expected)['commit'],'a'*40)
            for key in [*expected,'commit']:
                bad=dict(receipt,**{key:'wrong'});path.write_text(json.dumps(bad))
                with self.assertRaises(ValueError):check_source_commit(root,expected)

    def test_preclaim_ledger_must_exist_on_registered_machine(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'state.json';machine={'fixture':'M1'}
            with self.assertRaises(ValueError):check_ledger(path,machine)
            self.assertFalse(path.exists())
            state=dict(schema='dodge_machine_accelerator_v1',machine=machine,
                       active_long_campaign=None,active_inference_diagnostic=None)
            path.write_text(json.dumps(state));before=path.read_bytes()
            self.assertEqual(check_ledger(path,machine)['lease_operations'],0)
            with self.assertRaises(ValueError):check_ledger(path,{'fixture':'foreign'})
            self.assertEqual(path.read_bytes(),before)

    def test_preclaim_occupied_ledger_is_never_cleared(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'state.json';machine={'fixture':'M1'}
            for field in ['active_long_campaign','active_inference_diagnostic']:
                state=dict(schema='dodge_machine_accelerator_v1',machine=machine,
                           active_long_campaign=None,active_inference_diagnostic=None)
                state[field]={'owner':'protected'};path.write_text(json.dumps(state));before=path.read_bytes()
                with self.assertRaisesRegex(ValueError,'occupied'):check_ledger(path,machine)
                self.assertEqual(path.read_bytes(),before)


if __name__=='__main__':unittest.main()
