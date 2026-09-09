"""def:PDFPageRef/@PageRefs isn't necessarily numeric: def:PDFPageRef/@Type distinguishes
a PhysicalRef (a real page number) from a NamedDestination (a PDF bookmark name, e.g.
"section2.1" - confirmed real, in the bundled SDTM example). Pages models both as
list[int] vs list[str]; xml_emit infers @Type from which one it's holding rather than
storing it, the same "derive it back out" principle the OID scheme runs on throughout.
"""

from __future__ import annotations

from lxml import etree

from defineyaml.linker import SymbolTable
from defineyaml.models import DocumentRef
from defineyaml.models.documents import PageRange
from defineyaml.xml_emit import DEF_NS, _document_ref
from defineyaml.xml_import import ReverseIndex, _import_document_ref


def _d(tag: str) -> str:
    return f"{{{DEF_NS}}}{tag}"


def test_pages_accepts_numeric_list_string_list_and_range():
    DocumentRef(ref="acrf", pages=[4, 5])
    DocumentRef(ref="acrf", pages=["section2.1"])
    DocumentRef(ref="acrf", pages=PageRange(first=112, last=114))


def _emit(doc_ref: DocumentRef) -> etree._Element:
    table = SymbolTable()
    table.register("document", "ACRF", "LF.ACRF", None, None)
    parent = etree.Element("parent")
    _document_ref(parent, doc_ref, table, context="test")
    return parent.find(_d("DocumentRef")).find(_d("PDFPageRef"))


def test_numeric_pages_emit_as_physicalref():
    page_el = _emit(DocumentRef(ref="acrf", pages=[4, 5]))
    assert page_el.get("Type") == "PhysicalRef"
    assert page_el.get("PageRefs") == "4 5"


def test_named_destination_pages_emit_as_nameddestination():
    page_el = _emit(DocumentRef(ref="acrf", pages=["section2.1"]))
    assert page_el.get("Type") == "NamedDestination"
    assert page_el.get("PageRefs") == "section2.1"


def test_page_range_emits_as_physicalref():
    page_el = _emit(DocumentRef(ref="acrf", pages=PageRange(first=112, last=114)))
    assert page_el.get("Type") == "PhysicalRef"
    assert page_el.get("FirstPage") == "112"
    assert page_el.get("LastPage") == "114"


def _import(page_el_xml: str) -> dict:
    doc_ref_el = etree.fromstring(
        f'<def:DocumentRef xmlns:def="{DEF_NS}" leafID="LF.ACRF">{page_el_xml}</def:DocumentRef>'
    )
    return _import_document_ref(doc_ref_el, ReverseIndex())


def test_import_numeric_pagerefs_as_ints():
    result = _import(
        f'<def:PDFPageRef xmlns:def="{DEF_NS}" Type="PhysicalRef" PageRefs="4 5"/>'
    )
    assert result["pages"] == [4, 5]


def test_import_named_destination_pagerefs_as_strings():
    result = _import(
        f'<def:PDFPageRef xmlns:def="{DEF_NS}" Type="NamedDestination" PageRefs="section2.1"/>'
    )
    assert result["pages"] == ["section2.1"]


def test_named_destination_roundtrips_through_emit_and_import():
    original = DocumentRef(ref="acrf", pages=["section2.1"], title="Section 2.1")
    page_el = _emit(original)
    reimported = _import(etree.tostring(page_el).decode())
    assert reimported["pages"] == ["section2.1"]
    assert reimported["title"] == "Section 2.1"
