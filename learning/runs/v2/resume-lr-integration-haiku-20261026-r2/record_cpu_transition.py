"""Write the CPU transition record for the accepted parent (model/Adam on CPU; no game, no MPS, no optimizer step)."""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(HERE / "proposed-adapter"))

import test_resume_lr_transition as t  # noqa: E402  (same CPU-only helpers and constants as the test suite)
from resume_lr_transition import (apply_resume_lr_override, fingerprint, sha256_file,  # noqa: E402
                                  transition_record, validate_arm_binding, without_group_lr)


def main():
    sys.path.insert(0, str(t.RUNTIME))
    import torch
    from dodge_rl import checkpoints as ckpt
    from dodge_rl.models.teacher import OmniscientEntityTeacher

    frozen = t.load_frozen_runner()
    state = ckpt.load_checkpoint(t.PARENT, expected_sha256=t.PARENT_SHA)
    ckpt.require_complete_update(state)
    frozen.validate_parent_checkpoint_for_restore(state, frozen.PARENT_SHA)
    model = OmniscientEntityTeacher().to(device="cpu", dtype=torch.float32)
    optimizer = torch.optim.Adam(model.parameters(), lr=t.PARENT_LR, eps=1e-5)
    model.load_state_dict(state["model"], strict=True)
    optimizer.load_state_dict(state["optimizer"])

    reg = t.registration(t.ARM_SHA)
    identity = validate_arm_binding(reg, parent_config_file_sha256=sha256_file(t.PARENT_CONFIG),
                                    arm_config_file_sha256=sha256_file(t.DRAFT_ARM_CONFIG))
    parent_state = optimizer.state_dict()
    model_before = fingerprint(model.state_dict())
    delta = apply_resume_lr_override(optimizer, t.ARM_LR, reg["arm_transition"])
    effective_state = optimizer.state_dict()
    record = transition_record(parent_state, effective_state, delta, identity)
    assert fingerprint(model.state_dict()) == model_before
    record.update({
        "scope": "CPU; accepted parent model and Adam tensors loaded on CPU; no MPS sampling RNG restore; "
                 "no environment, gradients, or optimizer step",
        "parent_checkpoint_file_sha256": sha256_file(t.PARENT),
        "parent_model_fingerprint": model_before,
        "parent_optimizer_fingerprint_excluding_lr_recomputed": fingerprint(without_group_lr(parent_state)),
        "lr_by_group_after": [g["lr"] for g in optimizer.param_groups],
    })
    (HERE / "cpu-real-parent-transition-record.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    print(json.dumps({k: record[k] for k in ("per_group_lr", "parent_optimizer_fingerprint",
                                              "effective_optimizer_fingerprint")}, indent=2))


if __name__ == "__main__":
    main()
