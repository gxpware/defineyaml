"""Controlled Terminology source: NCI EVS's own CDISC CT distribution.

Originally a fallback for when the configured CDISC Library server wasn't reachable;
it's now the primary CT lookup (the CDISC Library API integration is dormant - the
client/config/cache modules are still in the tree but nothing routes to them).

Confirmed live while building this: https://evs.nci.nih.gov/ftp1/ is an S3-backed file
store behind an Angular file-browser SPA (evs.nci.nih.gov itself), not a plain directory
listing - the folder-listing API the SPA calls is `GET /ftp1/folder?folder=<prefix>`
(an S3 ListObjectsV2 response as JSON: `Contents` = [{Key, Size, LastModified}],
`IsTruncated`, `CommonPrefixes`). `folder` is used as the S3 *prefix*, not required to
be a real directory - passing a narrow prefix like `CDISC/SDTM/Archive/SDTM Terminology`
returns just that standard's files (`IsTruncated: false`), which is how this avoids the
1000-key pagination the raw `CDISC/SDTM/Archive/` listing would need.

`CDISC/{SDTM,ADaM,SEND}/Archive/` holds every quarterly release as
`{Standard} Terminology YYYY-MM-DD.odm.xml`, newest included - the undated
`{Standard} Terminology.odm.xml` one level up is byte-identical to the newest of those
(same S3 Size + upload time), so this only lists and downloads the dated files. The
user picks a `YYYY-MM-DD` release (or passes `"current"`, an alias resolved to the
newest); each is downloaded once and cached on disk indefinitely (a published release's
content never changes), keyed by `(standard, date)`. `to_ct_csv()` re-serialises a
cached release as a CDISC-Data-Standards-Browser-style CT CSV for saving into a local
Standards folder.

The XML is an NCI-specific ODM dialect: NCI Concept ID and extensibility live directly
on `CodeList`/`EnumeratedItem` attributes in the `nciodm:` namespace
(`nciodm:ExtCodeID`, `nciodm:CodeListExtensible`), not via `def:Alias`; every term is an
`EnumeratedItem` (confirmed: 0 of SDTM's 1208 codelists use `CodeListItem`) carrying
`nciodm:CDISCSynonym`/`CDISCDefinition`/`PreferredTerm`. SDTM's current file alone is
~25MB, so every read streams it with `lxml.etree.iterparse` rather than loading a DOM.
"""

from __future__ import annotations

import csv
import io
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from lxml import etree

NCI_EVS_BASE = "https://evs.nci.nih.gov/ftp1"
ODM_NS = "http://www.cdisc.org/ns/odm/v1.3"
NCIODM_NS = "http://ncicb.nci.nih.gov/xml/odm/EVS/CDISC"

CACHE_DIR = Path.home() / ".cache" / "defineyaml" / "cdisc" / "nci-evs"
DOWNLOAD_TIMEOUT_SECONDS = 120
LISTING_TIMEOUT_SECONDS = 30
VERSIONS_TTL_SECONDS = 24 * 60 * 60

# standard -> (folder under the NCI EVS CDISC tree, filename prefix). CDASH/Define-XML
# CT live under the same tree but aren't part of what this project builds define.xml for.
STANDARDS: dict[str, dict[str, str]] = {
    "SDTM": {"dir": "CDISC/SDTM", "prefix": "SDTM Terminology"},
    "ADaM": {"dir": "CDISC/ADaM", "prefix": "ADaM Terminology"},
    "SEND": {"dir": "CDISC/SEND", "prefix": "SEND Terminology"},
}

# "current" isn't a distinct release - the undated CDISC/{Standard}/{Standard}
# Terminology.odm.xml is byte-identical to the newest dated file in Archive/ (confirmed:
# same Size, same upload timestamp). So it's an *alias* for "the newest available
# version", resolved to a real YYYY-MM-DD by resolve_version(); list_available_versions()
# never emits it as its own pickable entry.
CURRENT = "current"
_VERSION_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class NciEvsError(Exception):
    pass


def _odm(tag: str) -> str:
    return f"{{{ODM_NS}}}{tag}"


def _nci(attr: str) -> str:
    return f"{{{NCIODM_NS}}}{attr}"


def _require_known(standard: str) -> dict[str, str]:
    if standard not in STANDARDS:
        raise NciEvsError(
            f"unknown standard {standard!r} - expected one of {sorted(STANDARDS)}"
        )
    return STANDARDS[standard]


def resolve_version(standard: str, version: str | None = CURRENT) -> str:
    """A YYYY-MM-DD release date. A real date passes through; `"current"` (or None/empty)
    resolves to the newest available one via `list_available_versions`. Anything else is
    a NciEvsError.
    """
    _require_known(standard)
    if version and _VERSION_RE.match(version):
        return version
    if not version or version == CURRENT:
        available = list_available_versions(standard)
        if not available:
            raise NciEvsError(f"no {standard} CT releases listed by NCI EVS")
        return available[0]["version"]
    raise NciEvsError(
        f"invalid version {version!r} - expected a YYYY-MM-DD date or 'current'"
    )


def _file_path(standard: str, version: str) -> Path:
    return CACHE_DIR / f"{standard}@{version}.odm.xml"


def _meta_path(standard: str, version: str) -> Path:
    return CACHE_DIR / f"{standard}@{version}.meta.json"


def _index_path(standard: str, version: str) -> Path:
    return CACHE_DIR / f"{standard}@{version}.index.json"


def _versions_cache_path(standard: str) -> Path:
    return CACHE_DIR / f"{standard}.versions.json"


# --- remote listing -------------------------------------------------------------------


def _folder_listing(prefix: str) -> list[dict[str, Any]]:
    url = f"{NCI_EVS_BASE}/folder?folder={urllib.parse.quote(prefix)}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=LISTING_TIMEOUT_SECONDS) as resp:  # noqa: S310 (fixed https host)
            body = resp.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        raise NciEvsError(f"could not list {url}: {reason}") from exc
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise NciEvsError(f"folder listing for {prefix!r} wasn't valid JSON") from exc
    contents = data.get("Contents") if isinstance(data, dict) else None
    return contents if isinstance(contents, list) else []


def _versions_from_listing(entries: list[dict], folder: str, prefix: str) -> list[dict]:
    """Every `{prefix} YYYY-MM-DD.odm.xml` entry in an S3 Contents list. The undated
    `{prefix}.odm.xml` (the "current" pointer) is skipped - it duplicates the newest
    dated file. `folder` is the directory the download key is rebuilt under, so a
    listing of bare basenames and one of full paths both work.
    """
    pattern = re.compile(rf"^{re.escape(prefix)} (\d{{4}}-\d{{2}}-\d{{2}})\.odm\.xml$")
    found: list[dict] = []
    for entry in entries:
        basename = (entry.get("Key") or "").rsplit("/", 1)[-1]
        match = pattern.match(basename)
        if not match:
            continue
        found.append(
            {
                "version": match.group(1),
                "key": f"{folder}/{basename}",
                "size": entry.get("Size"),
                "last_modified": entry.get("LastModified"),
            }
        )
    return found


def list_available_versions(standard: str, *, force: bool = False) -> list[dict]:
    """Every archived quarterly CT release of `standard`, newest first, each annotated
    with whether it's already on disk. No separate "current" entry - the newest dated
    release *is* the current one. The remote listing is cached for 24h (a new quarter
    appears rarely); `force` re-fetches it.
    """
    spec = _require_known(standard)
    cache_path = _versions_cache_path(standard)
    versions: list[dict] | None = None
    if not force and cache_path.is_file():
        try:
            cached = json.loads(cache_path.read_text())
            if (
                isinstance(cached, dict)
                and time.time() - cached.get("fetched_at", 0) < VERSIONS_TTL_SECONDS
            ):
                versions = cached.get("versions")
        except (OSError, json.JSONDecodeError):
            versions = None
    if versions is not None:
        # A cache written by an older build may still carry the retired "current" entry.
        versions = [v for v in versions if _VERSION_RE.match(v.get("version", ""))]

    if versions is None:
        folder, prefix = spec["dir"], spec["prefix"]
        by_version = {
            v["version"]: v
            for v in _versions_from_listing(
                _folder_listing(f"{folder}/Archive/{prefix}"),
                f"{folder}/Archive",
                prefix,
            )
        }
        versions = sorted(by_version.values(), key=lambda v: v["version"], reverse=True)
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps({"fetched_at": time.time(), "versions": versions})
        )

    downloaded = set(downloaded_versions(standard))
    return [{**v, "downloaded": v["version"] in downloaded} for v in versions]


def _version_entry(standard: str, version: str) -> dict:
    for entry in list_available_versions(standard):
        if entry["version"] == version:
            return entry
    raise NciEvsError(
        f"no {version!r} release listed for {standard} - try 'check for updates' to refresh the version list"
    )


# --- download + local cache ---------------------------------------------------------


def downloaded_versions(standard: str) -> list[str]:
    """Which dated versions of `standard` are cached on disk, newest first. No network."""
    _require_known(standard)
    if not CACHE_DIR.is_dir():
        return []
    found = []
    for meta in CACHE_DIR.glob(f"{standard}@*.meta.json"):
        version = meta.name[len(standard) + 1 : -len(".meta.json")]
        if _VERSION_RE.match(version) and _file_path(standard, version).is_file():
            found.append(version)
    return sorted(found, reverse=True)


def cache_info(standard: str, version: str) -> dict[str, Any] | None:
    """Metadata about the locally cached file for `(standard, YYYY-MM-DD)`, or None if it
    hasn't been downloaded. No network - pass a resolved date, not "current".
    """
    _require_known(standard)
    meta_path = _meta_path(standard, version)
    if not meta_path.is_file():
        return None
    try:
        return json.loads(meta_path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def _download(key: str) -> bytes:
    url = f"{NCI_EVS_BASE}/{urllib.parse.quote(key)}"
    req = urllib.request.Request(url, headers={"Accept": "application/xml"})
    try:
        with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT_SECONDS) as resp:  # noqa: S310 (fixed https host)
            return resp.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        raise NciEvsError(f"could not download {url}: {reason}") from exc


def ensure_downloaded(
    standard: str, version: str = CURRENT, *, force: bool = False
) -> Path:
    """Downloads `(standard, version)`'s Terminology.odm.xml if it isn't already cached
    (or if `force`), and rebuilds the lightweight codelist index alongside it. A plain
    lookup never re-downloads - a published quarterly release's content never changes.
    `version` may be `"current"` (→ the newest available release) or a YYYY-MM-DD date.
    """
    version = resolve_version(standard, version)
    path = _file_path(standard, version)
    if path.is_file() and not force:
        return path
    entry = _version_entry(standard, version)
    data = _download(entry["key"])
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    _meta_path(standard, version).write_text(
        json.dumps(
            {
                "standard": standard,
                "version": version,
                "downloaded_at": time.time(),
                "size": len(data),
                "source_key": entry["key"],
                "source_last_modified": entry.get("last_modified"),
            }
        )
    )
    _build_index(standard, version, path)
    return path


def _submission_value(el: etree._Element) -> str:
    """A CodeList's CDISC submission value: the `nciodm:CDISCSubmissionValue` child if
    present (it is, in real files), else the trailing segment of the OID
    (`CL.C66742.NY` -> `NY`).
    """
    child = el.find(_nci("CDISCSubmissionValue"))
    if child is not None and child.text and child.text.strip():
        return child.text.strip()
    oid = el.get("OID") or ""
    return oid.rsplit(".", 1)[-1] if "." in oid else ""


def _codelist_index_entry(el: etree._Element) -> dict:
    return {
        "oid": el.get("OID"),
        "name": el.get("Name"),
        "submission_value": _submission_value(el),
        "data_type": el.get("DataType"),
        "nci_code": el.get(_nci("ExtCodeID")),
        "extensible": el.get(_nci("CodeListExtensible")) == "Yes",
    }


def _build_index(standard: str, version: str, path: Path) -> None:
    """One pass over the file, keeping only each CodeList's own attributes (not its
    terms) - cheap to hold and re-read, versus re-streaming the full ~25MB file just to
    answer "what codelists are there".
    """
    entries: list[dict] = []
    for _, el in etree.iterparse(str(path), events=("end",), tag=_odm("CodeList")):
        entries.append(_codelist_index_entry(el))
        el.clear()
        while el.getprevious() is not None:
            del el.getparent()[0]
    _index_path(standard, version).write_text(json.dumps(entries))


def list_codelists(standard: str, version: str = CURRENT) -> list[dict]:
    """The cached index for `(standard, version)` (built on download, or rebuilt here if
    the raw file is present but the index is missing). Downloads first if not cached.
    """
    version = resolve_version(standard, version)
    ensure_downloaded(standard, version)
    index_path = _index_path(standard, version)
    if not index_path.is_file():
        _build_index(standard, version, _file_path(standard, version))
    index = json.loads(index_path.read_text())
    # An index written by an older build won't have submission_value - rebuild once.
    if index and "submission_value" not in index[0]:
        _build_index(standard, version, _file_path(standard, version))
        index = json.loads(index_path.read_text())
    return index


def _text_of(parent: etree._Element, tag: str) -> str | None:
    child = parent.find(tag)
    if child is None:
        return None
    tt = child.find(_odm("TranslatedText"))
    return tt.text if tt is not None else child.text


def _term_from_item(item: etree._Element) -> dict:
    # Confirmed live: every term in a real NCI EVS CT file is an EnumeratedItem, never a
    # CodeListItem+Decode - CodeListItem is handled anyway, defensively.
    term: dict[str, Any] = {
        "code": item.get("CodedValue"),
        "nci_code": item.get(_nci("ExtCodeID")),
    }
    if etree.QName(item).localname == "CodeListItem":
        term["decode"] = _text_of(item, _odm("Decode"))
    synonym = item.find(_nci("CDISCSynonym"))
    if synonym is not None and synonym.text:
        term["synonym"] = synonym.text
    definition = item.find(_nci("CDISCDefinition"))
    if definition is not None and definition.text:
        term["definition"] = definition.text
    preferred = item.find(_nci("PreferredTerm"))
    if preferred is not None and preferred.text:
        term["preferred_term"] = preferred.text
    return term


def get_codelist_terms(standard: str, version: str, codelist_oid: str) -> dict:
    """Streams the cached file looking for one CodeList by OID, stopping as soon as it's
    found - a single early-exit pass, not a full-file parse.
    """
    version = resolve_version(standard, version)
    path = ensure_downloaded(standard, version)
    for _, el in etree.iterparse(str(path), events=("end",), tag=_odm("CodeList")):
        if el.get("OID") != codelist_oid:
            el.clear()
            continue
        result = {
            **_codelist_index_entry(el),
            "terms": [
                _term_from_item(item)
                for item in el
                if etree.QName(item).localname in ("CodeListItem", "EnumeratedItem")
            ],
        }
        el.clear()
        return result
    raise NciEvsError(
        f"no codelist with OID {codelist_oid!r} found in the cached {standard} {version} terminology file"
    )


# --- CSV export (for saving into the local Standards folder) -----------------------

# The column set the CDISC Data Standards Browser's CT exports use, which
# cdisc.standard_csv reads back (is_ct_file / codelist_detail). A header row per
# codelist (empty "Codelist Code") followed by one row per term ("Codelist Code" =
# the parent's C-code).
_CT_CSV_COLUMNS = [
    "Code",
    "Codelist Code",
    "Codelist Extensible (Yes/No)",
    "Codelist Name",
    "CDISC Submission Value",
    "CDISC Synonym(s)",
    "CDISC Definition",
    "NCI Preferred Term",
    "Standard and Date",
]


def _child_text(el: etree._Element, tag: str) -> str:
    child = el.find(tag)
    return (child.text or "").strip() if child is not None and child.text else ""


def _codelist_description(el: etree._Element) -> str:
    desc = _text_of(el, _odm("Description"))
    if desc:
        return desc.strip()
    return _child_text(el, _nci("CDISCDefinition"))


def to_ct_csv(standard: str, version: str = CURRENT) -> str:
    """The cached NCI EVS CT for `(standard, version)` re-serialised as a
    CDISC-Data-Standards-Browser-style CT CSV (see `_CT_CSV_COLUMNS`). Downloads the
    release first if it isn't cached. `cdisc.standard_csv` reads the result back
    unchanged, so a saved file scaffolds datasets/codelists like any hand-downloaded
    export.
    """
    version = resolve_version(standard, version)
    path = ensure_downloaded(standard, version)
    std_and_date = f"{standard} CT {version}"

    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(_CT_CSV_COLUMNS)

    for _, el in etree.iterparse(str(path), events=("end",), tag=_odm("CodeList")):
        ccode = el.get(_nci("ExtCodeID")) or ""
        name = el.get("Name") or ""
        extensible = "Yes" if el.get(_nci("CodeListExtensible")) == "Yes" else "No"
        writer.writerow(
            [
                ccode,
                "",
                extensible,
                name,
                _submission_value(el),
                _child_text(el, _nci("CDISCSynonym")),
                _codelist_description(el),
                _child_text(el, _nci("PreferredTerm")),
                std_and_date,
            ]
        )
        for item in el:
            if etree.QName(item).localname not in ("EnumeratedItem", "CodeListItem"):
                continue
            writer.writerow(
                [
                    item.get(_nci("ExtCodeID")) or "",
                    ccode,
                    "",
                    name,
                    item.get("CodedValue") or "",
                    _child_text(item, _nci("CDISCSynonym")),
                    _child_text(item, _nci("CDISCDefinition")),
                    _child_text(item, _nci("PreferredTerm")),
                    std_and_date,
                ]
            )
        el.clear()
        while el.getprevious() is not None:
            del el.getparent()[0]

    return buf.getvalue()
