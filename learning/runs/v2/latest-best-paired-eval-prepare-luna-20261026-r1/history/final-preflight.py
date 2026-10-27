from pathlib import Path

import worker

manifest = worker.verify_inputs()
origins = worker.verify_module_origins()
for label in worker.CHECKPOINTS:
    model, binding = worker.load_inference_model(label, device="cpu")
    assert sum(parameter.numel() for parameter in model.parameters()) == 321290
    assert not any(parameter.requires_grad for parameter in model.parameters())
    print(label, binding["checkpoint_sha256"], binding["receipt_sha256"],
          binding["audit_sha256"], binding["terminal_receipt_status"], "321290_parameters")
print("input_files", len(manifest["input_files"]))
print("runtime_files", len(manifest["frozen_runtime_files"]))
print("module_origins", len(origins))
print("game_episodes", 0)
