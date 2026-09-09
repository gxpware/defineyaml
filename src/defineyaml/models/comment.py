from __future__ import annotations

from pydantic import Field

from .common import DefineBaseModel
from .documents import DocumentRef


class CommentDef(DefineBaseModel):
    description: str
    # -> def:DocumentRef*; maxOccurs is unbounded in the schema (e.g. a comment citing
    # both an ADRG section and a supporting SAS program), so this is a list of the same
    # DocumentRef model used elsewhere (ResultDisplay.document, Documentation.document,
    # ProgrammingCode.document) rather than the flat document:/pages:/pages_title: fields
    # this used to have - those only ever supported one reference.
    documents: list[DocumentRef] = Field(default_factory=list)
    oid: str | None = None
