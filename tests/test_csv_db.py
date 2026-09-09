"""defineyaml.cdisc.csv_db - the DuckDB cache over a local standards CSV folder. Small
synthetic CSVs in a tmp folder, a tmp cache_root; asserts the query shapes match
local_standards, that a changed/removed CSV is picked up, and that it degrades to
streaming when duckdb is absent.
"""

from __future__ import annotations

import os
import time

import pytest

from defineyaml.cdisc import csv_db, local_standards

_CT = (
    '"Code","Codelist Code","Codelist Name","CDISC Submission Value","Def"\n'
    '"C1",,"Severity","AESEV","the list"\n'
    '"C11","C1","Severity","MILD","mild"\n'
    '"C12","C1","Severity","MODERATE","moderate"\n'
    '"C13","C1","Severity","SEVERE","severe"\n'
)
_IG = (
    '"Dataset Name","Variable Name","Variable Label"\n'
    '"AE","AETERM","Reported Term"\n'
    '"AE","AESEV","Severity"\n'
)


@pytest.fixture()
def folder(tmp_path):
    root = tmp_path / "csvs"
    (root / "terminology").mkdir(parents=True)
    (root / "tab").mkdir()
    (root / "terminology" / "ct.csv").write_text(_CT)
    (root / "tab" / "ig.csv").write_text(_IG)
    return root


@pytest.fixture()
def cache(tmp_path):
    return tmp_path / "tree"


def _bump_mtime(path):
    future = time.time() + 2
    os.utime(path, (future, future))


def test_db_and_gitignore_land_under_cache_root(folder, cache):
    csv_db.read_file(cache, folder, "terminology/ct.csv")
    assert (cache / ".cache" / "standards.duckdb").is_file()
    assert (cache / ".cache" / ".gitignore").read_text().strip().endswith("*")


def test_read_file_matches_streaming(folder, cache):
    got = csv_db.read_file(cache, folder, "terminology/ct.csv")
    want = local_standards.read_file(folder, "terminology/ct.csv")
    assert got["columns"] == want["columns"]
    assert got["rows"] == want["rows"]
    assert got["total_rows"] == want["total_rows"] == 4


def test_read_file_filter_and_paginate(folder, cache):
    filtered = csv_db.read_file(cache, folder, "terminology/ct.csv", q="mod")
    assert filtered["total_matched"] == 1
    assert filtered["rows"][0]["CDISC Submission Value"] == "MODERATE"

    page = csv_db.read_file(cache, folder, "terminology/ct.csv", limit=2, offset=2)
    assert [r["CDISC Submission Value"] for r in page["rows"]] == ["MODERATE", "SEVERE"]
    assert page["truncated"] is False


def test_search_across_files(folder, cache):
    res = csv_db.search(cache, folder, "severity")
    files = {m["file"] for m in res["matches"]}
    assert files == {"terminology/ct.csv", "tab/ig.csv"}
    assert res["matches"][0]["category"] in ("terminology", "tab")

    capped = csv_db.search(cache, folder, "severe", limit=1)
    assert len(capped["matches"]) == 1

    with pytest.raises(local_standards.LocalStandardsError):
        csv_db.search(cache, folder, "   ")


def test_changed_csv_is_reloaded(folder, cache):
    assert csv_db.read_file(cache, folder, "terminology/ct.csv")["total_rows"] == 4
    target = folder / "terminology" / "ct.csv"
    target.write_text(_CT + '"C14","C1","Severity","FATAL","fatal"\n')
    _bump_mtime(target)
    again = csv_db.read_file(cache, folder, "terminology/ct.csv")
    assert again["total_rows"] == 5
    assert (
        csv_db.read_file(cache, folder, "terminology/ct.csv", q="fatal")[
            "total_matched"
        ]
        == 1
    )


def test_removed_csv_drops_table(folder, cache):
    csv_db.search(cache, folder, "severity")  # loads both
    (folder / "tab" / "ig.csv").unlink()
    res = csv_db.search(cache, folder, "severity")
    assert {m["file"] for m in res["matches"]} == {"terminology/ct.csv"}
    with pytest.raises(FileNotFoundError):
        csv_db.read_file(cache, folder, "tab/ig.csv")


def test_rows_primitive_matches_local_standards(folder, cache):
    cols_db, rows_db = csv_db.rows(cache, folder, "tab/ig.csv")
    cols_s, rows_s = local_standards.rows(folder, "tab/ig.csv")
    assert (cols_db, rows_db) == (cols_s, rows_s)


def test_falls_back_to_streaming_without_duckdb(folder, cache, monkeypatch):
    monkeypatch.setattr(csv_db, "duckdb", None)
    assert csv_db.available() is False
    got = csv_db.read_file(cache, folder, "terminology/ct.csv", q="mild")
    assert got["total_matched"] == 1
    assert csv_db.rows(cache, folder, "tab/ig.csv") == local_standards.rows(
        folder, "tab/ig.csv"
    )
    assert not (cache / ".cache").exists()  # nothing written on the fallback path


@pytest.mark.skipif(not csv_db.available(), reason="duckdb not installed")
def test_connection_is_kept_open_and_reused(folder, cache):
    csv_db.read_file(cache, folder, "terminology/ct.csv")
    con1 = csv_db._CONNECTIONS[str(csv_db._db_path(cache))]
    csv_db.search(cache, folder, "severity")
    con2 = csv_db._CONNECTIONS[str(csv_db._db_path(cache))]
    assert con1 is con2
    csv_db.close_all()
    assert csv_db._CONNECTIONS == {}


@pytest.mark.skipif(not csv_db.available(), reason="duckdb not installed")
def test_deleting_the_cache_dir_underneath_rebuilds(folder, cache):
    import shutil

    assert csv_db.search(cache, folder, "severity")["matches"]
    shutil.rmtree(cache / ".cache")  # connection still open, file gone
    again = csv_db.search(cache, folder, "severity")
    assert again["matches"]
    assert (cache / ".cache" / "standards.duckdb").is_file()


@pytest.mark.skipif(not csv_db.available(), reason="duckdb not installed")
def test_a_stale_schema_version_wipes_and_rebuilds(folder, cache):
    csv_db.read_file(cache, folder, "terminology/ct.csv")
    csv_db.close_all()
    con = csv_db.duckdb.connect(str(csv_db._db_path(cache)))
    con.execute("INSERT OR REPLACE INTO _meta VALUES ('schema_version', '0')")
    n_before = con.execute(
        "SELECT count(*) FROM information_schema.tables "
        "WHERE starts_with(table_name, 'csv_')"
    ).fetchone()[0]
    con.close()
    assert n_before == 1

    # next call reconnects, sees the mismatch, drops the csv_ tables, rebuilds lazily
    got = csv_db.read_file(cache, folder, "terminology/ct.csv")
    assert got["total_rows"] == 4
