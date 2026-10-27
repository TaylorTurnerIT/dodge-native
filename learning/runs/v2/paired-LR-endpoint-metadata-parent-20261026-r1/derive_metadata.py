"""Read audited endpoint checkpoints on CPU; publish separate metadata attestations."""
import ast
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
OWN = Path(__file__).resolve().parent
BASE = OWN.parent
SOURCE = BASE / "paired-LR-upperD64-evaluator-luna-20261026-r2/paired_eval.py"
REG = BASE / "D2-retained324-linear-integrated-luna-20261026-r4/registration-final-r2.json"


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1048576), b""):
            h.update(chunk)
    return h.hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def read(path):
    return json.loads(Path(path).read_text())


def write(name, data):
    with (OWN / name).open("x") as stream:
        json.dump(data, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")


def main():
    require(sha(SOURCE) == "3263459ceb66eec189957931bcc389dbf1e43a391863d5a1f98b5a9b490557b6", "Analyzer source changed")
    require(sha(REG) == "0a6bf98221689ffcf62a28289dae7bb98eb89bc8d3c02b93127f4a04df75cb4e", "Registration changed")
    reg = read(REG)
    runtime = Path(reg["runtime_root"])
    for path, expected in reg["pins"].items():
        if Path(path).is_relative_to(runtime):
            require(sha(path) == expected, "Frozen runtime changed: " + path)
    # Extract exactly the previously reviewed state-dictionary algorithm, without importing the evaluator.
    tree = ast.parse(SOURCE.read_text())
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "state_dict_sha256")
    namespace = {"hashlib": hashlib, "json": json}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(SOURCE), "exec"), namespace)
    sys.path.insert(0, str(runtime))
    import torch
    torch.set_num_threads(2)
    import dodge_rl.checkpoints as checkpoints
    require(Path(checkpoints.__file__).resolve() == runtime / "dodge_rl/checkpoints.py", "Checkpoint loader origin differs")
    arms = {
        "constant": ("D2-retained324-continuation-20261026-r1", "e25117bf52f14629a3d2ffada319c49a10c6344763a25506a5f124a76a62199b",
                     "D2-retained324-all-candidate-auditor-luna-20261026-r2/full-audit.json", "a897963fc5663ead1073bd6c936a026465cc408f378c2b3ecfea6842cc5b5b96"),
        "linear": ("D2-retained324-linear-lr-20261026-r1", "cc5c3bee52b3fdad925ad90e793983df41954f16ce11403f9f32c431434e52e2",
                   "D2-retained324-linear-auditor-prepare-luna-20261026-r3/full-audit.json", "e1c32e9960e1b5dd832b88494771f01b02ef1e4f48fdb074f5f91fe4c9c9ee44"),
    }
    summary = {}
    for arm, (run_id, digest, audit_name, audit_digest) in arms.items():
        path = BASE / run_id / "checkpoint-000384-candidate.pt"
        audit_path = BASE / audit_name
        require(sha(audit_path) == audit_digest, "Full audit changed")
        candidate = read(audit_path)["audit"]["candidates"]["384"]
        require(candidate["checkpoint_sha256"] == digest == sha(path), "Endpoint bytes differ")
        sidecar = Path(str(path) + ".json")
        require(candidate["sidecar_sha256"] == sha(sidecar), "Birth sidecar differs")
        state = checkpoints.load_checkpoint(path, expected_sha256=digest)
        require(state["phase_update"] == 384 and state["local_update"] == 60
                and state["cumulative_counters"]["updates"] == 432
                and state["update_progress"]["complete"] is True, "Endpoint counters differ")
        require(state["native_sha256"] == reg["native"]["sha256"], "Endpoint native differs")
        # Run identity is established by immutable registration/audit/path binding; preserve the checkpoint identity verbatim.
        data = {"schema": "paired_LR_endpoint_metadata_parent_attestation_v1", "run_id": run_id,
                "checkpoint_path": str(path), "checkpoint_sha256": digest,
                "phase_update": state["phase_update"], "local_update": state["local_update"],
                "cumulative_updates": state["cumulative_counters"]["updates"],
                "identity": state["identity"], "identity_sha256": state["identity_sha256"],
                "model_state_dict_sha256": namespace["state_dict_sha256"](state["model"]),
                "native_sha256": state["native_sha256"], "runtime_sha256": state["runtime_sha256"],
                "source_audit_path": str(audit_path), "source_audit_sha256": audit_digest,
                "birth_sidecar_path": str(sidecar), "birth_sidecar_sha256": sha(sidecar),
                "algorithm_source_path": str(SOURCE), "algorithm_source_sha256": sha(SOURCE),
                "checkpoint_loader_path": str(Path(checkpoints.__file__).resolve()),
                "checkpoint_loader_sha256": sha(checkpoints.__file__),
                "CPU_only": True, "evaluation_or_training_run": False, "continuation_authority": False}
        require(sha(path) == digest and sha(sidecar) == candidate["sidecar_sha256"], "Endpoint changed during read")
        name = arm + "-endpoint-metadata.json"
        write(name, data)
        summary[arm] = {"path": str(OWN / name), "sha256": sha(OWN / name),
                        "checkpoint_sha256": digest, "model_state_dict_sha256": data["model_state_dict_sha256"]}
    write("receipt.json", {"schema": "paired_LR_endpoint_metadata_derivation_receipt_v1", "endpoints": summary,
                           "script_sha256": sha(__file__), "torch_version": torch.__version__, "CPU_only": True})
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
