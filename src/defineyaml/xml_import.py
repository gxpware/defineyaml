"""define.xml -> file tree (CLAUDE.md build order step 1).

Walks the subset of ODM 1.3.2 / Define-XML 2.1 / ARM 1.0 this tool models
and writes the corresponding `define/` file tree. Anything in the source
XML this tool does not model - an attribute or child element outside the
known set for that object kind - is reported to the console as
"not implemented" and dropped, rather than silently lost. A non-English
`TranslatedText` is different: CLAUDE.md §7.4 requires that to hard-fail
(real data loss, not a modelling gap), unless `force_lang_en` is set.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

from . import oid as oidmod
from .io.yaml_io import dump
from .xml_emit import ARM_NS, DEF_NS, ODM_NS, XLINK_NS, XML_NS, _a, _d, _o, _x  # noqa: F401  (namespace helpers)


class ImportError_(Exception):
    """Hard-fail condition on import: a non-English TranslatedText (CLAUDE.md §7.4)."""


def _report(kind: str, xpath: str, name: str) -> None:
    print(f"not implemented: {kind} {name!r} at {xpath}")


def _check_unknown(
    el: etree._Element, known_attrs: set[str], known_children: set[str], xpath: str
) -> None:
    for name in el.attrib:
        if name not in known_attrs:
            _report("attribute", xpath, name)
    for child in el:
        if not isinstance(child.tag, str):
            continue
        if child.tag not in known_children:
            _report("element", xpath, etree.QName(child.tag).localname)


@dataclass
class TranslatedTextViolation:
    xpath: str
    detail: str


@dataclass
class ImportContext:
    force_lang_en: bool
    violations: list[TranslatedTextViolation] = field(default_factory=list)

    def text_of(self, parent: etree._Element, tag: str, *, xpath: str) -> str | None:
        container = parent.find(tag)
        if container is None:
            return None
        texts = container.findall(_o("TranslatedText"))
        if not texts:
            return None
        en_texts = [t for t in texts if t.get(f"{{{XML_NS}}}lang") in (None, "en")]
        other_texts = [t for t in texts if t not in en_texts]
        for t in other_texts:
            lang = t.get(f"{{{XML_NS}}}lang")
            if self.force_lang_en:
                _report(
                    "TranslatedText",
                    xpath,
                    f"xml:lang={lang!r} (discarded, --force-lang en)",
                )
            else:
                self.violations.append(
                    TranslatedTextViolation(xpath, f"xml:lang={lang!r}")
                )
        if len(en_texts) > 1:
            if self.force_lang_en:
                _report(
                    "TranslatedText",
                    xpath,
                    "multiple en TranslatedText (using the first, --force-lang en)",
                )
            else:
                self.violations.append(
                    TranslatedTextViolation(
                        xpath, "more than one en TranslatedText per parent"
                    )
                )
        if en_texts:
            return en_texts[0].text
        if self.force_lang_en and texts:
            return texts[0].text
        return None


def _slug_tail(oid_value: str) -> str:
    """A filesystem-friendly name derived from an OID with no natural human name."""
    tail = oid_value.split(".", 1)[1] if "." in oid_value else oid_value
    return tail.lower().replace(".", "-")


@dataclass
class ReverseIndex:
    """OID -> (kind, human-readable reference string) for objects with a recoverable name."""

    by_oid: dict[str, tuple[str, str]] = field(default_factory=dict)

    def add(self, oid_value: str, kind: str, ref: str) -> None:
        self.by_oid[oid_value] = (kind, ref)

    def ref_or_oid(self, oid_value: str | None) -> str | dict[str, str] | None:
        if oid_value is None:
            return None
        found = self.by_oid.get(oid_value)
        if found is None:
            return {"oid": oid_value}
        return found[1]


def import_define_xml(
    xml_path: Path, destination: Path, *, force_lang_en: bool = False
) -> None:
    doc = etree.parse(str(xml_path))
    root = doc.getroot()
    if root.tag != _o("ODM"):
        raise ImportError_(
            f"not a define.xml: root element is {root.tag!r}, expected ODM"
        )

    ctx = ImportContext(force_lang_en=force_lang_en)
    index = ReverseIndex()

    study_el = root.find(_o("Study"))
    if study_el is None:
        raise ImportError_("no <Study> element found")
    gv_el = study_el.find(_o("GlobalVariables"))
    mdv_el = study_el.find(_o("MetaDataVersion"))
    if mdv_el is None:
        raise ImportError_("no <MetaDataVersion> element found")

    _check_unknown(
        root,
        {
            "FileOID",
            "ODMVersion",
            "FileType",
            "CreationDateTime",
            "AsOfDateTime",
            "Originator",
            "SourceSystem",
            "SourceSystemVersion",
            _d("Context"),
        },
        {_o("Study")},
        "/ODM",
    )

    stylesheet_pi = root.getprevious()
    stylesheet_href = (
        stylesheet_pi.get("href")
        if getattr(stylesheet_pi, "target", None) == "xml-stylesheet"
        else None
    )
    study_data = {
        "odm": {
            "file_oid": root.get("FileOID"),
            **(
                {"creation_datetime": root.get("CreationDateTime")}
                if root.get("CreationDateTime")
                else {}
            ),
            **(
                {"as_of_datetime": root.get("AsOfDateTime")}
                if root.get("AsOfDateTime")
                else {}
            ),
            **(
                {"originator": root.get("Originator")} if root.get("Originator") else {}
            ),
            **(
                {"source_system": root.get("SourceSystem")}
                if root.get("SourceSystem")
                else {}
            ),
            **(
                {"source_system_version": root.get("SourceSystemVersion")}
                if root.get("SourceSystemVersion")
                else {}
            ),
            **({"stylesheet": stylesheet_href} if stylesheet_href else {}),
        },
        "study": {"oid": study_el.get("OID"), "protocol_name": ""},
        "metadata_version": {
            "oid": mdv_el.get("OID"),
            "name": mdv_el.get("Name"),
            "define_version": mdv_el.get(_d("DefineVersion"), "2.1.0"),
        },
    }
    if mdv_el.get("Description"):
        study_data["metadata_version"]["description"] = mdv_el.get("Description")
    _check_unknown(
        mdv_el,
        {"OID", "Name", "Description", _d("DefineVersion"), _d("CommentOID")},
        {
            _d("Standards"),
            _d("AnnotatedCRF"),
            _d("SupplementalDoc"),
            _d("ValueListDef"),
            _d("WhereClauseDef"),
            _o("ItemGroupDef"),
            _o("ItemDef"),
            _o("CodeList"),
            _o("MethodDef"),
            _d("CommentDef"),
            _d("leaf"),
            _a("AnalysisResultDisplays"),
        },
        "/ODM/Study/MetaDataVersion",
    )

    if gv_el is not None:
        study_data["study"]["name"] = gv_el.findtext(_o("StudyName")) or ""
        desc = gv_el.findtext(_o("StudyDescription"))
        if desc:
            study_data["study"]["description"] = desc
        study_data["study"]["protocol_name"] = gv_el.findtext(_o("ProtocolName")) or ""
        _check_unknown(
            gv_el,
            set(),
            {_o("StudyName"), _o("StudyDescription"), _o("ProtocolName")},
            "/ODM/Study/GlobalVariables",
        )
    _check_unknown(
        study_el, {"OID"}, {_o("GlobalVariables"), _o("MetaDataVersion")}, "/ODM/Study"
    )

    # Item OIDs -> "DATASET.VARIABLE" registered up front, since WhereClauseDef and
    # AnalysisResult (processed before the ItemGroupDef loop below, to mirror document
    # order) reference variables by OID and need the dotted form already resolvable.
    item_defs_by_oid = {el.get("OID"): el for el in mdv_el.findall(_o("ItemDef"))}
    for ig_el in mdv_el.findall(_o("ItemGroupDef")):
        ds_name = ig_el.get("Name")
        for ir_el in ig_el.findall(_o("ItemRef")):
            item_oid_value = ir_el.get("ItemOID")
            item_el = item_defs_by_oid.get(item_oid_value)
            if item_el is not None and item_oid_value not in index.by_oid:
                index.add(item_oid_value, "item", f"{ds_name}.{item_el.get('Name')}")

    # def:leaf* (top-level = documents; dataset leafs are nested in their ItemGroupDef, handled
    # below). Processed ahead of def:CommentDef (which can reference one via def:DocumentRef) and
    # def:Standards (def:CommentOID) so those references resolve to a clean name rather than
    # falling back to {oid: ...} for lack of an index entry - this only reads the raw element
    # tree, so it doesn't need any other loop to have run first.
    dataset_leaf_ids = {
        ig_el.find(_d("leaf")).get("ID")
        for ig_el in mdv_el.findall(_o("ItemGroupDef"))
        if ig_el.find(_d("leaf")) is not None
    }
    documents_data: list[dict] = []
    for leaf_el in mdv_el.findall(_d("leaf")):
        leaf_id = leaf_el.get("ID")
        if leaf_id in dataset_leaf_ids:
            continue
        xpath = f"/.../leaf[@ID={leaf_id!r}]"
        title = leaf_el.findtext(_d("title")) or ""
        href = leaf_el.get(_x("href"))
        name = _slug_tail(leaf_id)
        documents_data.append(
            {"name": name, "href": href, "title": title, "oid": leaf_id}
        )
        index.add(leaf_id, "document", name)
        _check_unknown(leaf_el, {"ID", _x("href")}, {_d("title")}, xpath)

    # def:CommentDef* - no Name in Define-XML; always filed and overridden by OID. Processed
    # ahead of def:Standards (which can reference one via def:CommentOID) so that reference
    # resolves to a clean name rather than falling back to {oid: ...} for lack of an index entry.
    comments_data: dict[str, dict] = {}
    for com_el in mdv_el.findall(_d("CommentDef")):
        oid_value = com_el.get("OID")
        xpath = f"/.../CommentDef[@OID={oid_value!r}]"
        text = ctx.text_of(com_el, _o("Description"), xpath=xpath) or ""
        key = _slug_tail(oid_value)
        entry: dict = {"description": text, "oid": oid_value}
        doc_ref_els = com_el.findall(_d("DocumentRef"))
        if doc_ref_els:
            entry["documents"] = [
                _import_document_ref(doc_ref_el, index) for doc_ref_el in doc_ref_els
            ]
        comments_data[key] = entry
        index.add(oid_value, "comment", key)
        _check_unknown(com_el, {"OID"}, {_o("Description"), _d("DocumentRef")}, xpath)

    # def:Standards
    standards_data: list[dict] = []
    standards_el = mdv_el.find(_d("Standards"))
    if standards_el is not None:
        std_els = standards_el.findall(_d("Standard"))
        # Two def:Standard entries can legitimately share a Name - most commonly two CT
        # versions, one per model, distinguished only by PublishingSet (CLAUDE.md §3's
        # standard_key). A bare-name reference can't recover which one it means, so an
        # ambiguous name gets no name-based reverse-index entry: any codelist referencing it
        # falls back to {oid: ...} below, the same escape hatch a nameless WhereClauseDef uses.
        name_counts: dict[str, int] = {}
        for std_el in std_els:
            name_counts[std_el.get("Name")] = name_counts.get(std_el.get("Name"), 0) + 1
        for std_el in std_els:
            entry: dict = {
                "name": std_el.get("Name"),
                "type": std_el.get("Type"),
                "version": std_el.get("Version"),
                "status": std_el.get("Status", "Final"),
            }
            if std_el.get("PublishingSet"):
                entry["publishing_set"] = std_el.get("PublishingSet")
            comment_oid_value = std_el.get(_d("CommentOID"))
            if comment_oid_value:
                entry["comment"] = index.ref_or_oid(comment_oid_value)
            derived = f"STD.{_slugify(entry['name'])}"
            actual = std_el.get("OID")
            if actual != derived:
                entry["oid"] = actual
            if name_counts[entry["name"]] == 1:
                index.add(actual, "standard", entry["name"])
            _check_unknown(
                std_el,
                {
                    "OID",
                    "Name",
                    "Type",
                    "PublishingSet",
                    "Version",
                    "Status",
                    _d("CommentOID"),
                },
                set(),
                f"/.../Standards/Standard[@OID={actual!r}]",
            )
            standards_data.append(entry)
        _check_unknown(standards_el, set(), {_d("Standard")}, "/.../Standards")

    def _document_refs(container_el: etree._Element, xpath: str) -> list:
        refs = []
        for i, doc_ref_el in enumerate(container_el.findall(_d("DocumentRef"))):
            doc_ref = _import_document_ref(doc_ref_el, index)
            if "pages" in doc_ref:
                _report(
                    "element",
                    f"{xpath}/DocumentRef[{i}]",
                    "PDFPageRef (not modelled in a document reference list)",
                )
            refs.append(doc_ref["ref"])
        return refs

    # def:AnnotatedCRF / def:SupplementalDoc - each just a list of def:DocumentRef.
    annotated_crf_data: list = []
    acrf_el = mdv_el.find(_d("AnnotatedCRF"))
    if acrf_el is not None:
        annotated_crf_data = _document_refs(acrf_el, "/.../AnnotatedCRF")
        _check_unknown(acrf_el, set(), {_d("DocumentRef")}, "/.../AnnotatedCRF")
    supplemental_docs_data: list = []
    supp_el = mdv_el.find(_d("SupplementalDoc"))
    if supp_el is not None:
        supplemental_docs_data = _document_refs(supp_el, "/.../SupplementalDoc")
        _check_unknown(supp_el, set(), {_d("DocumentRef")}, "/.../SupplementalDoc")

    # def:WhereClauseDef* - no Name either; same treatment.
    whereclauses_data: dict[str, dict] = {}
    for wc_el in mdv_el.findall(_d("WhereClauseDef")):
        oid_value = wc_el.get("OID")
        xpath = f"/.../WhereClauseDef[@OID={oid_value!r}]"
        conditions = []
        for rc_el in wc_el.findall(_o("RangeCheck")):
            item_oid_value = rc_el.get(_d("ItemOID"))
            conditions.append(
                {
                    "variable": index.ref_or_oid(item_oid_value),
                    "comparator": rc_el.get("Comparator"),
                    "values": [cv.text or "" for cv in rc_el.findall(_o("CheckValue"))],
                }
            )
            _check_unknown(
                rc_el,
                {"Comparator", "SoftHard", _d("ItemOID")},
                {_o("CheckValue")},
                xpath + "/RangeCheck",
            )
        key = _slug_tail(oid_value)
        entry = {"conditions": conditions, "oid": oid_value}
        comment_oid_value = wc_el.get(_d("CommentOID"))
        if comment_oid_value:
            entry["comment"] = index.ref_or_oid(comment_oid_value)
        whereclauses_data[key] = entry
        index.add(oid_value, "whereclause", key)
        _check_unknown(wc_el, {"OID", _d("CommentOID")}, {_o("RangeCheck")}, xpath)

    # CodeList*
    codelists_data: dict[str, dict] = {}
    for cl_el in mdv_el.findall(_o("CodeList")):
        oid_value = cl_el.get("OID")
        name = cl_el.get("Name")
        xpath = f"/.../CodeList[@OID={oid_value!r}]"
        entry: dict = {"name": name, "label": name, "type": cl_el.get("DataType")}
        ext_el = cl_el.find(_o("ExternalCodeList"))
        if ext_el is not None:
            entry["external"] = {
                "dictionary": ext_el.get("Dictionary"),
                "version": ext_el.get("Version"),
            }
            _check_unknown(
                ext_el,
                {"Dictionary", "Version", "href"},
                set(),
                xpath + "/ExternalCodeList",
            )
        else:
            # CodeListItem (has Decode) and EnumeratedItem (no Decode - a coded value with no
            # human-readable label, e.g. age-group or treatment-arm codelists) are mutually
            # exclusive per CodeList in the schema, but a source file uses only one kind, so
            # collecting both element types and sorting together is safe.
            item_els = cl_el.findall(_o("CodeListItem")) + cl_el.findall(
                _o("EnumeratedItem")
            )
            terms = []
            for item_el in sorted(
                item_els,
                key=lambda e: float(e.get("OrderNumber") or e.get("Rank") or 0),
            ):
                is_enumerated = item_el.tag == _o("EnumeratedItem")
                term: dict = {"code": item_el.get("CodedValue")}
                if not is_enumerated:
                    decode_el = item_el.find(_o("Decode"))
                    decode_text = None
                    if decode_el is not None:
                        tts = decode_el.findall(_o("TranslatedText"))
                        decode_text = tts[0].text if tts else None
                    term["decode"] = decode_text or ""
                sponsor_aliases = []
                for alias_el in item_el.findall(_o("Alias")):
                    if alias_el.get("Context") == "nci:ExtCodeID":
                        term["nci_code"] = alias_el.get("Name")
                    else:
                        sponsor_aliases.append(
                            {
                                "context": alias_el.get("Context"),
                                "name": alias_el.get("Name"),
                            }
                        )
                if sponsor_aliases:
                    term["aliases"] = sponsor_aliases
                if item_el.get(_d("ExtendedValue")) == "Yes":
                    term["extended"] = True
                rank_raw = item_el.get("Rank")
                if rank_raw not in (None, ""):
                    try:
                        rank_val = float(rank_raw)
                        term["rank"] = (
                            int(rank_val) if rank_val.is_integer() else rank_val
                        )
                    except ValueError:
                        pass
                terms.append(term)
                known_attrs = {"CodedValue", "OrderNumber", "Rank", _d("ExtendedValue")}
                known_children = (
                    {_o("Alias")} if is_enumerated else {_o("Decode"), _o("Alias")}
                )
                item_xpath = (
                    xpath
                    + f"/{'EnumeratedItem' if is_enumerated else 'CodeListItem'}[@CodedValue={item_el.get('CodedValue')!r}]"
                )
                _check_unknown(item_el, known_attrs, known_children, item_xpath)
            entry["terms"] = terms
            if cl_el.get(_d("IsNonStandard")) == "Yes":
                entry["extended"] = True
            if cl_el.get("SASFormatName"):
                entry["sas_format_name"] = cl_el.get("SASFormatName")
            cl_std_oid_value = cl_el.get(_d("StandardOID"))
            if cl_std_oid_value:
                entry["standard"] = index.ref_or_oid(cl_std_oid_value)
            cl_comment_oid_value = cl_el.get(_d("CommentOID"))
            if cl_comment_oid_value:
                entry["comment"] = index.ref_or_oid(cl_comment_oid_value)
            cl_sponsor_aliases = []
            for cl_alias_el in cl_el.findall(_o("Alias")):
                if cl_alias_el.get("Context") == "nci:ExtCodeID":
                    entry["nci_code"] = cl_alias_el.get("Name")
                else:
                    cl_sponsor_aliases.append(
                        {
                            "context": cl_alias_el.get("Context"),
                            "name": cl_alias_el.get("Name"),
                        }
                    )
            if cl_sponsor_aliases:
                entry["aliases"] = cl_sponsor_aliases
        if ext_el is not None and cl_el.get(_d("StandardOID")):
            _report(
                "attribute",
                xpath,
                "def:StandardOID (not modelled on an external codelist)",
            )
        derived = f"CL.{_slugify(name)}"
        if oid_value != derived:
            entry["oid"] = oid_value
        index.add(oid_value, "codelist", name.lower())
        codelists_data[name.lower()] = entry
        known_children = (
            {_o("ExternalCodeList")}
            if ext_el is not None
            else {_o("CodeListItem"), _o("EnumeratedItem"), _o("Alias")}
        )
        _check_unknown(
            cl_el,
            {
                "OID",
                "Name",
                "DataType",
                "SASFormatName",
                _d("StandardOID"),
                _d("IsNonStandard"),
                _d("CommentOID"),
            },
            known_children | {_o("Description")},
            xpath,
        )

    # MethodDef*
    methods_data: dict[str, dict] = {}
    expression_contexts: list[str] = []
    for md_el in mdv_el.findall(_o("MethodDef")):
        oid_value = md_el.get("OID")
        xpath = f"/.../MethodDef[@OID={oid_value!r}]"
        entry: dict = {
            "name": md_el.get("Name"),
            "type": md_el.get("Type", "Computation"),
        }
        desc = ctx.text_of(md_el, _o("Description"), xpath=xpath)
        if desc:
            entry["description"] = desc
        expressions = []
        for fe_el in md_el.findall(_o("FormalExpression")):
            expressions.append(
                {"context": fe_el.get("Context"), "code": fe_el.text or ""}
            )
            if fe_el.get("Context") not in expression_contexts:
                expression_contexts.append(fe_el.get("Context"))
        if expressions:
            entry["expressions"] = expressions
        method_doc_refs = md_el.findall(_d("DocumentRef"))
        if method_doc_refs:
            entry["documents"] = [
                _import_document_ref(dr_el, index) for dr_el in method_doc_refs
            ]
        key = _slug_tail(oid_value)
        derived = f"MT.{_path_to_slug(key)}"
        if oid_value != derived:
            entry["oid"] = oid_value
        index.add(oid_value, "method", key)
        methods_data[key] = entry
        _check_unknown(
            md_el,
            {"OID", "Name", "Type"},
            {_o("Description"), _o("FormalExpression"), _d("DocumentRef")},
            xpath,
        )

    # ItemGroupDef* + ItemDef* -> datasets/<name>.yaml
    #
    # An ItemOID can be reused across ItemGroupDefs, not just within one - SDTM define.xml
    # files commonly share a single ItemDef for STUDYID (or DOMAIN) across every domain,
    # rather than giving each dataset its own. item_oid_owner_dataset tracks, globally, which
    # dataset first got the real ItemDef/Variable for a given ItemOID; every later ItemRef
    # against it - same dataset or a different one - becomes a same_as alias instead of a
    # second Variable claiming the same imported oid: override (which would collide at build
    # time, since two objects can't share one OID).
    datasets_data: dict[str, dict] = {}
    item_oid_owner_dataset: dict[str, str] = {}
    for ig_el in mdv_el.findall(_o("ItemGroupDef")):
        oid_value = ig_el.get("OID")
        name = ig_el.get("Name")
        xpath = f"/.../ItemGroupDef[@OID={oid_value!r}]"
        derived = f"IG.{_slugify(name)}"
        entry: dict = {
            "name": name,
            "label": ctx.text_of(ig_el, _o("Description"), xpath=xpath) or "",
            "structure": ig_el.get(_d("Structure"), ""),
            "purpose": ig_el.get("Purpose", "Analysis"),
            "repeating": ig_el.get("Repeating") == "Yes",
            "is_reference_data": ig_el.get("IsReferenceData") == "Yes",
        }
        if ig_el.get("Domain"):
            entry["domain"] = ig_el.get("Domain")
        if ig_el.get(_d("IsNonStandard")) == "Yes":
            entry["is_non_standard"] = True
        if ig_el.get(_d("HasNoData")) == "Yes":
            entry["has_no_data"] = True
        cls_el = ig_el.find(_d("Class"))
        entry["class"] = cls_el.get("Name") if cls_el is not None else ""
        if cls_el is None:
            _report("element", xpath, "def:Class (required; using an empty class:)")
        else:
            subclasses = []
            for sub_el in cls_el.findall(_d("SubClass")):
                sub_entry: dict = {"name": sub_el.get("Name")}
                if sub_el.get("ParentClass"):
                    sub_entry["parent_class"] = sub_el.get("ParentClass")
                subclasses.append(sub_entry)
                _check_unknown(
                    sub_el, {"Name", "ParentClass"}, set(), f"{xpath}/Class/SubClass"
                )
            if subclasses:
                entry["subclasses"] = subclasses
        std_oid_value = ig_el.get(_d("StandardOID"))
        if std_oid_value:
            entry["standard"] = index.ref_or_oid(std_oid_value)
        ig_comment_oid_value = ig_el.get(_d("CommentOID"))
        if ig_comment_oid_value:
            entry["comment"] = index.ref_or_oid(ig_comment_oid_value)
        leaf_el = ig_el.find(_d("leaf"))
        if leaf_el is not None:
            href = leaf_el.get(_x("href"))
            title = leaf_el.findtext(_d("title")) or ""
            leaf_entry: dict = {"href": href}
            if title and title != Path(href).name:
                leaf_entry["title"] = title
            entry["leaf"] = leaf_entry
            _check_unknown(leaf_el, {"ID", _x("href")}, {_d("title")}, xpath + "/leaf")
        if oid_value != derived:
            entry["oid"] = oid_value
        index.add(oid_value, "dataset", name.lower())

        item_refs = sorted(
            ig_el.findall(_o("ItemRef")),
            key=lambda e: int(e.get("OrderNumber", "0") or 0),
        )
        keys: list[tuple[int, str]] = []
        variables: list[dict] = []
        for ir_el in item_refs:
            item_oid_value = ir_el.get("ItemOID")
            var_xpath = f"{xpath}/ItemRef[@ItemOID={item_oid_value!r}]"
            _check_unknown(
                ir_el,
                {
                    "ItemOID",
                    "OrderNumber",
                    "Mandatory",
                    "KeySequence",
                    "MethodOID",
                    "Role",
                    _d("IsNonStandard"),
                    _d("HasNoData"),
                },
                {_d("WhereClauseRef")},
                var_xpath,
            )
            owner_dataset = item_oid_owner_dataset.get(item_oid_value)
            if owner_dataset is not None:
                target_def = item_defs_by_oid.get(item_oid_value)
                target_name = (
                    target_def.get("Name") if target_def is not None else "ALIAS"
                )
                if owner_dataset == name:
                    # Disjunction: a second ItemRef against an already-emitted ItemDef in this
                    # same dataset (CLAUDE.md §3, "No OR").
                    alias_name = f"{target_name}_ALIAS"
                    alias_label = f"Alias of {target_name}"
                else:
                    # The same ItemDef reused verbatim from a different dataset (e.g. STUDYID
                    # shared across every SDTM domain) - not a disjunction, so the alias keeps
                    # the real name and label rather than reading as an "OR" branch.
                    alias_name = target_name
                    alias_label = (
                        ctx.text_of(target_def, _o("Description"), xpath=var_xpath)
                        or target_name
                        if target_def is not None
                        else target_name
                    )
                var_entry = _import_alias_variable(
                    alias_name,
                    alias_label,
                    ir_el,
                    index,
                    item_oid_value,
                    context=var_xpath,
                )
                variables.append(var_entry)
                if ir_el.get("KeySequence"):
                    keys.append((int(ir_el.get("KeySequence")), var_entry["name"]))
                continue
            item_oid_owner_dataset[item_oid_value] = name
            item_el = item_defs_by_oid.get(item_oid_value)
            if item_el is None:
                _report(
                    "element",
                    var_xpath,
                    f"ItemRef with no matching ItemDef OID={item_oid_value!r}",
                )
                continue
            var_entry = _import_variable(
                item_el,
                ir_el,
                index,
                ctx,
                xpath=f"/.../ItemDef[@OID={item_oid_value!r}]",
            )
            var_oid = var_entry.pop("__oid__")
            if var_oid != oidmod.item_oid(name, var_entry["name"]):
                var_entry["oid"] = var_oid
            variables.append(var_entry)
            if ir_el.get("KeySequence"):
                keys.append((int(ir_el.get("KeySequence")), var_entry["name"]))
        entry["variables"] = variables
        if keys:
            entry["keys"] = [n for _, n in sorted(keys)]
        alias_els = ig_el.findall(_o("Alias"))
        if alias_els:
            entry["aliases"] = [
                {"context": a.get("Context"), "name": a.get("Name")} for a in alias_els
            ]
        datasets_data[name.lower()] = entry
        _check_unknown(
            ig_el,
            {
                "OID",
                "Name",
                "SASDatasetName",
                "Domain",
                "Repeating",
                "IsReferenceData",
                "Purpose",
                _d("StandardOID"),
                _d("Structure"),
                _d("ArchiveLocationID"),
                _d("IsNonStandard"),
                _d("HasNoData"),
                _d("CommentOID"),
            },
            {_o("Description"), _o("ItemRef"), _o("Alias"), _d("Class"), _d("leaf")},
            xpath,
        )

    # ItemGroupDef document order, captured for fidelity - study.yaml's dataset_order:
    # only needs writing when it says something datasets/*.yaml's own alphabetical
    # file-loading order wouldn't already give a rebuild for free.
    dataset_name_order = [entry["name"] for entry in datasets_data.values()]
    if dataset_name_order != sorted(dataset_name_order):
        study_data["dataset_order"] = dataset_name_order

    # A ValueListDef has no OID of its own on the referencing side - the owning
    # dataset/variable is recovered via whichever ItemDef points at it with
    # def:ValueListRef, not by matching variable names (which need not be unique
    # across datasets).
    valuelist_owner: dict[str, tuple[str, str]] = {}
    for item_oid_value, item_el in item_defs_by_oid.items():
        vl_ref_el = item_el.find(_d("ValueListRef"))
        if vl_ref_el is None:
            continue
        found = index.by_oid.get(item_oid_value)
        if found is not None and found[0] == "item" and "." in found[1]:
            ds_name, var_name = found[1].split(".", 1)
            valuelist_owner[vl_ref_el.get("ValueListOID")] = (ds_name, var_name)

    # def:ValueListDef* -> valuelists/<dataset>__<variable>.yaml
    valuelists_data: dict[str, dict] = {}
    for vl_el in mdv_el.findall(_d("ValueListDef")):
        oid_value = vl_el.get("OID")
        xpath = f"/.../ValueListDef[@OID={oid_value!r}]"
        item_refs = sorted(
            vl_el.findall(_o("ItemRef")),
            key=lambda e: int(e.get("OrderNumber", "0") or 0),
        )
        if not item_refs:
            _report("element", xpath, "ValueListDef with no ItemRef")
            continue
        owner = valuelist_owner.get(oid_value)
        if owner is not None:
            dataset_name, variable_name = owner
        else:
            first_item_el = item_defs_by_oid.get(item_refs[0].get("ItemOID"))
            variable_name = (
                first_item_el.get("Name") if first_item_el is not None else "UNKNOWN"
            )
            dataset_name = None
            _report(
                "element",
                xpath,
                "no ItemDef references this ValueListDef via def:ValueListRef; guessing dataset",
            )
        entries = []
        for i, ir_el in enumerate(item_refs, start=1):
            var_xpath = f"{xpath}/ItemRef[{i}]"
            _check_unknown(
                ir_el,
                {
                    "ItemOID",
                    "OrderNumber",
                    "Mandatory",
                    "MethodOID",
                    "Role",
                    _d("IsNonStandard"),
                    _d("HasNoData"),
                },
                {_d("WhereClauseRef")},
                var_xpath,
            )
            item_oid_value = ir_el.get("ItemOID")
            item_el = item_defs_by_oid.get(item_oid_value)
            if item_el is None:
                _report(
                    "element",
                    var_xpath,
                    f"ItemRef with no matching ItemDef OID={item_oid_value!r}",
                )
                continue
            var_entry = _import_variable(
                item_el,
                ir_el,
                index,
                ctx,
                xpath=f"/.../ItemDef[@OID={item_oid_value!r}]",
            )
            entry_name = f"ENTRY{i}"
            wc_ref_el = ir_el.find(_d("WhereClauseRef"))
            where_ref = (
                index.ref_or_oid(wc_ref_el.get("WhereClauseOID"))
                if wc_ref_el is not None
                else []
            )
            var_entry_oid = var_entry.pop("__oid__", None)
            item_data = {k: v for k, v in var_entry.items()}
            if var_entry_oid:
                item_data["oid"] = var_entry_oid
            entries.append({"name": entry_name, "where": where_ref, "item": item_data})
        key = f"{(dataset_name or 'unknown').lower()}__{variable_name.lower()}"
        vl_entry: dict = {
            "dataset": dataset_name or "UNKNOWN",
            "variable": variable_name,
            "entries": entries,
        }
        derived = f"VL.{_slugify(vl_entry['dataset'])}.{_slugify(variable_name)}"
        if oid_value != derived:
            vl_entry["oid"] = oid_value
        valuelists_data[key] = vl_entry
        _check_unknown(vl_el, {"OID"}, {_o("ItemRef"), _o("Description")}, xpath)

    # arm:AnalysisResultDisplays -> analysis-results/<name>.yaml
    analysis_results_data: dict[str, dict] = {}
    displays_el = mdv_el.find(_a("AnalysisResultDisplays"))
    if displays_el is not None:
        for rd_el in displays_el.findall(_a("ResultDisplay")):
            oid_value = rd_el.get("OID")
            xpath = f"/.../ResultDisplay[@OID={oid_value!r}]"
            key = _slug_tail(oid_value)
            rd_entry: dict = {
                "name": rd_el.get("Name"),
                "title": ctx.text_of(rd_el, _o("Description"), xpath=xpath) or "",
            }
            doc_ref_el = rd_el.find(_d("DocumentRef"))
            if doc_ref_el is not None:
                rd_entry["document"] = _import_document_ref(doc_ref_el, index)
            derived = f"RD.{_path_to_slug(key)}"
            if oid_value != derived:
                rd_entry["oid"] = oid_value
            results = []
            for ar_el in rd_el.findall(_a("AnalysisResult")):
                results.append(
                    _import_analysis_result(ar_el, index, ctx, item_defs_by_oid)
                )
            rd_entry["results"] = results
            analysis_results_data[key] = rd_entry
            _check_unknown(
                rd_el,
                {"OID", "Name"},
                {_o("Description"), _d("DocumentRef"), _a("AnalysisResult")},
                xpath,
            )
        _check_unknown(
            displays_el, set(), {_a("ResultDisplay")}, "/.../AnalysisResultDisplays"
        )

    if ctx.violations and not force_lang_en:
        print(
            f"error: {len(ctx.violations)} non-English or duplicate TranslatedText element(s) found:"
        )
        for v in ctx.violations:
            print(f"  {v.xpath}: {v.detail}")
        raise ImportError_(
            f"{len(ctx.violations)} TranslatedText element(s) would be silently discarded; "
            "re-run with --force-lang en to import anyway and drop them"
        )

    if destination.exists():
        removed = sum(1 for _ in destination.iterdir())
        shutil.rmtree(destination)
        if removed:
            print(
                f"cleared {removed} existing entr{'y' if removed == 1 else 'ies'} from {destination}"
            )
    destination.mkdir(parents=True)

    _write(destination / "study.yaml", study_data)
    if standards_data:
        _write(destination / "standards.yaml", {"standards": standards_data})
    if documents_data or annotated_crf_data or supplemental_docs_data:
        documents_file: dict = {"documents": documents_data}
        if annotated_crf_data:
            documents_file["annotated_crf"] = annotated_crf_data
        if supplemental_docs_data:
            documents_file["supplemental_docs"] = supplemental_docs_data
        _write(destination / "documents.yaml", documents_file)
    for name, entry in datasets_data.items():
        _write(destination / "datasets" / f"{name}.yaml", entry)
    for name, entry in codelists_data.items():
        _write(destination / "codelists" / f"{name}.yaml", entry)
    for relpath, entry in methods_data.items():
        _write(destination / "methods" / f"{relpath}.yaml", entry)
    for relpath, entry in comments_data.items():
        _write(destination / "comments" / f"{relpath}.yaml", entry)
    for relpath, entry in whereclauses_data.items():
        _write(destination / "whereclauses" / f"{relpath}.yaml", entry)
    for key, entry in valuelists_data.items():
        _write(destination / "valuelists" / f"{key}.yaml", entry)
    for relpath, entry in analysis_results_data.items():
        _write(destination / "analysis-results" / f"{relpath}.yaml", entry)

    if expression_contexts:
        study_data["expression_contexts"] = expression_contexts
        _write(destination / "study.yaml", study_data)


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    dump(data, path)


_slugify = oidmod.slugify
_path_to_slug = oidmod.path_to_slug


def _import_document_ref(doc_ref_el: etree._Element, index: ReverseIndex) -> dict:
    leaf_id = doc_ref_el.get("leafID")
    result: dict = {"ref": index.ref_or_oid(leaf_id)}
    page_el = doc_ref_el.find(_d("PDFPageRef"))
    if page_el is not None:
        if page_el.get("FirstPage") and page_el.get("LastPage"):
            result["pages"] = {
                "first": int(page_el.get("FirstPage")),
                "last": int(page_el.get("LastPage")),
            }
        elif page_el.get("PageRefs"):
            refs = page_el.get("PageRefs").split()
            # A PhysicalRef's PageRefs are real page numbers (list[int]); a
            # NamedDestination's are PDF bookmark names, e.g. "section2.1" (list[str]) -
            # Pages' own docstring is what xml_emit later infers Type back out from.
            result["pages"] = (
                [int(r) for r in refs] if all(r.isdigit() for r in refs) else refs
            )
        if page_el.get("Title"):
            result["title"] = page_el.get("Title")
        _check_unknown(
            page_el,
            {"PageRefs", "FirstPage", "LastPage", "Type", "Title"},
            set(),
            "/.../PDFPageRef",
        )
    _check_unknown(doc_ref_el, {"leafID"}, {_d("PDFPageRef")}, "/.../DocumentRef")
    return result


def _import_variable(
    item_el: etree._Element,
    ir_el: etree._Element,
    index: ReverseIndex,
    ctx: ImportContext,
    *,
    xpath: str,
) -> dict:
    name = item_el.get("Name")
    entry: dict = {
        "name": name,
        "label": ctx.text_of(item_el, _o("Description"), xpath=xpath) or "",
        "type": item_el.get("DataType"),
    }
    sas_field_name = item_el.get("SASFieldName")
    if sas_field_name and sas_field_name != name:
        entry["sas_field_name"] = sas_field_name
    if item_el.get("Length"):
        entry["length"] = int(item_el.get("Length"))
    if item_el.get("SignificantDigits"):
        entry["significant_digits"] = int(item_el.get("SignificantDigits"))
    if item_el.get(_d("DisplayFormat")):
        entry["display_format"] = item_el.get(_d("DisplayFormat"))
    entry["mandatory"] = ir_el.get("Mandatory") == "Yes"
    if ir_el.get("Role"):
        entry["role"] = ir_el.get("Role")
    if ir_el.get(_d("IsNonStandard")) == "Yes":
        entry["is_non_standard"] = True
    if ir_el.get(_d("HasNoData")) == "Yes":
        entry["has_no_data"] = True
    cl_ref_el = item_el.find(_o("CodeListRef"))
    if cl_ref_el is not None:
        entry["codelist"] = index.ref_or_oid(cl_ref_el.get("CodeListOID"))
        _check_unknown(cl_ref_el, {"CodeListOID"}, set(), xpath + "/CodeListRef")
    method_oid_value = ir_el.get("MethodOID")
    if method_oid_value:
        entry["method"] = index.ref_or_oid(method_oid_value)
    comment_oid_value = item_el.get(_d("CommentOID"))
    if comment_oid_value:
        entry["comment"] = index.ref_or_oid(comment_oid_value)
    vl_ref_el = item_el.find(_d("ValueListRef"))
    if vl_ref_el is not None:
        entry["valuelist"] = index.ref_or_oid(vl_ref_el.get("ValueListOID"))
        _check_unknown(vl_ref_el, {"ValueListOID"}, set(), xpath + "/ValueListRef")
    origin_els = item_el.findall(_d("Origin"))
    if origin_els:
        entry["origin"] = _import_origin(
            origin_els[0], index, ctx, xpath=xpath + "/Origin"
        )
        if len(origin_els) > 1:
            _report("element", xpath, "multiple def:Origin (using the first)")
    _check_unknown(
        item_el,
        {
            "OID",
            "Name",
            "SASFieldName",
            "DataType",
            "Length",
            "SignificantDigits",
            _d("DisplayFormat"),
            _d("CommentOID"),
        },
        {_o("Description"), _o("CodeListRef"), _d("Origin"), _d("ValueListRef")},
        xpath,
    )
    entry["__oid__"] = item_el.get("OID")
    return entry


def _import_alias_variable(
    name: str,
    label: str,
    ir_el: etree._Element,
    index: ReverseIndex,
    item_oid_value: str,
    *,
    context: str,
) -> dict:
    entry: dict = {
        "name": name,
        "label": label,
        "type": "text",
        "mandatory": ir_el.get("Mandatory") == "Yes",
        "same_as": index.ref_or_oid(item_oid_value),
    }
    if ir_el.get("Role"):
        entry["role"] = ir_el.get("Role")
    if ir_el.get(_d("IsNonStandard")) == "Yes":
        entry["is_non_standard"] = True
    if ir_el.get(_d("HasNoData")) == "Yes":
        entry["has_no_data"] = True
    method_oid_value = ir_el.get("MethodOID")
    if method_oid_value:
        entry["method"] = index.ref_or_oid(method_oid_value)
    return entry


def _import_origin(
    origin_el: etree._Element, index: ReverseIndex, ctx: ImportContext, *, xpath: str
) -> dict:
    origin_type = origin_el.get("Type")
    entry: dict = {"type": origin_type}
    desc_text = ctx.text_of(origin_el, _o("Description"), xpath=xpath)
    if desc_text:
        if origin_type == "Predecessor":
            entry["source"] = desc_text
        else:
            entry["description"] = desc_text
    if origin_el.get("Source"):
        entry["data_source"] = origin_el.get("Source")
    doc_ref_el = origin_el.find(_d("DocumentRef"))
    if doc_ref_el is not None:
        doc_ref = _import_document_ref(doc_ref_el, index)
        entry["document"] = doc_ref["ref"]
        if "pages" in doc_ref:
            entry["pages"] = doc_ref["pages"]
        if "title" in doc_ref:
            entry["pages_title"] = doc_ref["title"]
    _check_unknown(
        origin_el, {"Type", "Source"}, {_o("Description"), _d("DocumentRef")}, xpath
    )
    return entry


def _import_analysis_result(
    ar_el: etree._Element,
    index: ReverseIndex,
    ctx: ImportContext,
    item_defs_by_oid: dict,
) -> dict:
    oid_value = ar_el.get("OID")
    xpath = f"/.../AnalysisResult[@OID={oid_value!r}]"
    entry: dict = {
        "name": _slug_tail(oid_value).upper(),
        "description": ctx.text_of(ar_el, _o("Description"), xpath=xpath) or "",
        "reason": ar_el.get("AnalysisReason"),
        "purpose": ar_el.get("AnalysisPurpose"),
    }
    if ar_el.get("ParameterOID"):
        entry["parameter"] = index.ref_or_oid(ar_el.get("ParameterOID"))
    datasets_el = ar_el.find(_a("AnalysisDatasets"))
    datasets: list[dict] = []
    if datasets_el is not None:
        join_comment_oid = datasets_el.get(_d("CommentOID"))
        if join_comment_oid:
            entry["join_comment"] = index.ref_or_oid(join_comment_oid)
        for ad_el in datasets_el.findall(_a("AnalysisDataset")):
            ig_oid_value = ad_el.get("ItemGroupOID")
            ad_xpath = f"{xpath}/AnalysisDataset[@ItemGroupOID={ig_oid_value!r}]"
            ds_entry: dict = {"dataset": index.ref_or_oid(ig_oid_value)}
            wc_ref_el = ad_el.find(_d("WhereClauseRef"))
            if wc_ref_el is not None:
                ds_entry["where"] = index.ref_or_oid(wc_ref_el.get("WhereClauseOID"))
            variables = []
            for av_el in ad_el.findall(_a("AnalysisVariable")):
                item_oid_value = av_el.get("ItemOID")
                item_el = item_defs_by_oid.get(item_oid_value)
                variables.append(
                    item_el.get("Name")
                    if item_el is not None
                    else {"oid": item_oid_value}
                )
            ds_entry["variables"] = variables
            datasets.append(ds_entry)
            _check_unknown(
                ad_el,
                {"ItemGroupOID"},
                {_d("WhereClauseRef"), _a("AnalysisVariable")},
                ad_xpath,
            )
        _check_unknown(
            datasets_el,
            {_d("CommentOID")},
            {_a("AnalysisDataset")},
            xpath + "/AnalysisDatasets",
        )
    entry["datasets"] = datasets
    doc_el = ar_el.find(_a("Documentation"))
    if doc_el is not None:
        doc_entry: dict = {
            "description": ctx.text_of(
                doc_el, _o("Description"), xpath=xpath + "/Documentation"
            )
            or ""
        }
        dr_el = doc_el.find(_d("DocumentRef"))
        if dr_el is not None:
            doc_entry["document"] = _import_document_ref(dr_el, index)
        entry["documentation"] = doc_entry
        _check_unknown(
            doc_el,
            set(),
            {_o("Description"), _d("DocumentRef")},
            xpath + "/Documentation",
        )
    pc_el = ar_el.find(_a("ProgrammingCode"))
    if pc_el is not None:
        pc_entry: dict = {}
        if pc_el.get("Context"):
            pc_entry["context"] = pc_el.get("Context")
        code_el = pc_el.find(_a("Code"))
        if code_el is not None:
            pc_entry["code"] = code_el.text or ""
        dr_el = pc_el.find(_d("DocumentRef"))
        if dr_el is not None:
            pc_entry["document"] = _import_document_ref(dr_el, index)
        entry["programming_code"] = pc_entry
        _check_unknown(
            pc_el,
            {"Context"},
            {_a("Code"), _d("DocumentRef")},
            xpath + "/ProgrammingCode",
        )
    # AnalysisResult's derived OID includes the parent ResultDisplay's path (AR.<PATH>.<ENTRY>);
    # `name:` here is synthesised from the OID tail rather than a real CDISC Name (there isn't
    # one), so it is not worth recomputing the derivation just to possibly skip a redundant
    # override - always set it, like the other value-level / no-natural-name imports.
    entry["oid"] = oid_value
    _check_unknown(
        ar_el,
        {"OID", "ParameterOID", "AnalysisReason", "AnalysisPurpose"},
        {
            _o("Description"),
            _a("AnalysisDatasets"),
            _a("Documentation"),
            _a("ProgrammingCode"),
        },
        xpath,
    )
    return entry
