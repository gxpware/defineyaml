from __future__ import annotations

from .common import DefineBaseModel, Ref


class PageRange(DefineBaseModel):
    first: int
    last: int


# def:PDFPageRef/@PageRefs is schema-typed as free text ("List of PDF pages separated by
# a space"), not necessarily numeric: def:PDFPageRef/@Type distinguishes a PhysicalRef
# (an actual page number - list[int] here) from a NamedDestination (a PDF bookmark name,
# e.g. "section2.1" - list[str]). @FirstPage/@LastPage, by contrast, are schema-typed as
# odm:integer with no such alternative, so PageRange stays numeric-only either way. Which
# of list[int]/list[str] applies isn't stored: YAML itself already tells them apart -
# `pages: [4, 5]` parses as ints, `pages: [section2.1]` can only parse as strings - so
# xml_emit infers Type the same way on the way back out (CLAUDE.md's usual preference for
# deriving over storing, applied here to a case that isn't even ambiguous to infer).
Pages = list[int] | list[str] | PageRange


class DocumentRef(DefineBaseModel):
    ref: Ref
    pages: Pages | None = None
    title: str | None = (
        None  # -> def:PDFPageRef/@Title; a human label, meaningful mainly for a NamedDestination
    )


class Document(DefineBaseModel):
    name: str
    href: str
    title: str
    oid: str | None = None
