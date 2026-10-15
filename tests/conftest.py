import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def tidy():
    from surveil import transform
    weekly, issues = transform.tidy(FIXTURES)
    return weekly, issues


@pytest.fixture(scope="session")
def warehouse(tidy):
    from surveil import load
    con = load.connect(":memory:")
    load.write(con, "staging.weekly", tidy[0])
    load.build_marts(con)
    return con
