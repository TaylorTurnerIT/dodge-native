import hashlib, json, tempfile, unittest
from pathlib import Path
from stage_and_check import verify_artifacts

class StageContractNegativeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.archive=self.root/'dodge-075-stage.tar.gz';self.archive.write_bytes(b'archive bytes')
        self.script=self.root/'dodge-075-stage-and-check.py';self.script.write_bytes(b'current script bytes')
        self.contract={'archive':{'filename':self.archive.name,'bytes':self.archive.stat().st_size,'sha256':hashlib.sha256(self.archive.read_bytes()).hexdigest()},'script':{'filename':self.script.name,'bytes':self.script.stat().st_size,'sha256':hashlib.sha256(self.script.read_bytes()).hexdigest()}}
    def tearDown(self): self.temp.cleanup()
    def test_archive_name_mismatch_is_rejected(self):
        wrong=self.root/'stage-bundle.tar.gz';wrong.write_bytes(self.archive.read_bytes())
        with self.assertRaisesRegex(ValueError,'archive filename mismatch'):
            verify_artifacts(self.contract,wrong,self.script)
    def test_stale_script_readback_is_rejected(self):
        stale=self.root/'dodge-075-stage-and-check.py';stale.write_bytes(b'stale script bytes')
        with self.assertRaisesRegex(ValueError,'stale stage script readback'):
            verify_artifacts(self.contract,self.archive,stale)
if __name__=='__main__': unittest.main()
