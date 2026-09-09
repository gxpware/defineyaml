"""defineyaml.cdisc.local_standards - reading a folder of CDISC CSV exports. Purely
functional now: every call takes the folder as an explicit Path (the webui layer
resolves it from the tree's standards.yaml). No config file of its own.
"""

from __future__ import annotations

import pytest

from defineyaml.cdisc import local_standards

_ADAMIG = (
    '"Version","Data Structure Name","Variable Name","Variable Label","Core"\n'
    '"ADaMIG v1.3","Subject-Level Analysis Dataset","STUDYID","Study Identifier","Req"\n'
    '"ADaMIG v1.3","Subject-Level Analysis Dataset","TRTSDT","Date of First Exposure","Perm"\n'
)
_CT = (
    '"Code","Codelist Name","CDISC Submission Value","Standard and Date"\n'
    '"C64848","Severity/Intensity","MILD","SDTM CT 2026-03-27"\n'
    '"C64849","Severity/Intensity","MODERATE","SDTM CT 2026-03-27"\n'
)


@pytest.fixture()
def folder(tmp_path):
    root = tmp_path / "cl-dsb"
    (root / "data_analysis").mkdir(parents=True)
    (root / "terminology" / "sdtm").mkdir(parents=True)
    (root / "data_analysis" / "ADaMIG_v1.3.csv").write_text(_ADAMIG)
    (root / "terminology" / "sdtm" / "SDTM_CT_2026-03-27.csv").write_text(_CT)
    return root


def test_resolve_folder_rejects_unset_missing_and_nondir(tmp_path):
    with pytest.raises(
        local_standards.LocalStandardsError, match="no standards folder"
    ):
        local_standards.resolve_folder(None)
    with pytest.raises(local_standards.LocalStandardsError, match="does not exist"):
        local_standards.resolve_folder(tmp_path / "nope")
    afile = tmp_path / "afile"
    afile.write_text("x")
    with pytest.raises(local_standards.LocalStandardsError, match="not a directory"):
        local_standards.resolve_folder(afile)


def test_list_files_groups_by_category_with_name_heuristics(folder):
    result = local_standards.list_files(folder)
    cats = {c["category"]: c["files"] for c in result["categories"]}
    assert set(cats) == {"data_analysis", "terminology/sdtm"}
    assert cats["data_analysis"][0]["path"] == "data_analysis/ADaMIG_v1.3.csv"
    assert cats["data_analysis"][0]["version"] == "v1.3"
    assert cats["terminology/sdtm"][0]["version"] == "2026-03-27"


def test_read_file_all_rows_and_filtered_and_paginated(folder):
    data = local_standards.read_file(folder, "data_analysis/ADaMIG_v1.3.csv")
    assert data["columns"][:3] == ["Version", "Data Structure Name", "Variable Name"]
    assert data["total_rows"] == 2 and data["rows"][1]["Variable Name"] == "TRTSDT"

    filtered = local_standards.read_file(
        folder, "data_analysis/ADaMIG_v1.3.csv", q="trtsdt"
    )
    assert (
        filtered["total_matched"] == 1
        and filtered["rows"][0]["Variable Name"] == "TRTSDT"
    )

    page = local_standards.read_file(
        folder, "terminology/sdtm/SDTM_CT_2026-03-27.csv", limit=1, offset=0
    )
    assert len(page["rows"]) == 1 and page["truncated"] is True
    page2 = local_standards.read_file(
        folder, "terminology/sdtm/SDTM_CT_2026-03-27.csv", limit=1, offset=1
    )
    assert (
        page2["rows"][0]["CDISC Submission Value"] == "MODERATE"
        and page2["truncated"] is False
    )


def test_read_file_path_traversal_blocked_and_missing(folder):
    with pytest.raises(local_standards.LocalStandardsError, match="escapes"):
        local_standards.read_file(folder, "../../etc/passwd")
    with pytest.raises(FileNotFoundError):
        local_standards.read_file(folder, "data_analysis/nope.csv")


def test_search_across_files_and_cap(folder):
    result = local_standards.search(folder, "severity")
    assert result["files_scanned"] == 2 and len(result["matches"]) == 2
    assert all(
        m["file"] == "terminology/sdtm/SDTM_CT_2026-03-27.csv"
        for m in result["matches"]
    )

    capped = local_standards.search(folder, "adamig", limit=1)
    assert len(capped["matches"]) == 1 and capped["truncated"] is True

    with pytest.raises(local_standards.LocalStandardsError, match="non-empty"):
        local_standards.search(folder, "   ")


def test_raw_path_returns_guarded_file(folder):
    p = local_standards.raw_path(folder, "data_analysis/ADaMIG_v1.3.csv")
    assert p.name == "ADaMIG_v1.3.csv"
    with pytest.raises(local_standards.LocalStandardsError):
        local_standards.raw_path(folder, "../x.csv")
