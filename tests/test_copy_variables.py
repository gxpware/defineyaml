"""webui.copy_variables - "Copy variables from..." in the editor. Exercised against a
scratch copy of the real repo tree so the reference-duplication paths (method, comment,
value list + its entries' where clause) run against real, representative data, not a
synthetic fixture built to make the code look correct.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from defineyaml.webui import copy_variables, tree

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "define"


@pytest.fixture()
def scratch_tree(tmp_path: Path) -> Path:
    dest = tmp_path / "define"
    shutil.copytree(FIXTURE_ROOT, dest)
    return dest


def _names(scratch_tree, dataset_key):
    return [
        v["name"]
        for v in tree.read_object(scratch_tree, "datasets", dataset_key)["variables"]
    ]


def _drop_variables(scratch_tree: Path, dataset_key: str, *names: str) -> None:
    """Remove `names` from a dataset in the scratch copy so a copy-*into* test starts
    from a known state. The `define/` fixture tree is a live scratch tree (gitignored,
    routinely mutated through the editor), so a test that needs the target dataset to
    *lack* a variable has to make that true itself rather than assume it - otherwise a
    stray variable added to ADCM months later silently turns the copy into a skip.
    """
    ds = tree.read_object(scratch_tree, "datasets", dataset_key)
    drop = set(names)
    ds["variables"] = [v for v in ds["variables"] if v.get("name") not in drop]
    tree.save_object(scratch_tree, "datasets", dataset_key, ds)


def test_share_mode_copies_variable_and_keeps_original_references(scratch_tree: Path):
    _drop_variables(scratch_tree, "ADCM", "TRTSDT")
    result = copy_variables.copy_variables(
        scratch_tree,
        target_key="ADCM",
        source_key="adsl",
        variable_names=["TRTSDT"],
        reference_mode="share",
        set_predecessor=False,
    )
    assert result["copied"] == ["TRTSDT"]
    assert result["skipped"] == []
    assert result["created"] == []  # nothing duplicated in share mode

    copied = next(
        v
        for v in tree.read_object(scratch_tree, "datasets", "ADCM")["variables"]
        if v["name"] == "TRTSDT"
    )
    assert (
        copied["method"] == "adsl/trtsdt"
    )  # same reference as the source, not a new one
    # The source dataset itself is untouched.
    assert "TRTSDT" in _names(scratch_tree, "adsl")


def test_duplicate_mode_creates_an_independent_method_copy(scratch_tree: Path):
    _drop_variables(scratch_tree, "ADCM", "TRTSDT")
    result = copy_variables.copy_variables(
        scratch_tree,
        target_key="ADCM",
        source_key="adsl",
        variable_names=["TRTSDT"],
        reference_mode="duplicate",
        set_predecessor=False,
    )
    assert result["copied"] == ["TRTSDT"]
    assert {"kind": "methods", "key": "ADCM/trtsdt"} in result["created"]

    copied = next(
        v
        for v in tree.read_object(scratch_tree, "datasets", "ADCM")["variables"]
        if v["name"] == "TRTSDT"
    )
    assert copied["method"] == "ADCM/trtsdt"
    # The new method is a real, independent file with the source's content, and the
    # source method file itself is untouched.
    new_method = tree.read_object(scratch_tree, "methods", "ADCM/trtsdt")
    original_method = tree.read_object(scratch_tree, "methods", "adsl/trtsdt")
    assert new_method["description"] == original_method["description"]
    assert new_method["expressions"] == original_method["expressions"]


def test_duplicate_mode_never_duplicates_codelists(scratch_tree: Path):
    result = copy_variables.copy_variables(
        scratch_tree,
        target_key="ADCM",
        source_key="adsl",
        variable_names=["RACE"],
        reference_mode="duplicate",
        set_predecessor=False,
    )
    copied = next(
        v
        for v in tree.read_object(scratch_tree, "datasets", "ADCM")["variables"]
        if v["name"] == "RACE"
    )
    assert copied["codelist"] == "racec"  # unchanged, shared regardless of mode
    assert not any(c["kind"] == "codelists" for c in result["created"])


def test_duplicate_mode_copies_valuelist_and_its_nested_where_clause(
    scratch_tree: Path,
):
    _drop_variables(scratch_tree, "ADCM", "AVAL")
    result = copy_variables.copy_variables(
        scratch_tree,
        target_key="ADCM",
        source_key="adlb",
        variable_names=["AVAL"],
        reference_mode="duplicate",
        set_predecessor=False,
    )
    assert result["copied"] == ["AVAL"]
    created_kinds = {c["kind"] for c in result["created"]}
    # The value list, its entry's where clause, and the method that entry's item
    # points at (adlb__aval's ALT entry carries item.method: labaval) all get their
    # own copies - duplicate mode means the target dataset owns its references.
    assert created_kinds == {"valuelists", "whereclauses", "methods"}

    copied = next(
        v
        for v in tree.read_object(scratch_tree, "datasets", "ADCM")["variables"]
        if v["name"] == "AVAL"
    )
    # valuelist: is dataset-*relative* (linker.py's resolve_valuelist_ref) - copying the
    # source's bare "aval" verbatim would resolve against ADCM instead of ADLB and break,
    # so it must come back explicit, naming the *new* value list's own dataset.
    assert copied["valuelist"] == "ADCM.AVAL"
    new_vl = tree.read_object(
        scratch_tree,
        "valuelists",
        next(c["key"] for c in result["created"] if c["kind"] == "valuelists"),
    )
    assert new_vl["dataset"] == "ADCM"  # rewritten to the target dataset's own name
    assert (
        new_vl["variable"] == "AVAL"
    )  # unchanged -- same variable name, just a different dataset

    entry = new_vl["entries"][0]
    assert (
        entry["where"] != "alt-week4"
    )  # rewritten to the new, duplicated where clause
    new_wc = tree.read_object(scratch_tree, "whereclauses", entry["where"])
    original_wc = tree.read_object(scratch_tree, "whereclauses", "alt-week4")
    assert new_wc["conditions"] == original_wc["conditions"]

    # The entry's nested item.method is re-pointed at its own duplicate too.
    new_method_key = entry["item"]["method"]
    assert new_method_key != "labaval"
    new_method = tree.read_object(scratch_tree, "methods", new_method_key)
    assert (
        new_method["description"]
        == (tree.read_object(scratch_tree, "methods", "labaval")["description"])
    )

    # The originals are untouched.
    assert (
        tree.read_object(scratch_tree, "valuelists", "adlb__aval")["dataset"] == "ADLB"
    )
    assert (
        tree.read_object(scratch_tree, "valuelists", "adlb__aval")["entries"][0][
            "item"
        ]["method"]
        == "labaval"
    )
    original_aval = next(
        v
        for v in tree.read_object(scratch_tree, "datasets", "adlb")["variables"]
        if v["name"] == "AVAL"
    )
    assert original_aval["valuelist"] == "aval"


def test_share_mode_makes_a_moved_valuelist_reference_explicit(scratch_tree: Path):
    # The source wrote "aval" (bare, relative to ADLB, its own dataset) - copied
    # unmodified into ADCM it would resolve against ADCM instead and silently break.
    result = copy_variables.copy_variables(
        scratch_tree,
        target_key="ADCM",
        source_key="adlb",
        variable_names=["AVAL"],
        reference_mode="share",
        set_predecessor=False,
    )
    assert result["created"] == []  # nothing duplicated
    copied = next(
        v
        for v in tree.read_object(scratch_tree, "datasets", "ADCM")["variables"]
        if v["name"] == "AVAL"
    )
    assert copied["valuelist"] == "ADLB.AVAL"
    # Still the one, original value list - untouched.
    assert (
        tree.read_object(scratch_tree, "valuelists", "adlb__aval")["dataset"] == "ADLB"
    )


def test_existing_variable_name_is_skipped_not_overwritten(scratch_tree: Path):
    # adlb already has an AVAL - copying ADSL's own variables into it shouldn't clobber
    # anything, and STUDYID/USUBJID already exist in every dataset by convention.
    result = copy_variables.copy_variables(
        scratch_tree,
        target_key="adlb",
        source_key="adsl",
        variable_names=["STUDYID", "TRTSDT"],
        reference_mode="share",
        set_predecessor=False,
    )
    assert result["copied"] == ["TRTSDT"]
    assert result["skipped"] == [
        {"name": "STUDYID", "reason": "already exists in this dataset"}
    ]


def test_set_predecessor_replaces_origin(scratch_tree: Path):
    result = copy_variables.copy_variables(
        scratch_tree,
        target_key="ADCM",
        source_key="adsl",
        variable_names=["RACE"],
        reference_mode="share",
        set_predecessor=True,
    )
    assert result["copied"] == ["RACE"]
    copied = next(
        v
        for v in tree.read_object(scratch_tree, "datasets", "ADCM")["variables"]
        if v["name"] == "RACE"
    )
    assert copied["origin"] == {"type": "Predecessor", "source": "ADSL.RACE"}


def test_two_variables_sharing_one_method_produce_one_duplicate_not_two(
    scratch_tree: Path,
):
    # ASTDT and ASTDTF in the bundled adae... this repo's own fixture doesn't have that
    # shape, so build the shared-method case directly: two ADSL variables pointed at the
    # same method, copied together in duplicate mode.
    adsl = tree.read_object(scratch_tree, "datasets", "adsl")
    trtsdt = next(v for v in adsl["variables"] if v["name"] == "TRTSDT")
    trtedt = dict(trtsdt, name="TRTEDT2", label="second copy for the test")
    adsl["variables"].append(trtedt)
    tree.save_object(scratch_tree, "datasets", "adsl", adsl)
    _drop_variables(scratch_tree, "ADCM", "TRTSDT", "TRTEDT2")

    result = copy_variables.copy_variables(
        scratch_tree,
        target_key="ADCM",
        source_key="adsl",
        variable_names=["TRTSDT", "TRTEDT2"],
        reference_mode="duplicate",
        set_predecessor=False,
    )
    assert result["copied"] == ["TRTSDT", "TRTEDT2"]
    method_creations = [c for c in result["created"] if c["kind"] == "methods"]
    assert (
        len(method_creations) == 1
    )  # not two, even though two variables referenced it

    variables = tree.read_object(scratch_tree, "datasets", "ADCM")["variables"]
    methods_used = {
        v["method"] for v in variables if v["name"] in ("TRTSDT", "TRTEDT2")
    }
    assert len(methods_used) == 1  # both copies point at the same new duplicate


def test_copying_from_a_dataset_with_no_such_variable_is_skipped(scratch_tree: Path):
    result = copy_variables.copy_variables(
        scratch_tree,
        target_key="ADCM",
        source_key="adsl",
        variable_names=["DOES_NOT_EXIST"],
        reference_mode="share",
        set_predecessor=False,
    )
    assert result["copied"] == []
    assert result["skipped"] == [
        {"name": "DOES_NOT_EXIST", "reason": "not found in source dataset"}
    ]


def test_invalid_reference_mode_raises():
    with pytest.raises(ValueError):
        copy_variables.copy_variables(
            FIXTURE_ROOT, "x", "y", [], reference_mode="bogus", set_predecessor=False
        )
