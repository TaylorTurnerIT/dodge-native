"""Preparation-only execute entry. This revision has no launch or mutation path."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import preflight_prepare


def execute(*, validate_parent=preflight_prepare.validate):
    """Run actual parent validation before any possible mutation boundary."""
    result = validate_parent()
    if result.get("status") != "selected_parent_cpu_validation_passed":
        raise ValueError("Selected parent validation did not pass")
    # R4 intentionally ends at source-only preparation. Parent-owned registration,
    # lease, output creation, marker claim, and worker launch are absent.
    return {**result, "execute_status": "preparation_only_no_mutation"}


def main():
    print(json.dumps(execute(), sort_keys=True))


if __name__ == "__main__":
    main()
