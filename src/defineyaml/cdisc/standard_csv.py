"""Map one CDISC standards CSV export (from the per-tree Standards folder, CLAUDE.md
§9.2) into this tool's own dataset/variable and codelist shapes. Every function takes
the resolved folder Path as its first argument.

Two families of file, told apart by their columns:

- **IG variable tables** - SDTMIG/SENDIG (`Dataset Name`), CDASHIG (`Domain`), ADaMIG and
  its extensions (`Data Structure Name`). One row per (unit, variable). The "unit" is a
  domain for SDTM/CDASH and a data-structure name for ADaM; ADaM datasets are user-named
  instances of a structure, so the picker offers the structure and the user names the
  dataset. A file whose unit column is entirely blank (the bare SDTM model, `SDTM_v*.csv`)
  isn't offered for dataset scaffolding.

- **CT term lists** - `terminology/**/*_CT_*.csv`. A row with an empty `Codelist Code` is a
  codelist header (`Code` = the codelist's C-code, `CDISC Submission Value` = its submission
  value, `Codelist Name` = label, `Codelist Extensible (Yes/No)`); every following row whose
  `Codelist Code` equals that header's `Code` is one of its terms.

Everything here is pure: it reads a file and returns plain dicts. `webui/standard_scaffold.py`
turns those into validated tree objects.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import csv_db, local_standards

# (variable-name col, label col, type col, codelist-submission-value col, core col,
# role col-or-None) keyed by the unit column that identifies the file family. First
# match wins, so the more specific CDASHIG entry is checked before the generic ones.
# `codelist` = the column holding a CT *submission value* (may be blank in a given file);
# `ccode` = the column holding a CT *C-code* (SDTMIG only populates this one). The
# scaffold layer resolves a C-code to a submission value against a configured CT file.
_IG_LAYOUTS: list[dict[str, Any]] = [
    {
        "unit": "Domain",  # CDASHIG
        "name": "CDASHIG Variable",
        "label": "CDASHIG Variable Label",
        "type": "Type",
        "codelist": "Codelist Submission Value",
        "ccode": "CDISC CT Codelist Code(s), Subset Codes(s)",
        "core": "CDASHIG Core",
        "role": None,
        "cls": "Class",
        "notes": [
            "DRAFT CDASHIG Definition",
            "CDASHIG Definition",
            "Implementation Notes",
        ],
    },
    {
        "unit": "Dataset Name",  # SDTMIG / SENDIG (and the SDTM model, but its column is blank)
        "name": "Variable Name",
        "label": "Variable Label",
        "type": "Type",
        "codelist": "Codelist Submission Values",
        "ccode": "CDISC CT Codelist Code(s)",
        "core": "Core",
        "role": "Role",
        "cls": "Class",
        "notes": ["CDISC Notes"],
    },
    {
        "unit": "Data Structure Name",  # ADaMIG + extensions
        "name": "Variable Name",
        "label": "Variable Label",
        "type": "Type",
        "codelist": "CDISC CT Codelist Submission Value(s)",
        "ccode": "CDISC CT Codelist Code(s)",
        "core": "Core",
        "role": None,
        "cls": None,
        "notes": ["CDISC Notes"],
    },
]

_MANDATORY_CORE = {"REQ", "HR", "M", "MANDATORY", "REQUIRED"}


class StandardCsvError(Exception):
    pass


def _rows(
    folder: Path, relpath: str, *, cache_root: str | Path | None = None
) -> tuple[list[str], list[dict[str, str]]]:
    """(columns, rows) for one CSV. When `cache_root` is given the read goes through the
    DuckDB cache (`cdisc.csv_db`), which reloads the table only when the file changed;
    otherwise the file is streamed directly.
    """
    try:
        if cache_root is not None:
            return csv_db.rows(cache_root, folder, relpath)
        local_standards._safe_csv(folder, relpath)  # path guard
        return local_standards.rows(folder, relpath)
    except local_standards.LocalStandardsError as exc:
        raise StandardCsvError(str(exc)) from exc


def _ig_layout(columns: list[str]) -> dict[str, Any] | None:
    colset = set(columns)
    for layout in _IG_LAYOUTS:
        if layout["unit"] in colset and layout["name"] in colset:
            return layout
    return None


def is_ct_file(columns: list[str]) -> bool:
    return {"Codelist Code", "CDISC Submission Value", "Codelist Name"}.issubset(
        columns
    )


def file_kind(
    folder: Path, relpath: str, *, cache_root: str | Path | None = None
) -> str:
    """ "ig", "ct", or "other" (nothing this module can scaffold from)."""
    columns, rows = _rows(folder, relpath, cache_root=cache_root)
    if is_ct_file(columns):
        return "ct"
    layout = _ig_layout(columns)
    if layout and any((r.get(layout["unit"]) or "").strip() for r in rows):
        return "ig"
    return "other"


# --- IG variable tables ------------------------------------------------------------


def _clean(value: str | None) -> str:
    return (value or "").strip()


def _first_segment(value: str | None) -> str:
    """First ';'- or newline-separated segment, kept whole (spaces intact) - CT synonym
    and codelist-code cells are ';'-lists ("C71620; C78417", "NA; Not Applicable").
    """
    text = _clean(value)
    for sep in (";", "\n"):
        if sep in text:
            text = text.split(sep, 1)[0].strip()
    return text


def _map_type(raw: str) -> str:
    t = _clean(raw).lower()
    if t in ("num", "numeric", "number", "integer"):
        return "integer"
    if t == "float":
        return "float"
    return "text"


def list_units(
    folder: Path, relpath: str, *, cache_root: str | Path | None = None
) -> list[dict[str, Any]]:
    columns, rows = _rows(folder, relpath, cache_root=cache_root)
    layout = _ig_layout(columns)
    if not layout:
        raise StandardCsvError(
            f"{relpath} has no dataset/structure column this tool recognises"
        )
    counts: dict[str, int] = {}
    order: list[str] = []
    for row in rows:
        unit = _clean(row.get(layout["unit"]))
        if not unit:
            continue
        if unit not in counts:
            counts[unit] = 0
            order.append(unit)
        counts[unit] += 1
    if not order:
        raise StandardCsvError(
            f"{relpath} lists no datasets/structures (its {layout['unit']!r} column is blank)"
        )
    return [{"unit": u, "variable_count": counts[u]} for u in order]


def unit_class(
    folder: Path, relpath: str, unit: str, *, cache_root: str | Path | None = None
) -> str | None:
    columns, rows = _rows(folder, relpath, cache_root=cache_root)
    layout = _ig_layout(columns)
    if not layout:
        return None
    if not layout["cls"]:
        # ADaM: the structure name itself is the def:Class value.
        return unit.upper()
    for row in rows:
        if _clean(row.get(layout["unit"])) == unit:
            cls = _clean(row.get(layout["cls"]))
            if cls:
                return cls
    return None


def unit_variables(
    folder: Path, relpath: str, unit: str, *, cache_root: str | Path | None = None
) -> list[dict[str, Any]]:
    columns, rows = _rows(folder, relpath, cache_root=cache_root)
    layout = _ig_layout(columns)
    if not layout:
        raise StandardCsvError(
            f"{relpath} has no dataset/structure column this tool recognises"
        )
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        if _clean(row.get(layout["unit"])) != unit:
            continue
        name = _clean(row.get(layout["name"]))
        if not name or name in seen:
            continue
        seen.add(name)
        var: dict[str, Any] = {
            "name": name,
            "label": _clean(row.get(layout["label"])),
            "type": _map_type(row.get(layout["type"], "")),
            "mandatory": _clean(row.get(layout["core"])).upper() in _MANDATORY_CORE,
        }
        for notes_col in layout.get("notes") or []:
            if notes_col in row:
                note = _clean(row.get(notes_col))
                if note:
                    var["description"] = note
                break
        if layout["role"]:
            role = _clean(row.get(layout["role"]))
            if role:
                var["role"] = role
        codelist = _first_segment(row.get(layout["codelist"]))
        if codelist:
            var["codelist"] = codelist.lower()
        else:
            ccode = (
                _first_segment(row.get(layout["ccode"])) if layout.get("ccode") else ""
            )
            if ccode:
                # Only the C-code is known here; standard_scaffold resolves it to a
                # submission value against a configured CT file, or drops it.
                var["codelist_ccode"] = ccode
        out.append(var)
    if not out:
        raise StandardCsvError(f"{relpath} has no variables for {unit!r}")
    return out


# --- CT term lists ---------------------------------------------------------------


def _require_ct(
    folder: Path, relpath: str, *, cache_root: str | Path | None = None
) -> tuple[list[dict[str, str]], dict[str, dict[str, str]]]:
    columns, rows = _rows(folder, relpath, cache_root=cache_root)
    if not is_ct_file(columns):
        raise StandardCsvError(f"{relpath} is not a Controlled Terminology export")
    headers_by_ccode: dict[str, dict[str, str]] = {
        r["Code"]: r for r in rows if not _clean(r.get("Codelist Code"))
    }
    return rows, headers_by_ccode


def list_codelists(
    folder: Path,
    relpath: str,
    q: str | None = None,
    *,
    limit: int = 500,
    cache_root: str | Path | None = None,
) -> list[dict[str, Any]]:
    rows, headers = _require_ct(folder, relpath, cache_root=cache_root)
    term_counts: dict[str, int] = {}
    for row in rows:
        ccode = _clean(row.get("Codelist Code"))
        if ccode:
            term_counts[ccode] = term_counts.get(ccode, 0) + 1
    needle = _clean(q).lower()
    out: list[dict[str, Any]] = []
    for ccode, header in headers.items():
        value = _clean(header.get("CDISC Submission Value"))
        label = _clean(header.get("Codelist Name"))
        if not value:
            continue
        if needle and needle not in value.lower() and needle not in label.lower():
            continue
        out.append(
            {
                "value": value,
                "label": label,
                "nci_code": ccode,
                "extensible": _clean(header.get("Codelist Extensible (Yes/No)")).lower()
                == "yes",
                "term_count": term_counts.get(ccode, 0),
            }
        )
        if len(out) >= limit:
            break
    out.sort(key=lambda c: c["value"])
    return out


def ct_ccode_index(
    folder: Path, relpath: str, *, cache_root: str | Path | None = None
) -> dict[str, str]:
    """{codelist C-code -> submission value} for a CT file - lets the scaffold layer
    turn an SDTMIG variable's bare C-code into the codelist name to reference.
    """
    _, headers = _require_ct(folder, relpath, cache_root=cache_root)
    return {
        ccode: _clean(h.get("CDISC Submission Value"))
        for ccode, h in headers.items()
        if _clean(h.get("CDISC Submission Value"))
    }


def codelist_detail(
    folder: Path,
    relpath: str,
    value: str,
    *,
    cache_root: str | Path | None = None,
    codes: list[str] | None = None,
) -> dict[str, Any]:
    """One CT codelist as an `EnumeratedCodeList` dict. `codes` (case-insensitive) keeps
    only those term submission values - a sponsor subset of the published list."""
    rows, headers = _require_ct(folder, relpath, cache_root=cache_root)
    header = next(
        (
            h
            for h in headers.values()
            if _clean(h.get("CDISC Submission Value")) == value
        ),
        None,
    )
    if header is None:
        raise StandardCsvError(
            f"{relpath} has no codelist with submission value {value!r}"
        )
    ccode = header["Code"]
    raw_terms = [
        {
            "code": _clean(r.get("CDISC Submission Value")),
            "nci_code": _clean(r.get("Code")) or None,
            # CT CSVs carry no Define-XML "Decode"; NCI Preferred Term is the closest
            # human label (falls back to the first synonym segment).
            "decode": _clean(r.get("NCI Preferred Term"))
            or _first_segment(r.get("CDISC Synonym(s)"))
            or None,
        }
        for r in rows
        if _clean(r.get("Codelist Code")) == ccode
    ]
    raw_terms = [t for t in raw_terms if t["code"]]
    if codes is not None:
        # CodedValue is case-sensitive - match the requested subset exactly.
        want = {c.strip() for c in codes}
        raw_terms = [t for t in raw_terms if t["code"].strip() in want]
        if not raw_terms:
            raise StandardCsvError(
                f"none of the requested codes are in codelist {value!r}"
            )
    # EnumeratedCodeList requires decode present on every term or on none.
    if not all(t["decode"] for t in raw_terms):
        for t in raw_terms:
            t.pop("decode", None)
    terms = [{k: v for k, v in t.items() if v is not None} for t in raw_terms]
    detail: dict[str, Any] = {
        "name": value,
        "label": _clean(header.get("Codelist Name")) or value,
        "type": "text",
        "terms": terms,
    }
    if ccode:
        detail["nci_code"] = ccode
    if _clean(header.get("Codelist Extensible (Yes/No)")).lower() == "yes":
        detail["extended"] = True
    return detail
