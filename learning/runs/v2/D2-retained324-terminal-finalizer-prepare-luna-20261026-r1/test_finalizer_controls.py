"""CPU-only source and synthetic guard controls; never calls finalization."""
import ast
import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).with_name("finalize_parent.py")


def load_controls():
    spec = importlib.util.spec_from_file_location("prepared_finalizer", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_import_has_no_finalization_call():
    tree = ast.parse(SCRIPT.read_text())
    assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                   and node.func.id == "finalize_parent" for node in tree.body)


def test_exact_lease_and_no_inference_synthetic():
    m = load_controls()
    lease = {"run_id": "run", "parent_checkpoint_sha256": "incumbent"}
    m.validate_parent_guard({"active_long_campaign": lease}, lease, False)
    for state, cancel in [
        ({"active_long_campaign": {"run_id": "other"}}, False),
        ({"active_long_campaign": lease, "active_inference_lease": {"id": 1}}, False),
        ({"active_long_campaign": lease}, True),
        ({"active_long_campaign": lease, "cancel_requested": True}, False),
    ]:
        try:
            m.validate_parent_guard(state, lease, cancel)
        except ValueError:
            pass
        else:
            raise AssertionError("unsafe synthetic parent state accepted")


def test_concurrent_ledger_change_synthetic():
    m = load_controls()
    m.validate_snapshot_unchanged(b"same", b"same")
    try:
        m.validate_snapshot_unchanged(b"concurrent", b"original")
    except ValueError:
        pass
    else:
        raise AssertionError("concurrent ledger edit accepted")


def test_incumbent_and_no_replacement_literals_are_pinned():
    source = SCRIPT.read_text()
    assert 'INCUMBENT_SHA = "c10d90ec0e67503afef8f4d90c4968581d430ef2065117a75e81c445a04c8ddc"' in source
    assert 'OLD_RECEIPT_SHA = "76cb15733e87518cb3b473b7f8ebd847ed206351fb9f17d89b8b92e6bf853f08"' in source
    assert '"best_replacement": False' in source
    assert '"selected_phase_update": None' in source
    assert "os.replace(temporary, statepath)" in source
