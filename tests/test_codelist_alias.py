"""A CodeList, or one of its terms, can carry a sponsor-defined Alias (any Context
other than "nci:ExtCodeID", which stays modeled via nci_code:) - maxOccurs="unbounded"
at both CodeList and CodeListItem/EnumeratedItem level in the schema, each with its own
uniqueness-on-Context constraint (a codelist or term can't repeat the same Context
twice, but nci:ExtCodeID and a sponsor context coexist freely). Confirmed real on the
bundled SDTM submission: CL.XSTEST's EnumeratedItems each carry a single
Context="Sponsor" alias, and the codelist itself carries one too.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from lxml import etree
from pydantic import ValidationError
from ruamel.yaml import YAML

from defineyaml.models.codelist import EnumeratedCodeList, Term
from defineyaml.xml_emit import ODM_NS, write_define_xml
from defineyaml.xml_import import import_define_xml

_NS = {"odm": ODM_NS}


def test_term_and_codelist_aliases_default_to_empty():
    term = Term(code="X", decode="X")
    assert term.aliases == []
    cl = EnumeratedCodeList(name="X", label="X", terms=[term])
    assert cl.aliases == []


def test_nci_context_rejected_in_aliases_on_term():
    with pytest.raises(ValidationError):
        Term(code="X", decode="X", aliases=[{"context": "nci:ExtCodeID", "name": "C1"}])


def test_nci_context_rejected_in_aliases_on_codelist():
    with pytest.raises(ValidationError):
        EnumeratedCodeList(
            name="X",
            label="X",
            terms=[Term(code="X", decode="X")],
            aliases=[{"context": "nci:ExtCodeID", "name": "C1"}],
        )


def test_sdtm_fixture_imports_term_and_codelist_sponsor_aliases(tmp_path):
    dest_tree = tmp_path / "tree"
    import_define_xml(Path("tests/fixtures/definexml/examples/sdtm.xml"), dest_tree)
    xstest = YAML(typ="safe").load(
        (dest_tree / "codelists" / "s findings test name.yaml").read_text()
    )
    by_code = {t["code"]: t for t in xstest["terms"]}
    assert by_code["Test 1"]["aliases"] == [{"context": "Sponsor", "name": "X12346001"}]
    assert xstest["aliases"] == [{"context": "Sponsor", "name": "XY12346"}]


def test_nci_and_sponsor_alias_both_survive_on_same_codelist(tmp_path):
    dest_tree = tmp_path / "tree"
    import_define_xml(Path("tests/fixtures/definexml/examples/sdtm.xml"), dest_tree)
    xsresu = YAML(typ="safe").load(
        (dest_tree / "codelists" / "units for s findings results.yaml").read_text()
    )
    by_code = {t["code"]: t for t in xsresu["terms"]}
    assert by_code["g/dL"]["nci_code"] == "C64783"
    assert "aliases" not in by_code["g/dL"]
    assert xsresu["aliases"] == [{"context": "Sponsor", "name": "XY12345"}]


def test_alias_roundtrips_through_emit(tmp_path):
    import re

    dest_tree = tmp_path / "tree"
    import_define_xml(Path("tests/fixtures/definexml/examples/sdtm.xml"), dest_tree)
    # methods/bmisn.yaml: a source data-quality issue in the CDISC fixture itself, not a
    # bug here - see test_roundtrip.py's _patch_known_source_data_issues for the full story.
    bmisn = dest_tree / "methods" / "bmisn.yaml"
    patched, count = re.subn(
        r"(- context: ')", r"\1(variant 2) ", bmisn.read_text(), count=1
    )
    assert count == 1
    bmisn.write_text(patched)
    rebuilt_xml = tmp_path / "define.xml"
    write_define_xml(dest_tree, rebuilt_xml)
    rebuilt = etree.parse(str(rebuilt_xml))

    xstest_el = rebuilt.find(".//odm:CodeList[@Name='S Findings Test Name']", _NS)
    item_el = xstest_el.find("odm:EnumeratedItem[@CodedValue='Test 1']", _NS)
    alias_el = item_el.find("odm:Alias", _NS)
    assert alias_el.get("Context") == "Sponsor"
    assert alias_el.get("Name") == "X12346001"
    cl_alias_el = xstest_el.find("odm:Alias", _NS)
    assert cl_alias_el.get("Context") == "Sponsor"
    assert cl_alias_el.get("Name") == "XY12346"
