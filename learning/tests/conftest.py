import sys
from pathlib import Path

# Run from anywhere: `import dodge` finds learning/dodge.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from dodge import schedule


@pytest.fixture(autouse=True)
def _isolated_training_panel(tmp_path, monkeypatch):
    """Keep sessions off the working directory's training.json.

    A live Training panel file there would otherwise be applied to every
    session a test builds, stub models included, which have no learning rate
    to set and park the run in its error loop.
    """
    monkeypatch.setattr(schedule, "CONFIG_PATH", tmp_path / "training.json")
