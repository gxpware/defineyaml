"""'Copy variables from...' (the editor's dataset-to-dataset variable copy) -
orchestrated server-side over tree.py's read/save primitives, since one copy can
touch several files (the target dataset, plus any duplicated methods/comments/value
lists/where-clauses): doing that as a sequence of separate frontend API calls risks
a half-completed copy if one step fails partway through.

Codelists are never duplicated - always shared, matching CLAUDE.md §2's own granularity
rationale (a codelist is CT-governed and meant to be reused, the highest-contention
object in a define). A variable's `same_as:` (a rare cross-reference to another item,
used only for the "No OR" disjunction pattern - CLAUDE.md §3) is likewise left exactly
as the source wrote it, never duplicated: rewriting it correctly would mean knowing
whether the item it points at moved too, which a same-name-based copy has no way to
determine.
"""

from __future__ import annotations

import copy
from pathlib import Path

from .. import oid as oidmod
from . import tree as treemod

# Reference fields duplicated when reference_mode == "duplicate", by the kind whose
# object they hold. codelist:/same_as: are deliberately absent - see module docstring.
_DUPLICABLE_FIELDS = {
    "method": "methods",
    "comment": "comments",
    "valuelist": "valuelists",
}


def _resolve_valuelist_key(
    root: Path, ref_text: str, owning_dataset_name: str
) -> str | None:
    """`valuelist:` is the one reference field that's dataset-*relative* (linker.py's
    resolve_valuelist_ref: a bare `VARIABLE` means "in the current dataset", so it
    resolves differently depending on which dataset the variable holding it lives in)
    rather than a direct file key like method:/comment: are - so, unlike those, it has
    to be resolved against the actual value-list files before it can be treated as one.
    """
    if "." in ref_text:
        dataset_part, variable_part = ref_text.split(".", 1)
    else:
        dataset_part, variable_part = owning_dataset_name, ref_text
    target_slug = f"{oidmod.slugify(dataset_part)}.{oidmod.slugify(variable_part)}"
    for item in treemod.list_items(root, "valuelists"):
        try:
            data = treemod.read_object(root, "valuelists", item["key"])
        except treemod.NotFoundError:
            continue
        ds, var = data.get("dataset"), data.get("variable")
        if ds and var and f"{oidmod.slugify(ds)}.{oidmod.slugify(var)}" == target_slug:
            return item["key"]
    return None


def _unique_key(root: Path, kind: str, proposed: str) -> str:
    existing = {i["key"] for i in treemod.list_items(root, kind)}
    if proposed not in existing:
        return proposed
    n = 2
    while f"{proposed}-{n}" in existing:
        n += 1
    return f"{proposed}-{n}"


def _rekey(source_key: str, target_dataset_key: str) -> str:
    """A duplicated object's own key: the source key with its dataset-scoping prefix
    swapped for the target dataset's, mirroring whichever convention the source key
    already uses (`<dataset>/...` for methods, `<dataset>__...` for comments/value
    lists) - so the duplicate reads as "the target dataset's own copy", the same way
    the original read as the source's. Falls back to a suffix for a key that isn't
    dataset-scoped at all (a named where clause, typically shared on purpose).
    """
    for sep in ("/", "__"):
        if sep in source_key:
            _, _, rest = source_key.partition(sep)
            return f"{target_dataset_key}{sep}{rest}"
    return f"{source_key}-{target_dataset_key}"


def _duplicate_object(
    root: Path, kind: str, source_key: str, ctx: "_CopyContext"
) -> str:
    """Returns the key the copy should reference: `source_key` unchanged if this
    object was already duplicated earlier in the same operation (so five variables
    sharing one method end up sharing one duplicate, not five near-identical files).
    """
    memo_key = (kind, source_key)
    if memo_key in ctx.memo:
        return ctx.memo[memo_key]
    try:
        data = copy.deepcopy(treemod.read_object(root, kind, source_key))
    except treemod.NotFoundError:
        return source_key  # a dangling reference in the source; not this operation's problem to fix
    new_key = _unique_key(root, kind, _rekey(source_key, ctx.target_dataset_key))
    if kind == "valuelists":
        data["dataset"] = ctx.target_dataset_name
        for entry in data.get("entries") or []:
            _process_value_list_entry(root, entry, ctx)
    elif kind == "whereclauses":
        if isinstance(data.get("comment"), str):
            data["comment"] = _duplicate_object(root, "comments", data["comment"], ctx)
    treemod.save_object(root, kind, new_key, data)
    ctx.created.append({"kind": kind, "key": new_key})
    ctx.memo[memo_key] = new_key
    return new_key


def _process_value_list_entry(root: Path, entry: dict, ctx: "_CopyContext") -> None:
    item = entry.get("item") or {}
    for field in ("method", "comment"):
        if isinstance(item.get(field), str):
            item[field] = _duplicate_object(
                root, _DUPLICABLE_FIELDS[field], item[field], ctx
            )
    if isinstance(entry.get("comment"), str):
        entry["comment"] = _duplicate_object(root, "comments", entry["comment"], ctx)
    if isinstance(entry.get("where"), str):
        entry["where"] = _duplicate_object(root, "whereclauses", entry["where"], ctx)
    # item.codelist is deliberately untouched (always shared); item.valuelist (a
    # value-level item referencing *another* value list) isn't a real pattern worth
    # chasing a second level deep, so it's left as-is too.


class _CopyContext:
    def __init__(self, target_dataset_key: str, target_dataset_name: str):
        self.target_dataset_key = target_dataset_key
        self.target_dataset_name = target_dataset_name
        self.memo: dict[tuple[str, str], str] = {}
        self.created: list[dict] = []


def copy_variables(
    root: Path,
    target_key: str,
    source_key: str,
    variable_names: list[str],
    reference_mode: str,
    set_predecessor: bool,
) -> dict:
    """Copy `variable_names` from dataset `source_key` into dataset `target_key`.

    reference_mode "share": copied variables keep pointing at the source's method/
    comment/value-list/where-clause objects. "duplicate": each of those gets its own
    new copy instead, so the target dataset ends up owning independent files rather
    than sharing them with the source.

    set_predecessor: replace every copied variable's origin: with
    {"type": "Predecessor", "source": "<SOURCE_DATASET_NAME>.<VARIABLE_NAME>"},
    discarding whatever origin the source variable had.

    A variable whose name already exists in the target is skipped, not overwritten -
    two variables sharing a name in one dataset derive the same OID and hard-fail
    define build's collision check (CLAUDE.md §3).
    """
    if reference_mode not in ("share", "duplicate"):
        raise ValueError(
            f"reference_mode must be 'share' or 'duplicate', got {reference_mode!r}"
        )

    target_data = treemod.read_object(root, "datasets", target_key)
    source_data = treemod.read_object(root, "datasets", source_key)
    source_name = source_data.get("name") or source_key

    existing_names = {v.get("name") for v in target_data.get("variables") or []}
    source_vars_by_name = {v.get("name"): v for v in source_data.get("variables") or []}

    ctx = _CopyContext(
        target_dataset_key=target_key,
        target_dataset_name=target_data.get("name") or target_key,
    )
    copied: list[str] = []
    skipped: list[dict] = []
    variables = target_data.setdefault("variables", [])

    for name in variable_names:
        source_var = source_vars_by_name.get(name)
        if source_var is None:
            skipped.append({"name": name, "reason": "not found in source dataset"})
            continue
        if name in existing_names:
            skipped.append({"name": name, "reason": "already exists in this dataset"})
            continue
        new_var = copy.deepcopy(source_var)
        if isinstance(new_var.get("valuelist"), str):
            vl_key = _resolve_valuelist_key(root, new_var["valuelist"], source_name)
            if vl_key is not None:
                if reference_mode == "duplicate":
                    _duplicate_object(
                        root, "valuelists", vl_key, ctx
                    )  # creates the copy; ref below is name-based, not the file key
                    new_var["valuelist"] = f"{ctx.target_dataset_name}.{name}"
                else:
                    # Copied verbatim it would still say "aval" - resolved relative to
                    # *this* dataset (linker.py's resolve_valuelist_ref), which is wrong
                    # the moment it's no longer the value list's own dataset. Made
                    # explicit instead, so it keeps pointing at the (still shared,
                    # unduplicated) source value list correctly.
                    new_var["valuelist"] = f"{source_name}.{name}"
        if reference_mode == "duplicate":
            for field, kind in _DUPLICABLE_FIELDS.items():
                if field == "valuelist":
                    continue  # handled above - needs resolving before it can be duplicated
                if isinstance(new_var.get(field), str):
                    new_var[field] = _duplicate_object(root, kind, new_var[field], ctx)
        if set_predecessor:
            new_var["origin"] = {
                "type": "Predecessor",
                "source": f"{source_name}.{name}",
            }
        variables.append(new_var)
        existing_names.add(name)
        copied.append(name)

    if copied:
        treemod.save_object(root, "datasets", target_key, target_data)

    return {"copied": copied, "skipped": skipped, "created": ctx.created}
