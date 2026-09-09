"""defineyaml.cdisc.standard_csv - mapping a CDISC standards CSV export into dataset/
variable and codelist shapes. Small synthetic CSVs in a tmp Standards folder.
"""

from __future__ import annotations

import pytest

from defineyaml.cdisc import standard_csv

_SDTMIG = (
    '"Version","Variable Order","Class","Dataset Name","Variable Name","Variable Label","Type",'
    '"CDISC CT Codelist Code(s)","Codelist Submission Values","Described Value Domain(s)","Value List","Role","CDISC Notes","Core"\n'
    '"SDTMIG v3.4","1","Events","AE","STUDYID","Study Identifier","Char","","",,"","Identifier","x","Req"\n'
    '"SDTMIG v3.4","2","Events","AE","AESEQ","Sequence Number","Num","","",,"","Identifier","x","Req"\n'
    '"SDTMIG v3.4","3","Events","AE","AESEV","Severity","Char","C66769","",,"","Record Qualifier","x","Perm"\n'
    '"SDTMIG v3.4","1","Findings","LB","LBTESTCD","Test Short Name","Char","","",,"","Topic","x","Req"\n'
)
_ADAMIG = (
    '"Version","Data Structure Name","Variable Set","Variable Name","Variable Label","Type",'
    '"CDISC CT Codelist Code(s)","CDISC CT Codelist Submission Value(s)","Described Value Domain(s)","Value List Value","Core","CDISC Notes"\n'
    '"ADaMIG v1.3","Basic Data Structure","Identifier","STUDYID","Study Identifier","Char","","","","","Req","x"\n'
    '"ADaMIG v1.3","Basic Data Structure","Timing","ADT","Analysis Date","Num","","","","","Perm","x"\n'
    '"ADaMIG v1.3","Subject-Level Analysis Dataset","Identifier","AGE","Age","Num","C66781","AGEU","","","Cond","x"\n'
)
_CT = (
    '"Code","Codelist Code","Codelist Extensible (Yes/No)","Codelist Name","CDISC Submission Value","CDISC Synonym(s)","CDISC Definition","NCI Preferred Term","Standard and Date"\n'
    '"C66769",,"No","Severity/Intensity Scale for Adverse Events","AESEV","","x","CDISC AE Severity Terminology","CT 2026"\n'
    '"C41338","C66769",,"Severity/Intensity Scale for Adverse Events","MILD","1; Grade 1","x","Mild Adverse Event","CT 2026"\n'
    '"C41339","C66769",,"Severity/Intensity Scale for Adverse Events","MODERATE","2; Grade 2","x","Moderate Adverse Event","CT 2026"\n'
    '"C66731",,"Yes","Sex","SEX","","x","CDISC Sex Terminology","CT 2026"\n'
    '"C20197","C66731",,"Sex","M","Male","x","Male","CT 2026"\n'
    '"C16576","C66731",,"Sex","F","Female","x","Female","CT 2026"\n'
    '"C55555",,"No","No Decode List","NODEC","","x","","CT 2026"\n'
    '"C1","C55555",,"No Decode List","A","","x","","CT 2026"\n'
    '"C2","C55555",,"No Decode List","B","","x","","CT 2026"\n'
)


@pytest.fixture()
def folder(tmp_path):
    root = tmp_path / "std"
    (root / "data_tabulation").mkdir(parents=True)
    (root / "data_analysis").mkdir(parents=True)
    (root / "terminology").mkdir(parents=True)
    (root / "data_tabulation" / "SDTMIG_v3.4.csv").write_text(_SDTMIG)
    (root / "data_analysis" / "ADaMIG_v1.3.csv").write_text(_ADAMIG)
    (root / "terminology" / "CT.csv").write_text(_CT)
    return root


def test_file_kind(folder):
    assert standard_csv.file_kind(folder, "data_tabulation/SDTMIG_v3.4.csv") == "ig"
    assert standard_csv.file_kind(folder, "data_analysis/ADaMIG_v1.3.csv") == "ig"
    assert standard_csv.file_kind(folder, "terminology/CT.csv") == "ct"


def test_list_units_sdtmig(folder):
    units = standard_csv.list_units(folder, "data_tabulation/SDTMIG_v3.4.csv")
    assert units == [
        {"unit": "AE", "variable_count": 3},
        {"unit": "LB", "variable_count": 1},
    ]


def test_unit_variables_sdtmig_types_and_mandatory(folder):
    vs = {
        v["name"]: v
        for v in standard_csv.unit_variables(
            folder, "data_tabulation/SDTMIG_v3.4.csv", "AE"
        )
    }
    assert vs["STUDYID"]["type"] == "text" and vs["STUDYID"]["mandatory"] is True
    assert vs["AESEQ"]["type"] == "integer"
    assert (
        vs["AESEV"]["mandatory"] is False and vs["AESEV"]["role"] == "Record Qualifier"
    )
    # "CDISC Notes" is surfaced as description (for the add-from-standards search).
    assert vs["AESEV"]["description"] == "x"
    # SDTMIG carries only the C-code, not the submission value.
    assert vs["AESEV"]["codelist_ccode"] == "C66769" and "codelist" not in vs["AESEV"]


def test_unit_variables_adamig_uses_submission_value_column(folder):
    vs = {
        v["name"]: v
        for v in standard_csv.unit_variables(
            folder, "data_analysis/ADaMIG_v1.3.csv", "Subject-Level Analysis Dataset"
        )
    }
    assert vs["AGE"]["codelist"] == "ageu"


def test_unit_class(folder):
    assert (
        standard_csv.unit_class(folder, "data_tabulation/SDTMIG_v3.4.csv", "AE")
        == "Events"
    )
    # ADaM has no Class column - the structure name is the class.
    assert (
        standard_csv.unit_class(
            folder, "data_analysis/ADaMIG_v1.3.csv", "Basic Data Structure"
        )
        == "BASIC DATA STRUCTURE"
    )


def test_list_codelists_and_search(folder):
    all_cl = standard_csv.list_codelists(folder, "terminology/CT.csv")
    assert {c["value"] for c in all_cl} == {"AESEV", "SEX", "NODEC"}
    sev = standard_csv.list_codelists(folder, "terminology/CT.csv", "sev")
    assert [c["value"] for c in sev] == ["AESEV"]


def test_codelist_detail_decode_from_preferred_term(folder):
    d = standard_csv.codelist_detail(folder, "terminology/CT.csv", "AESEV")
    assert d["name"] == "AESEV" and d["nci_code"] == "C66769" and "extended" not in d
    assert {t["code"]: t["decode"] for t in d["terms"]} == {
        "MILD": "Mild Adverse Event",
        "MODERATE": "Moderate Adverse Event",
    }


def test_codelist_detail_extensible_flag(folder):
    assert (
        standard_csv.codelist_detail(folder, "terminology/CT.csv", "SEX")["extended"]
        is True
    )


def test_codelist_detail_codes_subset(folder):
    d = standard_csv.codelist_detail(folder, "terminology/CT.csv", "SEX", codes=["F"])
    assert [t["code"] for t in d["terms"]] == ["F"]
    assert d["nci_code"] == "C66731"  # keeps the parent codelist's C-code
    # CodedValue is case-sensitive - "f" is not the CT term "F".
    with pytest.raises(standard_csv.StandardCsvError, match="none of the requested"):
        standard_csv.codelist_detail(folder, "terminology/CT.csv", "SEX", codes=["f"])


def test_codelist_detail_drops_decode_when_not_uniform(folder):
    d = standard_csv.codelist_detail(folder, "terminology/CT.csv", "NODEC")
    assert all("decode" not in t for t in d["terms"])
    assert [t["code"] for t in d["terms"]] == ["A", "B"]


def test_ct_ccode_index(folder):
    idx = standard_csv.ct_ccode_index(folder, "terminology/CT.csv")
    assert idx["C66769"] == "AESEV" and idx["C66731"] == "SEX"
