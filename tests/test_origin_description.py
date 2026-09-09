"""def:Origin/Description for a non-Predecessor origin - Origin.source: is
Predecessor-only free text (a dataset.variable mnemonic, e.g. "DM.STUDYID");
every other origin type's Description is genuine descriptive prose with nowhere
to go, so it gets its own field, Origin.description:, rather than overloading
source: by type. Confirmed real on the bundled SDTM VS.VSSTRESC ItemDef:
Type="Derived" Source="Sponsor" with Description "EDC System".
"""

from __future__ import annotations

from pathlib import Path

import pytest
from lxml import etree
from pydantic import ValidationError
from ruamel.yaml import YAML

from defineyaml.linker import SymbolTable
from defineyaml.models.dataset import Origin
from defineyaml.xml_emit import DEF_NS, _origin
from defineyaml.xml_import import ReverseIndex, _import_origin
from defineyaml.xml_import import ImportContext

_NS = {"def": DEF_NS}


def test_predecessor_accepts_source_not_description():
    Origin(type="Predecessor", source="DM.STUDYID")
    with pytest.raises(ValidationError):
        Origin(type="Predecessor", description="not allowed here")


def test_non_predecessor_accepts_description_not_source():
    Origin(type="Derived", description="EDC System")
    with pytest.raises(ValidationError):
        Origin(type="Derived", source="not allowed here")


def _emit(origin: Origin) -> etree._Element:
    parent = etree.Element("parent")
    _origin(parent, origin, SymbolTable(), context="test")
    return parent.find(f"{{{DEF_NS}}}Origin")


def test_derived_description_emits_as_description_element():
    el = _emit(Origin(type="Derived", description="EDC System", data_source="Sponsor"))
    desc = el.find(".//{http://www.cdisc.org/ns/odm/v1.3}Description")
    assert desc is not None
    tt = desc.find("{http://www.cdisc.org/ns/odm/v1.3}TranslatedText")
    assert tt.text == "EDC System"


def test_predecessor_source_emits_as_description_element():
    el = _emit(Origin(type="Predecessor", source="DM.STUDYID"))
    desc = el.find(".//{http://www.cdisc.org/ns/odm/v1.3}Description")
    tt = desc.find("{http://www.cdisc.org/ns/odm/v1.3}TranslatedText")
    assert tt.text == "DM.STUDYID"


def test_import_non_predecessor_description(tmp_path):
    origin_el = etree.fromstring(
        f'<def:Origin xmlns:def="{DEF_NS}" xmlns:odm="http://www.cdisc.org/ns/odm/v1.3" '
        'Type="Collected" Source="Vendor">'
        '<odm:Description><odm:TranslatedText xml:lang="en">From Central lab</odm:TranslatedText></odm:Description>'
        "</def:Origin>"
    )
    ctx = ImportContext(force_lang_en=False)
    result = _import_origin(origin_el, ReverseIndex(), ctx, xpath="/test")
    assert result["description"] == "From Central lab"
    assert "source" not in result


def test_sdtm_fixture_captures_derived_origin_description(tmp_path):
    from defineyaml.xml_import import import_define_xml

    dest_tree = tmp_path / "tree"
    import_define_xml(Path("tests/fixtures/definexml/examples/sdtm.xml"), dest_tree)
    vs = YAML(typ="safe").load((dest_tree / "datasets" / "vs.yaml").read_text())
    vsstresc = next(v for v in vs["variables"] if v["name"] == "VSSTRESC")
    assert vsstresc["origin"]["type"] == "Derived"
    assert vsstresc["origin"]["description"] == "EDC System"
    assert "source" not in vsstresc["origin"]
