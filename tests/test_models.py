from pathlib import Path

import pytest
from pydantic import ValidationError

from defineyaml.io.yaml_io import dump, load
from defineyaml.models import (
    AnalysisDataset,
    CommentDef,
    Dataset,
    DocumentsFile,
    EnumeratedCodeList,
    ExternalCodeListDef,
    MethodDef,
    RefByOid,
    ResultDisplay,
    StandardsFile,
    StudyFile,
    ValueListDef,
    Variable,
    WhereClauseDef,
    parse_codelist,
)

ROOT = Path(__file__).resolve().parent / "fixtures" / "define"


def test_study_file_loads():
    StudyFile.model_validate(load(ROOT / "study.yaml"))


def test_standards_file_loads():
    StandardsFile.model_validate(load(ROOT / "standards.yaml"))


def test_documents_file_loads():
    DocumentsFile.model_validate(load(ROOT / "documents.yaml"))


def test_adsl_dataset_loads():
    Dataset.model_validate(load(ROOT / "datasets" / "adsl.yaml"))


def test_race_codelist_is_enumerated():
    cl = parse_codelist(load(ROOT / "codelists" / "racec.yaml"))
    assert isinstance(cl, EnumeratedCodeList)
    assert "WHITE" in {t.code for t in cl.terms}


def test_enumerated_codelist_rejects_duplicate_term_codes():
    data = {
        "name": "DUP",
        "label": "Dup",
        "terms": [
            {"code": "Y", "decode": "Yes"},
            {"code": "Y", "decode": "Yes again"},
        ],
    }
    with pytest.raises(ValidationError, match="duplicate code"):
        EnumeratedCodeList.model_validate(data)


def test_enumerated_codelist_term_codes_are_case_sensitive():
    # CodedValue is case-sensitive per ODM - "PA" and "Pa" are different terms.
    cl = EnumeratedCodeList.model_validate(
        {
            "name": "CASE",
            "label": "Case",
            "terms": [
                {"code": "PA", "decode": "Physician Assistant"},
                {"code": "Pa", "decode": "Pascal"},
            ],
        }
    )
    assert [t.code for t in cl.terms] == ["PA", "Pa"]


def test_enumerated_codelist_accepts_all_distinct_ranks():
    cl = EnumeratedCodeList.model_validate(
        {
            "name": "SEV",
            "label": "Severity",
            "terms": [
                {"code": "MILD", "decode": "Mild", "rank": 1},
                {"code": "MOD", "decode": "Moderate", "rank": 2},
                {"code": "SEV", "decode": "Severe", "rank": 3},
            ],
        }
    )
    assert [t.rank for t in cl.terms] == [1, 2, 3]


def test_enumerated_codelist_rejects_partial_ranks():
    data = {
        "name": "P",
        "label": "P",
        "terms": [
            {"code": "A", "decode": "A", "rank": 1},
            {"code": "B", "decode": "B"},
        ],
    }
    with pytest.raises(ValidationError, match="every term or none"):
        EnumeratedCodeList.model_validate(data)


def test_enumerated_codelist_rejects_duplicate_ranks():
    data = {
        "name": "D",
        "label": "D",
        "terms": [
            {"code": "A", "decode": "A", "rank": 1},
            {"code": "B", "decode": "B", "rank": 1},
        ],
    }
    with pytest.raises(ValidationError, match="distinct"):
        EnumeratedCodeList.model_validate(data)


def test_meddra_codelist_is_external():
    cl = parse_codelist(load(ROOT / "codelists" / "meddra.yaml"))
    assert isinstance(cl, ExternalCodeListDef)


def test_external_codelist_rejects_terms():
    data = load(ROOT / "codelists" / "meddra.yaml")
    data["terms"] = []
    with pytest.raises(ValidationError):
        ExternalCodeListDef.model_validate(data)


def test_trtsdt_method_loads():
    MethodDef.model_validate(load(ROOT / "methods" / "adsl" / "trtsdt.yaml"))


def test_method_expressions_require_description():
    with pytest.raises(ValidationError):
        MethodDef.model_validate(
            {"name": "X", "expressions": [{"context": "SAS 9.4", "code": "x = 1;"}]}
        )


def test_method_accepts_document_refs_with_page_refs():
    md = MethodDef.model_validate(
        {
            "name": "Age",
            "description": "see ADRG",
            "documents": [
                {"ref": "adrg", "pages": [3], "title": "Section 4.1"},
                {"ref": "adrg", "pages": {"first": 10, "last": 12}},
            ],
        }
    )
    assert [d.ref for d in md.documents] == ["adrg", "adrg"]
    assert md.documents[0].pages == [3]
    assert md.documents[1].pages.first == 10


def test_usubjid_comment_loads():
    CommentDef.model_validate(load(ROOT / "comments" / "adsl__usubjid.yaml"))


def test_aval_valuelist_loads():
    ValueListDef.model_validate(load(ROOT / "valuelists" / "adlb__aval.yaml"))


def test_alt_week4_whereclause_loads():
    WhereClauseDef.model_validate(load(ROOT / "whereclauses" / "alt-week4.yaml"))


def test_whereclause_rejects_multi_value_eq():
    with pytest.raises(ValidationError):
        WhereClauseDef.model_validate(
            {
                "conditions": [
                    {
                        "variable": "ADLB.PARAMCD",
                        "comparator": "EQ",
                        "values": ["ALT", "AST"],
                    }
                ]
            }
        )


def test_t14_2_1_result_display_loads():
    ResultDisplay.model_validate(load(ROOT / "analysis-results" / "t14-2-1.yaml"))


def test_round_trip_preserves_comments(tmp_path):
    src = ROOT / "datasets" / "adsl.yaml"
    data = load(src)
    out = tmp_path / "adsl.yaml"
    dump(data, out)
    assert "CT extended per protocol" in out.read_text()


def test_dump_quotes_code_position_scalars(tmp_path):
    data = load(ROOT / "codelists" / "racec.yaml")
    out = tmp_path / "racec.yaml"
    dump(data, out)
    text = out.read_text()
    assert 'code: "WHITE"' in text
    assert 'nci_code: "C41261"' in text


def test_variable_reference_fields_accept_plain_name():
    var = Variable.model_validate(
        {
            "name": "RACE",
            "label": "Race",
            "type": "text",
            "codelist": "race",
            "method": "adsl/trtsdt",
        }
    )
    assert var.codelist == "race"
    assert var.method == "adsl/trtsdt"


def test_variable_reference_fields_accept_literal_oid():
    var = Variable.model_validate(
        {
            "name": "RACE",
            "label": "Race",
            "type": "text",
            "codelist": {"oid": "CL.RACE_LEGACY"},
            "same_as": {"oid": "IT.ADSL.RACE"},
        }
    )
    assert isinstance(var.codelist, RefByOid)
    assert var.codelist.oid == "CL.RACE_LEGACY"
    assert isinstance(var.same_as, RefByOid)
    assert var.same_as.oid == "IT.ADSL.RACE"


def test_dataset_standard_accepts_literal_oid():
    data = load(ROOT / "datasets" / "adsl.yaml")
    data["standard"] = {"oid": "STD.LEGACY"}
    dataset = Dataset.model_validate(data)
    assert isinstance(dataset.standard, RefByOid)
    assert dataset.standard.oid == "STD.LEGACY"


def test_rangecheck_variable_accepts_literal_oid():
    wc = WhereClauseDef.model_validate(
        {
            "conditions": [
                {
                    "variable": {"oid": "IT.ADLB.PARAMCD"},
                    "comparator": "EQ",
                    "values": ["ALT"],
                }
            ]
        }
    )
    assert isinstance(wc.conditions[0].variable, RefByOid)
    assert wc.conditions[0].variable.oid == "IT.ADLB.PARAMCD"


def test_analysis_dataset_variables_accept_mixed_name_and_oid_refs():
    ds = AnalysisDataset.model_validate(
        {"dataset": "ADLB", "variables": ["AVAL", {"oid": "IT.ADLB.BASE"}]}
    )
    assert ds.variables[0] == "AVAL"
    assert isinstance(ds.variables[1], RefByOid)
    assert ds.variables[1].oid == "IT.ADLB.BASE"


def test_ref_reference_fields_still_reject_unknown_keys():
    with pytest.raises(ValidationError):
        Variable.model_validate(
            {
                "name": "RACE",
                "label": "Race",
                "type": "text",
                "codelist": {"oid": "CL.RACE", "name": "race"},
            }
        )
