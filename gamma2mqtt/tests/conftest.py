from pathlib import Path

import pytest

# Local-only bus captures (gitignored). Tests using them skip when the folder is missing.
CAPTURES = Path(__file__).resolve().parents[2] / "private"


@pytest.fixture(scope="session")
def captures_dir():
    if not CAPTURES.is_dir():
        pytest.skip("capture package not present")
    return CAPTURES
