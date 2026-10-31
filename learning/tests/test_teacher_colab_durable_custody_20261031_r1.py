"""Run the39 real disk/HTTP/process custody faults on the integrated064 copy."""
import importlib.util,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
p=ROOT/'learning/tests/test_teacher_colab_result_safety_20261031_r1.py'
spec=importlib.util.spec_from_file_location('durable_custody_faults',p);m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
package=ROOT/'learning/experiments/teacher_ray_colab_training_r3/result_safety/__init__.py'
spec=importlib.util.spec_from_file_location('durable_custody_under_test',package);module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
import importlib
for name,field in [('custody','c'),('lifecycle','life'),('remote_stage','remote_stage'),('transport','wire')]:
    setattr(m,field,importlib.import_module('durable_custody_under_test.'+name))
if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(m))
    raise SystemExit(0 if result.wasSuccessful() else 1)
