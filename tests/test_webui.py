"""defineyaml.webui.tree: the editor's load/merge/save layer. The one guarantee that
actually matters here - a save preserves comments and untouched fields, per
CLAUDE.md §1's whole rationale for choosing ruamel.yaml - is asserted directly against
a real file, not just against the in-memory merge function.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError

from defineyaml.webui import state as state_module
from defineyaml.webui import tree
from defineyaml.webui import usages

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "define"


@pytest.fixture()
def scratch_tree(tmp_path: Path) -> Path:
    dest = tmp_path / "define"
    shutil.copytree(FIXTURE_ROOT, dest)
    return dest


def test_list_kinds_covers_every_object_kind():
    kinds = {k["kind"] for k in tree.list_kinds()}
    assert kinds == set(tree.KIND_SPECS)


def test_list_items_and_read_object_roundtrip(scratch_tree: Path):
    items = tree.list_items(scratch_tree, "datasets")
    keys = {i["key"] for i in items}
    assert "adsl" in keys

    data = tree.read_object(scratch_tree, "datasets", "adsl")
    assert data["name"] == "ADSL"
    assert any(v["name"] == "RACE" for v in data["variables"])


def test_read_object_missing_raises_not_found(scratch_tree: Path):
    with pytest.raises(tree.NotFoundError):
        tree.read_object(scratch_tree, "datasets", "does-not-exist")


def test_save_preserves_comments_and_untouched_fields(scratch_tree: Path):
    path = scratch_tree / "datasets" / "adsl.yaml"
    original_text = path.read_text()
    assert "# CT extended per protocol s7.2" in original_text

    data = tree.read_object(scratch_tree, "datasets", "adsl")
    race = next(v for v in data["variables"] if v["name"] == "RACE")
    assert race["origin"]["pages"] == [
        4,
        5,
    ]  # a field the web UI has no dedicated widget for
    race["label"] = "Race (edited)"

    tree.save_object(scratch_tree, "datasets", "adsl", data)

    new_text = path.read_text()
    assert "# CT extended per protocol s7.2" in new_text
    reloaded = tree.read_object(scratch_tree, "datasets", "adsl")
    race_reloaded = next(v for v in reloaded["variables"] if v["name"] == "RACE")
    assert race_reloaded["label"] == "Race (edited)"
    assert race_reloaded["origin"]["pages"] == [
        4,
        5,
    ]  # survived even though nothing touched it
    other_var = next(v for v in reloaded["variables"] if v["name"] == "USUBJID")
    assert (
        other_var["comment"] == "adsl/usubjid"
    )  # untouched sibling variable, unchanged


def test_save_invalid_data_raises_and_leaves_file_untouched(scratch_tree: Path):
    path = scratch_tree / "datasets" / "adsl.yaml"
    original_text = path.read_text()
    with pytest.raises(ValidationError):
        tree.save_object(scratch_tree, "datasets", "adsl", {"name": "ADSL"})
    assert path.read_text() == original_text


def test_save_creates_new_file(scratch_tree: Path):
    tree.save_object(
        scratch_tree, "comments", "brand-new", {"description": "a new comment"}
    )
    data = tree.read_object(scratch_tree, "comments", "brand-new")
    assert data["description"] == "a new comment"


def test_delete_object_removes_file(scratch_tree: Path):
    tree.save_object(scratch_tree, "comments", "to-delete", {"description": "temp"})
    assert (scratch_tree / "comments" / "to-delete.yaml").exists()
    tree.delete_object(scratch_tree, "comments", "to-delete")
    assert not (scratch_tree / "comments" / "to-delete.yaml").exists()


def test_delete_singleton_is_rejected(scratch_tree: Path):
    with pytest.raises(ValueError):
        tree.delete_object(scratch_tree, "study", "study")


def test_codelist_save_discriminates_enumerated_vs_external(scratch_tree: Path):
    enumerated = tree.read_object(scratch_tree, "codelists", "racec")
    assert "terms" in enumerated
    validated = tree.validate("codelists", enumerated)
    assert validated.__class__.__name__ == "EnumeratedCodeList"

    external = tree.read_object(scratch_tree, "codelists", "meddra")
    assert "external" in external
    validated_external = tree.validate("codelists", external)
    assert validated_external.__class__.__name__ == "ExternalCodeListDef"


def test_merge_reorders_and_preserves_matched_list_items(scratch_tree: Path):
    # A term list reordered and one term edited: the untouched term's own position
    # in the list changes, but the file should still parse and the comment-bearing
    # neighbor field should survive - this is the harder case _merge's identity
    # matching (not a wholesale list replace) exists for.
    data = tree.read_object(scratch_tree, "codelists", "racec")
    data["terms"] = list(reversed(data["terms"]))
    data["terms"][0]["decode"] = data["terms"][0]["decode"] + " (edited)"
    tree.save_object(scratch_tree, "codelists", "racec", data)
    reloaded = tree.read_object(scratch_tree, "codelists", "racec")
    assert reloaded["terms"][0]["decode"].endswith("(edited)")
    assert len(reloaded["terms"]) == len(data["terms"])


def test_search_items_blank_query_lists_all_as_name_matches(scratch_tree: Path):
    results = tree.search_items(scratch_tree, "codelists", "")
    assert results == [
        {**it, "match": "name", "snippet": None}
        for it in tree.list_items(scratch_tree, "codelists")
    ]


def test_search_items_matches_file_contents_when_the_name_does_not(scratch_tree: Path):
    # "male" is nowhere in any codelist's name/label/key, but the SEX codelist's terms
    # spell it out - the picker's whole point is finding that codelist anyway.
    results = tree.search_items(scratch_tree, "codelists", "male")
    hit = next(r for r in results if r["key"] == "sex")
    assert hit["match"] == "content"
    assert hit["snippet"] and "male" in hit["snippet"].lower()
    # a name/key match still ranks ahead of any content-only match
    named = tree.search_items(scratch_tree, "codelists", "sex")
    assert named[0]["key"] == "sex" and named[0]["match"] == "name"


# ---------------------------------------------------------------------------
# state.py - last-opened-view / autosave persistence
# ---------------------------------------------------------------------------


@pytest.fixture()
def isolated_state_path(tmp_path: Path, monkeypatch):
    # state.py's STATE_PATH defaults to ~/.config/defineyaml/editor-state.json - never
    # touch the real one from a test.
    path = tmp_path / "editor-state.json"
    monkeypatch.setattr(state_module, "STATE_PATH", path)
    return path


def test_state_roundtrips_and_merges_updates(isolated_state_path: Path, tmp_path: Path):
    source_a = tmp_path / "define-a"
    source_b = tmp_path / "define-b"
    assert state_module.get_state(source_a) == {}

    state_module.update_state(source_a, {"kind": "datasets", "key": "adsl"})
    state_module.update_state(source_a, {"autosave": True})
    assert state_module.get_state(source_a) == {
        "kind": "datasets",
        "key": "adsl",
        "autosave": True,
    }

    # A different tree's state is independent.
    assert state_module.get_state(source_b) == {}
    state_module.update_state(source_b, {"kind": "methods", "key": "adsl/trtsdt"})
    assert state_module.get_state(source_a) == {
        "kind": "datasets",
        "key": "adsl",
        "autosave": True,
    }
    assert state_module.get_state(source_b) == {"kind": "methods", "key": "adsl/trtsdt"}


def test_state_survives_reload_from_disk(isolated_state_path: Path, tmp_path: Path):
    source = tmp_path / "define-c"
    state_module.update_state(source, {"kind": "codelists", "key": "race"})
    assert (
        json.loads(isolated_state_path.read_text())[str(source.resolve())]["key"]
        == "race"
    )
    assert state_module.get_state(source) == {"kind": "codelists", "key": "race"}


# ---------------------------------------------------------------------------
# usages.py - "who references this" / orphan detection
# ---------------------------------------------------------------------------


def test_codelist_used_by_the_dataset_variable_referencing_it(scratch_tree: Path):
    result = usages.usages_for(scratch_tree, "codelists", "racec")
    assert result["orphan"] is False
    assert any(
        u["kind"] == "datasets" and u["key"] == "adsl" and u["field"] == "codelist"
        for u in result["used_by"]
    )


def test_unreferenced_codelist_is_an_orphan(scratch_tree: Path):
    tree.save_object(
        scratch_tree,
        "codelists",
        "unused-cl",
        {
            "name": "UNUSEDCL",
            "label": "Unused",
            "terms": [{"code": "X", "decode": "X"}],
        },
    )
    result = usages.usages_for(scratch_tree, "codelists", "unused-cl")
    assert result["orphan"] is True
    assert result["used_by"] == []
    assert "unused-cl" in usages.orphan_keys(scratch_tree, "codelists")


def test_valuelist_identity_resolves_from_dataset_and_variable_not_a_name_field(
    scratch_tree: Path,
):
    # ValueListDef has no name: field at all (just dataset:/variable:) - this is the
    # exact bug the first cut of _identity_slug had: it always returned None for
    # valuelists, so a real valuelist: reference could never match anything.
    assert "adlb__aval" not in usages.orphan_keys(scratch_tree, "valuelists")
    result = usages.usages_for(scratch_tree, "valuelists", "adlb__aval")
    assert any(
        u["kind"] == "datasets" and u["key"] == "adlb" and u["field"] == "valuelist"
        for u in result["used_by"]
    )


def test_method_used_by_the_variable_referencing_it(scratch_tree: Path):
    result = usages.usages_for(scratch_tree, "methods", "adsl/trtsdt")
    assert any(
        u["kind"] == "datasets" and u["key"] == "adsl" and u["field"] == "method"
        for u in result["used_by"]
    )


def test_method_document_ref_with_page_ref_saves_and_round_trips(scratch_tree: Path):
    data = tree.read_object(scratch_tree, "methods", "adsl/trtsdt")
    data["documents"] = [
        {"ref": "adrg", "pages": [3], "title": "Sec 4.1"},
        {"ref": "adrg", "pages": {"first": 10, "last": 12}},
    ]
    tree.save_object(scratch_tree, "methods", "adsl/trtsdt", data)
    reloaded = tree.read_object(scratch_tree, "methods", "adsl/trtsdt")
    assert reloaded["documents"] == data["documents"]
    # the comment on an untouched field of this method still survives the save
    assert (
        "trtsdt = datepart"
        in (scratch_tree / "methods" / "adsl" / "trtsdt.yaml").read_text()
    )


def test_analysis_result_dataset_and_parameter_resolve_to_the_owning_dataset(
    scratch_tree: Path,
):
    result = usages.usages_for(scratch_tree, "datasets", "adlb")
    fields = {u["field"] for u in result["used_by"] if u["kind"] == "analysis_results"}
    assert "dataset" in fields
    assert (
        "parameter" in fields
    )  # AnalysisResult.parameter: "ADLB.PARAMCD" resolves to its dataset


def test_singleton_kinds_are_never_flagged_orphan(scratch_tree: Path):
    assert usages.orphan_keys(scratch_tree, "study") == set()
    assert usages.usages_for(scratch_tree, "study", "study")["orphan"] is False
    assert usages.orphan_keys(scratch_tree, "standards") == set()


def test_literal_oid_reference_is_not_tracked_as_a_usage(scratch_tree: Path):
    # {oid: ...} references (CLAUDE.md §3's round-trip escape hatch) carry no name to
    # match against - by design, not a bug, they're simply invisible here.
    tree.save_object(
        scratch_tree,
        "datasets",
        "oid-ref-test",
        {
            "name": "OIDREF",
            "label": "x",
            "class": "x",
            "structure": "x",
            "variables": [
                {
                    "name": "V1",
                    "label": "v",
                    "type": "text",
                    "codelist": {"oid": "CL.RACE"},
                }
            ],
        },
    )
    result = usages.usages_for(scratch_tree, "codelists", "race")
    assert not any(
        u["kind"] == "datasets" and u["key"] == "oid-ref-test"
        for u in result["used_by"]
    )
