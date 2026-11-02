"""Retain the original control12 learner and complete Adam without an LR edit."""
import importlib.util
from pathlib import Path
spec=importlib.util.spec_from_file_location('_fresh_accepted_warmstart', Path(__file__).resolve().parent.parent/'continuation/warmstart.py')
accepted=importlib.util.module_from_spec(spec);spec.loader.exec_module(accepted)
load_control=accepted.load_control


def verify_optimizer_unchanged(before, after, fingerprint):
    if (len(before['param_groups']) != 1 or len(after['param_groups']) != 1
            or before['param_groups'][0]['lr'] != 3e-5 or after['param_groups'][0]['lr'] != 3e-5
            or fingerprint(before) != fingerprint(after)):
        raise ValueError('Fresh-seed continuation must preserve the entire source Adam')
