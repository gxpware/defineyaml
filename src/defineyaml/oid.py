"""OID derivation, per CLAUDE.md §3.

OIDs are never stored; they are a pure function of (kind, name/path). Same
inputs always give the same OID, on any machine, in any branch - that
determinism is what keeps concurrent edits from colliding on identifiers.
"""

from __future__ import annotations

import re

_SLUG_INVALID = re.compile(r"[^A-Z0-9._]+")
_SLUG_REPEAT = re.compile(r"\.{2,}")


def slugify(text: str) -> str:
    """Uppercase; non [A-Z0-9._] -> '.'; collapse repeats; strip separators."""
    slug = _SLUG_REPEAT.sub(".", _SLUG_INVALID.sub(".", text.upper())).strip(".")
    if not slug:
        raise ValueError(f"slug of {text!r} is empty after normalisation")
    return slug


def path_to_slug(path: str) -> str:
    """Derive a slug from a file path, e.g. 'adsl/trtsdt' -> 'ADSL.TRTSDT'.

    `__` splits a segment too, alongside `/` and `\\`: comments and value
    lists are one flat file per object (CLAUDE.md §2), named
    `<dataset>__<variable>.yaml` rather than nested in a directory per
    dataset, and the two conventions compose (e.g. a value-level method at
    `methods/adlb/aval__alt.yaml` -> 'ADLB.AVAL.ALT').
    """
    parts = [p for p in re.split(r"[\\/]+|__", path) if p]
    if not parts:
        raise ValueError(f"path {path!r} has no components")
    return ".".join(slugify(p) for p in parts)


def resolve_oid(explicit: str | None, derived: str) -> str:
    """An `oid:` override always wins over the derived value."""
    return explicit if explicit is not None else derived


def standard_oid(name: str) -> str:
    return f"STD.{slugify(name)}"


def itemgroup_oid(dataset: str) -> str:
    return f"IG.{slugify(dataset)}"


def item_oid(dataset: str, variable: str) -> str:
    return f"IT.{slugify(dataset)}.{slugify(variable)}"


def item_value_level_oid(dataset: str, variable: str, entry: str) -> str:
    return f"IT.{slugify(dataset)}.{slugify(variable)}.{slugify(entry)}"


def codelist_oid(name: str) -> str:
    return f"CL.{slugify(name)}"


def method_oid(path: str) -> str:
    return f"MT.{path_to_slug(path)}"


def comment_oid(path: str) -> str:
    return f"COM.{path_to_slug(path)}"


def valuelist_oid(dataset: str, variable: str) -> str:
    return f"VL.{slugify(dataset)}.{slugify(variable)}"


def whereclause_inline_oid(dataset: str, variable: str, entry: str) -> str:
    return f"WC.{slugify(dataset)}.{slugify(variable)}.{slugify(entry)}"


def whereclause_named_oid(path: str) -> str:
    return f"WC.{path_to_slug(path)}"


def leaf_dataset_oid(dataset: str) -> str:
    return f"LF.{slugify(dataset)}"


def leaf_document_oid(name: str) -> str:
    return f"LF.{slugify(name)}"


def result_display_oid(path: str) -> str:
    return f"RD.{path_to_slug(path)}"


def analysis_result_oid(path: str, entry: str) -> str:
    return f"AR.{path_to_slug(path)}.{slugify(entry)}"
