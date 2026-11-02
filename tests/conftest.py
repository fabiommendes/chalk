import shutil
from pathlib import Path

import pytest

EXAMPLES = Path(__file__).parent / "examples"


@pytest.fixture
def classroom(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """
    A copy of the example classroom, used as the current directory.
    """
    root = tmp_path / "turma"
    shutil.copytree(EXAMPLES / "turma", root)
    monkeypatch.chdir(root)
    monkeypatch.setenv("CHALK_DEBUG", "1")
    monkeypatch.setenv("COLUMNS", "200")
    return root
