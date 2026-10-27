"""Independent standard-library-only learner integration review checks."""
import ast
import copy
import hashlib
import importlib.util
import inspect
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
PREP = ROOT / 'learning/runs/v2/postovernight-long-D2-prepare-r1'
PROTOCOL = ROOT / 'learning/runs/v2-orchestration/postovernight-long-D2-r1-protocol.json'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def save(name, value):
    with (OUT / name).open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')

pins = {}
def read(path):
    pins[str(path.relative_to(ROOT))] = sha(path)
    return path.read_text()

protocol = json.loads(read(PROTOCOL))
config = json.loads(read(ROOT / protocol['config_path']))
identity = json.loads(read(PREP / 'long-identity.json'))
manifest = json.loads(read(PREP / 'capsule/capsule-manifest.json'))
source = read(PREP / 'long_d2.py')
assert sha(PREP / 'long_d2.py') == '62ece46ba9a59d3c116013580ce29875aa76eaceed59eb56480a804649c8ffca'
assert sha(PREP / 'long-identity.json') == 'f163c3e0d76ed9d839d8f9838840f6427c0e8ad379b24da6efc585f7f6e51ab4'
assert sha(PREP / 'capsule/capsule-manifest.json') == '6284b4389b1fdd1eadbd3f7d1c9104831a49af9482b78e21d84e1b19cb89227e'
for name, digest in protocol['base_identity']['sources'].items():
    path = ROOT / name
    assert sha(path) == digest == sha(PREP / 'capsule' / name)
    pins[name] = digest
assert len(protocol['base_identity']['sources']) == 75
assert source == read(PREP / 'capsule' / protocol['controller'])

spec = importlib.util.spec_from_file_location('independent_long_D2_review', PREP / 'long_d2.py')
controller = importlib.util.module_from_spec(spec)
spec.loader.exec_module(controller)
assert not any(name in {'torch','numpy','dodge_rl'} or name.startswith(('torch.','numpy.','dodge_rl.')) for name in sys.modules)
assert controller.semantic_hash(identity) == '5a64550c7103d23c371f0677b5739990602c08b3a95bc93368eec5f13d9301cb'
assert controller.semantic_hash(identity) != sha(PREP / 'long-identity.json')
entry = json.loads(read(ROOT / protocol['entry_control']))['evaluations']['D2']['rows']
assert controller.compare_control(list(reversed(entry)), entry)['matched']
killed = []
for key in controller.ROW_KEYS:
    changed = copy.deepcopy(entry)
    value = changed[0][key]
    changed[0][key] = not value if type(value) is bool else value + 1
    try:
        controller.compare_control(changed, entry)
    except controller.Stop:
        killed.append(key)
assert killed == list(controller.ROW_KEYS)

class Array:
    dtype = 'float32'
    shape = (1,)
    def __init__(self, value): self.value = value
    def tobytes(self): return self.value

class Tensor:
    dtype = 'torch.float32'
    shape = (1,)
    def __init__(self, value): self.value = value
    def detach(self): return self
    def cpu(self): return self
    def contiguous(self): return self
    def numpy(self): return Array(self.value)

controller.assert_equal_tree({'state':{0:{'step':Tensor(b'\x00\x00\xc0E')}}},
                             {'state':{0:{'step':Tensor(b'\x00\x00\xc0E')}}}, 'Adam')
try:
    controller.assert_equal_tree(Tensor(b'1234'), Tensor(b'1235'), 'tensor bytes')
except controller.Stop:
    pass
else:
    raise AssertionError('One byte tensor change accepted')

worker = json.loads(read(ROOT / 'learning/runs/v2/milestone3-D1-curriculum-r1/worker-result.json'))
assert worker['counters'] == controller.PARENT_COUNTERS
assert worker['checkpoint_sha256'] == protocol['parent_checkpoint_sha256']
boundary_path = ROOT / 'learning/runs/v2/milestone3-D1-curriculum-r1/training-episodes.jsonl'
boundaries = [json.loads(line) for line in read(boundary_path).splitlines()]
boundary = [row for row in boundaries if row.get('kind') == 'checkpoint_resume_boundary'
            and row['checkpoint_sha256'] == protocol['parent_checkpoint_sha256']]
assert len(boundary) == 1 and len(boundary[0]['abandoned_on_resume']) == 64
assert len(boundary[0]['next_episode_indices']) == 64

def signature(path, name, class_name=None):
    tree = ast.parse(read(ROOT / path))
    candidates = tree.body if class_name is None else next(node for node in tree.body
        if isinstance(node,ast.ClassDef) and node.name == class_name).body
    node = next(n for n in candidates if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name == name)
    args = node.args
    positional = list(args.posonlyargs) + list(args.args)
    if class_name: positional = positional[1:]
    defaults = [inspect.Parameter.empty] * (len(positional) - len(args.defaults)) + [None] * len(args.defaults)
    params = [inspect.Parameter(arg.arg, inspect.Parameter.POSITIONAL_OR_KEYWORD, default=default)
              for arg, default in zip(positional, defaults)]
    params += [inspect.Parameter(arg.arg,inspect.Parameter.KEYWORD_ONLY,
              default=inspect.Parameter.empty if default is None else None)
              for arg, default in zip(args.kwonlyargs,args.kw_defaults)]
    return inspect.Signature(params)

api = {
 'a.ckpt.restore_learner':('python/dodge_rl/checkpoints.py','restore_learner',None),
 'a.ckpt.capture_rng':('python/dodge_rl/checkpoints.py','capture_rng',None),
 'a.make_optimizer':('python/dodge_rl/train_teacher.py','make_optimizer',None),
 'a.training_env_config':('python/dodge_rl/identity.py','training_env_config',None),
 'a.TrainingEnvLog':('python/dodge_rl/train_teacher.py','__init__','TrainingEnvLog'),
 'a.verify_training_env':('python/dodge_rl/identity.py','verify_training_env',None),
 'self.api.ckpt.make_state':('python/dodge_rl/checkpoints.py','make_state',None),
 'self.api.ckpt.save_checkpoint':('python/dodge_rl/checkpoints.py','save_checkpoint',None),
 'a.evaluate':('python/dodge_rl/dev_eval.py','evaluate',None),
 'a.validate_summary':('python/dodge_rl/dev_eval.py','validate_summary',None),
 'a.progress_passed':('python/dodge_rl/dev_eval.py','progress_passed',None),
 'a.collect_rollout':('python/dodge_rl/ppo.py','collect_rollout',None),
 'a.require_raw_diagnostics':('python/dodge_rl/train_teacher.py','require_raw_diagnostics',None),
 'a.ppo_update':('python/dodge_rl/ppo.py','ppo_update',None),
 'old_identity.check_frozen':('python/dodge_rl/identity.py','check_frozen',None),
 'ckpt.validate_terminal_receipt':('python/dodge_rl/checkpoints.py','validate_terminal_receipt',None),
 'ckpt.validate_transition':('python/dodge_rl/checkpoints.py','validate_transition',None),
}
calls=[]
for node in ast.walk(ast.parse(source)):
    if isinstance(node,ast.Call) and ast.unparse(node.func) in api:
        name=ast.unparse(node.func)
        sig=signature(*api[name])
        sig.bind(*[object() for arg in node.args],**{arg.arg:object() for arg in node.keywords})
        calls.append({'callee':name,'line':node.lineno,'signature':str(sig)})
assert set(call['callee'] for call in calls) == set(api)
save('api-call-signatures.json',calls)
for path in ('docs/implementation-plan-v2.md','docs/SPEC_PRIVILEGED_VIT_RL.md',
             'learning/runs/v2-orchestration/postovernight-long-D2-design-parent-reconciliation-r1.json',
             'learning/runs/v2/postovernight-long-D2-api-audit-r1/api-audit.md',
             'learning/runs/v2/postovernight-long-D2-prepare-r1/test_long_d2.py',
             'learning/runs/v2/postovernight-long-D2-prepare-r1/freeze.py'):
    read(ROOT/path)
save('input-hashes.json',pins)
save('synthetic-static-checks.json',{
 'status':'passed','legacy_source_and_capsule_mirrors_checked':75,
 'controller_and_identity_document_and_capsule_hashes_checked':True,
 'checkpoint_identity_semantic_hash_checked':True,
 'nine_independent_entry_row_field_mutations_rejected':killed,
 'reversed_completion_order_accepted':True,
 'tensor_duck_type_bitwise_equality_and_one_byte_rejection':True,
 'actual_Torch_CPU_MPS_tensor_path_executed':False,
 'D1_counter_and_terminal_checkpoint_JSON_matches':True,
 'D1_exact_terminal_checkpoint_abandoned_episode_records':64,
 'actual_unchanged_API_call_sites_signature_bound':len(calls),
 'Torch_numpy_project_import_deserialization_inference_gameplay_or_gradient':False,
})
print(json.dumps({'status':'passed','signature_bound_calls':len(calls),'source_pins':75,'mutations_killed':len(killed),'abandoned':64}))
