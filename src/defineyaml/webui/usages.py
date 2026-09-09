"""Best-effort "who references this object" / orphan detection, for the editor.

Deliberately independent of linker.py's resolution, which requires the whole
tree to validate before it will resolve anything: one typo in one file would
otherwise blank out the usages panel for every object, not just the broken one.
This scans raw YAML instead - the same tolerant loading tree.py already does
for browsing and editing - and matches reference text against object identity
text via oid.slugify()/path_to_slug(), the same normalisation the real linker
uses, so a match here is one the real build would resolve the same way.

Two things this does NOT track, both by design, not oversight:
  - `{oid: literal}` references (CLAUDE.md §3's escape hatch for round-tripping
    imported content) - these don't carry a name to match against, and aren't
    the form anyone hand-authors, so they're simply invisible here rather than
    guessed at.
  - Anything inside a `where:` field that's an inline condition list rather
    than a named reference - read for the item references it contains
    (RangeCheck.variable), but the where clause itself has no name to be "used"
    under; it's inline, owned by exactly one parent.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .. import oid as oidmod
from . import tree as treemod

# Trailing field name -> the kind of object a string value there names. Fields not
# listed are walked into (if a dict/list) but never treated as a reference themselves.
_FIELD_TARGET_KIND = {
    "codelist": "codelists",
    "method": "methods",
    "comment": "comments",
    "join_comment": "comments",
    "standard": "standards",
    "document": "documents",
    "ref": "documents",  # the ref: inside a DocumentRef {ref:, pages:} wrapper
    "where": "whereclauses",  # only fires when the value is a string; a list is inline
    "same_as": "__item__",
    "parameter": "__item__",
    "variable": "__item__",  # RangeCheck.variable
    "dataset": "__dataset__",  # AnalysisDataset.dataset / ValueListDef.dataset (bare name, not dotted)
}
_ITEM_FIELDS = {
    "same_as",
    "parameter",
    "variable",
}  # DATASET.VARIABLE[.ENTRY] dotted form


@dataclass
class Usage:
    kind: str
    key: str
    label: str
    field: str


@dataclass
class _Node:
    kind: str
    key: str
    label: str
    name_slug: str | None  # this object's own identity, as the linker would derive it


def _identity_slug(kind: str, key: str, data: dict) -> str | None:
    """The slug a reference to this object would need to match, mirroring
    linker.py's derivation: name-based for most kinds, path-based (from the file's
    own key, which the loader already derived the same way) for the "no Name in
    Define-XML" kinds, and dataset+variable for value lists (which have neither).
    """
    if kind in ("methods", "comments", "whereclauses", "analysis_results"):
        return oidmod.path_to_slug(key)
    if kind == "valuelists":
        dataset, variable = data.get("dataset"), data.get("variable")
        return (
            f"{oidmod.slugify(dataset)}.{oidmod.slugify(variable)}"
            if dataset and variable
            else None
        )
    name = data.get("name")
    return oidmod.slugify(name) if name else None


def _walk(data, dataset_name: str | None, edges: list[tuple[str, str, str]]):
    """Depth-first walk collecting (target_kind, target_text, field_name) edges out
    of one object's data. `dataset_name` is the owning dataset's own name, when this
    object is a dataset - needed to resolve a bare (undotted) valuelist: reference,
    which is relative to the dataset it's written in.
    """
    if isinstance(data, dict):
        for k, v in data.items():
            if k == "valuelist" and isinstance(v, str):
                target = (
                    v if "." in v else (f"{dataset_name}.{v}" if dataset_name else v)
                )
                edges.append(("valuelists", target, k))
                continue
            if k in _FIELD_TARGET_KIND and isinstance(v, str):
                edges.append((_FIELD_TARGET_KIND[k], v, k))
                continue
            _walk(v, dataset_name, edges)
    elif isinstance(data, list):
        for item in data:
            _walk(item, dataset_name, edges)


def _dataset_token(text: str) -> str:
    return text.split(".", 1)[0]


def build_usage_graph(root: Path) -> dict[tuple[str, str], list[Usage]]:
    """{(kind, key): [Usage, ...]} - every object that references it, best-effort.
    A file that fails to even parse as YAML is skipped for both directions (it can
    neither be resolved as a target nor contribute outgoing references) rather than
    failing the whole scan.
    """
    nodes: dict[str, list[_Node]] = {k: [] for k in treemod.KIND_SPECS}
    raw: dict[tuple[str, str], dict] = {}

    for kind in treemod.KIND_SPECS:
        for item in treemod.list_items(root, kind):
            key = item["key"]
            try:
                data = treemod.read_object(root, kind, key)
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            raw[(kind, key)] = data
            nodes[kind].append(
                _Node(kind, key, item["label"], _identity_slug(kind, key, data))
            )

    # Index: kind -> slug -> [(kind, key), ...] (a list since names aren't always unique,
    # e.g. two def:Standard entries sharing a Name - see CLAUDE.md §3).
    index: dict[str, dict[str, list[tuple[str, str]]]] = {
        k: {} for k in treemod.KIND_SPECS
    }
    for kind, node_list in nodes.items():
        for n in node_list:
            if n.name_slug:
                index[kind].setdefault(n.name_slug, []).append((n.kind, n.key))
    # Items (dataset variables) resolve against the owning dataset, not their own kind.
    dataset_of_item: dict[str, tuple[str, str]] = {}
    for (kind, key), data in raw.items():
        if kind != "datasets":
            continue
        ds_name = data.get("name")
        if not ds_name:
            continue
        for var in data.get("variables") or []:
            if isinstance(var, dict) and var.get("name"):
                dataset_of_item[
                    f"{oidmod.slugify(ds_name)}.{oidmod.slugify(var['name'])}"
                ] = (kind, key)

    usages: dict[tuple[str, str], list[Usage]] = {}

    def record(
        target_kind: str,
        target_key: str,
        from_kind: str,
        from_key: str,
        from_label: str,
        field_name: str,
    ):
        usages.setdefault((target_kind, target_key), []).append(
            Usage(from_kind, from_key, from_label, field_name)
        )

    for (kind, key), data in raw.items():
        label = next((n.label for n in nodes[kind] if n.key == key), key)
        dataset_name = data.get("name") if kind == "datasets" else None
        edges: list[tuple[str, str, str]] = []
        _walk(data, dataset_name, edges)
        for target_kind, target_text, field_name in edges:
            if target_kind == "__item__":
                item_slug = ".".join(oidmod.slugify(p) for p in target_text.split("."))
                # A value-level (3-part) item reference resolves to the same dataset as
                # its 2-part prefix; try progressively shorter prefixes.
                parts = item_slug.split(".")
                for n in (len(parts), 2):
                    candidate = ".".join(parts[:n])
                    if candidate in dataset_of_item:
                        t_kind, t_key = dataset_of_item[candidate]
                        record(t_kind, t_key, kind, key, label, field_name)
                        break
                continue
            if target_kind == "__dataset__":
                target_slug = oidmod.slugify(_dataset_token(target_text))
                for t_kind, t_key in index["datasets"].get(target_slug, []):
                    record(t_kind, t_key, kind, key, label, field_name)
                continue
            target_slug = (
                oidmod.slugify(target_text)
                if target_kind not in ("methods", "comments", "whereclauses")
                else oidmod.path_to_slug(target_text)
            )
            for t_kind, t_key in index.get(target_kind, {}).get(target_slug, []):
                record(t_kind, t_key, kind, key, label, field_name)

    return usages


def usages_for(root: Path, kind: str, key: str) -> dict:
    # A singleton file (study/standards/documents) is never itself the target of a
    # reference - only individual entries *within* standards.yaml/documents.yaml are
    # (and this scanner works at file granularity, matching the editor's own
    # addressable units) - so "orphan" isn't a meaningful question to ask of it.
    if treemod.KIND_SPECS[kind].singleton:
        return {"used_by": [], "orphan": False}
    graph = build_usage_graph(root)
    used_by = graph.get((kind, key), [])
    return {
        "used_by": [
            {"kind": u.kind, "key": u.key, "label": u.label, "field": u.field}
            for u in used_by
        ],
        "orphan": len(used_by) == 0,
    }


def orphan_keys(root: Path, kind: str) -> set[str]:
    """Every key in `kind` with zero incoming usages - for an at-a-glance sidebar
    indicator. Builds the whole-tree graph once per call; callers listing several
    kinds' items should still expect one scan per kind, not several per kind.
    """
    if treemod.KIND_SPECS[kind].singleton:
        return set()
    graph = build_usage_graph(root)
    referenced = {key for (k, key) in graph if k == kind and graph[(k, key)]}
    return {item["key"] for item in treemod.list_items(root, kind)} - referenced
