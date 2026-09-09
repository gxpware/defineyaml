"""webui.standard_scaffold - "new dataset / codelists from a standard's local CSV".
Run against a scratch copy of the tests/fixtures/define tree plus the trimmed CDISC
CSV exports under tests/fixtures/cl-dsb (real headers and rows for the SDTM DM/AE
domains, the ADaMIG BDS/ADSL structures, and a handful of CT codelists - enough to
exercise the SDTMIG / CT column handling on real data without vendoring the full
~50k-row exports).
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from defineyaml.webui import standard_scaffold as ss
from defineyaml.webui import tree

FIXTURES = Path(__file__).parent / "fixtures"
DEFINE_TREE = FIXTURES / "define"
CL_DSB = FIXTURES / "cl-dsb"

# Committed fixtures - the guard only trips if one is deleted, degrading to a skip
# rather than a collection error.
pytestmark = pytest.mark.skipif(
    not CL_DSB.is_dir(), reason="tests/fixtures/cl-dsb not present"
)


@pytest.fixture()
def scratch(tmp_path):
    dest = tmp_path / "define"
    shutil.copytree(DEFINE_TREE, dest)
    # Start these tests from empty datasets/ and codelists/ so the fixture tree's own
    # objects can't collide with the ones the tests create.
    for sub in ("datasets", "codelists"):
        for f in (dest / sub).glob("*.yaml"):
            f.unlink()
    tree.save_object(
        dest,
        "standards",
        "standards",
        {
            "standards_folder": str(CL_DSB),
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
                {
                    "name": "ADaMIG",
                    "type": "IG",
                    "version": "1.3",
                    "standards_file": "data_analysis/ADaMIG_v1.3.csv",
                },
            ],
        },
    )
    return dest


def test_folder_resolution_relative_and_absolute(tmp_path):
    dest = tmp_path / "define"
    shutil.copytree(DEFINE_TREE, dest)
    # Relative paths resolve against the define/ tree root.
    (dest / "csvs").mkdir()
    tree.save_object(
        dest, "standards", "standards", {"standards_folder": "csvs", "standards": []}
    )
    assert ss.resolve_folder(dest) == (dest / "csvs").resolve()
    # Absolute passes straight through.
    tree.save_object(
        dest,
        "standards",
        "standards",
        {"standards_folder": str(CL_DSB), "standards": []},
    )
    assert ss.resolve_folder(dest) == CL_DSB.resolve()
    # Unset -> error.
    tree.save_object(dest, "standards", "standards", {"standards": []})
    with pytest.raises(ss.local_standards.LocalStandardsError):
        ss.resolve_folder(dest)


def _tree_with_folder(tmp_path, folder_value):
    dest = tmp_path / "define"
    shutil.copytree(DEFINE_TREE, dest)
    tree.save_object(
        dest,
        "standards",
        "standards",
        {"standards_folder": str(folder_value), "standards": []},
    )
    return dest


def test_folder_status_flags_a_missing_folder_as_creatable(tmp_path):
    missing = tmp_path / "csv-exports"
    dest = _tree_with_folder(tmp_path, missing)
    st = ss.folder_status(dest)
    assert st == {
        "folder": str(missing),
        "resolved": None,
        "exists": False,
        "creatable": True,
        "error": f"standards folder does not exist: {missing}",
    }


def test_create_folder_makes_the_missing_folder_including_parents(tmp_path):
    missing = tmp_path / "a" / "b" / "csvs"  # no parents on disk either
    dest = _tree_with_folder(tmp_path, missing)
    st = ss.create_folder(dest)
    assert missing.is_dir()
    assert st["exists"] is True and st["creatable"] is False
    assert st["resolved"] == str(missing.resolve())


def test_create_folder_resolves_a_relative_path_against_the_tree(tmp_path):
    dest = _tree_with_folder(tmp_path, "my-csvs")
    ss.create_folder(dest)
    assert (dest / "my-csvs").is_dir()


def test_create_folder_is_a_no_op_when_the_folder_already_exists(tmp_path):
    existing = tmp_path / "here"
    existing.mkdir()
    dest = _tree_with_folder(tmp_path, existing)
    assert ss.folder_status(dest)["creatable"] is False
    assert ss.create_folder(dest)["exists"] is True


def test_create_folder_errors_when_a_file_sits_at_the_path(tmp_path):
    clash = tmp_path / "not-a-folder"
    clash.write_text("x")
    dest = _tree_with_folder(tmp_path, clash)
    assert ss.folder_status(dest)["creatable"] is False
    with pytest.raises(ss.local_standards.LocalStandardsError, match="already exists"):
        ss.create_folder(dest)


def test_create_folder_errors_when_no_folder_is_set(tmp_path):
    dest = tmp_path / "define"
    shutil.copytree(DEFINE_TREE, dest)
    tree.save_object(dest, "standards", "standards", {"standards": []})
    with pytest.raises(ss.local_standards.LocalStandardsError):
        ss.create_folder(dest)


def test_standards_with_files_reports_kind(scratch):
    kinds = {s["name"]: s["kind"] for s in ss.standards_with_files(scratch)}
    assert kinds == {"SDTMIG": "ig", "SDTMCT": "ct", "ADaMIG": "ig"}


def test_units_and_missing_standards_file(scratch):
    units = ss.standard_units(scratch, "SDTMIG")["units"]
    assert any(u["unit"] == "DM" for u in units)
    with pytest.raises(tree.NotFoundError):
        ss.standard_units(scratch, "NOPE")


def test_create_dataset_from_sdtmig(scratch):
    res = ss.create_dataset(scratch, "SDTMIG", "DM", "DM", None)
    assert res["key"].startswith("dm")  # "dm", or "dm-2" if the copied tree has a dm
    ds = tree.read_object(scratch, "datasets", res["key"])
    assert ds["class"] and ds["purpose"] == "Tabulation" and ds["domain"] == "DM"
    assert ds["standard"] == "SDTMIG"
    names = [v["name"] for v in ds["variables"]]
    assert "USUBJID" in names and "AGEU" in names
    # SDTMIG carries only the codelist C-code; scaffold resolves it to a submission-value
    # ref against the attached CT file (AGEU variable -> AGEU codelist).
    ageu = next(v for v in ds["variables"] if v["name"] == "AGEU")
    assert ageu.get("codelist") == "ageu"


def test_create_dataset_from_adam_structure(scratch):
    res = ss.create_dataset(scratch, "ADaMIG", "Basic Data Structure", "ADVS", None)
    ds = tree.read_object(scratch, "datasets", res["key"])
    assert ds["class"] == "BASIC DATA STRUCTURE" and ds["purpose"] == "Analysis"
    assert "PARAMCD" in [v["name"] for v in ds["variables"]]


def test_create_dataset_unique_key(scratch):
    ss.create_dataset(scratch, "SDTMIG", "AE", "AE", None)
    second = ss.create_dataset(scratch, "SDTMIG", "AE", "AE", None)
    assert second["key"] == "ae-2"


def test_create_codelists_skips_existing(scratch):
    existing = {i["key"] for i in tree.list_items(scratch, "codelists")}
    r = ss.create_codelists(scratch, "SDTMCT", ["SEX", "AESEV"])
    assert "sex" in r["created"] or any(s["value"] == "SEX" for s in r["skipped"])
    sex = tree.read_object(scratch, "codelists", "sex")
    assert sex["name"] == "SEX" and {t["code"] for t in sex["terms"]} >= {"M", "F"}
    # Re-running skips it.
    again = ss.create_codelists(scratch, "SDTMCT", ["SEX"])
    assert again["created"] == [] and again["skipped"][0]["reason"].startswith(
        "a codelist"
    )
    _ = existing


def test_ct_codelist_terms(scratch):
    d = ss.ct_codelist_terms(scratch, "SDTMCT", "NY")
    codes = {t["code"] for t in d["terms"]}
    assert {"Y", "N"} <= codes and "nci_code" in d


def test_create_codelists_rename_and_subset(scratch):
    r = ss.create_codelists(
        scratch, "SDTMCT", [{"value": "NY", "name": "SAFETY_YN", "codes": ["Y"]}]
    )
    assert r["created"] == ["safety_yn"] and not r["skipped"]
    cl = tree.read_object(scratch, "codelists", "safety_yn")
    assert cl["name"] == "SAFETY_YN"  # renamed
    assert [t["code"] for t in cl["terms"]] == ["Y"]  # subset
    assert cl["nci_code"]  # still points at the parent CT codelist

    # plain-string items still work (used by create_missing_codelists) - the scratch tree
    # is a copy of define/, which may already carry an AGEU codelist, so accept either.
    plain = ss.create_codelists(scratch, "SDTMCT", ["AGEU"])
    assert (
        plain["created"] == ["ageu"]
        or "already exists" in plain["skipped"][0]["reason"]
    )

    # a subset with no matching codes is skipped, not fatal
    bad = ss.create_codelists(
        scratch, "SDTMCT", [{"value": "SEX", "name": "SX", "codes": ["ZZZ"]}]
    )
    assert bad["created"] == [] and bad["skipped"][0]["value"] == "SEX"


def test_codelist_reference_matches_by_ccode_then_name(scratch):
    # By C-code.
    ref = ss.codelist_reference(scratch, None, "C66731")
    assert ref["found"] and ref["value"] == "SEX" and ref["standard"] == "SDTMCT"
    assert {t["code"] for t in ref["terms"]} >= {"M", "F"}
    assert all("nci_code" in t for t in ref["terms"])
    # By submission value when no C-code given.
    ref2 = ss.codelist_reference(scratch, "AGEU", None)
    assert ref2["found"] and ref2["value"] == "AGEU"
    # Nothing attached provides it.
    assert ss.codelist_reference(scratch, "MADE_UP_LIST", "C99999")["found"] is False


def test_external_dictionary_names_from_attached_ct(scratch):
    res = ss.external_dictionary_names(scratch)
    assert res["names"], "expected some dictionary names"
    # An attached CT CSV with C66788 wins; otherwise the built-in fallback is used.
    if res["source"]:
        assert "MedDRA" in res["names"]
    else:
        assert res["names"] == ss._DICTIONARY_NAME_FALLBACK


def test_ig_catalog_and_search(scratch):
    cat = ss.ig_catalog(scratch)
    names = {s["name"] for s in cat["standards"]}
    assert {"SDTMIG", "ADaMIG"} <= names
    assert any(
        u["unit"] == "DM"
        for s in cat["standards"]
        if s["name"] == "SDTMIG"
        for u in s["units"]
    )

    # narrowed by standard + unit + query, codelist C-codes resolved to names
    res = ss.search_ig_variables(scratch, ["SDTMIG"], ["DM"], "age", 800)
    by_name = {v["name"]: v for v in res["variables"]}
    assert "AGE" in by_name and "AGEU" in by_name
    assert by_name["AGEU"]["codelist"] == "ageu"
    assert by_name["AGE"]["standard"] == "SDTMIG" and by_name["AGE"]["unit"] == "DM"
    assert "description" in by_name["AGE"]

    # limit + truncation
    small = ss.search_ig_variables(scratch, ["SDTMIG"], None, None, 5)
    assert len(small["variables"]) == 5 and small["truncated"] is True


def test_dataset_standard_hints_matches_and_suggests(scratch):
    ss.create_dataset(scratch, "SDTMIG", "DM", "DM", None)
    hints = ss.dataset_standard_hints(scratch, "dm")
    assert {"standard": "SDTMIG", "unit": "DM"} in hints["matched"]
    assert hints["variables"]["AGEU"]["codelist"] == ["ageu"]
    assert hints["variables"]["AGE"]["role"]  # SDTM Role column populated
    src = hints["variables"]["AGEU"]["sources"][0]
    assert (
        src["standard"] == "SDTMIG"
        and src["codelist"] == "ageu"
        and src["template"] is False
    )

    # ADaM dataset matches on class (the structure name)
    ss.create_dataset(scratch, "ADaMIG", "Basic Data Structure", "ADVS", None)
    adam = ss.dataset_standard_hints(scratch, "advs")
    assert adam["matched"] == [{"standard": "ADaMIG", "unit": "Basic Data Structure"}]


def test_dataset_standard_hints_resolves_adam_templated_names(scratch):
    tree.save_object(
        scratch,
        "datasets",
        "adsl",
        {
            "name": "ADSL",
            "label": "",
            "class": "SUBJECT LEVEL ANALYSIS DATASET",
            "structure": "",
            "purpose": "Analysis",
            "variables": [
                {"name": "RACE", "label": "Race", "type": "text", "mandatory": False},
                {"name": "TR01SDTF", "label": "x", "type": "text", "mandatory": False},
            ],
        },
    )
    h = ss.dataset_standard_hints(scratch, "adsl")
    assert h["variables"]["RACE"]["codelist"] == ["race"]
    # TR01SDTF resolves against the standard's TRxxSDTF template (a date-flag codelist)
    tr = h["variables"]["TR01SDTF"]
    assert tr["codelist"] == ["datefl"]
    assert (
        tr["sources"][0]["template"] is True and "x" in tr["sources"][0]["name"].lower()
    )


def test_template_regex():
    assert ss._template_regex("STUDYID") is None
    assert ss._template_regex("TRTxxPN").match("TRT01PN")
    assert ss._template_regex("SITEGRy").match("SITEGR3")
    assert not ss._template_regex("SITEGRy").match("SITEGR")
    # 2-letter runs (xx/yy/zz) are exactly two digits, single letters (y/z/w) are 1+
    assert ss._template_regex("PARMCDzz").match("PARMCD07")
    assert not ss._template_regex("PARMCDzz").match("PARMCD7")
    assert ss._template_regex("APHASEw").match("APHASE1")
    assert ss._template_regex("PxxSwEDT").match("P01S2EDT")


def test_missing_referenced_codelists_and_create(scratch):
    ss.create_dataset(scratch, "SDTMIG", "DM", "DM", None)
    missing = ss.missing_referenced_codelists(scratch)["missing"]
    resolvable = [m for m in missing if m["standard"] == "SDTMCT"]
    assert resolvable, missing
    created = ss.create_missing_codelists(scratch)["created"]
    assert created
    still_missing = ss.missing_referenced_codelists(scratch)["missing"]
    assert not [m for m in still_missing if m["standard"] == "SDTMCT"]
