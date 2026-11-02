"""Hash-bound complete control learner/Adam loading; fresh simulator segment."""
import copy
import io
from pathlib import Path
import common as c


def load_control(reg, torch, fingerprint):
    binding = reg['warmstart']; path = Path(binding['path'])
    c.need(c.sha(path) == binding['sha256'], 'Warm-start bytes differ')
    state = torch.load(io.BytesIO(path.read_bytes()), map_location='cpu', weights_only=False)
    c.need(c.sha(path) == binding['sha256'] and state['schema'] == 'performance_loop_learner_v1'
           and state['arm'] == 'control' and state['completed_updates'] == 12
           and state['actual_gameplay_frames'] == 786432 and state['actual_Adam_steps'] == 1536
           and not state['full_environment_state_captured'] and not state['promoted']
           and state['registration_sha256'] == binding['registration_sha256'], 'Accepted complete control12 identity differs')
    c.need(fingerprint(state['model']) == binding['model_fingerprint'] == state['model_fingerprint']
           and fingerprint(state['optimizer']) == binding['adam_fingerprint'] == state['adam_fingerprint'],
           'Source learner/Adam fingerprint differs')
    return state


def verify_only_lr_changed(before, after, fingerprint):
    normalized = copy.deepcopy(after)
    c.need(len(before['param_groups']) == len(after['param_groups']) == 1, 'One complete Adam group required')
    c.need(before['param_groups'][0]['lr'] == 3e-5 and after['param_groups'][0]['lr'] == 1e-5, 'LR override differs')
    normalized['param_groups'][0]['lr'] = before['param_groups'][0]['lr']
    c.need(fingerprint(normalized) == fingerprint(before), 'Adam content other than LR changed')
