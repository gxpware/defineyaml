"""`define init`'s underlying scaffolding - a fresh define/ file tree (CLAUDE.md §2's
subdirectory layout) plus a minimal study.yaml carrying only what StudyFile actually
requires. Tests exercise scaffold_tree() directly rather than the CLI's interactive
prompts, which cli.py's init command is a thin wrapper around.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from ruamel.yaml import YAML

from defineyaml.linker import load_tree
from defineyaml.scaffold import SCAFFOLD_SUBDIRS, ScaffoldError, scaffold_tree
from defineyaml.xml_emit import render_xml_bytes

_FIELDS = dict(
    file_oid="FILE.1",
    study_oid="STUDY.1",
    study_name="Test Study",
    protocol_name="PROTO-1",
    metadata_version_oid="MDV.1",
    metadata_version_name="MDV",
)


def test_creates_every_scaffold_subdir(tmp_path):
    dest = tmp_path / "define"
    scaffold_tree(dest, **_FIELDS)
    for subdir in SCAFFOLD_SUBDIRS:
        assert (dest / subdir).is_dir()


def test_writes_study_yaml_with_prefilled_odm_header(tmp_path):
    dest = tmp_path / "define"
    scaffold_tree(dest, **_FIELDS)
    data = YAML(typ="safe").load((dest / "study.yaml").read_text())

    assert data["study"] == {
        "oid": "STUDY.1",
        "name": "Test Study",
        "protocol_name": "PROTO-1",
    }
    assert data["metadata_version"] == {
        "oid": "MDV.1",
        "name": "MDV",
        "define_version": "2.1.0",
    }

    odm = data["odm"]
    assert odm["file_oid"] == "FILE.1"
    assert odm["source_system"] == "DefineYAML"
    assert odm["source_system_version"]  # this tool's version, non-empty
    assert odm["originator"]
    assert odm["stylesheet"] == "define2-1.xsl"
    # as-of is stamped at scaffold time; creation is left blank on purpose - the build
    # fills it from the tree's latest modification (test_tree_time.py covers that).
    created = datetime.fromisoformat(odm["as_of_datetime"])
    assert abs((datetime.now(created.tzinfo) - created).total_seconds()) < 120
    assert "creation_datetime" not in odm

    # Fields that are None or equal to their default are still omitted, not written as
    # null/empty - description: (None) and expression_contexts: ([]) most notably.
    assert "description" not in data["study"]
    assert "expression_contexts" not in data


def test_scaffolded_tree_builds_with_header_and_stylesheet(tmp_path):
    import re

    dest = tmp_path / "define"
    scaffold_tree(dest, **_FIELDS)
    xml = render_xml_bytes(dest).decode()
    assert '<?xml-stylesheet type="text/xsl" href="define2-1.xsl"?>' in xml
    assert 'SourceSystem="DefineYAML"' in xml
    assert 'def:DefineVersion="2.1.0"' in xml
    # CreationDateTime is XSD-required - even with study.yaml's field blank, the build
    # fills it (here from study.yaml's own mtime, the tree not being a git repo).
    m = re.search(r'CreationDateTime="([^"]+)"', xml)
    assert m and datetime.fromisoformat(m.group(1))


def test_scaffolded_tree_loads_and_builds(tmp_path):
    dest = tmp_path / "define"
    scaffold_tree(dest, **_FIELDS)
    tree = load_tree(dest)
    assert tree.study.study.name == "Test Study"
    assert tree.datasets == {}
    assert tree.standards.standards == []


def test_refuses_to_overwrite_existing_destination(tmp_path):
    dest = tmp_path / "define"
    dest.mkdir()
    with pytest.raises(ScaffoldError, match="already exists"):
        scaffold_tree(dest, **_FIELDS)
    # Refusing means refusing - no subdirectories or study.yaml appear either.
    assert list(dest.iterdir()) == []


def test_refuses_when_destination_is_an_existing_file(tmp_path):
    dest = tmp_path / "define"
    dest.write_text("not a directory")
    with pytest.raises(ScaffoldError, match="already exists"):
        scaffold_tree(dest, **_FIELDS)


def test_invalid_fields_leave_nothing_on_disk(tmp_path):
    dest = tmp_path / "define"
    fields = dict(_FIELDS, study_name="")  # empty str still satisfies `name: str`...
    fields["protocol_name"] = None  # ...but None does not, and raises before any I/O
    with pytest.raises(ScaffoldError):
        scaffold_tree(dest, **fields)
    assert not dest.exists()
