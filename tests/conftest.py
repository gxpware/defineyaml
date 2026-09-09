from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _close_csv_db_connections():
    """csv_db keeps one DuckDB connection open per cache path (perf); each test uses a
    fresh tmp cache_root, so close them all after every test rather than leak handles
    to deleted tmp dirs across the run.
    """
    yield
    from defineyaml.cdisc import csv_db

    csv_db.close_all()
