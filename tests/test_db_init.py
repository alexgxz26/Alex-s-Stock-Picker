from pathlib import Path

from data.db import init_db


def test_init_db(tmp_path: Path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    assert db_path.exists()
