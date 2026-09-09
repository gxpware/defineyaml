"""def:ExtendedValue on CodeListItem/EnumeratedItem - a per-term extensibility flag
distinct from the codelist-wide def:IsNonStandard (Term.extended: here vs
EnumeratedCodeList.extended:). Confirmed real in the bundled SDTM example: the
LBRESU unit codelist carries two sponsor-added units ("X10^9/L", "pg/mL") each
ExtendedValue="Yes", while the codelist itself has no def:IsNonStandard at all -
proving the two flags are genuinely independent, not one derived from the other.
"""

from __future__ import annotations

from pathlib import Path

from lxml import etree
from ruamel.yaml import YAML

from defineyaml.models.codelist import Term
from defineyaml.xml_emit import DEF_NS, ODM_NS, write_define_xml
from defineyaml.xml_import import import_define_xml

_NS = {"odm": ODM_NS, "def": DEF_NS}


def test_term_extended_defaults_to_false():
    term = Term(code="X", decode="X")
    assert term.extended is False


def test_sdtm_fixture_imports_extended_value_on_terms(tmp_path):
    dest_tree = tmp_path / "tree"
    import_define_xml(Path("tests/fixtures/definexml/examples/sdtm.xml"), dest_tree)
    lbresu = YAML(typ="safe").load(
        (dest_tree / "codelists" / "unit (lbresu).yaml").read_text()
    )
    by_code = {t["code"]: t for t in lbresu["terms"]}
    assert by_code["X10^9/L"]["extended"] is True
    assert by_code["pg/mL"]["extended"] is True
    assert "extended" not in by_code["%"]
    # The codelist itself is not flagged non-standard, despite carrying extended terms -
    # the two flags are independent.
    assert "extended" not in lbresu or lbresu["extended"] is False


def test_extended_value_roundtrips_through_emit(tmp_path):
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

    lbresu_el = rebuilt.find(".//odm:CodeList[@Name='Unit (LBRESU)']", _NS)
    extended_items = [
        item
        for item in lbresu_el.findall("odm:CodeListItem", _NS)
        if item.get(f"{{{DEF_NS}}}ExtendedValue") == "Yes"
    ]
    assert {item.get("CodedValue") for item in extended_items} == {"X10^9/L", "pg/mL"}
    assert lbresu_el.get(f"{{{DEF_NS}}}IsNonStandard") is None
