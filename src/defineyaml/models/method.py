from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from .common import DefineBaseModel
from .documents import DocumentRef


class Expression(DefineBaseModel):
    context: str
    code: str


class MethodDef(DefineBaseModel):
    name: str
    type: Literal["Computation", "Imputation", "Other"] = "Computation"
    description: str | None = None
    expressions: list[Expression] = Field(default_factory=list)
    # -> def:DocumentRef* (with an optional def:PDFPageRef each) - a method citing the
    # documentation it's specified in, e.g. an ADRG page. Same DocumentRef model, and same
    # maxOccurs="unbounded", as CommentDef.documents; the XSD puts it last in MethodDef's
    # child sequence (Description, FormalExpression*, Alias*, def:DocumentRef*).
    documents: list[DocumentRef] = Field(default_factory=list)
    oid: str | None = None

    @model_validator(mode="after")
    def _check_expressions(self) -> "MethodDef":
        if self.expressions and not self.description:
            raise ValueError(
                "expressions: requires description: - a receiving system that "
                "cannot interpret the expression falls back to the description"
            )
        contexts = [e.context for e in self.expressions]
        if len(contexts) != len(set(contexts)):
            raise ValueError("duplicate Context within one method's expressions:")
        return self
