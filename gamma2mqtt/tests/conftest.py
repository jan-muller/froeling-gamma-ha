from pathlib import Path

import pytest

CAPTURES = Path(__file__).resolve().parents[2] / "GAMMA_23B_COMPLEET_CLAUDE_PAKKET"


@pytest.fixture(scope="session")
def captures_dir():
    if not CAPTURES.is_dir():
        pytest.skip("capture package not present")
    return CAPTURES
