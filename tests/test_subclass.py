"""def:SubClass under def:Class (ADaM's two-level classification, e.g.
"OCCURRENCE DATA STRUCTURE" > "ADVERSE EVENT") - confirmed real in the bundled ADaM
example (adam.xml's ADAE: <def:Class Name="OCCURRENCE DATA STRUCTURE">
<def:SubClass Name="ADVERSE EVENT"/></def:Class>). ItemGroupSubClass is a closed
2-value XSD enumeration, unlike the AnalysisReason/Purpose unions elsewhere in the
model, so SubClass.name is Literal-enforced rather than left as free text.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from lxml import etree
from pydantic import ValidationError

from defineyaml.models.dataset import SubClass


def test_subclass_accepts_only_the_two_defined_values():
    SubClass(name="ADVERSE EVENT")
    SubClass(name="TIME-TO-EVENT")
    with pytest.raises(ValidationError):
        SubClass(name="NOT A REAL SUBCLASS")


def test_subclass_parent_class_is_optional():
    sub = SubClass(name="ADVERSE EVENT")
    assert sub.parent_class is None
    sub = SubClass(name="ADVERSE EVENT", parent_class="OCCURRENCE DATA STRUCTURE")
    assert sub.parent_class == "OCCURRENCE DATA STRUCTURE"


def test_adae_fixture_imports_subclass(tmp_path):
    from ruamel.yaml import YAML

    from defineyaml.xml_import import import_define_xml

    dest_tree = tmp_path / "tree"
    import_define_xml(Path("tests/fixtures/definexml/examples/adam.xml"), dest_tree)
    data = YAML(typ="safe").load((dest_tree / "datasets" / "adae.yaml").read_text())
    assert data["class"] == "OCCURRENCE DATA STRUCTURE"
    assert data["subclasses"] == [{"name": "ADVERSE EVENT"}]


def test_subclass_roundtrips_through_emit(tmp_path):
    from defineyaml.xml_emit import write_define_xml
    from defineyaml.xml_import import import_define_xml

    dest_tree = tmp_path / "tree"
    import_define_xml(Path("tests/fixtures/definexml/examples/adam.xml"), dest_tree)
    rebuilt_xml = tmp_path / "define.xml"
    write_define_xml(dest_tree, rebuilt_xml)
    rebuilt = etree.parse(str(rebuilt_xml))
    ns = {"def": "http://www.cdisc.org/ns/def/v2.1"}
    sub_els = rebuilt.findall(
        ".//odm:ItemGroupDef[@Name='ADAE']/def:Class/def:SubClass",
        {"odm": "http://www.cdisc.org/ns/odm/v1.3", **ns},
    )
    assert len(sub_els) == 1
    assert sub_els[0].get("Name") == "ADVERSE EVENT"
