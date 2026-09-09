"""ItemGroupDef/Alias (maxOccurs="unbounded" in the schema) - used on a SUPPQUAL-shaped
domain to carry Context="DomainDescription", naming the parent domain the supplemental
qualifier dataset relates to. Confirmed real in the bundled SDTM submission: SUPPDM
carries <Alias Context="DomainDescription" Name="Demographics"/>, SUPPVS carries the
same for "Vital Signs". Modeled generically (Dataset.aliases: list[Alias]) rather than
assuming DomainDescription is the only Context a sponsor would ever use, since the
schema itself places no such restriction.
"""

from __future__ import annotations

from pathlib import Path

from lxml import etree
from ruamel.yaml import YAML

from defineyaml.models.common import Alias
from defineyaml.xml_emit import ODM_NS, write_define_xml
from defineyaml.xml_import import import_define_xml

_NS = {"odm": ODM_NS}


def test_dataset_aliases_defaults_to_empty_list():
    from defineyaml.models.dataset import Dataset

    ds = Dataset(
        name="XX", label="X", **{"class": "FINDINGS"}, structure="s", variables=[]
    )
    assert ds.aliases == []


def test_sdtm_fixture_imports_suppdm_alias(tmp_path):
    dest_tree = tmp_path / "tree"
    import_define_xml(Path("tests/fixtures/definexml/examples/sdtm.xml"), dest_tree)
    suppdm = YAML(typ="safe").load((dest_tree / "datasets" / "suppdm.yaml").read_text())
    assert suppdm["aliases"] == [
        {"context": "DomainDescription", "name": "Demographics"}
    ]

    suppvs = YAML(typ="safe").load((dest_tree / "datasets" / "suppvs.yaml").read_text())
    assert suppvs["aliases"] == [
        {"context": "DomainDescription", "name": "Vital Signs"}
    ]


def test_regular_dataset_has_no_aliases(tmp_path):
    dest_tree = tmp_path / "tree"
    import_define_xml(Path("tests/fixtures/definexml/examples/sdtm.xml"), dest_tree)
    dm = YAML(typ="safe").load((dest_tree / "datasets" / "dm.yaml").read_text())
    assert "aliases" not in dm


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

    suppdm_el = rebuilt.find(".//odm:ItemGroupDef[@Name='SUPPDM']", _NS)
    alias_el = suppdm_el.find("odm:Alias", _NS)
    assert alias_el is not None
    assert alias_el.get("Context") == "DomainDescription"
    assert alias_el.get("Name") == "Demographics"


def test_alias_model_requires_both_fields():
    Alias(context="DomainDescription", name="Demographics")
