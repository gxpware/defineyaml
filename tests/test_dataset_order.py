"""study.yaml's dataset_order: - the one ordering concern in the whole model that has
to be stored explicitly rather than derived, since datasets are separate files with no
list position of their own to derive an OrderNumber-style sequence from (CLAUDE.md §3's
"Ordering attributes are positional, never stored" covers ordering *within* one object;
this is ordering *across* objects). Confirmed real and non-alphabetical on both bundled
fixtures: ADaM's ADSL comes first, SDTM's TS/DI/DM precede the rest.
"""

from __future__ import annotations

import re
from pathlib import Path

from ruamel.yaml import YAML

from defineyaml.linker import _ordered_datasets, load_tree
from defineyaml.models.study import StudyFile
from defineyaml.xml_emit import render_xml_bytes
from defineyaml.xml_import import import_define_xml

FIXTURES = Path(__file__).parent / "fixtures" / "definexml"
EXAMPLES = {
    "adam": FIXTURES / "examples" / "adam.xml",
    "sdtm": FIXTURES / "examples" / "sdtm.xml",
}


def test_dataset_order_defaults_to_empty_list():
    study = StudyFile.model_validate(
        {
            "odm": {"file_oid": "F"},
            "study": {"oid": "S", "name": "N", "protocol_name": "P"},
            "metadata_version": {"oid": "M", "name": "M"},
        }
    )
    assert study.dataset_order == []


def test_ordered_datasets_listed_first_then_alphabetical_remainder():
    by_name = {n: (Path(n), n) for n in ["ADAE", "ADLB", "ADSL", "ADCM"]}
    result = _ordered_datasets(by_name, ["ADSL", "ADAE"])
    assert list(result.keys()) == ["ADSL", "ADAE", "ADCM", "ADLB"]


def test_ordered_datasets_ignores_unknown_and_duplicate_names():
    by_name = {n: (Path(n), n) for n in ["ADAE", "ADSL"]}
    result = _ordered_datasets(by_name, ["ADSL", "DOES-NOT-EXIST", "ADSL"])
    assert list(result.keys()) == ["ADSL", "ADAE"]


def test_empty_order_is_plain_alphabetical():
    by_name = {n: (Path(n), n) for n in ["ADSL", "ADAE", "ADCM"]}
    assert list(_ordered_datasets(by_name, []).keys()) == ["ADAE", "ADCM", "ADSL"]


def _itemgroupdef_names(xml_bytes: bytes) -> list[str]:
    return re.findall(r"<ItemGroupDef[^>]*?Name=\"([^\"]*)\"", xml_bytes.decode())


def test_sdtm_fixture_import_captures_non_alphabetical_order(tmp_path):
    dest_tree = tmp_path / "tree"
    import_define_xml(EXAMPLES["sdtm"], dest_tree)
    data = YAML(typ="safe").load((dest_tree / "study.yaml").read_text())
    assert data["dataset_order"][:3] == ["TS", "DI", "DM"]


def test_adam_fixture_roundtrips_dataset_order_exactly(tmp_path):
    original_names = _itemgroupdef_names(EXAMPLES["adam"].read_bytes())
    dest_tree = tmp_path / "tree"
    import_define_xml(EXAMPLES["adam"], dest_tree)
    rebuilt_names = _itemgroupdef_names(render_xml_bytes(dest_tree))
    assert rebuilt_names == original_names


def test_load_tree_applies_dataset_order_from_study_yaml(tmp_path):
    dest_tree = tmp_path / "tree"
    import_define_xml(EXAMPLES["adam"], dest_tree)
    tree = load_tree(dest_tree)
    assert list(tree.datasets.keys())[0] == "ADSL"
