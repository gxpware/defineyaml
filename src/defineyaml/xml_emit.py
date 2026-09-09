"""File tree -> define.xml (CLAUDE.md build order step 2).

Builds the lxml tree for the subset of ODM 1.3.2 / Define-XML 2.1 / ARM 1.0
this tool models (CLAUDE.md §2-§7) and resolves every `Ref` field via the
linker (linker.py) along the way. An unresolved reference or an OID
collision raises `linker.LinkError`, which the CLI reports and exits on -
per CLAUDE.md §3 ("the linker pass"), that is a hard error, not a warning.
"""

from __future__ import annotations

from pathlib import Path

from lxml import etree

from . import oid as oidmod
from .linker import (
    LoadedTree,
    SymbolTable,
    resolve_item_ref,
    resolve_ref,
    resolve_scoped_item_ref,
    resolve_valuelist_ref,
    standard_lookup_key,
    standard_name_counts,
)
from .models import (
    AnalysisDataset,
    DocumentRef,
    EnumeratedCodeList,
    PageRange,
    RangeCheck,
    RefByOid,
    Variable,
)

ODM_NS = "http://www.cdisc.org/ns/odm/v1.3"
DEF_NS = "http://www.cdisc.org/ns/def/v2.1"
XLINK_NS = "http://www.w3.org/1999/xlink"
ARM_NS = "http://www.cdisc.org/ns/arm/v1.0"
XML_NS = "http://www.w3.org/XML/1998/namespace"

NSMAP = {None: ODM_NS, "def": DEF_NS, "xlink": XLINK_NS, "arm": ARM_NS}


def _o(tag: str) -> str:
    return f"{{{ODM_NS}}}{tag}"


def _d(tag: str) -> str:
    return f"{{{DEF_NS}}}{tag}"


def _x(tag: str) -> str:
    return f"{{{XLINK_NS}}}{tag}"


def _a(tag: str) -> str:
    return f"{{{ARM_NS}}}{tag}"


def _yn(value: bool) -> str:
    return "Yes" if value else "No"


def _text_el(parent: etree._Element, tag: str, text: str) -> etree._Element:
    el = etree.SubElement(parent, _o(tag))
    tt = etree.SubElement(el, _o("TranslatedText"))
    tt.set(f"{{{XML_NS}}}lang", "en")
    tt.text = text
    return el


def _document_ref(
    parent: etree._Element, doc_ref: DocumentRef, table: SymbolTable, *, context: str
) -> None:
    leaf_oid = resolve_ref(table, "document", doc_ref.ref, context=context)
    el = etree.SubElement(parent, _d("DocumentRef"))
    el.set("leafID", leaf_oid)
    if doc_ref.pages is not None:
        page_el = etree.SubElement(el, _d("PDFPageRef"))
        if isinstance(doc_ref.pages, PageRange):
            page_el.set("Type", "PhysicalRef")
            page_el.set("FirstPage", str(doc_ref.pages.first))
            page_el.set("LastPage", str(doc_ref.pages.last))
        else:
            # A list of actual page numbers is a PhysicalRef; a list of PDF bookmark
            # names (Pages' list[str] alternative) is a NamedDestination - inferred from
            # which one the pages: value parsed as, per Pages' own docstring.
            is_physical = all(isinstance(p, int) for p in doc_ref.pages)
            page_el.set("Type", "PhysicalRef" if is_physical else "NamedDestination")
            page_el.set("PageRefs", " ".join(str(p) for p in doc_ref.pages))
        if doc_ref.title is not None:
            page_el.set("Title", doc_ref.title)


def _leaf(parent: etree._Element, leaf_id: str, href: str, title: str | None) -> None:
    el = etree.SubElement(parent, _d("leaf"))
    el.set("ID", leaf_id)
    el.set(_x("href"), href)
    etree.SubElement(el, _d("title")).text = title or Path(href).name


def _range_check(
    parent: etree._Element, check: RangeCheck, table: SymbolTable, *, context: str
) -> None:
    el = etree.SubElement(parent, _o("RangeCheck"))
    el.set("Comparator", check.comparator)
    el.set("SoftHard", "Soft")
    el.set(_d("ItemOID"), resolve_item_ref(table, check.variable, context=context))
    for value in check.values:
        etree.SubElement(el, _o("CheckValue")).text = value


def _where_clause_def(
    parent: etree._Element,
    oid_value: str,
    conditions: list[RangeCheck],
    comment_oid: str | None,
    table: SymbolTable,
    *,
    context: str,
) -> None:
    el = etree.SubElement(parent, _d("WhereClauseDef"))
    el.set("OID", oid_value)
    if comment_oid is not None:
        el.set(_d("CommentOID"), comment_oid)
    for check in conditions:
        _range_check(el, check, table, context=context)


def _origin(
    parent: etree._Element, origin, table: SymbolTable, *, context: str
) -> None:
    el = etree.SubElement(parent, _d("Origin"))
    el.set("Type", origin.type)
    if origin.data_source is not None:
        el.set("Source", origin.data_source)
    desc_text = origin.source if origin.type == "Predecessor" else origin.description
    if desc_text:
        _text_el(el, "Description", desc_text)
    if origin.document is not None:
        doc_ref = DocumentRef(
            ref=origin.document, pages=origin.pages, title=origin.pages_title
        )
        _document_ref(el, doc_ref, table, context=context)


def _item_def(
    parent: etree._Element,
    oid_value: str,
    var: Variable,
    table: SymbolTable,
    *,
    context: str,
) -> None:
    el = etree.SubElement(parent, _o("ItemDef"))
    el.set("OID", oid_value)
    el.set("Name", var.name)
    el.set("SASFieldName", var.sas_field_name or var.name)
    el.set("DataType", var.type)
    if var.length is not None:
        el.set("Length", str(var.length))
    if var.significant_digits is not None:
        el.set("SignificantDigits", str(var.significant_digits))
    if var.display_format:
        el.set(_d("DisplayFormat"), var.display_format)
    if var.comment is not None:
        el.set(
            _d("CommentOID"),
            resolve_ref(table, "comment", var.comment, context=context),
        )
    _text_el(el, "Description", var.label)
    if var.codelist is not None:
        cl_ref = etree.SubElement(el, _o("CodeListRef"))
        cl_ref.set(
            "CodeListOID", resolve_ref(table, "codelist", var.codelist, context=context)
        )
    if var.origin is not None:
        _origin(el, var.origin, table, context=context)
    if var.valuelist is not None:
        vl_ref = etree.SubElement(el, _d("ValueListRef"))
        vl_ref.set(
            "ValueListOID",
            resolve_valuelist_ref(
                table, context.split(".")[0], var.valuelist, context=context
            ),
        )


def _item_ref(
    parent: etree._Element,
    item_oid_value: str,
    *,
    order: int,
    mandatory: bool,
    key_sequence: int | None = None,
    method_oid_value: str | None = None,
    where_clause_oid: str | None = None,
    role: str | None = None,
    is_non_standard: bool = False,
    has_no_data: bool = False,
) -> None:
    el = etree.SubElement(parent, _o("ItemRef"))
    el.set("ItemOID", item_oid_value)
    el.set("OrderNumber", str(order))
    el.set("Mandatory", _yn(mandatory))
    if key_sequence is not None:
        el.set("KeySequence", str(key_sequence))
    if method_oid_value is not None:
        el.set("MethodOID", method_oid_value)
    if role is not None:
        el.set("Role", role)
    if is_non_standard:
        el.set(_d("IsNonStandard"), "Yes")
    if has_no_data:
        el.set(_d("HasNoData"), "Yes")
    if where_clause_oid is not None:
        wc_ref = etree.SubElement(el, _d("WhereClauseRef"))
        wc_ref.set("WhereClauseOID", where_clause_oid)


def _codelist(parent: etree._Element, name: str, cl, table: SymbolTable) -> None:
    oid_value = table.lookup_own(
        "codelist", oidmod.slugify(name)
    ) or oidmod.codelist_oid(name)
    el = etree.SubElement(parent, _o("CodeList"))
    el.set("OID", oid_value)
    el.set("Name", cl.name)
    el.set("DataType", cl.type)
    if isinstance(cl, EnumeratedCodeList):
        if cl.sas_format_name is not None:
            el.set("SASFormatName", cl.sas_format_name)
        if cl.standard is not None:
            el.set(
                _d("StandardOID"),
                resolve_ref(table, "standard", cl.standard, context=name),
            )
        if cl.comment is not None:
            el.set(
                _d("CommentOID"),
                resolve_ref(table, "comment", cl.comment, context=name),
            )
        if cl.extended:
            el.set(_d("IsNonStandard"), "Yes")
        # A term with no decode: emits as EnumeratedItem, not CodeListItem - the two element
        # kinds are a schema-level choice per CodeList, never mixed (EnumeratedCodeList's
        # _check_decode_uniform enforces every term agrees, so checking the first is enough).
        has_decode = bool(cl.terms) and cl.terms[0].decode is not None
        item_tag = "CodeListItem" if has_decode else "EnumeratedItem"
        for i, term in enumerate(cl.terms, start=1):
            item_el = etree.SubElement(el, _o(item_tag))
            item_el.set("CodedValue", term.code)
            item_el.set("OrderNumber", str(i))
            if term.rank is not None:
                item_el.set(
                    "Rank",
                    str(int(term.rank))
                    if isinstance(term.rank, float) and term.rank.is_integer()
                    else str(term.rank),
                )
            if term.extended:
                item_el.set(_d("ExtendedValue"), "Yes")
            if has_decode:
                _text_el(item_el, "Decode", term.decode)
            if term.nci_code:
                alias = etree.SubElement(item_el, _o("Alias"))
                alias.set("Context", "nci:ExtCodeID")
                alias.set("Name", term.nci_code)
            for term_alias in term.aliases:
                alias = etree.SubElement(item_el, _o("Alias"))
                alias.set("Context", term_alias.context)
                alias.set("Name", term_alias.name)
        if cl.nci_code:
            alias = etree.SubElement(el, _o("Alias"))
            alias.set("Context", "nci:ExtCodeID")
            alias.set("Name", cl.nci_code)
        for cl_alias in cl.aliases:
            alias = etree.SubElement(el, _o("Alias"))
            alias.set("Context", cl_alias.context)
            alias.set("Name", cl_alias.name)
    else:
        ext = etree.SubElement(el, _o("ExternalCodeList"))
        ext.set("Dictionary", cl.external.dictionary)
        ext.set("Version", cl.external.version)


def _method_def(parent: etree._Element, relpath: str, md, table: SymbolTable) -> None:
    oid_value = table.lookup_own(
        "method", oidmod.path_to_slug(relpath)
    ) or oidmod.method_oid(relpath)
    el = etree.SubElement(parent, _o("MethodDef"))
    el.set("OID", oid_value)
    el.set("Name", md.name)
    el.set("Type", md.type)
    _text_el(el, "Description", md.description or "")
    for expr in md.expressions:
        fe = etree.SubElement(el, _o("FormalExpression"))
        fe.set("Context", expr.context)
        fe.text = expr.code
    # Last in MethodDef's child sequence, after FormalExpression (and Alias, unmodeled).
    for doc_ref in md.documents:
        _document_ref(el, doc_ref, table, context=relpath)


def _comment_def(parent: etree._Element, relpath: str, com, table: SymbolTable) -> None:
    oid_value = table.lookup_own(
        "comment", oidmod.path_to_slug(relpath)
    ) or oidmod.comment_oid(relpath)
    el = etree.SubElement(parent, _d("CommentDef"))
    el.set("OID", oid_value)
    _text_el(el, "Description", com.description)
    for doc_ref in com.documents:
        _document_ref(el, doc_ref, table, context=relpath)


def _resolve_where(
    table: SymbolTable,
    mdv: etree._Element,
    where,
    inline_oid: str,
    comment_oid: str | None,
    *,
    context: str,
) -> str | None:
    """Resolve a `where:` field: a named reference, or an inline list -> synthesised WhereClauseDef."""
    if where is None:
        return None
    if isinstance(where, list):
        _where_clause_def(mdv, inline_oid, where, comment_oid, table, context=context)
        return inline_oid
    return resolve_ref(table, "whereclause", where, context=context)


def build_odm(tree: LoadedTree, table: SymbolTable) -> etree._Element:
    root = etree.Element(_o("ODM"), nsmap=NSMAP)
    odm_header = tree.study.odm
    root.set("FileOID", odm_header.file_oid)
    root.set("ODMVersion", "1.3.2")
    root.set("FileType", "Snapshot")
    if odm_header.creation_datetime:
        root.set("CreationDateTime", odm_header.creation_datetime)
    if odm_header.as_of_datetime:
        root.set("AsOfDateTime", odm_header.as_of_datetime)
    if odm_header.originator:
        root.set("Originator", odm_header.originator)
    if odm_header.source_system:
        root.set("SourceSystem", odm_header.source_system)
    if odm_header.source_system_version:
        root.set("SourceSystemVersion", odm_header.source_system_version)
    root.set(_d("Context"), "Submission")

    study_el = etree.SubElement(root, _o("Study"))
    study_el.set("OID", tree.study.study.oid)
    gv = etree.SubElement(study_el, _o("GlobalVariables"))
    etree.SubElement(gv, _o("StudyName")).text = tree.study.study.name
    etree.SubElement(gv, _o("StudyDescription")).text = (
        tree.study.study.description or ""
    )
    etree.SubElement(gv, _o("ProtocolName")).text = tree.study.study.protocol_name

    mdv = etree.SubElement(study_el, _o("MetaDataVersion"))
    mdv.set("OID", tree.study.metadata_version.oid)
    mdv.set("Name", tree.study.metadata_version.name)
    if tree.study.metadata_version.description:
        mdv.set("Description", tree.study.metadata_version.description)
    mdv.set(_d("DefineVersion"), tree.study.metadata_version.define_version)

    if tree.standards.standards:
        standards_el = etree.SubElement(mdv, _d("Standards"))
        std_name_counts = standard_name_counts(tree)
        for std in tree.standards.standards:
            key = standard_lookup_key(
                std_name_counts, std.name, std.publishing_set, std.version
            )
            std_oid = table.lookup_own("standard", key) or oidmod.standard_oid(std.name)
            el = etree.SubElement(standards_el, _d("Standard"))
            el.set("OID", std_oid)
            el.set("Name", std.name)
            el.set("Type", std.type)
            if std.publishing_set:
                el.set("PublishingSet", std.publishing_set)
            el.set("Version", std.version)
            el.set("Status", std.status)
            if std.comment is not None:
                el.set(
                    _d("CommentOID"),
                    resolve_ref(table, "comment", std.comment, context=std.name),
                )

    if tree.documents.annotated_crf:
        acrf_el = etree.SubElement(mdv, _d("AnnotatedCRF"))
        for i, ref in enumerate(tree.documents.annotated_crf):
            _document_ref(
                acrf_el,
                DocumentRef(ref=ref),
                table,
                context=f"documents.annotated_crf[{i}]",
            )
    if tree.documents.supplemental_docs:
        supp_el = etree.SubElement(mdv, _d("SupplementalDoc"))
        for i, ref in enumerate(tree.documents.supplemental_docs):
            _document_ref(
                supp_el,
                DocumentRef(ref=ref),
                table,
                context=f"documents.supplemental_docs[{i}]",
            )

    # def:ValueListDef* and def:WhereClauseDef* (named + inline), before any ItemGroupDef.
    for key, (path, vl) in tree.valuelists.items():
        vl_oid = table.lookup_own(
            "valuelist", f"{oidmod.slugify(vl.dataset)}.{oidmod.slugify(vl.variable)}"
        ) or oidmod.valuelist_oid(vl.dataset, vl.variable)
        el = etree.SubElement(mdv, _d("ValueListDef"))
        el.set("OID", vl_oid)
        for i, entry in enumerate(vl.entries, start=1):
            context = f"{vl.dataset}.{vl.variable}.{entry.name}"
            item_oid_value = table.lookup_own(
                "item",
                f"{oidmod.slugify(vl.dataset)}.{oidmod.slugify(vl.variable)}.{oidmod.slugify(entry.name)}",
            ) or oidmod.item_value_level_oid(vl.dataset, vl.variable, entry.name)
            method_oid_value = (
                resolve_ref(table, "method", entry.item.method, context=context)
                if entry.item.method
                else None
            )
            # entry.comment, when set, is the inline where clause's def:CommentOID (cross-dataset
            # join comment) - not related to entry.item.comment, which _item_def handles separately.
            comment_oid_value = (
                resolve_ref(table, "comment", entry.comment, context=context)
                if entry.comment
                else None
            )
            inline_oid = oidmod.whereclause_inline_oid(
                vl.dataset, vl.variable, entry.name
            )
            where_clause_oid_value = _resolve_where(
                table, mdv, entry.where, inline_oid, comment_oid_value, context=context
            )
            _item_ref(
                el,
                item_oid_value,
                order=i,
                mandatory=entry.item.mandatory,
                method_oid_value=method_oid_value,
                where_clause_oid=where_clause_oid_value,
                role=entry.item.role,
                is_non_standard=entry.item.is_non_standard,
                has_no_data=entry.item.has_no_data,
            )

    for relpath, (path, wc) in tree.whereclauses.items():
        wc_oid = table.lookup_own(
            "whereclause", oidmod.path_to_slug(relpath)
        ) or oidmod.whereclause_named_oid(relpath)
        comment_oid_value = (
            resolve_ref(table, "comment", wc.comment, context=relpath)
            if wc.comment
            else None
        )
        _where_clause_def(
            mdv, wc_oid, wc.conditions, comment_oid_value, table, context=relpath
        )

    # ItemGroupDef* (datasets)
    for name, (path, ds) in tree.datasets.items():
        ig_oid = table.lookup_own(
            "dataset", oidmod.slugify(name)
        ) or oidmod.itemgroup_oid(name)
        leaf_id = oidmod.leaf_dataset_oid(name)
        el = etree.SubElement(mdv, _o("ItemGroupDef"))
        el.set("OID", ig_oid)
        el.set("Name", ds.name)
        el.set("SASDatasetName", ds.name)
        el.set("Repeating", _yn(ds.repeating))
        el.set("IsReferenceData", _yn(ds.is_reference_data))
        if ds.domain is not None:
            el.set("Domain", ds.domain)
        if ds.is_non_standard:
            el.set(_d("IsNonStandard"), "Yes")
        if ds.has_no_data:
            el.set(_d("HasNoData"), "Yes")
        el.set("Purpose", ds.purpose)
        if ds.standard is not None:
            el.set(
                _d("StandardOID"),
                resolve_ref(table, "standard", ds.standard, context=name),
            )
        if ds.comment is not None:
            el.set(
                _d("CommentOID"),
                resolve_ref(table, "comment", ds.comment, context=name),
            )
        el.set(_d("Structure"), ds.structure)
        if ds.leaf is not None:
            el.set(_d("ArchiveLocationID"), leaf_id)
        _text_el(el, "Description", ds.label)
        for i, var in enumerate(ds.variables, start=1):
            context = f"{name}.{var.name}"
            if var.same_as is not None:
                # Disjunction: a second ItemRef against an existing ItemDef's OID,
                # not a new ItemDef of its own (CLAUDE.md §3, "No OR").
                item_oid_value = resolve_item_ref(table, var.same_as, context=context)
            else:
                item_oid_value = table.lookup_own(
                    "item", f"{oidmod.slugify(name)}.{oidmod.slugify(var.name)}"
                ) or oidmod.item_oid(name, var.name)
            key_sequence = ds.keys.index(var.name) + 1 if var.name in ds.keys else None
            method_oid_value = (
                resolve_ref(table, "method", var.method, context=context)
                if var.method
                else None
            )
            _item_ref(
                el,
                item_oid_value,
                order=i,
                mandatory=var.mandatory,
                key_sequence=key_sequence,
                method_oid_value=method_oid_value,
                role=var.role,
                is_non_standard=var.is_non_standard,
                has_no_data=var.has_no_data,
            )
        for alias in ds.aliases:
            alias_el = etree.SubElement(el, _o("Alias"))
            alias_el.set("Context", alias.context)
            alias_el.set("Name", alias.name)
        cls_el = etree.SubElement(el, _d("Class"))
        cls_el.set("Name", ds.cls)
        for sub in ds.subclasses:
            sub_el = etree.SubElement(cls_el, _d("SubClass"))
            sub_el.set("Name", sub.name)
            if sub.parent_class is not None:
                sub_el.set("ParentClass", sub.parent_class)
        if ds.leaf is not None:
            _leaf(el, leaf_id, ds.leaf.href, ds.leaf.title)

    # ItemDef* (dataset variables, then value-level items) - a same_as alias has no ItemDef.
    for name, (path, ds) in tree.datasets.items():
        for var in ds.variables:
            if var.same_as is not None:
                continue
            item_oid_value = table.lookup_own(
                "item", f"{oidmod.slugify(name)}.{oidmod.slugify(var.name)}"
            ) or oidmod.item_oid(name, var.name)
            _item_def(mdv, item_oid_value, var, table, context=f"{name}.{var.name}")
    for key, (path, vl) in tree.valuelists.items():
        for entry in vl.entries:
            item_oid_value = table.lookup_own(
                "item",
                f"{oidmod.slugify(vl.dataset)}.{oidmod.slugify(vl.variable)}.{oidmod.slugify(entry.name)}",
            ) or oidmod.item_value_level_oid(vl.dataset, vl.variable, entry.name)
            _item_def(
                mdv,
                item_oid_value,
                entry.item,
                table,
                context=f"{vl.dataset}.{vl.variable}.{entry.name}",
            )

    # CodeList*
    for name, (path, cl) in tree.codelists.items():
        _codelist(mdv, name, cl, table)

    # MethodDef*
    for relpath, (path, md) in tree.methods.items():
        _method_def(mdv, relpath, md, table)

    # def:CommentDef*
    for relpath, (path, com) in tree.comments.items():
        _comment_def(mdv, relpath, com, table)

    # def:leaf* (documents; dataset leafs are already nested in their ItemGroupDef)
    for doc in tree.documents.documents:
        leaf_id = table.lookup_own(
            "document", oidmod.slugify(doc.name)
        ) or oidmod.leaf_document_oid(doc.name)
        _leaf(mdv, leaf_id, doc.href, doc.title)

    # arm:AnalysisResultDisplays
    if tree.analysis_results:
        displays_el = etree.SubElement(mdv, _a("AnalysisResultDisplays"))
        for relpath, (path, rd) in tree.analysis_results.items():
            rd_oid = table.lookup_own(
                "resultdisplay", oidmod.path_to_slug(relpath)
            ) or oidmod.result_display_oid(relpath)
            rd_el = etree.SubElement(displays_el, _a("ResultDisplay"))
            rd_el.set("OID", rd_oid)
            rd_el.set("Name", rd.name)
            _text_el(rd_el, "Description", rd.title)
            _document_ref(rd_el, rd.document, table, context=relpath)
            for result in rd.results:
                context = f"{relpath}.{result.name}"
                ar_oid = table.lookup_own(
                    "analysisresult",
                    f"{oidmod.path_to_slug(relpath)}.{oidmod.slugify(result.name)}",
                ) or oidmod.analysis_result_oid(relpath, result.name)
                ar_el = etree.SubElement(rd_el, _a("AnalysisResult"))
                ar_el.set("OID", ar_oid)
                if result.parameter:
                    ar_el.set(
                        "ParameterOID",
                        resolve_item_ref(table, result.parameter, context=context),
                    )
                ar_el.set("AnalysisReason", result.reason)
                ar_el.set("AnalysisPurpose", result.purpose)
                _text_el(ar_el, "Description", result.description)
                datasets_el = etree.SubElement(ar_el, _a("AnalysisDatasets"))
                if result.join_comment:
                    datasets_el.set(
                        _d("CommentOID"),
                        resolve_ref(
                            table, "comment", result.join_comment, context=context
                        ),
                    )
                for ds_index, analysis_dataset in enumerate(result.datasets):
                    _analysis_dataset(
                        datasets_el,
                        mdv,
                        analysis_dataset,
                        table,
                        relpath=relpath,
                        result_name=result.name,
                        ds_index=ds_index,
                    )
                if result.documentation is not None:
                    doc_el = etree.SubElement(ar_el, _a("Documentation"))
                    _text_el(doc_el, "Description", result.documentation.description)
                    if result.documentation.document is not None:
                        _document_ref(
                            doc_el,
                            result.documentation.document,
                            table,
                            context=context,
                        )
                if result.programming_code is not None:
                    pc_el = etree.SubElement(ar_el, _a("ProgrammingCode"))
                    if result.programming_code.context:
                        pc_el.set("Context", result.programming_code.context)
                    if result.programming_code.code:
                        etree.SubElement(
                            pc_el, _a("Code")
                        ).text = result.programming_code.code
                    if result.programming_code.document is not None:
                        _document_ref(
                            pc_el,
                            result.programming_code.document,
                            table,
                            context=context,
                        )

    return root


def _analysis_dataset(
    parent: etree._Element,
    mdv: etree._Element,
    analysis_dataset: AnalysisDataset,
    table: SymbolTable,
    *,
    relpath: str,
    result_name: str,
    ds_index: int,
) -> None:
    context = f"{relpath}.{result_name}[{ds_index}]"
    ig_oid = resolve_ref(table, "dataset", analysis_dataset.dataset, context=context)
    el = etree.SubElement(parent, _a("AnalysisDataset"))
    el.set("ItemGroupOID", ig_oid)

    # No CLAUDE.md-documented OID pattern exists for an inline (non-named) ARM
    # where clause; this derives one from the AnalysisDataset's own position,
    # since it's owned by exactly one parent. Not registered in the symbol
    # table (nothing references it by name), so it is not collision-checked
    # against the rest of the tree the way every other derived OID is.
    inline_oid = oidmod.whereclause_named_oid(f"{relpath}.{result_name}.{ds_index}")
    where_clause_oid_value = _resolve_where(
        table, mdv, analysis_dataset.where, inline_oid, None, context=context
    )
    if where_clause_oid_value is not None:
        wc_ref = etree.SubElement(el, _d("WhereClauseRef"))
        wc_ref.set("WhereClauseOID", where_clause_oid_value)
    dataset_name = (
        analysis_dataset.dataset if isinstance(analysis_dataset.dataset, str) else None
    )
    for var_ref in analysis_dataset.variables:
        if isinstance(var_ref, RefByOid) or dataset_name is None:
            item_oid_value = var_ref.oid if isinstance(var_ref, RefByOid) else None
            if item_oid_value is None:
                raise ValueError(
                    f"cannot resolve variable {var_ref!r} in {context}: dataset is a literal OID, "
                    "so bare variable names have no dataset context - give the variable as {oid: ...} too"
                )
        else:
            item_oid_value = resolve_scoped_item_ref(
                table, dataset_name, var_ref, context=context
            )
        av_el = etree.SubElement(el, _a("AnalysisVariable"))
        av_el.set("ItemOID", item_oid_value)


def build_document_tree(source: Path) -> tuple[etree._ElementTree, SymbolTable]:
    """The linker pass plus XML emission, shared by write_define_xml (disk) and
    render_xml_bytes/html_render.render_html (served over HTTP by webui) - one place
    building the ODM tree so those three never drift into producing different XML for
    the same source tree.
    """
    from .linker import build_symbol_table, load_tree
    from .tree_time import latest_modification, now_iso

    tree = load_tree(source)
    # CreationDateTime is XSD-required. study.yaml leaves odm.creation_datetime blank by
    # default (scaffold.py) - so when it's empty, stamp it with the tree's latest
    # modification: git-history date if version-controlled, else newest YAML mtime, and
    # `now` only if neither can be determined (a tree with no files, which can't build
    # anyway). An explicitly-set value is emitted verbatim and never touched.
    if not tree.study.odm.creation_datetime:
        stamp, _ = latest_modification(source)
        tree.study.odm.creation_datetime = stamp or now_iso()
    table = build_symbol_table(tree)
    root = build_odm(tree, table)
    document_tree = etree.ElementTree(root)
    if tree.study.odm.stylesheet:
        pi = etree.ProcessingInstruction(
            "xml-stylesheet", f'type="text/xsl" href="{tree.study.odm.stylesheet}"'
        )
        root.addprevious(pi)
    return document_tree, table


def write_define_xml(source: Path, output: Path) -> None:
    document_tree, table = build_document_tree(source)
    output.parent.mkdir(parents=True, exist_ok=True)
    document_tree.write(
        str(output), xml_declaration=True, encoding="UTF-8", pretty_print=True
    )

    for kind, key, path in table.orphans(
        ("codelist", "method", "comment", "whereclause")
    ):
        print(f"warning: orphan {kind} {key!r} in {path} - nothing references it")


def render_xml_bytes(source: Path) -> bytes:
    """The same define.xml write_define_xml() writes to disk, as bytes - for serving
    over HTTP (the webui's "View define.xml" button) without touching the filesystem.
    """
    document_tree, _table = build_document_tree(source)
    return etree.tostring(
        document_tree, xml_declaration=True, encoding="UTF-8", pretty_print=True
    )
