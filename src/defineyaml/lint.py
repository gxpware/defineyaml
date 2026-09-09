"""`define lint` (CLAUDE.md build order step 4): everything Define-XML's XSD and this
tool's own pydantic models don't already catch - cross-reference integrity, orphaned
objects, and the project's own documented conventions (CLAUDE.md §3/§6/§7.5).

Deliberately tolerant, the same posture as webui/usages.py: one file with a schema error
is reported on its own, and every other check still runs against whatever *did* load -
unlike `define build`'s linker pass, which hard-fails the whole run on the first problem
(correctly so; a build should never silently emit a partial define.xml). A linter's job is
finding as much as it can in one pass, not stopping at the first thing wrong.

Severities:
  - "error": would also fail `define build` (a duplicate slug, an unresolved reference,
    a file that doesn't validate against its model).
  - "warning": schema-valid but worth a human's attention - a convention drifted from,
    an unreferenced object, a likely oversight.
  - "info": CLAUDE.md §3's `{oid: ...}`/`oid:` escape hatches, surfaced "for visibility,
    not restriction" - not a defect, just something worth a human confirming is
    intentional (round-tripping a define.xml this tool didn't generate) rather than
    something that crept in by accident.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ValidationError

from . import ct
from . import oid as oidmod
from .linker import LinkError, build_symbol_table, load_tree
from .models.common import RefByOid
from .webui import tree as treemod
from .xml_emit import build_odm

_COLLECTION_KINDS = (
    "datasets",
    "codelists",
    "methods",
    "comments",
    "whereclauses",
    "valuelists",
    "analysis_results",
)
_ALL_KINDS = ("study", "standards", "documents", *_COLLECTION_KINDS)

# kinds excluded from the duplicate-name/slug-collision scan: CLAUDE.md §3 explicitly
# allows two def:Standard entries to share a bare Name (different CT vintages or IG
# versions) - the real ambiguity there is caught by standard_lookup_key's qualified key
# at xref-integrity time, not by a same-kind-same-slug scan like this one.
_NAME_SCAN_EXCLUDED = ("study", "standards", "documents")


@dataclass
class LintFinding:
    severity: str  # "error" | "warning" | "info"
    rule: str
    message: str
    path: str | None = None

    def __str__(self) -> str:
        loc = f" ({self.path})" if self.path else ""
        return f"{self.severity}: [{self.rule}] {self.message}{loc}"


LoadedObjects = dict[tuple[str, str], tuple[BaseModel, Path]]


def run_lint(root: Path) -> list[LintFinding]:
    findings: list[LintFinding] = []
    objects = _load_tolerant(root, findings)
    _check_xref_and_orphans(root, findings)
    _check_duplicate_names_and_slug_collisions(objects, findings)
    _check_analysis_ct(objects, findings)
    _check_expression_contexts(objects, findings)
    _check_undocumented_methods(objects, findings)
    _check_valuelist_where_shape(objects, findings)
    _check_oid_visibility(objects, findings)
    _check_dataset_order(objects, findings)
    _check_collected_origin_page_ref(objects, findings)
    return findings


def _path_for(root: Path, kind: str, key: str) -> Path:
    spec = treemod.KIND_SPECS[kind]
    return (
        root / spec.filename if spec.singleton else root / spec.subdir / f"{key}.yaml"
    )


def _load_tolerant(root: Path, findings: list[LintFinding]) -> LoadedObjects:
    """Every object that validates against its own model, keyed by (kind, key) - one
    validation failure is reported and skipped, not fatal to the objects around it.
    """
    objects: LoadedObjects = {}
    for kind in _ALL_KINDS:
        for item in treemod.list_items(root, kind):
            key = item["key"]
            path = _path_for(root, kind, key)
            try:
                data = treemod.read_object(root, kind, key)
                model = treemod.validate(kind, data)
            except ValidationError as exc:
                findings.append(LintFinding("error", "schema", str(exc), str(path)))
                continue
            except Exception as exc:  # a YAML file that doesn't even parse as a mapping
                findings.append(
                    LintFinding("error", "schema", f"failed to load: {exc}", str(path))
                )
                continue
            objects[(kind, key)] = (model, path)
    return objects


def _check_xref_and_orphans(root: Path, findings: list[LintFinding]) -> None:
    """Reuses the real build pipeline (linker + xml_emit) rather than re-implementing
    reference resolution - lint and build can never disagree about what resolves. The
    tradeoff: like `build` itself, this stops at the first LinkError (a duplicate name,
    an unresolved reference, an OID collision) rather than collecting every one - a
    genuinely different, harder problem (register()/resolve_ref() raise immediately by
    design) left to a future pass. Everything else this module checks is independent of
    this succeeding, so one unresolved reference doesn't blank out the rest of the report.
    """
    try:
        tree = load_tree(root)
        table = build_symbol_table(tree)
        build_odm(tree, table)
    except LinkError as exc:
        findings.append(LintFinding("error", "xref", str(exc)))
        return
    # def:WhereClauseDef orphans this also catches ARM's use of one (an
    # arm:AnalysisDataset's where: resolves through the same table.lookup("whereclause",
    # ...) call as a value list entry's does, marking it referenced either way) - so
    # "named where clauses unused across ARM + value lists" falls out of this for free,
    # not as a separate scan.
    for kind, key, path in table.orphans(
        ("codelist", "method", "comment", "whereclause")
    ):
        findings.append(
            LintFinding(
                "warning", "orphan", f"{kind} {key!r} is never referenced", str(path)
            )
        )


def _slug_for(kind: str, key: str, data: dict) -> str | None:
    """Mirrors linker.py's own key derivation (name-based for most kinds, path-based for
    the "no Name in Define-XML" kinds, dataset+variable for value lists) - the same
    normalisation a real build would apply when registering this object in the symbol
    table. Written independently of webui/usages.py's identical _identity_slug rather
    than importing it, since that one is that module's own private helper.
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


def _check_duplicate_names_and_slug_collisions(
    objects: LoadedObjects, findings: list[LintFinding]
) -> None:
    """Two independent checks sharing one slug computation:
    - same kind, same slug -> "error": build_symbol_table's register() would hard-fail
      on this too (CLAUDE.md's "a collision is a naming problem the humans should fix"),
      surfaced here before a full build is needed to discover it, and every such
      collision is listed in one pass rather than just the first.
    - same slug, different kinds -> "warning": not a build failure (OIDs are
      kind-prefixed, so IG.ADSL and MT.ADSL can't collide), but a name reused across
      kinds reads as confusing in a report or a review, worth a human's attention.
    """
    by_kind_slug: dict[str, dict[str, list[tuple[str, Path]]]] = {}
    by_slug: dict[str, list[tuple[str, str, Path]]] = {}
    for (kind, key), (model, path) in objects.items():
        if kind in _NAME_SCAN_EXCLUDED:
            continue
        slug = _slug_for(kind, key, model.model_dump())
        if slug is None:
            continue
        by_kind_slug.setdefault(kind, {}).setdefault(slug, []).append((key, path))
        by_slug.setdefault(slug, []).append((kind, key, path))

    for kind, slugs in by_kind_slug.items():
        for slug, entries in slugs.items():
            if len(entries) > 1:
                where = ", ".join(str(p) for _, p in entries)
                findings.append(
                    LintFinding(
                        "error",
                        "slug-collision",
                        f"{len(entries)} {kind} objects derive the same OID slug {slug!r}: {where}",
                    )
                )

    for slug, entries in by_slug.items():
        kinds_involved = {k for k, _, _ in entries}
        if len(kinds_involved) > 1:
            where = ", ".join(f"{k} {key!r} ({path})" for k, key, path in entries)
            findings.append(
                LintFinding(
                    "warning",
                    "duplicate-name",
                    f"name {slug!r} is used by more than one object kind: {where}",
                )
            )


def _check_analysis_ct(objects: LoadedObjects, findings: list[LintFinding]) -> None:
    """arm:AnalysisResult's AnalysisReason/AnalysisPurpose are XSD-extensible unions
    (CLAUDE.md §8, "Resolved") - a sponsor value is schema-valid, so this is a warning
    flagging it for a second look, not a hard error.
    """
    for (kind, key), (model, path) in objects.items():
        if kind != "analysis_results":
            continue
        for result in model.results:
            if result.reason not in ct.ANALYSIS_REASON_CT:
                findings.append(
                    LintFinding(
                        "warning",
                        "analysis-ct",
                        f"result {result.name!r}: reason {result.reason!r} is not in the CDISC 2.1 controlled list - confirm this sponsor extension is intentional",
                        str(path),
                    )
                )
            if result.purpose not in ct.ANALYSIS_PURPOSE_CT:
                findings.append(
                    LintFinding(
                        "warning",
                        "analysis-ct",
                        f"result {result.name!r}: purpose {result.purpose!r} is not in the CDISC 2.1 controlled list - confirm this sponsor extension is intentional",
                        str(path),
                    )
                )


def _check_expression_contexts(
    objects: LoadedObjects, findings: list[LintFinding]
) -> None:
    """CLAUDE.md §7.5: 'Declare the permitted set once in study.yaml... and lint every
    context: against it' - applies to both MethodDef.expressions[].context and
    arm:ProgrammingCode's context (AnalysisResult.programming_code.context), the two
    FormalExpression-shaped fields in the model. Opt-in: a study.yaml that hasn't
    declared expression_contexts: at all is a project that hasn't adopted the
    convention yet, not one violating it, so this is silent rather than flagging every
    context ever written.
    """
    study_entry = objects.get(("study", "study"))
    if study_entry is None:
        return
    study_model, _ = study_entry
    allowed = set(study_model.expression_contexts)
    if not allowed:
        return
    for (kind, key), (model, path) in objects.items():
        if kind == "methods":
            for expr in model.expressions:
                if expr.context not in allowed:
                    findings.append(
                        LintFinding(
                            "warning",
                            "expression-context",
                            f"context {expr.context!r} is not declared in study.yaml's expression_contexts:",
                            str(path),
                        )
                    )
        if kind == "analysis_results":
            for result in model.results:
                pc = result.programming_code
                if (
                    pc is not None
                    and pc.context is not None
                    and pc.context not in allowed
                ):
                    findings.append(
                        LintFinding(
                            "warning",
                            "expression-context",
                            f"result {result.name!r}: programming_code context {pc.context!r} is not declared in study.yaml's expression_contexts:",
                            str(path),
                        )
                    )


def _check_undocumented_methods(
    objects: LoadedObjects, findings: list[LintFinding]
) -> None:
    """MethodDef._check_expressions already hard-requires description: whenever
    expressions: is present (CLAUDE.md §7.5). The gap that leaves open is a method with
    *neither* - name/type and nothing else explaining what it does, which is schema-valid
    (both fields are optional) but useless to a reviewer or the define.html reader.
    """
    for (kind, key), (model, path) in objects.items():
        if kind != "methods":
            continue
        if not model.description and not model.expressions:
            findings.append(
                LintFinding(
                    "warning",
                    "undocumented-method",
                    f"method {key!r} has neither description: nor expressions: - nothing explains what it does",
                    str(path),
                )
            )


def _check_collected_origin_page_ref(
    objects: LoadedObjects, findings: list[LintFinding]
) -> None:
    """Define-XML business rule: a def:Origin's def:DocumentRef/def:PDFPageRef is
    *required* (not merely allowed) when Type="Collected" and Source is Investigator or
    Subject - a collected field is assumed to have an annotated CRF page. Neither the XSD
    (def:DocumentRef and def:PDFPageRef are both optional there) nor the model enforces
    it, so it's a warning: the origin fits the condition but points at no page.
    """

    def origins(model, kind):
        if kind == "datasets":
            for v in model.variables:
                if v.origin is not None:
                    yield v.name, v.origin
        elif kind == "valuelists":
            for e in model.entries:
                if e.item.origin is not None:
                    yield e.name, e.item.origin

    for (kind, key), (model, path) in objects.items():
        if kind not in ("datasets", "valuelists"):
            continue
        for where, origin in origins(model, kind):
            if (
                origin.type == "Collected"
                and origin.data_source in ("Investigator", "Subject")
                and origin.document is None
                and origin.pages is None
            ):
                findings.append(
                    LintFinding(
                        "warning",
                        "collected-origin-page-ref",
                        f"{key}:{where} origin is Collected / {origin.data_source} but cites no "
                        "CRF page - Define-XML requires a def:DocumentRef with def:PDFPageRef here",
                        str(path),
                    )
                )


def _where_shape(where) -> str:
    return "inline" if isinstance(where, list) else "named"


def _check_valuelist_where_shape(
    objects: LoadedObjects, findings: list[LintFinding]
) -> None:
    """Not a Define-XML rule - a project-consistency smell. A value list's entries each
    pick their where: independently (a named reference, string/{oid: ...}, or an inline
    condition list), and either is always valid, but a value list that mixes the two
    styles across its own entries reads as if it grew ad hoc rather than by one
    consistent authoring convention, which is worth a second look.
    """
    for (kind, key), (model, path) in objects.items():
        if kind != "valuelists":
            continue
        shapes = {_where_shape(entry.where) for entry in model.entries}
        if len(shapes) > 1:
            findings.append(
                LintFinding(
                    "warning",
                    "valuelist-where-shape",
                    f"value list {key!r} mixes named where: references and inline condition lists across its entries",
                    str(path),
                )
            )


def _check_oid_visibility(objects: LoadedObjects, findings: list[LintFinding]) -> None:
    """CLAUDE.md §3: both the `oid:` override and the `{oid: ...}` reference-side escape
    hatch exist for round-tripping a define.xml this tool didn't generate - legitimate,
    but 'define lint reports overrides so they stay visible rather than accumulating
    silently.' This walks every loaded object's full field tree (not just the fields
    this module happens to know about), so a new model growing an oid: or a Ref-typed
    field is covered automatically, without lint needing to be told about it.
    """
    for (kind, key), (model, path) in objects.items():
        _walk_for_oid_visibility(model, f"{kind}/{key}", path, findings)


def _walk_for_oid_visibility(
    obj, location: str, path: Path, findings: list[LintFinding]
) -> None:
    if isinstance(obj, RefByOid):
        findings.append(
            LintFinding(
                "info",
                "literal-oid-ref",
                f"{location} references {{oid: {obj.oid}}} directly, bypassing the symbol table - confirm this is round-tripping an OID this tool didn't derive, not something that could be a normal name reference",
                str(path),
            )
        )
        return
    if isinstance(obj, BaseModel):
        for field_name, field_info in obj.__class__.model_fields.items():
            value = getattr(obj, field_name)
            if (
                field_name == "oid"
                and value is not None
                and not field_info.is_required()
            ):
                findings.append(
                    LintFinding(
                        "info",
                        "oid-override",
                        f"{location}.oid = {value!r} is an explicit OID override - confirm it's intentional (round-tripping an existing define.xml's OIDs), not left over from an import",
                        str(path),
                    )
                )
            _walk_for_oid_visibility(value, f"{location}.{field_name}", path, findings)
        return
    if isinstance(obj, list):
        for i, item in enumerate(obj):
            _walk_for_oid_visibility(item, f"{location}[{i}]", path, findings)
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            _walk_for_oid_visibility(v, f"{location}.{k}", path, findings)


def _check_dataset_order(objects: LoadedObjects, findings: list[LintFinding]) -> None:
    """study.yaml's dataset_order: names datasets by Dataset.name:, not by file key -
    a rename that doesn't update dataset_order: (or a plain typo) leaves a stale entry
    that _ordered_datasets() (linker.py) silently drops rather than erroring on, since
    the loader has no reporting channel of its own. This is where that gets surfaced.
    """
    study_entry = objects.get(("study", "study"))
    if study_entry is None:
        return
    study_model, path = study_entry
    if not study_model.dataset_order:
        return
    real_names = {
        model.name
        for (kind, _key), (model, _path) in objects.items()
        if kind == "datasets"
    }
    for name in study_model.dataset_order:
        if name not in real_names:
            findings.append(
                LintFinding(
                    "error",
                    "dataset-order",
                    f"dataset_order: names {name!r}, which doesn't match any dataset's name: - a stale entry from a rename, or a typo",
                    str(path),
                )
            )
