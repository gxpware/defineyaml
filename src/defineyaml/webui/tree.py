"""File-tree discovery and comment-preserving save, for the web editor.

Deliberately independent of linker.load_tree: that requires every file in the
tree to validate, which would break browsing the instant one file has a typo
mid-edit. Listing and reading here only ever need raw YAML (io.yaml_io.load);
pydantic validation happens once, at save time, against the data about to be
written - exactly where CLAUDE.md's design puts the "readable message before
the XSD gets a chance to produce an opaque one" boundary (§7.2).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from ruamel.yaml.comments import CommentedMap, CommentedSeq

from ..io.yaml_io import dump, load
from ..models import (
    CommentDef,
    Dataset,
    DocumentsFile,
    EnumeratedCodeList,
    ExternalCodeListDef,
    MethodDef,
    ResultDisplay,
    StandardsFile,
    StudyFile,
    ValueListDef,
    WhereClauseDef,
    parse_codelist,
)

# Identity keys tried in order when matching an existing list item to an edited one,
# for every list-of-object field in the schema: Variable.name, Term.code,
# Expression.context, StandardDef.name, Document.name, ValueListEntry.name, ...
_IDENTITY_KEYS = ("name", "code", "context")


class NotFoundError(Exception):
    pass


@dataclass(frozen=True)
class KindSpec:
    kind: str
    label: str
    singleton: bool
    subdir: str | None  # collection kinds: directory under root
    filename: str | None  # singleton kinds: file name directly under root
    model: type[BaseModel] | None  # None only for "codelists" (discriminated union)


KIND_SPECS: dict[str, KindSpec] = {
    "study": KindSpec("study", "Study", True, None, "study.yaml", StudyFile),
    "standards": KindSpec(
        "standards", "Standards", True, None, "standards.yaml", StandardsFile
    ),
    "documents": KindSpec(
        "documents", "Documents", True, None, "documents.yaml", DocumentsFile
    ),
    "datasets": KindSpec("datasets", "Datasets", False, "datasets", None, Dataset),
    "codelists": KindSpec("codelists", "Codelists", False, "codelists", None, None),
    "methods": KindSpec("methods", "Methods", False, "methods", None, MethodDef),
    "comments": KindSpec("comments", "Comments", False, "comments", None, CommentDef),
    "whereclauses": KindSpec(
        "whereclauses", "Where Clauses", False, "whereclauses", None, WhereClauseDef
    ),
    "valuelists": KindSpec(
        "valuelists", "Value Lists", False, "valuelists", None, ValueListDef
    ),
    "analysis_results": KindSpec(
        "analysis_results",
        "Analysis Results",
        False,
        "analysis-results",
        None,
        ResultDisplay,
    ),
}

# Fixed key collection kinds address their singleton file with, so /api/object/study/study works.
SINGLETON_KEY = {kind: kind for kind, spec in KIND_SPECS.items() if spec.singleton}


def _path_for(root: Path, spec: KindSpec, key: str) -> Path:
    if spec.singleton:
        return root / spec.filename
    safe_key = key.replace(
        "..", ""
    )  # a key is always a path relative_to()-derived stem; belt and braces
    return root / spec.subdir / f"{safe_key}.yaml"


def _to_plain(obj: Any) -> Any:
    if isinstance(obj, (CommentedMap, dict)):
        return {k: _to_plain(v) for k, v in obj.items()}
    if isinstance(obj, (CommentedSeq, list)):
        return [_to_plain(v) for v in obj]
    return obj


def _name_and_label(path: Path, key: str) -> tuple[str | None, str]:
    try:
        data = load(path)
    except Exception:
        return None, key
    if not isinstance(data, dict):
        return None, key
    name = data.get("name")
    label = data.get("label") or data.get("description") or data.get("title")
    if name and label:
        return name, f"{name} - {label}"
    if name:
        return name, str(name)
    return None, key


def list_kinds() -> list[dict]:
    return [
        {"kind": spec.kind, "label": spec.label, "singleton": spec.singleton}
        for spec in KIND_SPECS.values()
    ]


def _apply_dataset_order(root: Path, items: list[dict]) -> list[dict]:
    """Mirrors linker.py's _ordered_datasets on the lightweight {key, label, name} shape
    list_items works with, rather than the validated Dataset models linker.load_tree
    requires - this module's whole point is browsing a tree that doesn't fully validate
    yet, so it can't lean on linker.py's own ordering without first paying for that.
    """
    try:
        study_data = load(root / "study.yaml")
    except Exception:
        return items
    order = study_data.get("dataset_order") if isinstance(study_data, dict) else None
    if not order:
        return items
    by_name = {item["name"]: item for item in items if item.get("name")}
    ordered: list[dict] = []
    seen: set[str] = set()
    for name in order:
        if name in by_name and name not in seen:
            ordered.append(by_name[name])
            seen.add(name)
    for item in items:  # already alphabetical, from the directory scan below
        if item.get("name") not in seen:
            ordered.append(item)
            seen.add(item.get("name"))
    return ordered


def list_items(root: Path, kind: str) -> list[dict]:
    spec = KIND_SPECS[kind]
    if spec.singleton:
        path = root / spec.filename
        return [{"key": kind, "label": spec.label}] if path.exists() else []
    directory = root / spec.subdir
    if not directory.is_dir():
        return []
    items = []
    for path in sorted(directory.rglob("*.yaml")):
        key = path.relative_to(directory).with_suffix("").as_posix()
        name, label = _name_and_label(path, key)
        items.append({"key": key, "label": label, "name": name})
    if kind == "datasets":
        items = _apply_dataset_order(root, items)
    return items


def _walk_scalars(obj: Any, prefix: str = ""):
    """Yield (dotted-field-path, scalar) for every leaf value in a loaded YAML doc -
    lists don't add an index to the path (a term's decode is just `terms.decode`),
    which keeps a content-match snippet readable."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _walk_scalars(v, f"{prefix}{k}.")
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_scalars(v, prefix)
    elif obj is not None and not isinstance(obj, bool):
        yield prefix.rstrip("."), obj


def search_items(root: Path, kind: str, q: str, limit: int = 200) -> list[dict]:
    """list_items() plus a full-text pass over each file's contents. A blank query is
    just list_items() (every entry `match: "name"`). Otherwise each entry is tagged
    `match: "name"` when the query hits its name/label/file key, or `match: "content"`
    (with a `snippet` of the first field that matched - e.g. a codelist term's decode)
    when it only turns up inside the file. Name matches are returned before content
    matches; the two groups are each already in list_items() order.
    """
    spec = KIND_SPECS[kind]
    items = list_items(root, kind)
    q_l = (q or "").strip().lower()
    if not q_l:
        return [{**it, "match": "name", "snippet": None} for it in items][:limit]

    name_hits: list[dict] = []
    content_hits: list[dict] = []
    for it in items:
        haystack = " ".join(
            str(it.get(f) or "") for f in ("name", "label", "key")
        ).lower()
        if q_l in haystack:
            name_hits.append({**it, "match": "name", "snippet": None})
            continue
        if spec.singleton:
            continue
        try:
            data = _to_plain(load(_path_for(root, spec, it["key"])))
        except Exception:
            continue
        for field_path, value in _walk_scalars(data):
            if q_l in str(value).lower():
                text = " ".join(str(value).split())
                if len(text) > 90:
                    text = text[:90] + "…"
                content_hits.append(
                    {
                        **it,
                        "match": "content",
                        "snippet": f"{field_path}: {text}" if field_path else text,
                    }
                )
                break
    return (name_hits + content_hits)[:limit]


def read_object(root: Path, kind: str, key: str) -> dict:
    spec = KIND_SPECS[kind]
    path = _path_for(root, spec, key)
    if not path.exists():
        raise NotFoundError(f"{kind}/{key} not found")
    return _to_plain(load(path))


def model_class(kind: str, data: dict | None = None) -> type[BaseModel]:
    spec = KIND_SPECS[kind]
    if spec.model is not None:
        return spec.model
    return ExternalCodeListDef if data and "external" in data else EnumeratedCodeList


def schema_for(kind: str) -> dict:
    if kind == "codelists":
        return {
            "enumerated": EnumeratedCodeList.model_json_schema(),
            "external": ExternalCodeListDef.model_json_schema(),
        }
    return KIND_SPECS[kind].model.model_json_schema()


def validate(kind: str, data: dict) -> BaseModel:
    if kind == "codelists":
        return parse_codelist(data)
    return KIND_SPECS[kind].model.model_validate(data)


def _identity(item: Any) -> tuple[str, Any] | None:
    if not isinstance(item, dict):
        return None
    for k in _IDENTITY_KEYS:
        if k in item:
            return (k, item[k])
    return None


def _merge(existing: Any, new: Any) -> Any:
    """Merge `new` (plain JSON-derived data) into `existing` (a ruamel node loaded
    from disk) in place where the shapes line up, so an untouched key or list item
    keeps its comment. A list-of-objects field matches items by name/code/context
    (whichever the item has) so reordering, editing, adding and removing rows each
    only disturb the rows actually affected - not every comment in the list. A field
    whose value changed *type* (e.g. a scalar replaced by a mapping) can't merge
    structurally; it's just replaced, same as a brand new key or item.
    """
    if isinstance(existing, CommentedMap) and isinstance(new, dict):
        for key in list(existing.keys()):
            if key not in new:
                del existing[key]
        for key, value in new.items():
            existing[key] = _merge(existing[key], value) if key in existing else value
        return existing
    if isinstance(existing, CommentedSeq) and isinstance(new, list):
        by_identity = {
            ident: item for item in existing if (ident := _identity(item)) is not None
        }
        merged_items = []
        for item in new:
            ident = _identity(item)
            merged_items.append(
                _merge(by_identity[ident], item)
                if ident is not None and ident in by_identity
                else item
            )
        existing[:] = merged_items
        return existing
    return new


def save_object(root: Path, kind: str, key: str, new_data: dict) -> BaseModel:
    """Validate `new_data`; only if that succeeds, merge it into the on-disk YAML
    (preserving comments per `_merge`'s rules) and write it back. Raises
    pydantic.ValidationError, leaving the file untouched, if `new_data` is invalid.
    """
    validated = validate(kind, new_data)
    spec = KIND_SPECS[kind]
    path = _path_for(root, spec, key)
    if path.exists():
        merged = _merge(load(path), new_data)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        merged = new_data
    dump(merged, path)
    return validated


def delete_object(root: Path, kind: str, key: str) -> None:
    spec = KIND_SPECS[kind]
    if spec.singleton:
        raise ValueError(
            f"{kind} is a singleton file and can't be deleted, only edited"
        )
    path = _path_for(root, spec, key)
    if not path.exists():
        raise NotFoundError(f"{kind}/{key} not found")
    path.unlink()
