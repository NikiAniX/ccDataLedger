import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402

SAMPLES = Path(__file__).resolve().parents[2] / "target" / "ccDataExtractor" / "output"


@pytest.fixture()
def db_path(tmp_path):
    return str(tmp_path / "ledger.db")


@pytest.fixture()
def client(db_path):
    return create_app(db_path).test_client()


@pytest.fixture(scope="session")
def samples_dir():
    return SAMPLES
