"""A CommentDef can carry more than one def:DocumentRef (maxOccurs="unbounded" in the
schema, e.g. a comment citing both an ADRG section and a supporting SAS program) - the
old comment.document:/pages:/pages_title: flat fields only ever modeled one.
CommentDef.documents: is now a list of the same DocumentRef model used elsewhere
(ResultDisplay.document, Documentation.document, ProgrammingCode.document). Neither
bundled fixture happens to have a multi-DocumentRef CommentDef, so this is a synthetic
round-trip through a minimal file tree rather than a fixture-derived check.
"""

from __future__ import annotations

from lxml import etree

from defineyaml.linker import SymbolTable
from defineyaml.models import CommentDef, DocumentRef
from defineyaml.xml_emit import DEF_NS, _comment_def
from defineyaml.xml_import import ReverseIndex, _import_document_ref


def test_comment_documents_defaults_to_empty_list():
    com = CommentDef(description="x")
    assert com.documents == []


def _emit(com: CommentDef, *, relpath: str = "test") -> etree._Element:
    table = SymbolTable()
    table.register("document", "ACRF", "LF.ACRF", None, None)
    table.register("document", "SAP", "LF.SAP", None, None)
    parent = etree.Element("parent")
    _comment_def(parent, relpath, com, table)
    return parent.find(f"{{{DEF_NS}}}CommentDef")


def test_multiple_documents_each_emit_their_own_document_ref():
    com = CommentDef(
        description="See both the ADRG and the derivation program.",
        documents=[
            DocumentRef(ref="acrf", pages=[4]),
            DocumentRef(ref="sap", pages=["section9.2"]),
        ],
    )
    el = _emit(com)
    doc_refs = el.findall(f"{{{DEF_NS}}}DocumentRef")
    assert len(doc_refs) == 2
    assert doc_refs[0].get("leafID") == "LF.ACRF"
    assert doc_refs[1].get("leafID") == "LF.SAP"


def test_import_captures_every_document_ref_not_just_the_first():
    comment_xml = f"""
    <def:CommentDef xmlns:def="{DEF_NS}" xmlns:odm="http://www.cdisc.org/ns/odm/v1.3" OID="COM.TEST">
      <odm:Description><odm:TranslatedText xml:lang="en">text</odm:TranslatedText></odm:Description>
      <def:DocumentRef leafID="LF.ACRF"/>
      <def:DocumentRef leafID="LF.SAP"/>
    </def:CommentDef>
    """
    com_el = etree.fromstring(comment_xml)
    index = ReverseIndex()
    index.add("LF.ACRF", "document", "acrf")
    index.add("LF.SAP", "document", "sap")
    doc_ref_els = com_el.findall(f"{{{DEF_NS}}}DocumentRef")
    documents = [_import_document_ref(e, index) for e in doc_ref_els]
    assert documents == [{"ref": "acrf"}, {"ref": "sap"}]
