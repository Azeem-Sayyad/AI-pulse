import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_paths(tmp_path, monkeypatch):
    """Keep tests away from the real database and outputs folder, and force mock AI."""
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(config, "MOCK_AI", True)
    import publisher
    monkeypatch.setattr(publisher, "OUTPUTS_DIR", str(tmp_path / "outputs"))
    monkeypatch.chdir(ROOT)
    return tmp_path
