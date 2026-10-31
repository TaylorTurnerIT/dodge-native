"""Repin the unlaunched062 candidate; preserve source, payload and rejected r1.

Only metadata and a new empty parent cache are created. No service, allocator,
ledger, seed reader, original preparer or learning runtime is invoked.
"""
import copy
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
PARENT=ROOT/'learning/runs/v2/teacher-cloud-parent-20261031-r1'
BASE_REG_SHA='14b616d432a9bdf6ba775e2bfbb73c7bf8407eee32db7a9d85fd34357cec9534'
SDK_PACKAGES=Path('/tmp/dodge-colab-cli-20261031-venv/lib/python3.12/site-packages')


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dependency_pins():
    """Pin source and loaded native helpers, including requests alias targets."""
    pins={}
    for name in ['idna','charset_normalizer']:
        for path in sorted((SDK_PACKAGES/name).rglob('*')):
            if path.is_file() and path.suffix in ('.py','.so') and '__pycache__' not in path.parts:
                pins[str(path)]=sha(path)
    if not pins:raise ValueError('Required HTTP dependency inventory absent')
    return pins


def prepare():
    base=PARENT/'DODGE-062-A100-training-registration-r1.json'
    if sha(base)!=BASE_REG_SHA:raise ValueError('Rejected r1 changed')
    reg=copy.deepcopy(json.loads(base.read_text()))
    for path,digest in {**reg['source_pins'],**reg['input_pins']}.items():
        if sha(path)!=digest:raise ValueError('Frozen r1 pin changed')
    reg['input_pins'].update(dependency_pins())
    for path in [Path(__file__).resolve(),ROOT/'learning/tests/test_teacher_colab_control_service_20261031_r1.py']:
        reg['source_pins'][str(path)]=sha(path)
    review=PARENT/'reviews/DODGE-062-A100-persistent-control-luna-r1'
    for path in [base,review/'review.json',review/'evidence.json',
                 PARENT/'DODGE-062-warm-service-CPU-r1.stdout',PARENT/'DODGE-062-warm-service-CPU-r1.stderr']:
        reg['input_pins'][str(path)]=sha(path)
    target=PARENT/'DODGE-062-A100-training-registration-r2.json'
    reg['registration_local']=str(target)
    cache=PARENT/'DODGE062-parent-empty-pycache-r2';cache.mkdir()
    reg['empty_pycache']=str(cache)
    reg['CPU_evidence']['warm_service_tests']=7
    reg['CPU_evidence']['warm_service_scope']='Actual Transport.prepare_control, adapter main, serve_control and official StateStore; fake owned session/lease; loopback HTTP only; cloud auth forbidden.'
    reg['candidate_revision_note']='r1 source review blocked on missing HTTP transitive dependency pins. r2 adds complete idna/charset_normalizer source/native-helper pins and real-service regression tests; runtime/controller/payload/authority/nonce/lease/recipe/caps unchanged.'
    def write(path,value):
        with path.open('x') as f:json.dump(value,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n')
    write(target,reg)
    plan=json.loads((PARENT/'DODGE-062-preparation-plan-r1.json').read_text())
    plan.update(registration_path=str(target),registration_sha256=sha(target))
    plan_path=PARENT/'DODGE-062-preparation-plan-r2.json';write(plan_path,plan)
    print(json.dumps(dict(registration_sha256=sha(target),preparation_plan_sha256=sha(plan_path),
                          added_dependency_members=len(dependency_pins()),execution_authorized=False)))


if __name__=='__main__':prepare()
