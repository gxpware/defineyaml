"""Scaffold datasets and codelists from a standard's local CSV (CLAUDE.md §9.2).

A `standards.yaml` entry with `standards_file:` set points at a CDISC CSV export, relative
to the same file's `standards_folder:` (per-tree, resolved by `_folder`). This module turns
that into editable tree objects:

- a new dataset pre-filled with every standard variable of a chosen SDTM domain / ADaM
  data structure;
- codelists picked from a CT export, or the set a dataset already references but that
  doesn't exist on disk yet.

Server-side orchestration over `tree.py` primitives, the same shape as
`webui/copy_variables.py` - one action can write several files.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .. import oid as oidmod
from ..cdisc import local_standards
from ..cdisc import nci_evs
from ..cdisc import standard_csv
from . import tree as treemod
from .copy_variables import _unique_key


def _standards_file(root: Path) -> dict:
    try:
        return treemod.read_object(root, "standards", "standards")
    except treemod.NotFoundError:
        return {}


def _standards(root: Path) -> list[dict]:
    return _standards_file(root).get("standards") or []


def resolve_folder(root: Path) -> Path:
    """The tree's resolved Standards CSV folder - `standards.yaml`'s `standards_folder:`,
    taken as-is if absolute, else relative to the define/ tree root. Raises
    LocalStandardsError if unset or not a directory.
    """
    raw = _standards_file(root).get("standards_folder")
    if not raw:
        raise local_standards.LocalStandardsError(
            "no standards_folder: set in standards.yaml for this tree"
        )
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    return local_standards.resolve_folder(candidate)


_folder = resolve_folder  # internal alias, kept short at the many call sites below


def _candidate_path(root: Path) -> Path | None:
    """The path `standards_folder:` points at (absolute, or relative to the tree root),
    without any existence check. None if `standards_folder:` isn't set.
    """
    raw = _standards_file(root).get("standards_folder")
    if not raw:
        return None
    candidate = Path(raw).expanduser()
    return candidate if candidate.is_absolute() else root / candidate


def folder_status(root: Path) -> dict:
    """What `GET /api/standards/config` returns: the raw stored value, whether it
    currently resolves to a real directory, and - when it doesn't - whether it's simply
    missing and could be created (`creatable`), vs. blocked by a file already sitting at
    that path.
    """
    raw = _standards_file(root).get("standards_folder")
    try:
        resolved = resolve_folder(root)
        return {
            "folder": raw,
            "resolved": str(resolved),
            "exists": True,
            "creatable": False,
            "error": None,
        }
    except local_standards.LocalStandardsError as exc:
        candidate = _candidate_path(root)
        return {
            "folder": raw,
            "resolved": None,
            "exists": False,
            "creatable": bool(raw) and candidate is not None and not candidate.exists(),
            "error": None if not raw else str(exc),
        }


def create_folder(root: Path) -> dict:
    """`mkdir -p` the folder `standards_folder:` points at, then re-report the status.
    Backs `POST /api/standards/config/create-folder` - the "create the missing folder"
    button the editor shows when the path is set but doesn't exist yet.
    """
    candidate = _candidate_path(root)
    if candidate is None:
        raise local_standards.LocalStandardsError(
            "no standards_folder: set in standards.yaml for this tree"
        )
    if candidate.exists():
        if candidate.is_dir():
            return folder_status(root)  # already there - nothing to do
        raise local_standards.LocalStandardsError(
            f"a file (not a folder) already exists at {candidate}"
        )
    try:
        candidate.mkdir(parents=True)
    except OSError as exc:
        raise local_standards.LocalStandardsError(
            f"could not create {candidate}: {exc}"
        ) from exc
    return folder_status(root)


def save_nci_evs_ct(root: Path, standard: str, version: str) -> dict:
    """Download NCI EVS CT for `(standard, version)` and write it into this tree's
    Standards folder as `terminology/<standard>/<STANDARD>_CT_<date>.csv`, in the
    CDISC-Data-Standards-Browser layout `cdisc.standard_csv` reads. Backs
    `POST /api/cdisc/nci-evs/{standard}/save-to-folder`.
    """
    folder = resolve_folder(root)  # LocalStandardsError if unset / not a directory
    resolved = nci_evs.resolve_version(standard, version)
    csv_text = nci_evs.to_ct_csv(standard, resolved)

    relpath = f"terminology/{standard.lower()}/{standard}_CT_{resolved}.csv"
    target = folder / relpath
    existed = target.is_file()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(csv_text, encoding="utf-8")

    return {
        "path": relpath,
        "existed": existed,
        "bytes": len(csv_text.encode("utf-8")),
        "standard": standard,
        "version": resolved,
    }


def set_folder(root: Path, value: str | None) -> dict:
    """Writes `standards.yaml`'s `standards_folder:` (empty/None clears it). Validates it
    resolves to a real directory when non-empty. Raises LocalStandardsError otherwise.
    """
    value = (value or "").strip() or None
    if value:
        candidate = Path(value).expanduser()
        local_standards.resolve_folder(
            candidate if candidate.is_absolute() else root / candidate
        )
    data = _standards_file(root)
    if not data:
        raise treemod.NotFoundError("standards.yaml not found")
    if value:
        data["standards_folder"] = value
    else:
        data.pop("standards_folder", None)
    treemod.save_object(root, "standards", "standards", data)
    return folder_status(root)


def _resolve(root: Path, standard_name: str) -> tuple[dict, str]:
    for entry in _standards(root):
        if entry.get("name") == standard_name:
            relpath = entry.get("standards_file")
            if not relpath:
                raise ValueError(
                    f"standard {standard_name!r} has no standards_file: set"
                )
            return entry, relpath
    raise treemod.NotFoundError(
        f"no standard named {standard_name!r} in standards.yaml"
    )


def standards_with_files(root: Path) -> list[dict]:
    """Every standards.yaml entry carrying a standards_file, annotated with the file's
    kind ("ig" / "ct" / "other") so the frontend can offer the right action.
    """
    try:
        folder = _folder(root)
    except local_standards.LocalStandardsError:
        return []
    out = []
    for entry in _standards(root):
        relpath = entry.get("standards_file")
        if not relpath:
            continue
        try:
            kind = standard_csv.file_kind(folder, relpath, cache_root=root)
        except standard_csv.StandardCsvError:
            kind = "other"
        out.append(
            {
                "name": entry.get("name"),
                "type": entry.get("type"),
                "file": relpath,
                "kind": kind,
            }
        )
    return out


# --- datasets ------------------------------------------------------------------


def _is_tabulation(relpath: str) -> bool:
    low = relpath.lower()
    return "tabulation" in low or Path(low).name.startswith(("sdtm", "send", "cdash"))


def _ccode_index(root: Path) -> dict[str, str]:
    """Merged {codelist C-code -> submission value} across every configured CT file -
    used to resolve an SDTMIG variable's bare C-code to a codelist name.
    """
    try:
        folder = _folder(root)
    except local_standards.LocalStandardsError:
        return {}
    index: dict[str, str] = {}
    for std in standards_with_files(root):
        if std["kind"] != "ct":
            continue
        try:
            for ccode, value in standard_csv.ct_ccode_index(
                folder, std["file"], cache_root=root
            ).items():
                index.setdefault(ccode, value)
        except standard_csv.StandardCsvError:
            continue
    return index


def _resolve_codelists(
    variables: list[dict], ccode_index: dict[str, str]
) -> list[dict]:
    out = []
    for var in variables:
        var = dict(var)
        ccode = var.pop("codelist_ccode", None)
        var.pop(
            "description", None
        )  # a CSV note, not a Variable field (extra="forbid")
        if "codelist" not in var and ccode:
            value = ccode_index.get(ccode)
            if value:
                var["codelist"] = value.lower()
        out.append(var)
    return out


def _resolve_codelist_ref(var: dict, ccode_index: dict[str, str]) -> str | None:
    """The codelist name to reference for a standard variable - its submission-value cell,
    or the CT name its bare C-code resolves to against a configured CT file."""
    cl = var.get("codelist")
    if cl:
        return cl
    ccode = var.get("codelist_ccode")
    if ccode:
        value = ccode_index.get(ccode)
        if value:
            return value.lower()
    return None


def _ig_standards(root: Path) -> list[dict]:
    return [s for s in standards_with_files(root) if s["kind"] == "ig"]


def standard_units(root: Path, standard_name: str) -> dict:
    _, relpath = _resolve(root, standard_name)
    return {
        "standard": standard_name,
        "file": relpath,
        "units": standard_csv.list_units(_folder(root), relpath, cache_root=root),
    }


def standard_unit_variables(root: Path, standard_name: str, unit: str) -> dict:
    _, relpath = _resolve(root, standard_name)
    variables = _resolve_codelists(
        standard_csv.unit_variables(_folder(root), relpath, unit, cache_root=root),
        _ccode_index(root),
    )
    return {"unit": unit, "variables": variables}


def ig_catalog(root: Path) -> dict:
    """Every attached IG standard with its unit (SDTM domain / ADaM structure) list -
    populates the filters on the 'add variables from standards' overlay."""
    folder = _folder(root)
    out = []
    for std in _ig_standards(root):
        try:
            units = standard_csv.list_units(folder, std["file"], cache_root=root)
        except standard_csv.StandardCsvError:
            continue
        out.append({"name": std["name"], "file": std["file"], "units": units})
    return {"standards": out}


def search_ig_variables(
    root: Path,
    standards: list[str] | None = None,
    units: list[str] | None = None,
    q: str | None = None,
    limit: int = 800,
) -> dict:
    """Every variable of every attached IG standard, optionally narrowed to some
    standard names / unit names and a case-insensitive substring over name/label/
    description. Codelist C-codes are resolved to names; each row also carries its
    `standard` and `unit`."""
    folder = _folder(root)
    want_std = {s.strip() for s in (standards or []) if s and s.strip()}
    want_unit = {u.strip().upper() for u in (units or []) if u and u.strip()}
    needle = (q or "").strip().lower()
    ccode_index = _ccode_index(root)
    rows: list[dict] = []
    for std in _ig_standards(root):
        if want_std and std["name"] not in want_std:
            continue
        try:
            unit_list = standard_csv.list_units(folder, std["file"], cache_root=root)
        except standard_csv.StandardCsvError:
            continue
        for entry in unit_list:
            unit = entry["unit"]
            if want_unit and unit.upper() not in want_unit:
                continue
            try:
                variables = standard_csv.unit_variables(
                    folder, std["file"], unit, cache_root=root
                )
            except standard_csv.StandardCsvError:
                continue
            for var in variables:
                if needle and not (
                    needle in var["name"].lower()
                    or needle in (var.get("label") or "").lower()
                    or needle in (var.get("description") or "").lower()
                ):
                    continue
                row = {
                    "standard": std["name"],
                    "unit": unit,
                    "name": var["name"],
                    "label": var.get("label", ""),
                    "type": var.get("type", "text"),
                    "mandatory": bool(var.get("mandatory")),
                }
                if var.get("role"):
                    row["role"] = var["role"]
                if var.get("description"):
                    row["description"] = var["description"]
                cl = _resolve_codelist_ref(var, ccode_index)
                if cl:
                    row["codelist"] = cl
                rows.append(row)
    truncated = len(rows) > limit
    return {"variables": rows[:limit], "total": len(rows), "truncated": truncated}


def _dataset_matches_unit(dataset: dict, unit: str) -> bool:
    """Whether a `datasets/*.yaml` object corresponds to a standard's unit: an SDTM/CDASH
    domain matches on name/domain, an ADaM dataset on its class (the structure name)."""
    unit_u = (unit or "").strip().upper()
    if not unit_u:
        return False
    candidates = {
        str(dataset.get(k) or "").strip().upper() for k in ("name", "domain", "class")
    }
    candidates.discard("")
    if unit_u in candidates:
        return True
    try:
        unit_slug = oidmod.slugify(unit)
    except ValueError:
        return False
    for cand in candidates:
        try:
            if oidmod.slugify(cand) == unit_slug:
                return True
        except ValueError:
            continue
    return False


def _template_regex(name: str) -> "re.Pattern[str] | None":
    """A regex for an ADaM templated variable name. Every run of lowercase letters is a
    token standing for digits - a 2-letter run (`xx`, `yy`, `zz`) is exactly two digits
    (CDISC zero-pads those), any other run (`y`, `z`, `w`, ...) is one or more:
    `TRTxxP` -> `TRT\\d\\dP`, `SITEGRy` -> `SITEGR\\d+`, `PxxSwEDT` -> `P\\d\\dS\\d+EDT`.
    None for a plain all-uppercase name."""
    if name == name.upper():
        return None
    out: list[str] = []
    i = 0
    while i < len(name):
        if name[i].islower():
            j = i
            while j < len(name) and name[j].islower():
                j += 1
            out.append(r"\d\d" if j - i == 2 else r"\d+")
            i = j
        else:
            out.append(re.escape(name[i]))
            i += 1
    try:
        return re.compile("^" + "".join(out) + "$")
    except re.error:
        return None


def _std_var_detail(
    std_name: str, unit: str, var: dict, ccode_index: dict[str, str]
) -> dict:
    return {
        "standard": std_name,
        "unit": unit,
        "name": var["name"],
        "label": var.get("label", ""),
        "type": var.get("type", ""),
        "mandatory": bool(var.get("mandatory")),
        "role": var.get("role"),
        "codelist": _resolve_codelist_ref(var, ccode_index),
        "description": var.get("description"),
    }


def _hint_entry(details: list[dict], template: bool) -> dict:
    codelists: list[str] = []
    roles: list[str] = []
    for d in details:
        if d["codelist"] and d["codelist"] not in codelists:
            codelists.append(d["codelist"])
        if d["role"] and d["role"] not in roles:
            roles.append(d["role"])
    return {
        "codelist": codelists,
        "role": roles,
        "sources": [{**d, "template": template} for d in details],
    }


def dataset_standard_hints(root: Path, dataset_key: str) -> dict:
    """For one dataset: the attached-standard units that describe it, plus - per variable
    name - everything those standards say about it (`variables[NAME]` = `{codelist: [...],
    role: [...], sources: [{standard, unit, name, label, type, mandatory, role, codelist,
    description, template}]}`). Backs the variables list's Codelist/Role datalist and its
    "ⓘ Standard" info overlay. ADaM templated names (`TRTxxP`, `AGEGRy`, `PxxSwEDT`, ...)
    are matched against the dataset's actual variables (`_template_regex`)."""
    try:
        dataset = treemod.read_object(root, "datasets", dataset_key)
    except treemod.NotFoundError:
        return {"matched": [], "variables": {}}
    try:
        folder = _folder(root)
    except local_standards.LocalStandardsError:
        return {"matched": [], "variables": {}}
    ccode_index = _ccode_index(root)
    matched: list[dict] = []
    literal: dict[str, list[dict]] = {}  # NAME.upper() -> [detail]
    templates: list[tuple[Any, dict]] = []  # (regex, detail) for TRTxxP-style names

    for std in _ig_standards(root):
        try:
            unit_list = standard_csv.list_units(folder, std["file"], cache_root=root)
        except standard_csv.StandardCsvError:
            continue
        for entry in unit_list:
            if not _dataset_matches_unit(dataset, entry["unit"]):
                continue
            try:
                variables = standard_csv.unit_variables(
                    folder, std["file"], entry["unit"], cache_root=root
                )
            except standard_csv.StandardCsvError:
                continue
            matched.append({"standard": std["name"], "unit": entry["unit"]})
            for var in variables:
                name = var["name"].strip()
                detail = _std_var_detail(std["name"], entry["unit"], var, ccode_index)
                literal.setdefault(name.upper(), []).append(detail)
                rx = _template_regex(name)
                if rx is not None:
                    templates.append((rx, detail))

    out: dict[str, dict] = {
        name: _hint_entry(details, template=False) for name, details in literal.items()
    }
    # each of the dataset's own variable names that isn't a literal standard name:
    # try the templates (TRT01P -> TRTxxP), collecting every template it matches.
    for var in dataset.get("variables") or []:
        if not isinstance(var, dict):
            continue
        vname = str(var.get("name") or "").strip().upper()
        if not vname or vname in out:
            continue
        hits = [d for rx, d in templates if rx.match(vname)]
        if hits:
            out[vname] = _hint_entry(hits, template=True)

    return {"matched": matched, "variables": out}


def create_dataset(
    root: Path,
    standard_name: str,
    unit: str,
    dataset_name: str,
    dataset_key: str | None,
) -> dict:
    _, relpath = _resolve(root, standard_name)
    folder = _folder(root)
    name = (dataset_name or "").strip()
    if not name:
        raise ValueError("dataset name is required")
    variables = _resolve_codelists(
        standard_csv.unit_variables(folder, relpath, unit, cache_root=root),
        _ccode_index(root),
    )
    tabulation = _is_tabulation(relpath)
    data: dict[str, Any] = {
        "name": name,
        "label": "",
        "class": standard_csv.unit_class(folder, relpath, unit, cache_root=root) or "",
        "structure": "",
        "purpose": "Tabulation" if tabulation else "Analysis",
        "standard": standard_name,
        "variables": variables,
    }
    if tabulation and len(name) == 2:
        data["domain"] = name
    key = (dataset_key or "").strip() or oidmod.slugify(name).lower()
    key = _unique_key(root, "datasets", key)
    treemod.save_object(root, "datasets", key, data)
    return {"key": key, "variable_count": len(variables)}


# --- codelists ----------------------------------------------------------------


def list_ct_codelists(root: Path, standard_name: str, q: str | None) -> dict:
    _, relpath = _resolve(root, standard_name)
    return {
        "standard": standard_name,
        "file": relpath,
        "codelists": standard_csv.list_codelists(
            _folder(root), relpath, q, cache_root=root
        ),
    }


def ct_codelist_terms(root: Path, standard_name: str, value: str) -> dict:
    """One CT codelist's full term list (from the named standard's CT file) - backs the
    per-codelist term subset picker in the 'new codelist from standard' dialog."""
    _, relpath = _resolve(root, standard_name)
    return standard_csv.codelist_detail(_folder(root), relpath, value, cache_root=root)


def codelist_reference(
    root: Path, name: str | None, nci_code: str | None = None
) -> dict:
    """The standard-CT view of one codelist - its full term list, for the editor's
    per-term autocomplete / extended-flag logic. Searches every configured CT
    standards_file, matching first on the codelist's C-code (`nci_code`), then on its
    submission value (`name`). `{found: false}` if no attached CT file has it.
    """
    wanted_name = (name or "").strip().lower()
    try:
        folder = _folder(root)
    except local_standards.LocalStandardsError:
        return {"found": False}
    for std in standards_with_files(root):
        if std["kind"] != "ct":
            continue
        try:
            catalog = standard_csv.list_codelists(
                folder, std["file"], None, limit=100000, cache_root=root
            )
        except standard_csv.StandardCsvError:
            continue
        match = None
        if nci_code:
            match = next((c for c in catalog if c["nci_code"] == nci_code), None)
        if match is None and wanted_name:
            match = next(
                (c for c in catalog if c["value"].lower() == wanted_name), None
            )
        if match is None:
            continue
        detail = standard_csv.codelist_detail(
            folder, std["file"], match["value"], cache_root=root
        )
        return {
            "found": True,
            "standard": std["name"],
            "value": match["value"],
            "label": match["label"],
            "nci_code": match["nci_code"],
            "extensible": match["extensible"],
            "terms": [
                {
                    "code": t["code"],
                    "decode": t.get("decode"),
                    "nci_code": t.get("nci_code"),
                }
                for t in detail["terms"]
            ],
        }
    return {"found": False}


# CDISC CT C66788 "CodeList Dictionary Name" (an extensible codelist). Used when no CT
# CSV is attached, or it doesn't carry C66788 - the field stays free-text-editable either
# way, so this is a starting menu, not a closed list.
_DICTIONARY_NAME_FALLBACK = [
    "COSTART",
    "CTCAE",
    "ICD-9",
    "ICD-9-CM",
    "ICD-10",
    "ICD-O-3",
    "LOINC",
    "MED-RT",
    "MedDRA",
    "SNOMED CT",
    "UNII",
    "WHO-ART",
    "WHODrug",
    "WHO-DDE",
]


def external_dictionary_names(root: Path) -> dict:
    """The menu for an ExternalCodeList's `dictionary:` field - CDISC CT C66788's
    submission values, drawn from an attached CT `standards_file` when one has it, else a
    built-in sample list. Purely an input aid: the chosen value is written straight to
    `ExternalCodeList/@Dictionary` and never becomes a `def:Standard` entry.
    """
    ref = codelist_reference(root, name=None, nci_code="C66788")
    if ref.get("found"):
        names = sorted({t["code"] for t in ref["terms"] if t.get("code")})
        if names:
            return {
                "source": ref["standard"],
                "extensible": ref.get("extensible", True),
                "names": names,
            }
    return {"source": None, "extensible": True, "names": _DICTIONARY_NAME_FALLBACK}


def _existing_codelist_slugs(root: Path) -> set[str]:
    slugs: set[str] = set()
    for item in treemod.list_items(root, "codelists"):
        try:
            data = treemod.read_object(root, "codelists", item["key"])
        except treemod.NotFoundError:
            continue
        nm = data.get("name")
        if nm:
            try:
                slugs.add(oidmod.slugify(str(nm)))
            except ValueError:
                pass
    return slugs


def create_codelists(root: Path, standard_name: str, values: list) -> dict:
    """Create a codelist file per item. Each item is either a plain submission-value
    string (whole codelist, standard name) or `{value, name?, codes?}` - `name` renames
    the codelist, `codes` keeps only that subset of its terms (a sponsor-narrowed list)."""
    _, relpath = _resolve(root, standard_name)
    folder = _folder(root)
    existing_keys = {i["key"] for i in treemod.list_items(root, "codelists")}
    existing_slugs = _existing_codelist_slugs(root)
    created: list[str] = []
    skipped: list[dict] = []
    for item in values:
        spec = {"value": item} if isinstance(item, str) else dict(item)
        value = spec.get("value")
        target = (spec.get("name") or value or "").strip()
        codes = spec.get("codes") or None
        try:
            slug = oidmod.slugify(target)
        except ValueError:
            skipped.append({"value": value, "reason": "invalid name"})
            continue
        if slug in existing_slugs:
            skipped.append(
                {"value": value, "reason": "a codelist with this name already exists"}
            )
            continue
        try:
            detail = standard_csv.codelist_detail(
                folder, relpath, value, cache_root=root, codes=codes
            )
        except standard_csv.StandardCsvError as exc:
            skipped.append({"value": value, "reason": str(exc)})
            continue
        detail["name"] = target  # honour a rename (label stays the standard's)
        key = (
            _unique_key(root, "codelists", slug.lower())
            if slug.lower() in existing_keys
            else slug.lower()
        )
        treemod.save_object(root, "codelists", key, detail)
        existing_keys.add(key)
        existing_slugs.add(slug)
        created.append(key)
    return {"created": created, "skipped": skipped}


def _referenced_codelist_slugs(root: Path) -> dict[str, str]:
    """slug -> a representative reference string, over every `codelist:` in datasets and
    value lists. `{oid: ...}` references are skipped (no name to match on).
    """
    refs: dict[str, str] = {}

    def note(value: Any) -> None:
        if not isinstance(value, str) or not value.strip():
            return
        try:
            refs.setdefault(oidmod.slugify(value), value)
        except ValueError:
            pass

    for item in treemod.list_items(root, "datasets"):
        try:
            data = treemod.read_object(root, "datasets", item["key"])
        except treemod.NotFoundError:
            continue
        for var in data.get("variables") or []:
            if isinstance(var, dict):
                note(var.get("codelist"))
    for item in treemod.list_items(root, "valuelists"):
        try:
            data = treemod.read_object(root, "valuelists", item["key"])
        except treemod.NotFoundError:
            continue
        for entry in data.get("entries") or []:
            if isinstance(entry, dict) and isinstance(entry.get("item"), dict):
                note(entry["item"].get("codelist"))
    return refs


def missing_referenced_codelists(root: Path) -> dict:
    missing_slugs = {
        s: ref
        for s, ref in _referenced_codelist_slugs(root).items()
        if s not in _existing_codelist_slugs(root)
    }
    ct_files = [s for s in standards_with_files(root) if s["kind"] == "ct"]
    try:
        folder = _folder(root) if ct_files else None
    except local_standards.LocalStandardsError:
        folder = None
    # slug -> (standard_name, submission value) for whatever a configured CT file provides
    available: dict[str, tuple[str, str]] = {}
    for std in ct_files if folder else []:
        try:
            for cl in standard_csv.list_codelists(
                folder, std["file"], None, limit=100000, cache_root=root
            ):
                try:
                    available.setdefault(
                        oidmod.slugify(cl["value"]), (std["name"], cl["value"])
                    )
                except ValueError:
                    pass
        except standard_csv.StandardCsvError:
            continue
    rows = []
    for slug, ref in sorted(missing_slugs.items()):
        hit = available.get(slug)
        rows.append(
            {
                "ref": ref,
                "slug": slug,
                "standard": hit[0] if hit else None,
                "value": hit[1] if hit else None,
            }
        )
    return {"missing": rows}


def create_missing_codelists(root: Path) -> dict:
    by_standard: dict[str, list[str]] = {}
    for row in missing_referenced_codelists(root)["missing"]:
        if row["standard"]:
            by_standard.setdefault(row["standard"], []).append(row["value"])
    created: list[str] = []
    skipped: list[dict] = []
    for standard_name, values in by_standard.items():
        result = create_codelists(root, standard_name, values)
        created.extend(result["created"])
        skipped.extend(result["skipped"])
    return {"created": created, "skipped": skipped}
