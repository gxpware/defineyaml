from __future__ import annotations

from pydantic import model_validator

from .common import DefineBaseModel, Ref
from .documents import DocumentRef
from .whereclause import RangeCheck


class ProgrammingCode(DefineBaseModel):
    context: str | None = None
    code: str | None = None
    document: DocumentRef | None = None

    @model_validator(mode="after")
    def _exactly_one_source(self) -> "ProgrammingCode":
        if bool(self.code) == bool(self.document):
            raise ValueError("programming_code needs exactly one of code: or document:")
        return self


class Documentation(DefineBaseModel):
    description: str
    document: DocumentRef | None = None


class AnalysisDataset(DefineBaseModel):
    dataset: Ref
    where: Ref | list[RangeCheck] | None = None
    variables: list[Ref]


class AnalysisResult(DefineBaseModel):
    name: str
    description: str
    parameter: Ref | None = None
    reason: str
    purpose: str
    datasets: list[AnalysisDataset]
    join_comment: Ref | None = None
    documentation: Documentation | None = None
    programming_code: ProgrammingCode | None = None
    oid: str | None = None

    @model_validator(mode="after")
    def _join_comment_required_for_multi_dataset(self) -> "AnalysisResult":
        if len(self.datasets) > 1 and not self.join_comment:
            raise ValueError(
                "join_comment is required when a result spans more than one dataset"
            )
        return self


class ResultDisplay(DefineBaseModel):
    name: str
    title: str
    document: DocumentRef
    results: list[AnalysisResult]
    oid: str | None = None
