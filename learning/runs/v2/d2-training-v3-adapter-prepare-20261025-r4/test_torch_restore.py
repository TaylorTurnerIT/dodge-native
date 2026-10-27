"""Small actual Torch model/Adam restoration fixtures; no gradients or updates."""
from collections import OrderedDict

import torch

import helper


def main():
    model_a = torch.nn.Linear(2, 2)
    model_b = torch.nn.Linear(2, 2)
    model_b.load_state_dict(model_a.state_dict())
    adam_a = torch.optim.Adam(model_a.parameters(), lr=0.0003, eps=0.00001)
    adam_b = torch.optim.Adam(model_b.parameters(), lr=0.0003, eps=0.00001)
    state_a = adam_a.state_dict()
    for parameter_id, parameter in zip(state_a["param_groups"][0]["params"], model_a.parameters()):
        state_a["state"][parameter_id] = {
            "step": torch.tensor(7.0),
            "exp_avg": torch.full_like(parameter, 0.125),
            "exp_avg_sq": torch.full_like(parameter, 0.25),
        }
    adam_b.load_state_dict(state_a)
    expected_model = dict(model_a.state_dict())
    restored_model = OrderedDict(model_b.state_dict())
    expected_adam = state_a
    restored_adam = adam_b.state_dict()
    assert helper.fingerprint(expected_model) == helper.fingerprint(restored_model)
    assert helper.fingerprint(expected_adam) == helper.fingerprint(restored_adam)

    changed = OrderedDict(restored_model)
    changed["weight"] = changed["weight"].clone(); changed["weight"][0, 0] += 1
    assert helper.fingerprint(expected_model) != helper.fingerprint(changed)
    assert "$.weight" in helper.mismatch_paths(expected_model, changed)
    wrong_dtype = OrderedDict(restored_model); wrong_dtype["weight"] = restored_model["weight"].double()
    assert helper.fingerprint(expected_model) != helper.fingerprint(wrong_dtype)
    assert "$.weight.<dtype>" in helper.mismatch_paths(expected_model, wrong_dtype)
    wrong_shape = OrderedDict(restored_model); wrong_shape["weight"] = restored_model["weight"].reshape(4)
    assert helper.fingerprint(expected_model) != helper.fingerprint(wrong_shape)
    assert "$.weight.<shape>" in helper.mismatch_paths(expected_model, wrong_shape)
    assert helper.fingerprint({"v": 1}) != helper.fingerprint({"v": 1.0})
    assert helper.fingerprint({"v": [1]}) != helper.fingerprint({"v": (1,)})
    changed_adam = dict(restored_adam); changed_adam["state"] = dict(restored_adam["state"])
    first_id = next(iter(changed_adam["state"]))
    changed_adam["state"][first_id] = {key: value.clone() if isinstance(value, torch.Tensor) else value
                                        for key, value in changed_adam["state"][first_id].items()}
    changed_adam["state"][first_id]["exp_avg"][0, 0] += 1
    assert helper.fingerprint(expected_adam) != helper.fingerprint(changed_adam)
    print("actual Torch model and Adam restoration fixtures passed")


if __name__ == "__main__":
    main()
