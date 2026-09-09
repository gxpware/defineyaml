from pathlib import Path

import pytest

from defineyaml.linker import LinkError, LoadedTree, build_symbol_table
from defineyaml.models import (
    DocumentsFile,
    MetaDataVersion,
    OdmHeader,
    StandardDef,
    StandardsFile,
    Study,
    StudyFile,
)


def _minimal_tree(standards: list[StandardDef]) -> LoadedTree:
    return LoadedTree(
        root=Path("."),
        study=StudyFile(
            odm=OdmHeader(file_oid="FILE.1"),
            study=Study(oid="STUDY.1", name="Study", protocol_name="PROT-1"),
            metadata_version=MetaDataVersion(oid="MDV.1", name="MDV"),
        ),
        standards=StandardsFile(standards=standards),
        documents=DocumentsFile(documents=[]),
    )


def test_standard_with_a_unique_name_resolves_by_bare_name():
    # The hand-authoring convention (CLAUDE.md's derivation table, and define/standards.yaml's
    # own "adamig-1-3" / "ct-2024-06-28" entries): a standard with a name nothing else shares
    # must stay reachable through a plain `standard: <name>` reference, publishing_set or not.
    tree = _minimal_tree(
        [
            StandardDef(
                name="adamig-1-3", type="IG", version="1.3", publishing_set="ADaM"
            )
        ]
    )
    table = build_symbol_table(tree)
    assert table.lookup("standard", "ADAMIG.1.3") == "STD.ADAMIG.1.3"


def test_standards_sharing_a_name_disambiguate_by_publishing_set_and_version():
    # Real-world case: two def:Standard entries can share Name (e.g. "CDISC/NCI") when they're
    # different CT versions for different models - distinguished by PublishingSet and Version,
    # not Name. Surfaced by importing the ADaM example (tests/fixtures/definexml/examples/adam.xml),
    # which hard-failed with a false "duplicate standard name" collision before this was handled.
    tree = _minimal_tree(
        [
            StandardDef(
                name="CDISC/NCI",
                type="CT",
                version="2017-09-29",
                publishing_set="ADaM",
                oid="STD.CT.01",
            ),
            StandardDef(
                name="CDISC/NCI",
                type="CT",
                version="2018-06-29",
                publishing_set="SDTM",
                oid="STD.CT.02",
            ),
        ]
    )
    table = build_symbol_table(tree)
    assert table.lookup("standard", "CDISC.NCI.ADAM.2017.09.29") == "STD.CT.01"
    assert table.lookup("standard", "CDISC.NCI.SDTM.2018.06.29") == "STD.CT.02"
    # Ambiguous: no bare-name entry is registered for either.
    assert table.lookup("standard", "CDISC.NCI") is None


def test_standards_sharing_a_name_and_publishing_set_disambiguate_by_version():
    # Real-world case from the SDTM example (tests/fixtures/definexml/examples/sdtm.xml): two
    # CDISC/NCI CT entries sharing both Name and PublishingSet="SDTM", distinguished only by
    # Version - the submission spans more than one CT vintage.
    tree = _minimal_tree(
        [
            StandardDef(
                name="CDISC/NCI",
                type="CT",
                version="2011-12-09",
                publishing_set="SDTM",
                oid="STD.3",
            ),
            StandardDef(
                name="CDISC/NCI",
                type="CT",
                version="2015-12-18",
                publishing_set="SDTM",
                oid="STD.4",
            ),
        ]
    )
    table = build_symbol_table(tree)
    assert table.lookup("standard", "CDISC.NCI.SDTM.2011.12.09") == "STD.3"
    assert table.lookup("standard", "CDISC.NCI.SDTM.2015.12.18") == "STD.4"


def test_standards_sharing_a_name_with_no_publishing_set_disambiguate_by_version():
    # Real-world case: two IG versions in one submission (SDTMIG 3.1.2 and 3.2), neither
    # carrying a PublishingSet at all.
    tree = _minimal_tree(
        [
            StandardDef(name="SDTMIG", type="IG", version="3.1.2", oid="STD.1"),
            StandardDef(name="SDTMIG", type="IG", version="3.2", oid="STD.2"),
        ]
    )
    table = build_symbol_table(tree)
    assert table.lookup("standard", "SDTMIG.3.1.2") == "STD.1"
    assert table.lookup("standard", "SDTMIG.3.2") == "STD.2"


def test_standards_sharing_name_publishing_set_and_version_still_collide():
    tree = _minimal_tree(
        [
            StandardDef(
                name="CDISC/NCI", type="CT", version="2017-09-29", publishing_set="ADaM"
            ),
            StandardDef(
                name="CDISC/NCI", type="CT", version="2017-09-29", publishing_set="ADaM"
            ),
        ]
    )
    with pytest.raises(LinkError, match="duplicate"):
        build_symbol_table(tree)
