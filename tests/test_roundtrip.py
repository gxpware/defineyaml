"""The round-trip hard gate (CLAUDE.md §6 step 3): real define.xml -> `define import` ->
YAML tree -> `define build` -> rebuilt define.xml -> XSD validation -> structural
equivalence against the original.

Fixtures are the two CDISC-published example submissions, vendored (with the schema
tree needed to validate them) under tests/fixtures/definexml/ so this runs in any clone.

"Canonicalised XML is equivalent" (not raw bytes) is operationalised per-object, not as
one whole-document comparison: this tool deliberately re-orders top-level children to the
XSD's mandated sequence (def:Standards, ValueListDef, WhereClauseDef, ItemGroupDef,
ItemDef, CodeList, MethodDef, CommentDef, leaf, arm:AnalysisResultDisplays - see
xml_emit.build_odm), which a source file need not already follow. A whole-document C14N
diff would be dominated by that reordering rather than by actual content loss. Comparing
each OID-bearing object's own canonicalised subtree, matched between original and rebuilt
by its OID (which this tool's derive-or-preserve design keeps stable end to end - see
CLAUDE.md §3), tests the same thing the instruction is after - nothing lost or corrupted
per object - without that noise.
"""

from __future__ import annotations

import copy
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pytest
from lxml import etree

from defineyaml.linker import LinkError
from defineyaml.xml_emit import ARM_NS, DEF_NS, ODM_NS, XLINK_NS, write_define_xml
from defineyaml.xml_import import import_define_xml

FIXTURES = Path(__file__).parent / "fixtures" / "definexml"
SCHEMA_PATH = FIXTURES / "schema" / "cdisc-arm-1.0" / "arm1-0-0.xsd"
EXAMPLES = {
    "adam": FIXTURES / "examples" / "adam.xml",
    "sdtm": FIXTURES / "examples" / "sdtm.xml",
}

_SCHEMA = etree.XMLSchema(etree.parse(str(SCHEMA_PATH)))


def _o(tag: str) -> str:
    return f"{{{ODM_NS}}}{tag}"


def _d(tag: str) -> str:
    return f"{{{DEF_NS}}}{tag}"


def _a(tag: str) -> str:
    return f"{{{ARM_NS}}}{tag}"


# Every OID/ID-bearing object kind this tool models, as (local name, namespace, id attr).
# Elements with no OID/ID of their own - ItemGroupDef's Alias, def:AnnotatedCRF,
# def:SupplementalDoc - are deliberately absent: there's nothing for an object-identity
# check to key on, so their content survival is checked elsewhere (dedicated tests, or the
# importer's "not implemented" reporting for anything still unmodeled), not by this suite.
OID_BEARING = [
    ("ItemGroupDef", ODM_NS, "OID"),
    ("ItemDef", ODM_NS, "OID"),
    ("CodeList", ODM_NS, "OID"),
    ("MethodDef", ODM_NS, "OID"),
    ("CommentDef", DEF_NS, "OID"),
    ("WhereClauseDef", DEF_NS, "OID"),
    ("ValueListDef", DEF_NS, "OID"),
    ("leaf", DEF_NS, "ID"),
    ("Standard", DEF_NS, "OID"),
    ("ResultDisplay", ARM_NS, "OID"),
    ("AnalysisResult", ARM_NS, "OID"),
]

# Every reference attribute the emitter writes (xml_emit.py), as (local name, namespace,
# attr name, attr namespace or None if unprefixed).
REF_ATTRS = [
    ("ItemRef", ODM_NS, "ItemOID", None),
    ("ItemRef", ODM_NS, "MethodOID", None),
    ("CodeListRef", ODM_NS, "CodeListOID", None),
    ("RangeCheck", ODM_NS, "ItemOID", DEF_NS),
    ("WhereClauseRef", DEF_NS, "WhereClauseOID", None),
    ("ValueListRef", DEF_NS, "ValueListOID", None),
    ("ItemGroupDef", ODM_NS, "StandardOID", DEF_NS),
    # DocumentRef@leafID and CodeList@StandardOID are handled separately below (with a known,
    # narrower gap each) - ItemDef's def:CommentOID likewise, in
    # test_itemdef_comment_oid_references_survive, since def:CommentOID appears on other
    # element kinds this list doesn't cover.
    ("AnalysisDataset", ARM_NS, "ItemGroupOID", None),
    ("AnalysisVariable", ARM_NS, "ItemOID", None),
    ("AnalysisResult", ARM_NS, "ParameterOID", None),
]


@dataclass
class RoundTrip:
    name: str
    source_xml: Path
    original: etree._ElementTree
    rebuilt: etree._ElementTree
    dest_tree: Path


# OIDs whose source content is deliberately altered by _patch_known_source_data_issues below -
# excluded from every content-equality check against the (now-inapplicable) original, since the
# whole point of the patch is that they no longer match it.
_PATCHED_SOURCE_OIDS = {"MT.BMISN"}


def _patch_known_source_data_issues(name: str, dest_tree: Path) -> None:
    """Work around data quality issues in the CDISC-published example itself - not bugs
    in this tool - so the round trip can run. Each is called out explicitly rather than
    silently normalised, and is covered by its own dedicated test elsewhere in this file.
    """
    if name == "sdtm":
        # methods/bmisn.yaml: the source XML's MethodDef OID="MT.BMISN" has two
        # FormalExpression elements with byte-for-byte identical (and unusually long,
        # prose-like) Context text, differing only in Code. CLAUDE.md §7.5 decides
        # "Duplicate Context within one method -> error", enforced by
        # MethodDef._check_expressions - correctly, per test_sdtm_duplicate_context_is_rejected
        # below. Patched here purely so the rest of the suite can exercise a full round trip.
        path = dest_tree / "methods" / "bmisn.yaml"
        text = path.read_text()
        patched, count = re.subn(r"(- context: ')", r"\1(variant 2) ", text, count=1)
        assert (
            count == 1
        ), "expected exactly one FormalExpression context to patch in bmisn.yaml"
        path.write_text(patched)


@pytest.fixture(scope="module", params=sorted(EXAMPLES))
def roundtrip(request, tmp_path_factory) -> RoundTrip:
    name = request.param
    source_xml = EXAMPLES[name]
    dest_tree = tmp_path_factory.mktemp(f"{name}-tree")
    import_define_xml(source_xml, dest_tree)
    _patch_known_source_data_issues(name, dest_tree)
    rebuilt_xml = tmp_path_factory.mktemp(f"{name}-out") / "define.xml"
    write_define_xml(dest_tree, rebuilt_xml)
    return RoundTrip(
        name=name,
        source_xml=source_xml,
        original=etree.parse(str(source_xml)),
        rebuilt=etree.parse(str(rebuilt_xml)),
        dest_tree=dest_tree,
    )


def test_sdtm_duplicate_context_is_rejected(tmp_path):
    """CLAUDE.md §7.5's decided rule, exercised against the real source data that motivates
    it, unpatched - proves the enforcement is intentional, not an oversight this suite works
    around silently.
    """
    dest_tree = tmp_path / "tree"
    import_define_xml(EXAMPLES["sdtm"], dest_tree)
    with pytest.raises(LinkError, match="duplicate Context"):
        write_define_xml(dest_tree, tmp_path / "define.xml")


# ---------------------------------------------------------------------------
# XSD validation
# ---------------------------------------------------------------------------


def test_rebuilt_xml_validates_against_xsd(roundtrip: RoundTrip):
    ok = _SCHEMA.validate(roundtrip.rebuilt)
    errors = "\n".join(str(e) for e in _SCHEMA.error_log)
    assert ok, f"{roundtrip.name}: rebuilt define.xml fails XSD validation:\n{errors}"


# ---------------------------------------------------------------------------
# Object survival: every OID survives, none disappear, none appear unexpectedly
# ---------------------------------------------------------------------------


def _oid_sets(tree: etree._ElementTree) -> dict[str, set[str]]:
    return {
        local: {el.get(attr) for el in tree.iter(f"{{{ns}}}{local}")}
        for local, ns, attr in OID_BEARING
    }


@pytest.mark.parametrize("local,ns,attr", OID_BEARING, ids=[t[0] for t in OID_BEARING])
def test_every_object_oid_survives(roundtrip: RoundTrip, local, ns, attr):
    original = {el.get(attr) for el in roundtrip.original.iter(f"{{{ns}}}{local}")}
    rebuilt = {el.get(attr) for el in roundtrip.rebuilt.iter(f"{{{ns}}}{local}")}
    missing = original - rebuilt
    unexpected = rebuilt - original
    assert (
        not missing
    ), f"{roundtrip.name}: {local} OIDs dropped on rebuild: {sorted(missing)}"
    assert not unexpected, f"{roundtrip.name}: {local} OIDs appeared from nowhere on rebuild: {sorted(unexpected)}"


# ---------------------------------------------------------------------------
# Reference survival: every OID reference attribute's value set is preserved
# ---------------------------------------------------------------------------


def _ref_counter(
    tree: etree._ElementTree, local: str, ns: str, attr: str, attr_ns: str | None
) -> Counter:
    qattr = f"{{{attr_ns}}}{attr}" if attr_ns else attr
    return Counter(
        el.get(qattr)
        for el in tree.iter(f"{{{ns}}}{local}")
        if el.get(qattr) is not None
    )


@pytest.mark.parametrize(
    "local,ns,attr,attr_ns",
    [r for r in REF_ATTRS if r[1] is not None],
    ids=[f"{r[0]}@{r[2]}" for r in REF_ATTRS if r[1] is not None],
)
def test_every_reference_survives(roundtrip: RoundTrip, local, ns, attr, attr_ns):
    original = _ref_counter(roundtrip.original, local, ns, attr, attr_ns)
    rebuilt = _ref_counter(roundtrip.rebuilt, local, ns, attr, attr_ns)
    assert original == rebuilt, (
        f"{roundtrip.name}: {local}@{attr} reference multiset changed on rebuild - "
        f"only in original: {original - rebuilt}, only in rebuilt: {rebuilt - original}"
    )


def test_document_ref_leaf_id_references_survive(roundtrip: RoundTrip):
    # def:DocumentRef@leafID appears under Origin, MethodDef, CommentDef, and ARM
    # Documentation/ProgrammingCode/ResultDisplay - all modeled now (MethodDef.documents:
    # and CommentDef.documents: each capture every DocumentRef, not just the first). The
    # one remaining partial is def:AnnotatedCRF/def:SupplementalDoc, modeled as a plain
    # list of document names (no per-ref PDFPageRef) - so the rebuild can be missing a
    # leafID a source put there, but must never invent one.
    original = _ref_counter(roundtrip.original, "DocumentRef", DEF_NS, "leafID", None)
    rebuilt = _ref_counter(roundtrip.rebuilt, "DocumentRef", DEF_NS, "leafID", None)
    unexpected = rebuilt - original
    assert not unexpected, f"{roundtrip.name}: DocumentRef@leafID referenced on rebuild that the source never had: {unexpected}"


def test_methoddef_document_ref_survives(roundtrip: RoundTrip):
    # MethodDef/def:DocumentRef (+ its optional def:PDFPageRef) - a method citing the
    # documentation it's specified in. Both fixtures have one; the ADaM one is a
    # PhysicalRef page, the SDTM one a NamedDestination. Modeled as MethodDef.documents:.
    def method_doc_refs(tree):
        out: dict[str, list[tuple]] = {}
        for md_el in tree.iter(_o("MethodDef")):
            refs = []
            for dr_el in md_el.findall(_d("DocumentRef")):
                pr_el = dr_el.find(_d("PDFPageRef"))
                refs.append(
                    (
                        dr_el.get("leafID"),
                        None
                        if pr_el is None
                        else (
                            pr_el.get("Type"),
                            pr_el.get("PageRefs"),
                            pr_el.get("FirstPage"),
                            pr_el.get("LastPage"),
                            pr_el.get("Title"),
                        ),
                    )
                )
            if refs:
                out[md_el.get("OID")] = refs
        return out

    original = method_doc_refs(roundtrip.original)
    assert original, f"{roundtrip.name}: no MethodDef/DocumentRef in source - fixture assumption is wrong"
    rebuilt = method_doc_refs(roundtrip.rebuilt)
    for oid, refs in original.items():
        assert (
            rebuilt.get(oid) == refs
        ), f"{roundtrip.name}: MethodDef {oid} DocumentRef changed: {refs} != {rebuilt.get(oid)}"


def test_codelist_standard_oid_references_survive(roundtrip: RoundTrip):
    # CodeList/@def:StandardOID isn't modeled on an external codelist (CLAUDE.md §7.2 keeps
    # ExternalCodeListDef narrow) - so the rebuild can be missing some, but never invent one.
    original = _ref_counter(
        roundtrip.original, "CodeList", ODM_NS, "StandardOID", DEF_NS
    )
    rebuilt = _ref_counter(roundtrip.rebuilt, "CodeList", ODM_NS, "StandardOID", DEF_NS)
    unexpected = rebuilt - original
    assert not unexpected, f"{roundtrip.name}: CodeList@StandardOID referenced on rebuild that the source never had: {unexpected}"


def test_itemdef_comment_oid_references_survive(roundtrip: RoundTrip):
    # def:CommentOID appears on more than one element kind (ItemDef, MetaDataVersion,
    # AnalysisDatasets, ...); scoped to ItemDef specifically here since that's the one
    # Variable.comment: actually resolves to (dataset.py / xml_emit._item_def).
    def comment_oids(tree):
        return Counter(
            el.get(_d("CommentOID"))
            for el in tree.iter(_o("ItemDef"))
            if el.get(_d("CommentOID")) is not None
        )

    original, rebuilt = (
        comment_oids(roundtrip.original),
        comment_oids(roundtrip.rebuilt),
    )
    assert original == rebuilt, (
        f"{roundtrip.name}: ItemDef def:CommentOID references changed - "
        f"only in original: {original - rebuilt}, only in rebuilt: {rebuilt - original}"
    )


# ---------------------------------------------------------------------------
# TranslatedText content survives
# ---------------------------------------------------------------------------


def _descriptions_by_owner(tree: etree._ElementTree) -> dict[tuple[str, str], str]:
    """{(owner local name, owner OID/ID): Description/TranslatedText text}, for every
    OID/ID-bearing element that has one - covers dataset, variable, codelist, method,
    comment, where-clause, value-list, leaf, standard and ARM display/result labels.
    """
    result: dict[tuple[str, str], str] = {}
    for el in tree.iter():
        if not isinstance(el.tag, str):
            continue
        owner_id = el.get("OID") or el.get("ID")
        if owner_id is None:
            continue
        desc_el = el.find(_o("Description"))
        if desc_el is None:
            continue
        tt = desc_el.find(_o("TranslatedText"))
        if tt is not None:
            result[(etree.QName(el).localname, owner_id)] = tt.text or ""
    return result


def test_translated_text_content_survives(roundtrip: RoundTrip):
    original = _descriptions_by_owner(roundtrip.original)
    rebuilt = _descriptions_by_owner(roundtrip.rebuilt)
    common = original.keys() & rebuilt.keys()
    assert common, f"{roundtrip.name}: no Description/TranslatedText owners matched at all - test is broken"
    changed = {
        k: (original[k], rebuilt[k]) for k in common if original[k] != rebuilt[k]
    }
    assert (
        not changed
    ), f"{roundtrip.name}: TranslatedText content changed for {list(changed)[:5]}"
    missing = original.keys() - rebuilt.keys()
    assert (
        not missing
    ), f"{roundtrip.name}: Description lost entirely for {sorted(missing)[:5]}"


def test_codelist_decode_text_survives(roundtrip: RoundTrip):
    def decodes_by_owner(tree):
        result: dict[tuple[str, str], str] = {}
        for cl_el in tree.iter(_o("CodeList")):
            cl_oid = cl_el.get("OID")
            for item_el in list(cl_el.iter(_o("CodeListItem"))):
                decode_el = item_el.find(_o("Decode"))
                if decode_el is None:
                    continue
                tt = decode_el.find(_o("TranslatedText"))
                result[(cl_oid, item_el.get("CodedValue"))] = (
                    tt.text if tt is not None else None
                )
        return result

    original, rebuilt = (
        decodes_by_owner(roundtrip.original),
        decodes_by_owner(roundtrip.rebuilt),
    )
    common = original.keys() & rebuilt.keys()
    changed = {
        k: (original[k], rebuilt[k]) for k in common if original[k] != rebuilt[k]
    }
    assert (
        not changed
    ), f"{roundtrip.name}: CodeListItem Decode text changed for {list(changed)[:5]}"


def test_codelist_rank_survives(roundtrip: RoundTrip):
    # @Rank (Term.rank) - "numeric significance relative to the other items", distinct from
    # OrderNumber/display order. Modeled and re-emitted; every source value must come back.
    def ranks_by_owner(tree):
        result: dict[tuple[str, str], str] = {}
        for cl_el in tree.iter(_o("CodeList")):
            cl_oid = cl_el.get("OID")
            for item_el in list(cl_el.iter(_o("CodeListItem"))) + list(
                cl_el.iter(_o("EnumeratedItem"))
            ):
                if item_el.get("Rank") is not None:
                    result[(cl_oid, item_el.get("CodedValue"))] = item_el.get("Rank")
        return result

    original = ranks_by_owner(roundtrip.original)
    assert (
        original
    ), f"{roundtrip.name}: no @Rank in source - fixture assumption is wrong"
    rebuilt = ranks_by_owner(roundtrip.rebuilt)
    common = original.keys() & rebuilt.keys()
    changed = {
        k: (original[k], rebuilt[k])
        for k in common
        if float(original[k]) != float(rebuilt[k])
    }
    missing = original.keys() - rebuilt.keys()
    assert not changed, f"{roundtrip.name}: Rank changed for {list(changed)[:5]}"
    assert not missing, f"{roundtrip.name}: Rank dropped for {list(missing)[:5]}"


# ---------------------------------------------------------------------------
# FormalExpression / code survives byte-for-byte
# ---------------------------------------------------------------------------


def test_formal_expression_code_survives_byte_for_byte(roundtrip: RoundTrip):
    def expressions_by_method(tree):
        result: dict[str, dict[str, str]] = {}
        for md_el in tree.iter(_o("MethodDef")):
            result[md_el.get("OID")] = {
                fe_el.get("Context"): fe_el.text or ""
                for fe_el in md_el.findall(_o("FormalExpression"))
            }
        return result

    original, rebuilt = (
        expressions_by_method(roundtrip.original),
        expressions_by_method(roundtrip.rebuilt),
    )
    common = (original.keys() & rebuilt.keys()) - _PATCHED_SOURCE_OIDS
    missing = original.keys() - rebuilt.keys() - _PATCHED_SOURCE_OIDS
    assert not missing, f"{roundtrip.name}: MethodDef with FormalExpression lost entirely: {sorted(missing)[:5]}"
    for oid in common:
        assert (
            original[oid] == rebuilt[oid]
        ), f"{roundtrip.name}: FormalExpression code changed for MethodDef {oid!r}"


def test_arm_programming_code_survives_byte_for_byte(roundtrip: RoundTrip):
    def codes_by_result(tree):
        result: dict[str, str] = {}
        for ar_el in tree.iter(_a("AnalysisResult")):
            pc_el = ar_el.find(_a("ProgrammingCode"))
            if pc_el is None:
                continue
            code_el = pc_el.find(_a("Code"))
            if code_el is not None:
                result[ar_el.get("OID")] = code_el.text or ""
        return result

    original, rebuilt = (
        codes_by_result(roundtrip.original),
        codes_by_result(roundtrip.rebuilt),
    )
    common = original.keys() & rebuilt.keys()
    for oid in common:
        assert (
            original[oid] == rebuilt[oid]
        ), f"{roundtrip.name}: arm:Code changed for AnalysisResult {oid!r}"


# ---------------------------------------------------------------------------
# document/leaf references survive
# ---------------------------------------------------------------------------


def test_leaf_href_and_title_survive(roundtrip: RoundTrip):
    def leaves(tree):
        return {
            el.get("ID"): (el.get(f"{{{XLINK_NS}}}href"), el.findtext(_d("title")))
            for el in tree.iter(_d("leaf"))
        }

    original, rebuilt = leaves(roundtrip.original), leaves(roundtrip.rebuilt)
    common = original.keys() & rebuilt.keys()
    changed = {
        k: (original[k], rebuilt[k]) for k in common if original[k] != rebuilt[k]
    }
    assert (
        not changed
    ), f"{roundtrip.name}: leaf href/title changed for {list(changed)[:5]}"


def test_xml_stylesheet_processing_instruction_survives(roundtrip: RoundTrip):
    # Define-XML spec §5.3.2: an optional <?xml-stylesheet type="text/xsl" href="..."?>
    # between the XML declaration and <ODM> - purely presentational, outside the ODM/def
    # content model, so lxml exposes it as the root element's previous sibling rather than
    # anything reachable via .iter().
    def stylesheet_href(tree):
        pi = tree.getroot().getprevious()
        return (
            pi.get("href") if getattr(pi, "target", None) == "xml-stylesheet" else None
        )

    original_href = stylesheet_href(roundtrip.original)
    if original_href is None:
        pytest.skip(f"{roundtrip.name}: no xml-stylesheet PI in this fixture")
    assert stylesheet_href(roundtrip.rebuilt) == original_href


# ---------------------------------------------------------------------------
# External codelists survive
# ---------------------------------------------------------------------------


def test_external_codelists_survive(roundtrip: RoundTrip):
    def externals(tree):
        result = {}
        for cl_el in tree.iter(_o("CodeList")):
            ext_el = cl_el.find(_o("ExternalCodeList"))
            if ext_el is not None:
                result[cl_el.get("OID")] = (
                    ext_el.get("Dictionary"),
                    ext_el.get("Version"),
                )
        return result

    original, rebuilt = externals(roundtrip.original), externals(roundtrip.rebuilt)
    assert original, f"{roundtrip.name}: no external codelists in source - test fixture assumption is wrong"
    assert (
        original == rebuilt
    ), f"{roundtrip.name}: external codelist Dictionary/Version changed: {original} != {rebuilt}"


# ---------------------------------------------------------------------------
# Ordering semantics survive
# ---------------------------------------------------------------------------


def test_itemref_order_survives_per_dataset(roundtrip: RoundTrip):
    def order_by_dataset(tree):
        return {
            ig_el.get("OID"): [
                ir_el.get("ItemOID") for ir_el in ig_el.findall(_o("ItemRef"))
            ]
            for ig_el in tree.iter(_o("ItemGroupDef"))
        }

    original, rebuilt = (
        order_by_dataset(roundtrip.original),
        order_by_dataset(roundtrip.rebuilt),
    )
    common = original.keys() & rebuilt.keys()
    changed = [oid for oid in common if original[oid] != rebuilt[oid]]
    assert (
        not changed
    ), f"{roundtrip.name}: ItemRef order changed for ItemGroupDef {changed[:3]}"


def test_codelist_item_order_survives(roundtrip: RoundTrip):
    def order_by_codelist(tree):
        result = {}
        for cl_el in tree.iter(_o("CodeList")):
            items = list(cl_el.iter(_o("CodeListItem"))) + list(
                cl_el.iter(_o("EnumeratedItem"))
            )
            if items:
                result[cl_el.get("OID")] = [i.get("CodedValue") for i in items]
        return result

    original, rebuilt = (
        order_by_codelist(roundtrip.original),
        order_by_codelist(roundtrip.rebuilt),
    )
    common = original.keys() & rebuilt.keys()
    changed = [oid for oid in common if original[oid] != rebuilt[oid]]
    assert (
        not changed
    ), f"{roundtrip.name}: CodeList term order changed for {changed[:3]}"


def test_analysis_dataset_variable_order_survives(roundtrip: RoundTrip):
    def order_by_result(tree):
        result = {}
        for ar_el in tree.iter(_a("AnalysisResult")):
            for i, ad_el in enumerate(
                ar_el.findall(f"{_a('AnalysisDatasets')}/{_a('AnalysisDataset')}")
            ):
                key = (ar_el.get("OID"), i)
                result[key] = [
                    v.get("ItemOID") for v in ad_el.findall(_a("AnalysisVariable"))
                ]
        return result

    original, rebuilt = (
        order_by_result(roundtrip.original),
        order_by_result(roundtrip.rebuilt),
    )
    if not original:
        pytest.skip(f"{roundtrip.name}: no ARM AnalysisDataset in this fixture")
    missing = original.keys() - rebuilt.keys()
    assert (
        not missing
    ), f"{roundtrip.name}: AnalysisDataset lost entirely: {sorted(missing)[:3]}"
    common = original.keys() & rebuilt.keys()
    changed = [k for k in common if original[k] != rebuilt[k]]
    assert (
        not changed
    ), f"{roundtrip.name}: AnalysisVariable order changed for {changed[:3]}"


# ---------------------------------------------------------------------------
# ARM survives (displays, results, datasets, reason/purpose, documentation)
# ---------------------------------------------------------------------------


def test_arm_result_displays_and_results_survive(roundtrip: RoundTrip):
    def reason_purpose(tree):
        return {
            ar.get("OID"): (ar.get("AnalysisReason"), ar.get("AnalysisPurpose"))
            for ar in tree.iter(_a("AnalysisResult"))
        }

    original, rebuilt = (
        reason_purpose(roundtrip.original),
        reason_purpose(roundtrip.rebuilt),
    )
    if not original:
        pytest.skip(f"{roundtrip.name}: no ARM AnalysisResult in this fixture")
    common = original.keys() & rebuilt.keys()
    changed = {
        k: (original[k], rebuilt[k]) for k in common if original[k] != rebuilt[k]
    }
    assert not changed, f"{roundtrip.name}: AnalysisReason/AnalysisPurpose changed for {list(changed)[:5]}"


# ---------------------------------------------------------------------------
# Per-object canonicalised XML equivalence
# ---------------------------------------------------------------------------


def _local(el: etree._Element) -> str:
    return etree.QName(el).localname


def _normalize_for_comparison(el: etree._Element) -> etree._Element:
    """A copy of `el`, whitespace-normalised and with exactly the tool's known, documented
    gaps (CLAUDE.md §8) and intentional design choices scrubbed from BOTH sides equally -
    so this comparison is a gate on everything the tool claims to model, not a demand that it
    already models everything Define-XML allows. Every rule here names its reason; a diff
    this function doesn't account for is a real regression, not a known gap.

    `list(el.iter())` is materialised upfront so the walk is over a frozen node set, not a
    live view - leaving room for a future rule here to mutate the tree (remove an element)
    without skipping siblings.
    """
    el = copy.deepcopy(el)
    nodes = list(el.iter())

    for e in nodes:
        # Pretty-printed indentation whitespace is presentation, not content - no field in
        # this model is ever legitimately all-whitespace. Done after removals above so a
        # removed element's own whitespace never lingers as an orphaned diff.
        if e.text is not None and e.text.strip() == "":
            e.text = None
        if e.tail is not None and e.tail.strip() == "":
            e.tail = None
        local = _local(e)
        if local in ("CodeListItem", "EnumeratedItem"):
            # CLAUDE.md §3, "Ordering attributes are positional, never stored": OrderNumber is
            # always derived from terms: list position on emission, never copied from a
            # source's OrderNumber. Relative order is checked separately
            # (test_codelist_item_order_survives); the absolute OrderNumber value isn't meant
            # to survive. @Rank *is* modeled now (Term.rank) and re-emitted faithfully, so
            # it's left in place for the comparison - see test_codelist_rank_survives.
            e.attrib.pop("OrderNumber", None)
        if local == "ItemRef":
            # Same positional-derivation rule, for variables: list position.
            e.attrib.pop("OrderNumber", None)
        if local == "CodeList" and e.find(_o("ExternalCodeList")) is not None:
            # def:IsNonStandard, def:StandardOID, def:CommentOID and ExternalCodeList/@href
            # aren't modeled on an external codelist - CLAUDE.md §7.2 deliberately keeps
            # ExternalCodeListDef narrow (only dictionary/version), so this is a design choice,
            # not an oversight; standard:/comment: are EnumeratedCodeList-only fields.
            e.attrib.pop(_d("IsNonStandard"), None)
            e.attrib.pop(_d("StandardOID"), None)
            e.attrib.pop(_d("CommentOID"), None)
            e.find(_o("ExternalCodeList")).attrib.pop("href", None)
        if local == "ItemDef" and e.get("SASFieldName") == e.get("Name"):
            # sas_field_name: defaults to name: and is always emitted (this session's decision)
            # even when the source omitted SASFieldName entirely because it happened to match
            # Name - not a content change, just making an implicit default explicit.
            e.attrib.pop("SASFieldName", None)
    return el


def _c14n(el: etree._Element) -> str:
    # exclusive=True: only namespaces actually used within the subtree are rendered, not every
    # namespace merely in scope from the document root (e.g. xmlns:arm on a Standard element
    # that never uses it) - that noise isn't a content difference and shouldn't read as one.
    return etree.tostring(_normalize_for_comparison(el), method="c14n", exclusive=True)


@pytest.mark.parametrize("local,ns,attr", OID_BEARING, ids=[t[0] for t in OID_BEARING])
def test_object_canonical_xml_equivalent(roundtrip: RoundTrip, local, ns, attr):
    original_by_oid = {
        el.get(attr): el for el in roundtrip.original.iter(f"{{{ns}}}{local}")
    }
    rebuilt_by_oid = {
        el.get(attr): el for el in roundtrip.rebuilt.iter(f"{{{ns}}}{local}")
    }
    common = (original_by_oid.keys() & rebuilt_by_oid.keys()) - _PATCHED_SOURCE_OIDS
    diffs = []
    for oid in sorted(common):
        original_c14n = _c14n(original_by_oid[oid])
        rebuilt_c14n = _c14n(rebuilt_by_oid[oid])
        if original_c14n != rebuilt_c14n:
            diffs.append(oid)
    assert not diffs, (
        f"{roundtrip.name}: {len(diffs)}/{len(common)} {local} object(s) differ after canonicalisation "
        f"(showing up to 3): {diffs[:3]}"
    )
