"""The /api/cdisc/nci-evs/* and /api/standards/* routes server.py adds - called
directly via their endpoint functions (this repo doesn't otherwise test server.py over
real HTTP; httpx isn't a dependency), mocked at urllib.request.urlopen for NCI EVS.

The CDISC Library API routes (config/status/query/cache) were retired - those modules
(defineyaml/cdisc/client.py etc.) are still in the tree and still unit-tested directly,
but nothing routes to them any more.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from defineyaml.cdisc import csv_db, nci_evs
from defineyaml.webui import tree as tree_module
from defineyaml.webui.server import create_app


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(nci_evs, "CACHE_DIR", tmp_path / "nci-evs-cache")


_SAMPLE_ODM = b"""<?xml version="1.0" encoding="UTF-8"?>
<ODM xmlns="http://www.cdisc.org/ns/odm/v1.3" xmlns:nciodm="http://ncicb.nci.nih.gov/xml/odm/EVS/CDISC">
  <Study OID="S"><MetaDataVersion OID="MDV" Name="Sample">
    <CodeList OID="CL.C66742.NY" Name="No Yes Response" DataType="text" nciodm:ExtCodeID="C66742" nciodm:CodeListExtensible="No">
      <EnumeratedItem CodedValue="N" nciodm:ExtCodeID="C49487"><nciodm:PreferredTerm>No</nciodm:PreferredTerm></EnumeratedItem>
      <EnumeratedItem CodedValue="Y" nciodm:ExtCodeID="C49488"><nciodm:PreferredTerm>Yes</nciodm:PreferredTerm></EnumeratedItem>
    </CodeList>
  </MetaDataVersion></Study>
</ODM>
"""

_LISTING = {
    "IsTruncated": False,
    "Contents": [
        {
            "Key": "CDISC/ADaM/ADaM Terminology.odm.xml",
            "Size": 97412,
            "LastModified": "x",
        }
    ],
}
_ARCHIVE = {
    "IsTruncated": False,
    "Contents": [
        {
            "Key": "CDISC/ADaM/Archive/ADaM Terminology 2025-09-26.odm.xml",
            "Size": 93927,
            "LastModified": "x",
        },
        {
            "Key": "CDISC/ADaM/Archive/ADaM Terminology 2026-03-27.odm.xml",
            "Size": 97412,
            "LastModified": "x",
        },
    ],
}


class _FakeResponse:
    def __init__(self, body):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _dispatch(req, *a, **k):
    url = req.full_url if hasattr(req, "full_url") else str(req)
    if "/folder?folder=" in url:
        return _FakeResponse(
            json.dumps(_ARCHIVE if "Archive" in url else _LISTING).encode()
        )
    return _FakeResponse(_SAMPLE_ODM)


def _route(app, path, method="GET"):
    return next(
        r
        for r in app.routes
        if getattr(r, "path", None) == path and method in getattr(r, "methods", set())
    )


@pytest.fixture()
def app(tmp_path):
    return create_app(tmp_path / "define")


# --- retired routes are gone -----------------------------------------------------


@pytest.mark.parametrize(
    "path",
    ["/api/cdisc/config", "/api/cdisc/status", "/api/cdisc/query", "/api/cdisc/cache"],
)
def test_retired_cdisc_library_routes_are_absent(app, path):
    assert not any(getattr(r, "path", None) == path for r in app.routes)


# --- NCI EVS -------------------------------------------------------------------


def test_nci_evs_standards_route_lists_all_three_with_no_downloads(app):
    result = _route(app, "/api/cdisc/nci-evs/standards").endpoint()
    assert {r["standard"] for r in result} == {"SDTM", "ADaM", "SEND"}
    assert all(r["downloaded"] == [] for r in result)


def test_nci_evs_versions_route(app):
    with patch("urllib.request.urlopen", side_effect=_dispatch):
        result = _route(app, "/api/cdisc/nci-evs/{standard}/versions").endpoint(
            "ADaM", force=False
        )
    assert [v["version"] for v in result] == ["2026-03-27", "2025-09-26"]


def test_nci_evs_versions_route_rejects_unknown_standard(app):
    with pytest.raises(HTTPException) as exc_info:
        _route(app, "/api/cdisc/nci-evs/{standard}/versions").endpoint(
            "BOGUS", force=False
        )
    assert exc_info.value.status_code == 400


def test_nci_evs_download_route_resolves_current_and_populates_cache(app):
    with patch("urllib.request.urlopen", side_effect=_dispatch):
        result = _route(app, "/api/cdisc/nci-evs/{standard}/download", "POST").endpoint(
            "ADaM", version="current", force=False
        )
    assert result["version"] == "2026-03-27"  # "current" resolved to the newest date
    assert result["cache"]["size"] == len(_SAMPLE_ODM)
    assert result["cache"]["version"] == "2026-03-27"


def test_nci_evs_download_route_archived_version(app):
    with patch("urllib.request.urlopen", side_effect=_dispatch):
        _route(app, "/api/cdisc/nci-evs/{standard}/download", "POST").endpoint(
            "ADaM", version="2025-09-26", force=False
        )
    standards = _route(app, "/api/cdisc/nci-evs/standards").endpoint()
    assert next(s for s in standards if s["standard"] == "ADaM")["downloaded"] == [
        "2025-09-26"
    ]


def test_nci_evs_codelists_route_downloads_then_lists(app):
    with patch("urllib.request.urlopen", side_effect=_dispatch):
        result = _route(app, "/api/cdisc/nci-evs/{standard}/codelists").endpoint(
            "ADaM", version="current"
        )
    assert result == [
        {
            "oid": "CL.C66742.NY",
            "name": "No Yes Response",
            "submission_value": "NY",
            "data_type": "text",
            "nci_code": "C66742",
            "extensible": False,
        }
    ]


def test_nci_evs_codelist_terms_route(app):
    with patch("urllib.request.urlopen", side_effect=_dispatch):
        result = _route(app, "/api/cdisc/nci-evs/{standard}/codelists/{oid}").endpoint(
            "ADaM", "CL.C66742.NY", version="current"
        )
    assert len(result["terms"]) == 2


def test_nci_evs_codelist_terms_route_404s_for_unknown_oid(app):
    with patch("urllib.request.urlopen", side_effect=_dispatch):
        with pytest.raises(HTTPException) as exc_info:
            _route(app, "/api/cdisc/nci-evs/{standard}/codelists/{oid}").endpoint(
                "ADaM", "NOPE", version="current"
            )
    assert exc_info.value.status_code == 404


# --- local standards folder (per-tree: standards.yaml's standards_folder:) -----------


@pytest.fixture()
def csv_folder(tmp_path):
    root = tmp_path / "csvs"
    (root / "data_analysis").mkdir(parents=True)
    (root / "data_analysis" / "ADaMIG_v1.3.csv").write_text(
        '"Var","Label"\n"STUDYID","Study Identifier"\n"AGE","Age"\n'
    )
    return root


@pytest.fixture()
def std_app(tmp_path):
    dest = tmp_path / "define"
    (dest / "codelists").mkdir(parents=True)
    tree_module.save_object(dest, "standards", "standards", {"standards": []})
    return create_app(dest)


def test_standards_config_defaults_to_unset(std_app):
    assert _route(std_app, "/api/standards/config").endpoint() == {
        "folder": None,
        "resolved": None,
        "exists": False,
        "creatable": False,
        "error": None,
    }


def test_standards_config_put_validates_bad_path(std_app):
    with pytest.raises(HTTPException) as exc_info:
        _route(std_app, "/api/standards/config", "PUT").endpoint(
            {"folder": "/no/such/place"}
        )
    assert exc_info.value.status_code == 400


def test_standards_config_create_missing_folder(std_app, tmp_path):
    # A path set in standards.yaml (hand-edited, or a cloned/moved tree) that isn't
    # on disk -> config reports it creatable, and the create route mkdir -p's it.
    missing = tmp_path / "csv-exports" / "cdisc"
    tree_module.save_object(
        std_app.state.root,
        "standards",
        "standards",
        {"standards_folder": str(missing), "standards": []},
    )
    status = _route(std_app, "/api/standards/config").endpoint()
    assert status["exists"] is False and status["creatable"] is True

    out = _route(std_app, "/api/standards/config/create-folder", "POST").endpoint()
    assert out["exists"] is True and out["creatable"] is False
    assert missing.is_dir()


def test_standards_config_create_folder_400_when_unset(std_app):
    with pytest.raises(HTTPException) as exc_info:
        _route(std_app, "/api/standards/config/create-folder", "POST").endpoint()
    assert exc_info.value.status_code == 400


def test_nci_evs_save_to_folder_route_writes_a_scaffolded_ct_csv(std_app, csv_folder):
    _route(std_app, "/api/standards/config", "PUT").endpoint(
        {"folder": str(csv_folder)}
    )
    save = _route(std_app, "/api/cdisc/nci-evs/{standard}/save-to-folder", "POST")

    with patch("urllib.request.urlopen", side_effect=_dispatch):
        r = save.endpoint("ADaM", version="current")
    assert r == {
        "path": "terminology/adam/ADaM_CT_2026-03-27.csv",
        "existed": False,
        "bytes": r["bytes"],
        "standard": "ADaM",
        "version": "2026-03-27",
    }
    written = csv_folder / r["path"]
    assert written.is_file()
    assert "Codelist Code" in written.read_text().splitlines()[0]

    # it now shows up in the local-standards file listing
    files = _route(std_app, "/api/standards/files").endpoint()
    paths = [f["path"] for cat in files["categories"] for f in cat["files"]]
    assert "terminology/adam/ADaM_CT_2026-03-27.csv" in paths

    # re-saving reports existed=True
    with patch("urllib.request.urlopen", side_effect=_dispatch):
        assert save.endpoint("ADaM", version="current")["existed"] is True


def test_nci_evs_save_to_folder_400_without_a_configured_folder(std_app):
    with patch("urllib.request.urlopen", side_effect=_dispatch):
        with pytest.raises(HTTPException) as exc_info:
            _route(
                std_app, "/api/cdisc/nci-evs/{standard}/save-to-folder", "POST"
            ).endpoint("ADaM", version="current")
    assert exc_info.value.status_code == 400


def test_standards_config_put_writes_standards_yaml_and_reads_back(std_app, csv_folder):
    result = _route(std_app, "/api/standards/config", "PUT").endpoint(
        {"folder": str(csv_folder)}
    )
    assert result["exists"] is True and result["resolved"] == str(csv_folder.resolve())
    assert tree_module.read_object(std_app.state.root, "standards", "standards")[
        "standards_folder"
    ] == str(csv_folder)
    assert _route(std_app, "/api/standards/config").endpoint()["exists"] is True
    # Clearing.
    _route(std_app, "/api/standards/config", "PUT").endpoint({"folder": ""})
    assert "standards_folder" not in tree_module.read_object(
        std_app.state.root, "standards", "standards"
    )


def test_standards_files_file_search(std_app, csv_folder):
    _route(std_app, "/api/standards/config", "PUT").endpoint(
        {"folder": str(csv_folder)}
    )
    files = _route(std_app, "/api/standards/files").endpoint()
    assert files["categories"][0]["files"][0]["path"] == "data_analysis/ADaMIG_v1.3.csv"
    rows = _route(std_app, "/api/standards/file").endpoint(
        path="data_analysis/ADaMIG_v1.3.csv", q="age", limit=10, offset=0
    )
    assert rows["total_matched"] == 1 and rows["rows"][0]["Var"] == "AGE"
    hits = _route(std_app, "/api/standards/search").endpoint(q="study", limit=50)
    assert len(hits["matches"]) == 1
    # the browse/search routes cache the CSVs in a DuckDB under the tree's .cache/
    if csv_db.available():
        assert (std_app.state.root / ".cache" / "standards.duckdb").is_file()


def test_standards_files_400_when_folder_unset(std_app):
    with pytest.raises(HTTPException) as exc_info:
        _route(std_app, "/api/standards/files").endpoint()
    assert exc_info.value.status_code == 400


def test_standards_file_404_for_missing(std_app, csv_folder):
    _route(std_app, "/api/standards/config", "PUT").endpoint(
        {"folder": str(csv_folder)}
    )
    with pytest.raises(HTTPException) as exc_info:
        _route(std_app, "/api/standards/file").endpoint(
            path="data_analysis/nope.csv", q=None, limit=10, offset=0
        )
    assert exc_info.value.status_code == 404


def test_standards_raw_route(std_app, csv_folder):
    _route(std_app, "/api/standards/config", "PUT").endpoint(
        {"folder": str(csv_folder)}
    )
    response = _route(std_app, "/api/standards/raw").endpoint(
        path="data_analysis/ADaMIG_v1.3.csv"
    )
    assert Path(response.path).name == "ADaMIG_v1.3.csv"


def test_cdisc_viewer_page_route_exists(app):
    response = _route(app, "/cdisc-viewer").endpoint()
    assert Path(response.path).name == "cdisc-viewer.html"


# --- scaffold-from-standard routes ---------------------------------------------

_FIXTURES = Path(__file__).parent / "fixtures"
_DEFINE_TREE = _FIXTURES / "define"
_CL_DSB = _FIXTURES / "cl-dsb"

# Retained so a stray fixture deletion degrades to a skip rather than a hard error;
# with the fixtures committed it never actually skips.
scaffold_skip = pytest.mark.skipif(
    not _CL_DSB.is_dir(), reason="tests/fixtures/cl-dsb not present"
)


@pytest.fixture()
def scaffold_app(tmp_path):
    dest = tmp_path / "define"
    shutil.copytree(_DEFINE_TREE, dest)
    # start from empty datasets/ + codelists/ so the fixture tree's own objects can't
    # collide with what these tests create
    for sub in ("datasets", "codelists"):
        for f in (dest / sub).glob("*.yaml"):
            f.unlink()
    tree_module.save_object(
        dest,
        "standards",
        "standards",
        {
            "standards_folder": str(_CL_DSB),
            "standards": [
                {
                    "name": "SDTMIG",
                    "type": "IG",
                    "version": "3.4",
                    "standards_file": "data_tabulation/SDTMIG_v3.4.csv",
                },
                {
                    "name": "SDTMCT",
                    "type": "CT",
                    "version": "2026-03-27",
                    "standards_file": "terminology/sdtm/SDTM_CT_2026-03-27.csv",
                },
            ],
        },
    )
    return create_app(dest)


@scaffold_skip
def test_scaffold_standards_route(scaffold_app):
    result = _route(scaffold_app, "/api/standards/scaffold/standards").endpoint()
    assert {s["name"]: s["kind"] for s in result} == {"SDTMIG": "ig", "SDTMCT": "ct"}


@scaffold_skip
def test_scaffold_units_and_unknown_standard(scaffold_app):
    units = _route(scaffold_app, "/api/standards/scaffold/units").endpoint(
        standard="SDTMIG"
    )["units"]
    assert any(u["unit"] == "DM" for u in units)
    with pytest.raises(HTTPException) as exc_info:
        _route(scaffold_app, "/api/standards/scaffold/units").endpoint(standard="NOPE")
    assert exc_info.value.status_code == 404


@scaffold_skip
def test_scaffold_ig_variables_and_hints_routes(scaffold_app):
    cat = _route(scaffold_app, "/api/standards/scaffold/ig-catalog").endpoint()
    assert any(s["name"] == "SDTMIG" for s in cat["standards"])

    found = _route(scaffold_app, "/api/standards/scaffold/ig-variables").endpoint(
        standard="SDTMIG", unit="DM", q="age", limit=800
    )
    names = {v["name"] for v in found["variables"]}
    assert "AGEU" in names
    assert (
        next(v for v in found["variables"] if v["name"] == "AGEU")["codelist"] == "ageu"
    )

    _route(scaffold_app, "/api/standards/scaffold/dataset", "POST").endpoint(
        {"standard": "SDTMIG", "unit": "DM", "name": "DM"}
    )
    hints = _route(scaffold_app, "/api/standards/scaffold/variable-hints").endpoint(
        dataset="dm"
    )
    assert {"standard": "SDTMIG", "unit": "DM"} in hints["matched"]
    assert hints["variables"]["AGEU"]["codelist"] == ["ageu"]
    assert hints["variables"]["AGEU"]["sources"][0]["label"]


@scaffold_skip
def test_scaffold_dataset_and_codelists_and_missing(scaffold_app):
    made = _route(scaffold_app, "/api/standards/scaffold/dataset", "POST").endpoint(
        {"standard": "SDTMIG", "unit": "DM", "name": "DM"}
    )
    assert made["key"].startswith("dm")  # "dm", or "dm-2" if the tree already has one

    cl = _route(scaffold_app, "/api/standards/scaffold/ct-codelists").endpoint(
        standard="SDTMCT", q="sex"
    )
    assert any(c["value"] == "SEX" for c in cl["codelists"])

    ref = _route(scaffold_app, "/api/standards/scaffold/ct-codelist").endpoint(
        name="SEX", nci_code="C66731"
    )
    assert (
        ref["found"]
        and ref["value"] == "SEX"
        and {t["code"] for t in ref["terms"]} >= {"M", "F"}
    )
    created = _route(
        scaffold_app, "/api/standards/scaffold/codelists", "POST"
    ).endpoint({"standard": "SDTMCT", "values": ["SEX"]})
    # the scratch tree is a copy of define/, which may already carry a SEX codelist
    assert "sex" in created["created"] or created["skipped"]

    # rename + term subset via `items`
    terms = _route(scaffold_app, "/api/standards/scaffold/ct-codelist-terms").endpoint(
        standard="SDTMCT", value="NY"
    )
    assert {t["code"] for t in terms["terms"]} >= {"Y", "N"}
    sub = _route(scaffold_app, "/api/standards/scaffold/codelists", "POST").endpoint(
        {
            "standard": "SDTMCT",
            "items": [{"value": "NY", "name": "YESONLY", "codes": ["Y"]}],
        }
    )
    assert sub["created"] == ["yesonly"]
    made_cl = tree_module.read_object(scaffold_app.state.root, "codelists", "yesonly")
    assert made_cl["name"] == "YESONLY"
    assert [t["code"] for t in made_cl["terms"]] == ["Y"]

    missing = _route(
        scaffold_app, "/api/standards/scaffold/missing-codelists"
    ).endpoint()
    assert any(m["standard"] == "SDTMCT" for m in missing["missing"])
    resolved = _route(
        scaffold_app, "/api/standards/scaffold/missing-codelists", "POST"
    ).endpoint()
    assert resolved["created"]
