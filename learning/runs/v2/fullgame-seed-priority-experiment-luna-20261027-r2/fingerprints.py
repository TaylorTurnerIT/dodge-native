"""Typed content fingerprints copied from the trusted integrated runner."""
from collections.abc import Mapping
import hashlib


def fingerprint(value):
    """Device-independent typed tree digest; does not consume RNG."""
    h = hashlib.sha256()

    def field(tag, payload=b""):
        tag = tag.encode("utf-8")
        h.update(len(tag).to_bytes(8, "big"))
        h.update(tag)
        h.update(len(payload).to_bytes(8, "big"))
        h.update(payload)

    def visit(v):
        if hasattr(v, "detach"):
            v = v.detach().cpu().contiguous().numpy()
        if hasattr(v, "dtype") and hasattr(v, "tobytes"):
            field("array", (str(v.dtype) + repr(tuple(v.shape))).encode())
            field("array-bytes", v.tobytes())
            return
        if isinstance(v, Mapping):
            field("mapping", len(v).to_bytes(8, "big"))
            for k in sorted(v, key=lambda key: (type(key).__name__, repr(key))):
                field("entry")
                visit(k)
                visit(v[k])
            field("end-mapping")
        elif isinstance(v, list):
            field("list", len(v).to_bytes(8, "big"))
            for item in v:
                visit(item)
            field("end-list")
        elif isinstance(v, tuple):
            field("tuple", len(v).to_bytes(8, "big"))
            for item in v:
                visit(item)
            field("end-tuple")
        else:
            field(
                "scalar:" + type(v).__module__ + "." + type(v).__qualname__,
                repr(v).encode(),
            )

    visit(value)
    return h.hexdigest()


def optimizer_content_fingerprint(state_dict):
    """Hash optimizer contents while excluding only param_groups[].lr."""
    if not isinstance(state_dict, Mapping):
        raise TypeError("optimizer state_dict must be a mapping")
    if "param_groups" not in state_dict or not isinstance(state_dict["param_groups"], list):
        raise ValueError("optimizer state_dict must contain a param_groups list")
    normalized_groups = []
    for group in state_dict["param_groups"]:
        if not isinstance(group, Mapping):
            raise ValueError("optimizer param group must be a mapping")
        normalized_groups.append({key: value for key, value in group.items() if key != "lr"})
    normalized = dict(state_dict)
    normalized["param_groups"] = normalized_groups
    return fingerprint(normalized)
