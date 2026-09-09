"""Reading a folder of CDISC standards CSV exports - the kind the CDISC Library's Data
Standards Browser produces (SDTM/SDTMIG/ADaMIG variable tables, CT term lists, CDASH,
QRS supplements, ...). This tool never downloads them: the user drops new versions into
the folder by hand as CDISC publishes them, and this module just reads whatever is
there - lists the files (grouped by the folder's own subdirectory layout), serves rows
from one file with an optional filter, searches across all files, and hands back a raw
file for download.

Every function takes the folder as an explicit `Path`. The folder is *not* a global
app setting - it's per-tree, stored as `standards_folder:` in that tree's `standards.yaml`
(models/study.py) and resolved by the webui layer (server.py). This module doesn't know
or care where the path came from.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

# csv.field_size_limit defaults can be too small for a few CT definition cells; bump it.
csv.field_size_limit(10 * 1024 * 1024)


class LocalStandardsError(Exception):
    pass


def resolve_folder(folder: str | Path | None) -> Path:
    """Validate `folder` is an existing directory and return it as a resolved Path.
    Raises LocalStandardsError otherwise (including when it's unset).
    """
    if not folder:
        raise LocalStandardsError("no standards folder is set for this tree")
    path = Path(folder).expanduser()
    if not path.exists():
        raise LocalStandardsError(f"standards folder does not exist: {folder}")
    if not path.is_dir():
        raise LocalStandardsError(f"standards folder is not a directory: {folder}")
    return path.resolve()


def _safe_csv(folder: Path, relpath: str) -> Path:
    root = folder.resolve()
    target = (root / relpath).resolve()
    if root != target and root not in target.parents:
        raise LocalStandardsError(f"path escapes the standards folder: {relpath}")
    if target.suffix.lower() != ".csv":
        raise LocalStandardsError(f"not a .csv file: {relpath}")
    if not target.is_file():
        raise FileNotFoundError(relpath)
    return target


def rows(folder: str | Path, relpath: str) -> tuple[list[str], list[dict[str, str]]]:
    """(column names, every row as a dict) for one CSV - the shared read primitive.
    Every cell is a string ('' for empty or short rows), matching csv.DictReader. This is
    the streaming fallback `cdisc.csv_db` drops back to when DuckDB isn't available.
    """
    target = _safe_csv(resolve_folder(folder), relpath)
    with target.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        columns = list(reader.fieldnames or [])
        data = [{c: (record.get(c) or "") for c in columns} for record in reader]
    return columns, data


# --- filename heuristics -----------------------------------------------------------


def _parse_name(name: str) -> dict[str, str | None]:
    stem = name[:-4] if name.lower().endswith(".csv") else name
    for sep in ("_", " "):
        if sep + "v" in stem:
            base, _, tail = stem.rpartition(sep + "v")
            if tail[:1].isdigit():
                return {"standard": base.replace("_", " "), "version": "v" + tail}
    # trailing YYYY-MM-DD
    if len(stem) > 11 and stem[-11] in ("_", " ") and _is_date(stem[-10:]):
        return {"standard": stem[:-11].replace("_", " "), "version": stem[-10:]}
    return {"standard": stem.replace("_", " "), "version": None}


def _is_date(text: str) -> bool:
    parts = text.split("-")
    return len(parts) == 3 and all(p.isdigit() for p in parts) and len(parts[0]) == 4


# --- listing ---------------------------------------------------------------------


def list_files(folder: str | Path) -> dict:
    """Every .csv under `folder`, grouped by its relative parent directory (the folder's
    own layout - `data_analysis`, `terminology/sdtm`, ...). Groups and files name-sorted.
    """
    root = resolve_folder(folder)
    groups: dict[str, list[dict]] = {}
    for path in sorted(root.rglob("*.csv")):
        rel = path.relative_to(root)
        parent = rel.parent.as_posix()
        category = "" if parent == "." else parent
        try:
            size = path.stat().st_size
        except OSError:
            size = None
        groups.setdefault(category, []).append(
            {
                "path": rel.as_posix(),
                "name": path.name,
                "category": category,
                "size": size,
                **_parse_name(path.name),
            }
        )
    return {
        "folder": str(root),
        "categories": [
            {
                "category": category,
                "files": sorted(groups[category], key=lambda f: f["name"]),
            }
            for category in sorted(groups)
        ],
    }


# --- reading + search ------------------------------------------------------------


def _row_matches(row: dict[str, Any], needle: str) -> bool:
    return any(needle in (value or "").lower() for value in row.values())


def read_file(
    folder: str | Path,
    relpath: str,
    *,
    q: str | None = None,
    limit: int = 500,
    offset: int = 0,
) -> dict:
    """Rows from one CSV. `q` is a case-insensitive substring filtered across every cell.
    `total_matched` counts all matches; `rows` is the `offset:offset+limit` slice of them.
    """
    target = _safe_csv(resolve_folder(folder), relpath)
    needle = (q or "").strip().lower()
    rows: list[dict] = []
    columns: list[str] = []
    total_rows = 0
    total_matched = 0
    with target.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        columns = list(reader.fieldnames or [])
        for record in reader:
            total_rows += 1
            if needle and not _row_matches(record, needle):
                continue
            total_matched += 1
            if offset <= total_matched - 1 < offset + limit:
                rows.append(record)
    return {
        "path": relpath,
        "columns": columns,
        "rows": rows,
        "total_rows": total_rows,
        "total_matched": total_matched if needle else total_rows,
        "offset": offset,
        "limit": limit,
        "truncated": (total_matched if needle else total_rows) > offset + limit,
    }


def search(folder: str | Path, q: str, *, limit: int = 200) -> dict:
    """Every row across every CSV in `folder` with a cell containing `q` (case-
    insensitive). Capped at `limit` total matches; `truncated` says whether more exist.
    """
    needle = (q or "").strip().lower()
    if not needle:
        raise LocalStandardsError("search needs a non-empty query")
    root = resolve_folder(folder)
    matches: list[dict] = []
    truncated = False
    files_scanned = 0
    for path in sorted(root.rglob("*.csv")):
        rel = path.relative_to(root)
        parent = rel.parent.as_posix()
        category = "" if parent == "." else parent
        files_scanned += 1
        try:
            with path.open(newline="", encoding="utf-8-sig") as handle:
                reader = csv.DictReader(handle)
                for record in reader:
                    if not _row_matches(record, needle):
                        continue
                    if len(matches) >= limit:
                        truncated = True
                        break
                    matches.append(
                        {
                            "file": rel.as_posix(),
                            "category": category,
                            "row": record,
                        }
                    )
        except (OSError, csv.Error):
            continue
        if truncated:
            break
    return {
        "query": q,
        "matches": matches,
        "truncated": truncated,
        "files_scanned": files_scanned,
    }


def raw_path(folder: str | Path, relpath: str) -> Path:
    """A guarded absolute path to one CSV, for FileResponse."""
    return _safe_csv(resolve_folder(folder), relpath)
