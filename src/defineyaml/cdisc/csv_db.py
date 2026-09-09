"""DuckDB-backed cache of the tree's local standards CSV folder (CLAUDE.md §9.2), so
filtering and searching large CT exports is a SQL query instead of a full re-stream of
the file on every request.

Layout: one DuckDB database at ``<cache_root>/.cache/standards.duckdb``:

- one ``csv_<hash>`` table per CSV under the standards folder - what ``rows`` and
  ``read_file`` (single-file browse) query;
- ``_search_index(relpath, category, blob, row)`` - one row per CSV row across the whole
  folder, ``blob`` a pre-lowercased values-only concat for matching and ``row`` a
  ``MAP`` of the original cells, so a cross-file ``search`` is one indexed ``LIKE`` scan
  instead of a per-file loop;
- ``_manifest`` (each file's size + mtime) and ``_meta`` (a schema version - a layout
  change wipes the cached tables and lets them rebuild).

Before any read the target file's current ``stat()`` is compared to the manifest - a
changed/new CSV is reloaded (table + its ``_search_index`` slice), a vanished one's rows
are dropped, an unchanged one is left alone. The connection is **kept open per database
path** (``_CONNECTIONS``) and reused: ``duckdb.connect`` + ``close`` is ~12 ms, the
queries themselves sub-millisecond. ``cache_root`` is whatever the caller passes (the
webui passes the ``define/`` tree root, so the cache sits at ``define/.cache/``).

The cache is disposable: delete ``.cache/`` and it rebuilds on the next query (a stale
open connection notices the file is gone and reconnects). A ``.cache/.gitignore`` with
``*`` is written on creation. If the optional ``duckdb`` dependency is missing, or a
specific CSV won't load, every function here falls back to streaming the CSV via
:mod:`defineyaml.cdisc.local_standards`.
"""

from __future__ import annotations

import hashlib
import threading
from pathlib import Path, PurePosixPath

from . import local_standards

try:  # pragma: no cover - the import outcome is what's exercised, both ways
    import duckdb
except ImportError:  # pragma: no cover
    duckdb = None  # type: ignore[assignment]

# DuckDB is single-writer and a connection isn't safe for concurrent use; `define edit`
# also serves sync routes from a threadpool. One process-wide lock around every
# connect/sync/query keeps it simple.
_LOCK = threading.RLock()

# One live connection per database path, reused across calls (see module docstring).
_CONNECTIONS: dict[str, "duckdb.DuckDBPyConnection"] = {}

# Bump when the cached table layout changes - an older cache is wiped and rebuilt.
_SCHEMA_VERSION = 2

_READ_CSV_OPTS = (
    "header = true, all_varchar = true, sample_size = -1, "
    "null_padding = true, ignore_errors = true"
)


def available() -> bool:
    """True when queries go through DuckDB; False when they stream the CSV directly."""
    return duckdb is not None


def close_all() -> None:
    """Close every cached connection. Called on server shutdown and between tests."""
    with _LOCK:
        for con in list(_CONNECTIONS.values()):
            try:
                con.close()
            except Exception:  # noqa: BLE001 - best-effort teardown
                pass
        _CONNECTIONS.clear()


def _db_path(cache_root: str | Path) -> Path:
    return Path(cache_root) / ".cache" / "standards.duckdb"


def _table(relpath: str) -> str:
    return "csv_" + hashlib.sha1(relpath.encode("utf-8")).hexdigest()[:20]


def _qi(name: str) -> str:
    """Quote a SQL identifier (CDISC headers carry spaces, parens, commas, slashes)."""
    return '"' + name.replace('"', '""') + '"'


def _sql_str(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _write_gitignore(cache_dir: Path) -> None:
    gitignore = cache_dir / ".gitignore"
    if not gitignore.exists():
        try:
            gitignore.write_text("# defineyaml cache - safe to delete\n*\n")
        except OSError:
            pass


def _ensure_schema(con) -> None:
    row = con.execute("SELECT value FROM _meta WHERE key = 'schema_version'").fetchone()
    if row and row[0] == str(_SCHEMA_VERSION):
        return
    # First run, or the cached layout changed under us: drop the derived tables and let
    # them rebuild lazily. The cache is disposable, so a one-off full rebuild is fine.
    stale = con.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE starts_with(table_name, 'csv_')"
    ).fetchall()
    for (name,) in stale:
        con.execute(f"DROP TABLE IF EXISTS {_qi(name)}")
    con.execute("DELETE FROM _search_index")
    con.execute("DELETE FROM _manifest")
    con.execute(
        "INSERT OR REPLACE INTO _meta VALUES ('schema_version', ?)",
        [str(_SCHEMA_VERSION)],
    )


def _new_connection(path: Path):
    try:
        con = duckdb.connect(str(path))
    except Exception:  # noqa: BLE001 - a corrupt cache file heals itself; it's disposable
        try:
            path.unlink()
        except OSError:
            pass
        con = duckdb.connect(str(path))
    con.execute(
        "CREATE TABLE IF NOT EXISTS _meta (key VARCHAR PRIMARY KEY, value VARCHAR)"
    )
    con.execute(
        "CREATE TABLE IF NOT EXISTS _manifest ("
        "relpath VARCHAR PRIMARY KEY, tbl VARCHAR, size BIGINT, mtime_ns BIGINT)"
    )
    con.execute(
        "CREATE TABLE IF NOT EXISTS _search_index ("
        "relpath VARCHAR, category VARCHAR, blob VARCHAR, row MAP(VARCHAR, VARCHAR))"
    )
    _ensure_schema(con)
    # An ART index on relpath makes the single-file `read_file` filter a seek into that
    # file's rows rather than a scan of the whole folder's worth of _search_index.
    con.execute("CREATE INDEX IF NOT EXISTS _six_relpath ON _search_index (relpath)")
    return con


def _get_con(cache_root: str | Path):
    path = _db_path(cache_root)
    key = str(path)
    con = _CONNECTIONS.get(key)
    if con is not None:
        if path.exists():
            return con
        # `.cache/` was deleted out from under us - drop the stale handle, rebuild.
        try:
            con.close()
        except Exception:  # noqa: BLE001
            pass
        _CONNECTIONS.pop(key, None)
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_gitignore(path.parent)
    con = _new_connection(path)
    _CONNECTIONS[key] = con
    return con


def _drop_con(cache_root: str | Path) -> None:
    """Discard a possibly-wedged connection so the next call reconnects fresh."""
    con = _CONNECTIONS.pop(str(_db_path(cache_root)), None)
    if con is not None:
        try:
            con.close()
        except Exception:  # noqa: BLE001
            pass


def _columns(con, tbl: str) -> list[str]:
    # strip a stray UTF-8 BOM off the first header if read_csv kept one
    return [r[0].lstrip("﻿") for r in con.execute(f"DESCRIBE {_qi(tbl)}").fetchall()]


def _rebuild_search_slice(con, relpath: str, tbl: str) -> None:
    """Replace `relpath`'s rows in `_search_index` from the freshly-loaded `tbl`."""
    con.execute("DELETE FROM _search_index WHERE relpath = ?", [relpath])
    cols = _columns(con, tbl)
    if not cols:
        return
    parent = PurePosixPath(relpath).parent.as_posix()
    category = "" if parent == "." else parent
    keys = "[" + ", ".join(_sql_str(c) for c in cols) + "]"
    vals = "[" + ", ".join(_qi(c) for c in cols) + "]"
    blob = "lower(concat_ws(chr(31), " + ", ".join(_qi(c) for c in cols) + "))"
    con.execute(
        f"INSERT INTO _search_index "
        f"SELECT ?, ?, {blob}, map({keys}, {vals}) FROM {_qi(tbl)}",
        [relpath, category],
    )


def _sync_one(con, folder: Path, relpath: str) -> str | None:
    """Make the table (and `_search_index` slice) for `relpath` match the file on disk.
    Returns its table name, or None when the file is gone/unreadable (any stale table,
    manifest row and search rows are removed).
    """
    try:
        target = local_standards._safe_csv(folder, relpath)
    except (local_standards.LocalStandardsError, FileNotFoundError):
        row = con.execute(
            "SELECT tbl FROM _manifest WHERE relpath = ?", [relpath]
        ).fetchone()
        if row:
            con.execute(f"DROP TABLE IF EXISTS {_qi(row[0])}")
            con.execute("DELETE FROM _manifest WHERE relpath = ?", [relpath])
        con.execute("DELETE FROM _search_index WHERE relpath = ?", [relpath])
        return None
    stat = target.stat()
    tbl = _table(relpath)
    row = con.execute(
        "SELECT size, mtime_ns FROM _manifest WHERE relpath = ?", [relpath]
    ).fetchone()
    if row and row[0] == stat.st_size and row[1] == stat.st_mtime_ns:
        return tbl
    con.execute(f"DROP TABLE IF EXISTS {_qi(tbl)}")
    con.execute(
        f"CREATE TABLE {_qi(tbl)} AS SELECT * FROM read_csv(?, {_READ_CSV_OPTS})",
        [str(target)],
    )
    con.execute(
        "INSERT OR REPLACE INTO _manifest VALUES (?, ?, ?, ?)",
        [relpath, tbl, stat.st_size, stat.st_mtime_ns],
    )
    _rebuild_search_slice(con, relpath, tbl)
    return tbl


def _sync_all(con, root: Path) -> list[str]:
    """Sync every CSV under `root` (rebuilding changed ones, dropping vanished ones).
    Reads the manifest once and only touches DuckDB for files that actually changed, so
    the steady state (nothing changed) is one `stat()` per file and no per-file query.
    Returns the surviving relpaths, name-sorted.
    """
    on_disk: dict[str, tuple[int, int]] = {}
    for path in root.rglob("*.csv"):
        try:
            stat = path.stat()
        except OSError:
            continue
        on_disk[path.relative_to(root).as_posix()] = (stat.st_size, stat.st_mtime_ns)
    manifest = {
        r[0]: (r[1], r[2])
        for r in con.execute("SELECT relpath, size, mtime_ns FROM _manifest").fetchall()
    }
    for relpath, signature in on_disk.items():
        if manifest.get(relpath) != signature:
            _sync_one(con, root, relpath)
    for gone in set(manifest).difference(on_disk):
        _sync_one(con, root, gone)
    return sorted(on_disk)


def _cell(value) -> str:
    return "" if value is None else str(value)


def _record(columns: list[str], values) -> dict[str, str]:
    return {c: _cell(v) for c, v in zip(columns, values)}


# --- public API (mirrors local_standards signatures, plus a leading cache_root) -------


def rows(
    cache_root: str | Path, folder: str | Path, relpath: str
) -> tuple[list[str], list[dict[str, str]]]:
    """(columns, every row) for one CSV - the DuckDB-cached form of
    :func:`local_standards.rows`, used by :mod:`defineyaml.cdisc.standard_csv`.
    """
    if duckdb is None:
        return local_standards.rows(folder, relpath)
    try:
        with _LOCK:
            con = _get_con(cache_root)
            tbl = _sync_one(con, local_standards.resolve_folder(folder), relpath)
            if tbl is None:
                raise FileNotFoundError(relpath)
            cols = _columns(con, tbl)
            data = [
                _record(cols, r)
                for r in con.execute(f"SELECT * FROM {_qi(tbl)}").fetchall()
            ]
            return cols, data
    except (FileNotFoundError, local_standards.LocalStandardsError):
        raise
    except Exception:  # noqa: BLE001
        _drop_con(cache_root)
        return local_standards.rows(folder, relpath)


def read_file(
    cache_root: str | Path,
    folder: str | Path,
    relpath: str,
    *,
    q: str | None = None,
    limit: int = 500,
    offset: int = 0,
) -> dict:
    """Rows from one CSV, optionally filtered by a case-insensitive substring across every
    cell, paginated. Same return shape as :func:`local_standards.read_file`.
    """
    if duckdb is None:
        return local_standards.read_file(
            folder, relpath, q=q, limit=limit, offset=offset
        )
    needle = (q or "").strip().lower()
    try:
        with _LOCK:
            con = _get_con(cache_root)
            tbl = _sync_one(con, local_standards.resolve_folder(folder), relpath)
            if tbl is None:
                raise FileNotFoundError(relpath)
            cols = _columns(con, tbl)
            total_rows = con.execute(f"SELECT count(*) FROM {_qi(tbl)}").fetchone()[0]
            if needle:
                # Filter via _search_index: the relpath index seeks to this file's
                # rows, then it's one LIKE over the pre-lowercased `blob` column
                # rather than a 9-column concat over the raw table.
                like = "blob LIKE '%' || ? || '%'"
                total = con.execute(
                    f"SELECT count(*) FROM _search_index WHERE relpath = ? AND {like}",
                    [relpath, needle],
                ).fetchone()[0]
                fetched = con.execute(
                    f"SELECT row FROM _search_index WHERE relpath = ? AND {like} "
                    f"LIMIT ? OFFSET ?",
                    [relpath, needle, limit, offset],
                ).fetchall()
                out_rows = [
                    {c: _cell(dict(r[0]).get(c)) for c in cols} for r in fetched
                ]
            else:
                total = total_rows
                cur = con.execute(
                    f"SELECT * FROM {_qi(tbl)} LIMIT ? OFFSET ?", [limit, offset]
                )
                out_rows = [_record(cols, r) for r in cur.fetchall()]
    except (FileNotFoundError, local_standards.LocalStandardsError):
        raise
    except Exception:  # noqa: BLE001
        _drop_con(cache_root)
        return local_standards.read_file(
            folder, relpath, q=q, limit=limit, offset=offset
        )
    return {
        "path": relpath,
        "columns": cols,
        "rows": out_rows,
        "total_rows": total_rows,
        "total_matched": total,
        "offset": offset,
        "limit": limit,
        "truncated": total > offset + limit,
    }


def search(
    cache_root: str | Path, folder: str | Path, q: str, *, limit: int = 200
) -> dict:
    """Every row across every CSV under `folder` with a cell containing `q` (case-
    insensitive), capped at `limit`. One `_search_index` scan rather than a per-file
    loop. Same return shape as :func:`local_standards.search`.
    """
    needle = (q or "").strip().lower()
    if not needle:
        raise local_standards.LocalStandardsError("search needs a non-empty query")
    if duckdb is None:
        return local_standards.search(folder, q, limit=limit)
    try:
        root = local_standards.resolve_folder(folder)
        with _LOCK:
            con = _get_con(cache_root)
            relpaths = _sync_all(con, root)
            fetched = con.execute(
                "SELECT relpath, category, row FROM _search_index "
                "WHERE blob LIKE '%' || ? || '%' ORDER BY relpath LIMIT ?",
                [needle, limit + 1],
            ).fetchall()
    except local_standards.LocalStandardsError:
        raise
    except Exception:  # noqa: BLE001
        _drop_con(cache_root)
        return local_standards.search(folder, q, limit=limit)
    truncated = len(fetched) > limit
    matches = [
        {
            "file": relpath,
            "category": category,
            "row": {k: _cell(v) for k, v in dict(row_map).items()},
        }
        for relpath, category, row_map in fetched[:limit]
    ]
    return {
        "query": q,
        "matches": matches,
        "truncated": truncated,
        "files_scanned": len(relpaths),
    }
