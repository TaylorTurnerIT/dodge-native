"""Read-only archived GPU checks and real temporary ledger transitions; no VM."""
import copy
import importlib.util
import io
import json
from pathlib import Path
import shutil
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'learning/experiments/teacher_colab_archived_evidence_20261031_r1.py'
spec=importlib.util.spec_from_file_location('archive_auditor',SOURCE)
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
REG=ROOT/'learning/runs/v2/teacher-ray-colab-evidence-20261031-r1/registration-draft-r1.json'


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.reg=c.read(REG);self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()

    def altered(self, mutation):
        reg=copy.deepcopy(self.reg);out=self.root/'copy';shutil.copytree(reg['original_output'],out)
        archive=out/'receipts.tar'
        with tarfile.open(archive) as content:
            data={f.name:content.extractfile(f).read() for f in content.getmembers()}
        docs={name:json.loads(value) for name,value in data.items() if name.endswith('.json')}
        mutation(docs)
        for name,value in docs.items():data[name]=json.dumps(value).encode()
        data['watchdog.json.stdout']=json.dumps(docs['CUDA-compatibility.json']).encode()
        with tarfile.open(archive,'w') as content:
            for name,value in data.items():
                member=tarfile.TarInfo(name);member.size=len(value);content.addfile(member,io.BytesIO(value))
        reg['original_output']=str(out);reg['archive_sha256']=c.sha(archive)
        return reg

    def test_real_archive_passes_without_editing_missing_field_or_failure(self):
        out=Path(self.reg['original_output']);before={p.name:c.sha(p) for p in out.iterdir() if p.is_file()}
        result=c.validate_evidence(self.reg)
        self.assertTrue(result['model_Adam_migration_passed'])
        self.assertFalse(result['original_campaign_success'])
        self.assertEqual(result['new_VM_allocations'],0)
        self.assertLess(result['combined_assigned_seconds_upper_bound'],900)
        self.assertEqual(before,{p.name:c.sha(p) for p in out.iterdir() if p.is_file()})
        with tarfile.open(out/'receipts.tar') as archive:
            doc=json.loads(archive.extractfile('CUDA-compatibility.json').read())
        self.assertNotIn('trained_weights_saved',doc)

    def test_numerical_violation_rejects_even_if_archive_hash_is_rebound(self):
        reg=self.altered(lambda d:d['CUDA-compatibility.json']['CPU_device_max_absolute_differences'].update(latent=.01))
        with self.assertRaisesRegex(ValueError,'numeric difference'):c.validate_evidence(reg)

    def test_resource_violation_rejects(self):
        reg=self.altered(lambda d:d['watchdog.json'].update(peak_sampled_CUDA_driver_process_bytes=6*2**30))
        with self.assertRaisesRegex(ValueError,'memory limit'):c.validate_evidence(reg)

    def test_explicit_outer_false_is_required_not_defaulted(self):
        reg=self.altered(lambda d:d['bootstrap-result.json'].pop('trained_weights_saved'))
        with self.assertRaises((KeyError,ValueError)):c.validate_evidence(reg)

    def test_backfilling_original_missing_field_is_rejected(self):
        reg=self.altered(lambda d:d['CUDA-compatibility.json'].update(trained_weights_saved=False))
        with self.assertRaisesRegex(ValueError,'no longer reproducible'):c.validate_evidence(reg)

    def final_setup(self):
        reg=copy.deepcopy(self.reg);reg['_registration_sha256']='a'*64
        parent=self.root/'parent';parent.mkdir();state=self.root/'state.json'
        state.write_text(json.dumps(dict(active_long_campaign=reg['previous_lease'],unrelated=[1,2,3])))
        reg['state_path']=str(state);review=self.root/'review.json'
        review.write_text(json.dumps(dict(status='no_blocking_findings',registration_sha256='a'*64,audit_source_pins=reg['source_pins'])))
        evidence=c.validate_evidence(self.reg)
        return reg,parent,state,review,evidence

    def test_accepted_audit_precedes_exact_release_and_cannot_repeat(self):
        reg,parent,state,review,evidence=self.final_setup();output=parent/'audit';original=c.save
        def ordered(path,value):
            if Path(path).name=='coordinator-terminal-audit.json':
                self.assertEqual(c.read(state)['active_long_campaign'],reg['expected_lease'])
            if Path(path).name=='lease-release.json':
                self.assertTrue((output/'coordinator-terminal-audit.json').exists())
                self.assertIsNone(c.read(state)['active_long_campaign'])
            return original(path,value)
        empty=lambda:dict(raw={'assignmentsCount':0},assignments=[])
        with patch.object(c,'PARENT',parent),patch.object(c,'validate_evidence',return_value=evidence),patch.object(c,'save',side_effect=ordered):
            audit=c.finalize(reg,review,c.sha(review),output,empty)
            before={p.name:p.read_bytes() for p in output.iterdir()}
            with self.assertRaisesRegex(ValueError,'already consumed'):
                c.finalize(reg,review,c.sha(review),output,empty)
            self.assertEqual(before,{p.name:p.read_bytes() for p in output.iterdir()})
        self.assertTrue(audit['original060_preserved_as_failed'])
        self.assertEqual(c.read(state),dict(active_long_campaign=None,unrelated=[1,2,3]))

    def test_failed_fresh_observation_keeps_audit_ownership_and_first_failure(self):
        reg,parent,state,review,evidence=self.final_setup();calls=[]
        def observation():
            calls.append(1)
            if len(calls)==2:raise TimeoutError('unavailable')
            return dict(raw={'assignmentsCount':0},assignments=[])
        with patch.object(c,'PARENT',parent),patch.object(c,'validate_evidence',return_value=evidence):
            with self.assertRaises(TimeoutError):c.finalize(reg,review,c.sha(review),parent/'audit',observation)
        self.assertEqual(c.read(state)['active_long_campaign'],reg['expected_lease'])
        self.assertTrue((parent/'audit/first-failure.json').exists())
        self.assertFalse((parent/'audit/coordinator-terminal-audit.json').exists())

    def test_foreign_owner_is_never_overwritten(self):
        reg,parent,state,review,evidence=self.final_setup();state.write_text(json.dumps(dict(active_long_campaign={'foreign':True})))
        with patch.object(c,'PARENT',parent),patch.object(c,'validate_evidence',return_value=evidence):
            with self.assertRaisesRegex(ValueError,'predecessor lease'):
                c.finalize(reg,review,c.sha(review),parent/'audit',lambda:dict(raw={'assignmentsCount':0},assignments=[]))
        self.assertEqual(c.read(state)['active_long_campaign'],{'foreign':True})


if __name__=='__main__':unittest.main(verbosity=2)
