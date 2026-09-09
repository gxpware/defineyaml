"""defineyaml.cdisc.nci_evs - the (now primary) CT source. Mocked at
urllib.request.urlopen with a dispatcher keyed on the request URL: the S3-style folder
listing returns synthetic JSON, the file download returns a small ODM-XML snippet
matching the real NCI EVS shape (EnumeratedItem-only, nciodm:-namespaced metadata). No
live network, and no need to vendor the real ~25MB SDTM file.
"""

from __future__ import annotations

import json
import urllib.error
from unittest.mock import patch

import pytest

from defineyaml.cdisc import nci_evs

_SAMPLE_ODM = b"""<?xml version="1.0" encoding="UTF-8"?>
<ODM xmlns="http://www.cdisc.org/ns/odm/v1.3" xmlns:nciodm="http://ncicb.nci.nih.gov/xml/odm/EVS/CDISC">
  <Study OID="S"><MetaDataVersion OID="MDV" Name="Sample">
    <CodeList OID="CL.C128689.RACEC" Name="Race As Collected" DataType="text" nciodm:ExtCodeID="C128689" nciodm:CodeListExtensible="Yes">
      <Description><TranslatedText xml:lang="en">Race as collected on the CRF.</TranslatedText></Description>
      <EnumeratedItem CodedValue="AFRICAN AMERICAN" nciodm:ExtCodeID="C128937">
        <nciodm:CDISCSynonym>Afro-American</nciodm:CDISCSynonym>
        <nciodm:CDISCDefinition>A person having origins in sub-Saharan Africa.</nciodm:CDISCDefinition>
        <nciodm:PreferredTerm>African American</nciodm:PreferredTerm>
      </EnumeratedItem>
      <EnumeratedItem CodedValue="ASIAN" nciodm:ExtCodeID="C41260">
        <nciodm:PreferredTerm>Asian</nciodm:PreferredTerm>
      </EnumeratedItem>
      <nciodm:CDISCSubmissionValue>RACE</nciodm:CDISCSubmissionValue>
    </CodeList>
    <CodeList OID="CL.C66742.NY" Name="No Yes Response" DataType="text" nciodm:ExtCodeID="C66742" nciodm:CodeListExtensible="No">
      <EnumeratedItem CodedValue="N" nciodm:ExtCodeID="C49487"><nciodm:PreferredTerm>No</nciodm:PreferredTerm></EnumeratedItem>
      <EnumeratedItem CodedValue="Y" nciodm:ExtCodeID="C49488"><nciodm:PreferredTerm>Yes</nciodm:PreferredTerm></EnumeratedItem>
    </CodeList>
  </MetaDataVersion></Study>
</ODM>
"""

# What the folder API returns for a narrow prefix. `Key` may be a full path or a bare
# basename in real responses - nci_evs handles both by taking the basename, so the tests
# use full paths (the SDTM-style response).
_CURRENT_LISTING = {
    "IsTruncated": False,
    "Contents": [
        {
            "Key": "CDISC/ADaM/ADaM Terminology.odm.xml",
            "Size": 97412,
            "LastModified": "2026-07-11T23:27:37.000Z",
        },
        {
            "Key": "CDISC/ADaM/ADaM Terminology.html",
            "Size": 91104,
            "LastModified": "2026-07-11T23:27:37.000Z",
        },
    ],
}
_ARCHIVE_LISTING = {
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
        {
            "Key": "CDISC/ADaM/Archive/adam-terminology.odm.xml",
            "Size": 12285,
            "LastModified": "x",
        },
    ],
}


class _FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _dispatch(req, *args, **kwargs):
    url = req.full_url if hasattr(req, "full_url") else str(req)
    if "/folder?folder=" in url:
        body = _ARCHIVE_LISTING if "Archive" in url else _CURRENT_LISTING
        return _FakeResponse(json.dumps(body).encode())
    return _FakeResponse(_SAMPLE_ODM)


@pytest.fixture(autouse=True)
def isolated_cache_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(nci_evs, "CACHE_DIR", tmp_path / "nci-evs")


def _patch_net():
    return patch("urllib.request.urlopen", side_effect=_dispatch)


def test_unknown_standard_raises():
    with pytest.raises(nci_evs.NciEvsError, match="unknown standard"):
        nci_evs.ensure_downloaded("BOGUS")


def test_invalid_version_raises():
    with _patch_net():
        with pytest.raises(nci_evs.NciEvsError, match="invalid version"):
            nci_evs.ensure_downloaded("ADaM", "latest")


def test_list_available_versions_returns_archived_dates_newest_first():
    with _patch_net():
        versions = nci_evs.list_available_versions("ADaM")
    got = [v["version"] for v in versions]
    # No "current" entry; the junk 'adam-terminology.odm.xml' key is filtered out.
    assert got == ["2026-03-27", "2025-09-26"]
    assert all(v["downloaded"] is False for v in versions)
    assert (
        versions[0]["key"] == "CDISC/ADaM/Archive/ADaM Terminology 2026-03-27.odm.xml"
    )


def test_resolve_version_maps_current_to_the_newest():
    with _patch_net():
        assert nci_evs.resolve_version("ADaM", "current") == "2026-03-27"
        assert nci_evs.resolve_version("ADaM", "2025-09-26") == "2025-09-26"
        with pytest.raises(nci_evs.NciEvsError, match="invalid version"):
            nci_evs.resolve_version("ADaM", "nope")


def test_list_available_versions_is_cached_and_force_refetches():
    with _patch_net() as m:
        nci_evs.list_available_versions("ADaM")
    first_calls = m.call_count
    with patch("urllib.request.urlopen", side_effect=_dispatch) as m2:
        nci_evs.list_available_versions("ADaM")
    m2.assert_not_called()
    with patch("urllib.request.urlopen", side_effect=_dispatch) as m3:
        nci_evs.list_available_versions("ADaM", force=True)
    assert m3.call_count == first_calls


def test_ensure_downloaded_current_resolves_to_the_newest_date_and_caches():
    with _patch_net():
        path = nci_evs.ensure_downloaded("ADaM", "current")
    assert path.read_bytes() == _SAMPLE_ODM
    info = nci_evs.cache_info("ADaM", "2026-03-27")
    assert info["size"] == len(_SAMPLE_ODM)
    assert info["version"] == "2026-03-27"
    assert nci_evs.downloaded_versions("ADaM") == ["2026-03-27"]
    assert nci_evs.cache_info("ADaM", "current") is None  # not a real cache key


def test_ensure_downloaded_archived_version():
    with _patch_net():
        nci_evs.ensure_downloaded("ADaM", "2025-09-26")
    assert nci_evs.downloaded_versions("ADaM") == ["2025-09-26"]


def test_ensure_downloaded_unknown_version_raises():
    with _patch_net():
        with pytest.raises(nci_evs.NciEvsError, match="no '1999-01-01' release"):
            nci_evs.ensure_downloaded("ADaM", "1999-01-01")


def test_ensure_downloaded_does_not_refetch_once_cached():
    with _patch_net():
        nci_evs.ensure_downloaded("ADaM", "2026-03-27")
    with patch("urllib.request.urlopen") as m2:
        nci_evs.ensure_downloaded("ADaM", "2026-03-27")
    m2.assert_not_called()


def test_list_codelists_downloads_once_and_returns_index_with_submission_value():
    with _patch_net():
        codelists = nci_evs.list_codelists("ADaM", "current")
    assert len(codelists) == 2
    race = next(c for c in codelists if c["name"] == "Race As Collected")
    assert race == {
        "oid": "CL.C128689.RACEC",
        "name": "Race As Collected",
        "submission_value": "RACE",  # from <nciodm:CDISCSubmissionValue>, not the OID
        "data_type": "text",
        "nci_code": "C128689",
        "extensible": True,
    }
    ny = next(c for c in codelists if c["nci_code"] == "C66742")
    assert ny["submission_value"] == "NY"  # OID fallback (no element present)


def test_get_codelist_terms_returns_real_term_fields():
    with _patch_net():
        result = nci_evs.get_codelist_terms("ADaM", "current", "CL.C128689.RACEC")
    assert result["extensible"] is True
    terms = {t["code"]: t for t in result["terms"]}
    assert terms["AFRICAN AMERICAN"] == {
        "code": "AFRICAN AMERICAN",
        "nci_code": "C128937",
        "synonym": "Afro-American",
        "definition": "A person having origins in sub-Saharan Africa.",
        "preferred_term": "African American",
    }
    assert "synonym" not in terms["ASIAN"]


def test_get_codelist_terms_raises_for_unknown_oid():
    with _patch_net():
        with pytest.raises(nci_evs.NciEvsError, match="no codelist"):
            nci_evs.get_codelist_terms("ADaM", "current", "DOES-NOT-EXIST")


def test_to_ct_csv_round_trips_through_standard_csv(tmp_path):
    from defineyaml.cdisc import standard_csv

    with _patch_net():
        text = nci_evs.to_ct_csv("ADaM", "current")

    folder = tmp_path / "std"
    rel = "terminology/adam/ADaM_CT_2026-03-27.csv"
    (folder / "terminology" / "adam").mkdir(parents=True)
    (folder / rel).write_text(text, encoding="utf-8")

    codelists = {c["value"]: c for c in standard_csv.list_codelists(folder, rel)}
    assert set(codelists) == {"RACE", "NY"}
    assert codelists["RACE"]["nci_code"] == "C128689"
    assert codelists["RACE"]["extensible"] is True
    assert codelists["NY"]["term_count"] == 2

    ny = standard_csv.codelist_detail(folder, rel, "NY")
    assert ny["nci_code"] == "C66742"
    assert [t["code"] for t in ny["terms"]] == ["N", "Y"]
    assert {t["decode"] for t in ny["terms"]} == {"No", "Yes"}  # NCI Preferred Term

    race = standard_csv.codelist_detail(folder, rel, "RACE")
    assert race["extended"] is True
    assert {t["code"] for t in race["terms"]} == {"AFRICAN AMERICAN", "ASIAN"}


def test_download_failure_raises_nci_evs_error():
    def _boom(req, *a, **k):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "/folder?folder=" in url:
            return _FakeResponse(json.dumps(_ARCHIVE_LISTING).encode())
        raise urllib.error.URLError("unreachable")

    with patch("urllib.request.urlopen", side_effect=_boom):
        with pytest.raises(nci_evs.NciEvsError, match="unreachable"):
            nci_evs.ensure_downloaded("ADaM", "current")


def test_listing_failure_raises_nci_evs_error():
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("no dns")):
        with pytest.raises(nci_evs.NciEvsError, match="could not list"):
            nci_evs.list_available_versions("ADaM")


def test_cache_info_is_none_before_any_download():
    assert nci_evs.cache_info("ADaM", "2026-03-27") is None
    assert nci_evs.downloaded_versions("ADaM") == []
