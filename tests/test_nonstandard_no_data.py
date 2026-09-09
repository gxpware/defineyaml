"""def:IsNonStandard / def:HasNoData on ItemGroupDef and ItemRef - a sponsor-defined
domain/variable (IsNonStandard) or one legitimately submitted with zero records
(HasNoData). Confirmed real in the bundled SDTM example: XS/XX are non-standard
findings domains, SUPPVS/SUPPDM and XS.XSORRESU/XS.XSSTRESU carry HasNoData. Both
attributes are odm:YesOnly (present-with-"Yes" or absent - no "No" value exists),
so they're modeled as plain bool = False, only emitted when true.
"""

from __future__ import annotations

from pathlib import Path

from lxml import etree
from ruamel.yaml import YAML

from defineyaml.models.dataset import Dataset, Variable
from defineyaml.xml_emit import DEF_NS, ODM_NS, write_define_xml
from defineyaml.xml_import import import_define_xml

_NS = {"odm": ODM_NS, "def": DEF_NS}


def test_dataset_and_variable_default_to_false():
    ds = Dataset(
        name="XX", label="X", **{"class": "FINDINGS"}, structure="s", variables=[]
    )
    assert ds.is_non_standard is False
    assert ds.has_no_data is False
    var = Variable(name="V", label="V", type="text")
    assert var.is_non_standard is False
    assert var.has_no_data is False


def test_sdtm_fixture_imports_itemgroupdef_flags(tmp_path):
    dest_tree = tmp_path / "tree"
    import_define_xml(Path("tests/fixtures/definexml/examples/sdtm.xml"), dest_tree)
    xs = YAML(typ="safe").load((dest_tree / "datasets" / "xs.yaml").read_text())
    assert xs["is_non_standard"] is True
    assert "has_no_data" not in xs

    xx = YAML(typ="safe").load((dest_tree / "datasets" / "xx.yaml").read_text())
    assert xx["is_non_standard"] is True
    assert xx["has_no_data"] is True


def test_sdtm_fixture_imports_itemref_has_no_data(tmp_path):
    dest_tree = tmp_path / "tree"
    import_define_xml(Path("tests/fixtures/definexml/examples/sdtm.xml"), dest_tree)
    xs = YAML(typ="safe").load((dest_tree / "datasets" / "xs.yaml").read_text())
    by_name = {v["name"]: v for v in xs["variables"]}
    assert by_name["XSORRESU"]["has_no_data"] is True
    assert by_name["XSSTRESU"]["has_no_data"] is True
    assert "has_no_data" not in by_name["XSORRES"]


def test_flags_roundtrip_through_emit(tmp_path):
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

    xx_el = rebuilt.find(".//odm:ItemGroupDef[@Name='XX']", _NS)
    assert xx_el.get(f"{{{DEF_NS}}}IsNonStandard") == "Yes"
    assert xx_el.get(f"{{{DEF_NS}}}HasNoData") == "Yes"

    xs_el = rebuilt.find(".//odm:ItemGroupDef[@Name='XS']", _NS)
    orresu_ref = xs_el.find(".//odm:ItemRef[@ItemOID='IT.XS.XSORRESU']", _NS)
    assert orresu_ref.get(f"{{{DEF_NS}}}HasNoData") == "Yes"
    orres_ref = xs_el.find(".//odm:ItemRef[@ItemOID='IT.XS.XSORRES']", _NS)
    assert orres_ref.get(f"{{{DEF_NS}}}HasNoData") is None
