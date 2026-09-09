"""Load the file tree, build the symbol table, resolve references.

Implements CLAUDE.md §3, "The linker pass": load every file, derive or
look up an OID for every object, resolve every `Ref` field against that
table, and hard-fail on a collision or an unresolved reference.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from . import oid as oidmod
from .io.yaml_io import load
from .models import (
    CodeList,
    CommentDef,
    Dataset,
    DocumentsFile,
    MethodDef,
    Ref,
    RefByOid,
    ResultDisplay,
    StandardsFile,
    StudyFile,
    ValueListDef,
    WhereClauseDef,
    parse_codelist,
)


class LinkError(Exception):
    """A hard-fail condition from the linker pass: collision or unresolved reference."""


@dataclass
class LoadedTree:
    root: Path
    study: StudyFile
    standards: StandardsFile
    documents: DocumentsFile
    datasets: dict[str, tuple[Path, Dataset]] = field(default_factory=dict)
    codelists: dict[str, tuple[Path, CodeList]] = field(default_factory=dict)
    methods: dict[str, tuple[Path, MethodDef]] = field(default_factory=dict)
    comments: dict[str, tuple[Path, CommentDef]] = field(default_factory=dict)
    valuelists: dict[str, tuple[Path, ValueListDef]] = field(default_factory=dict)
    whereclauses: dict[str, tuple[Path, WhereClauseDef]] = field(default_factory=dict)
    analysis_results: dict[str, tuple[Path, ResultDisplay]] = field(
        default_factory=dict
    )


def _validate(model_validate, data, path: Path):
    """Wrap a pydantic model_validate call so a bad file fails with its path attached,
    as a LinkError the CLI already renders cleanly, instead of a raw ValidationError
    traceback that names the model but not which of possibly dozens of files it came from.
    """
    try:
        return model_validate(data)
    except ValidationError as exc:
        raise LinkError(f"{path}: {exc}") from exc


def _load_dir(root: Path, subdir: str, parse):
    result: dict[str, tuple[Path, object]] = {}
    directory = root / subdir
    if not directory.is_dir():
        return result
    for path in sorted(directory.rglob("*.yaml")):
        rel = path.relative_to(directory).with_suffix("").as_posix()
        result[rel] = (path, _validate(parse, load(path), path))
    return result


def _ordered_datasets(
    by_name: dict[str, tuple[Path, Dataset]], order: list[str]
) -> dict[str, tuple[Path, Dataset]]:
    """study.yaml's dataset_order: first (each name at most once - a repeat or a name
    that doesn't match any dataset contributes nothing, silently; define lint reports
    the latter as a stale-reference warning, since this loader has no reporting channel
    of its own), then every remaining dataset alphabetically, exactly like today's
    behaviour for a study that has never set dataset_order:.
    """
    ordered: dict[str, tuple[Path, Dataset]] = {}
    for name in order:
        if name in by_name and name not in ordered:
            ordered[name] = by_name[name]
    for name in sorted(by_name):
        if name not in ordered:
            ordered[name] = by_name[name]
    return ordered


def load_tree(root: Path) -> LoadedTree:
    """Load every file under `root` into its pydantic model, keyed by relative path."""
    study_path = root / "study.yaml"
    study = _validate(StudyFile.model_validate, load(study_path), study_path)
    standards_path = root / "standards.yaml"
    standards = (
        _validate(StandardsFile.model_validate, load(standards_path), standards_path)
        if standards_path.exists()
        else StandardsFile(standards=[])
    )
    documents_path = root / "documents.yaml"
    documents = (
        _validate(DocumentsFile.model_validate, load(documents_path), documents_path)
        if documents_path.exists()
        else DocumentsFile(documents=[])
    )

    datasets_by_path = _load_dir(root, "datasets", Dataset.model_validate)
    datasets = _ordered_datasets(
        {ds.name: (path, ds) for path, ds in datasets_by_path.values()},
        study.dataset_order,
    )

    codelists_by_path = _load_dir(root, "codelists", parse_codelist)
    codelists = {cl.name: (path, cl) for path, cl in codelists_by_path.values()}

    methods = _load_dir(root, "methods", MethodDef.model_validate)
    comments = _load_dir(root, "comments", CommentDef.model_validate)
    whereclauses = _load_dir(root, "whereclauses", WhereClauseDef.model_validate)
    analysis_results = _load_dir(root, "analysis-results", ResultDisplay.model_validate)

    valuelists_by_path = _load_dir(root, "valuelists", ValueListDef.model_validate)
    valuelists = {
        f"{vl.dataset}/{vl.variable}": (path, vl)
        for path, vl in valuelists_by_path.values()
    }

    return LoadedTree(
        root=root,
        study=study,
        standards=standards,
        documents=documents,
        datasets=datasets,
        codelists=codelists,
        methods=methods,
        comments=comments,
        valuelists=valuelists,
        whereclauses=whereclauses,
        analysis_results=analysis_results,
    )


@dataclass
class _Registration:
    kind: str
    key: str
    oid: str
    path: Path


class SymbolTable:
    """kind, key -> final OID, plus the reverse map used for collision detection."""

    def __init__(self) -> None:
        self._by_key: dict[tuple[str, str], _Registration] = {}
        self._by_oid: dict[str, _Registration] = {}
        self._referenced: set[tuple[str, str]] = set()

    def register(
        self, kind: str, key: str, derived_oid: str, override: str | None, path: Path
    ) -> str:
        final_oid = oidmod.resolve_oid(override, derived_oid)
        existing = self._by_key.get((kind, key))
        if existing is not None:
            raise LinkError(
                f"duplicate {kind} name {key!r}: defined in {existing.path} and {path}"
            )
        collision = self._by_oid.get(final_oid)
        if collision is not None:
            raise LinkError(
                f"OID collision on {final_oid!r}: {collision.kind} {collision.key!r} "
                f"({collision.path}) and {kind} {key!r} ({path})"
            )
        reg = _Registration(kind, key, final_oid, path)
        self._by_key[(kind, key)] = reg
        self._by_oid[final_oid] = reg
        return final_oid

    def lookup(self, kind: str, key: str) -> str | None:
        reg = self._by_key.get((kind, key))
        if reg is None:
            return None
        self._referenced.add((kind, key))
        return reg.oid

    def lookup_own(self, kind: str, key: str) -> str | None:
        """Like lookup(), but for an object retrieving its own registered OID during
        emission (every `_xxx_def` in xml_emit.py does this, to respect an `oid:`
        override without re-deriving it) - not a real cross-reference, so it must NOT
        mark the object as referenced. Using lookup() here would make orphans() always
        return empty: build_odm's own emission loop touches every codelist/method/
        comment/whereclause's own key regardless of whether anything else references it.
        """
        reg = self._by_key.get((kind, key))
        return reg.oid if reg is not None else None

    def orphans(self, kinds: tuple[str, ...]) -> list[tuple[str, str, Path]]:
        return [
            (reg.kind, reg.key, reg.path)
            for (kind, key), reg in self._by_key.items()
            if kind in kinds and (kind, key) not in self._referenced
        ]


def _norm(name: str) -> str:
    return oidmod.slugify(name)


def _norm_path(path_str: str) -> str:
    return oidmod.path_to_slug(path_str)


def standard_name_counts(tree: LoadedTree) -> dict[str, int]:
    counts: dict[str, int] = {}
    for name, _ in _iter_standards(tree):
        key = _norm(name)
        counts[key] = counts.get(key, 0) + 1
    return counts


def standard_lookup_key(
    counts: dict[str, int], name: str, publishing_set: str | None, version: str
) -> str:
    """Symbol-table key for a `standard`, keeping registration (build_symbol_table) and
    lookup (xml_emit's def:Standards loop) in sync. A bare Name is the key whenever it's
    unique - that's what a hand-authored `standard: <name>` reference resolves through, per
    CLAUDE.md's derivation table (STD.<name>), and the only form worth writing by hand. Two
    def:Standard entries can still legitimately share a Name on import - most commonly two
    versions of the same CT or IG standard, coexisting because different parts of the
    submission were built against different vintages - distinguished by PublishingSet and/or
    Version; those get a qualified key instead, reachable only by {oid: ...} (nothing needs
    to reference one of them by bare name, since dataset.standard: always targets exactly one,
    unambiguously-named IG standard by convention).
    """
    plain = _norm(name)
    if counts.get(plain, 0) == 1:
        return plain
    parts = [plain]
    if publishing_set is not None:
        parts.append(_norm(publishing_set))
    parts.append(_norm(version))
    return ".".join(parts)


def build_symbol_table(tree: LoadedTree) -> SymbolTable:
    table = SymbolTable()

    std_name_counts = standard_name_counts(tree)
    for name, (path, std) in _iter_standards(tree):
        key = standard_lookup_key(
            std_name_counts, name, std.publishing_set, std.version
        )
        table.register("standard", key, oidmod.standard_oid(name), std.oid, path)

    for name, (path, doc) in _iter_documents(tree):
        table.register(
            "document", _norm(name), oidmod.leaf_document_oid(name), doc.oid, path
        )

    for name, (path, ds) in tree.datasets.items():
        table.register("dataset", _norm(name), oidmod.itemgroup_oid(name), ds.oid, path)
        for var in ds.variables:
            if var.same_as is not None:
                # An alias variable has no ItemDef, and so no OID, of its own:
                # it emits a second ItemRef against the same_as target's OID
                # (CLAUDE.md §3, "No OR" - see xml_emit._item_ref_for_variable).
                continue
            table.register(
                "item",
                f"{_norm(name)}.{_norm(var.name)}",
                oidmod.item_oid(name, var.name),
                var.oid,
                path,
            )

    for name, (path, cl) in tree.codelists.items():
        table.register("codelist", _norm(name), oidmod.codelist_oid(name), cl.oid, path)

    for relpath, (path, md) in tree.methods.items():
        table.register(
            "method", _norm_path(relpath), oidmod.method_oid(relpath), md.oid, path
        )

    for relpath, (path, com) in tree.comments.items():
        table.register(
            "comment", _norm_path(relpath), oidmod.comment_oid(relpath), com.oid, path
        )

    for relpath, (path, wc) in tree.whereclauses.items():
        table.register(
            "whereclause",
            _norm_path(relpath),
            oidmod.whereclause_named_oid(relpath),
            wc.oid,
            path,
        )

    for key, (path, vl) in tree.valuelists.items():
        table.register(
            "valuelist",
            f"{_norm(vl.dataset)}.{_norm(vl.variable)}",
            oidmod.valuelist_oid(vl.dataset, vl.variable),
            vl.oid,
            path,
        )
        for entry in vl.entries:
            item_key = f"{_norm(vl.dataset)}.{_norm(vl.variable)}.{_norm(entry.name)}"
            table.register(
                "item",
                item_key,
                oidmod.item_value_level_oid(vl.dataset, vl.variable, entry.name),
                entry.item.oid,
                path,
            )
            if isinstance(entry.where, list):
                table.register(
                    "whereclause",
                    item_key,
                    oidmod.whereclause_inline_oid(vl.dataset, vl.variable, entry.name),
                    None,
                    path,
                )

    for relpath, (path, rd) in tree.analysis_results.items():
        table.register(
            "resultdisplay",
            _norm_path(relpath),
            oidmod.result_display_oid(relpath),
            rd.oid,
            path,
        )
        for result in rd.results:
            table.register(
                "analysisresult",
                f"{_norm_path(relpath)}.{_norm(result.name)}",
                oidmod.analysis_result_oid(relpath, result.name),
                result.oid,
                path,
            )

    return table


def _iter_standards(tree: LoadedTree):
    path = tree.root / "standards.yaml"
    for std in tree.standards.standards:
        yield std.name, (path, std)


def _iter_documents(tree: LoadedTree):
    path = tree.root / "documents.yaml"
    for doc in tree.documents.documents:
        yield doc.name, (path, doc)


def resolve_ref(
    table: SymbolTable, kind: str, ref: Ref | None, *, context: str
) -> str | None:
    """Resolve a single-segment or path-form reference field to its OID."""
    if ref is None:
        return None
    if isinstance(ref, RefByOid):
        return ref.oid
    key = (
        _norm_path(ref) if kind in ("method", "comment", "whereclause") else _norm(ref)
    )
    oid_value = table.lookup(kind, key)
    if oid_value is None:
        raise LinkError(f"unresolved reference: {kind} {ref!r} ({context})")
    return oid_value


def resolve_item_ref(table: SymbolTable, ref: Ref, *, context: str) -> str:
    """Resolve a dotted `DATASET.VARIABLE` or `DATASET.VARIABLE.ENTRY` item reference."""
    if isinstance(ref, RefByOid):
        return ref.oid
    parts = ref.split(".")
    if len(parts) not in (2, 3):
        raise LinkError(
            f"item reference must be DATASET.VARIABLE or DATASET.VARIABLE.ENTRY, got {ref!r} ({context})"
        )
    key = ".".join(_norm(p) for p in parts)
    oid_value = table.lookup("item", key)
    if oid_value is None:
        raise LinkError(f"unresolved reference: item {ref!r} ({context})")
    return oid_value


def resolve_scoped_item_ref(
    table: SymbolTable, dataset_name: str, ref: Ref, *, context: str
) -> str:
    """Resolve a bare variable name against a known dataset (ARM AnalysisDataset.variables)."""
    if isinstance(ref, RefByOid):
        return ref.oid
    key = f"{_norm(dataset_name)}.{_norm(ref)}"
    oid_value = table.lookup("item", key)
    if oid_value is None:
        raise LinkError(f"unresolved reference: item {dataset_name}.{ref} ({context})")
    return oid_value


def resolve_valuelist_ref(
    table: SymbolTable, current_dataset: str, ref: Ref, *, context: str
) -> str:
    """Resolve `valuelist:` - either `VARIABLE` (within the current dataset) or `DATASET.VARIABLE`."""
    if isinstance(ref, RefByOid):
        return ref.oid
    parts = ref.split(".")
    if len(parts) == 1:
        dataset_name, variable_name = current_dataset, parts[0]
    elif len(parts) == 2:
        dataset_name, variable_name = parts
    else:
        raise LinkError(
            f"valuelist reference must be VARIABLE or DATASET.VARIABLE, got {ref!r} ({context})"
        )
    key = f"{_norm(dataset_name)}.{_norm(variable_name)}"
    oid_value = table.lookup("valuelist", key)
    if oid_value is None:
        raise LinkError(f"unresolved reference: valuelist {ref!r} ({context})")
    return oid_value
