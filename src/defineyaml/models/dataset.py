from __future__ import annotations

from typing import Literal

from pydantic import ConfigDict, Field, model_validator

from .common import Alias, DefineBaseModel, Ref
from .documents import Pages

OriginType = Literal[
    "Assigned", "Collected", "Derived", "Not Available", "Predecessor", "Protocol"
]
OriginSource = Literal["Investigator", "Sponsor", "Subject", "Vendor"]

VariableType = Literal[
    "text",
    "integer",
    "float",
    "date",
    "time",
    "datetime",
    "partialDate",
    "partialTime",
    "partialDatetime",
    "durationDatetime",
    "intervalDatetime",
    "incompleteDatetime",
    "incompleteDatePartialTime",
    "incompleteTimePartialDate",
    "boolean",
]


class Origin(DefineBaseModel):
    type: OriginType
    # Free descriptive text (e.g. a predecessor "DATASET.VARIABLE"), not an OID
    # reference: Define-XML's def:Origin has no OID slot for it. Predecessor-only -
    # a Derived/Collected/etc. origin's def:Origin/Description goes in description:
    # below instead. Distinct from data_source: further down - this and description:
    # are the Description text; def:Origin/@Source is a separate controlled-term
    # attribute.
    source: str | None = None
    # -> def:Origin/Description for every non-Predecessor type. Confirmed real in
    # the bundled SDTM submission, e.g. Type="Collected" Source="Vendor" with
    # Description "From Central lab (LB.LBNAM NE "LOCAL LAB")" - a free-form
    # clarification, not a dataset.variable mnemonic, which is why it's a separate
    # field from source: rather than the same field doing double duty by type.
    description: str | None = None
    data_source: OriginSource | None = None  # -> def:Origin/@Source
    document: Ref | None = None
    pages: Pages | None = None
    pages_title: str | None = None  # -> def:PDFPageRef/@Title

    @model_validator(mode="after")
    def _check_source_description_by_type(self) -> "Origin":
        if self.type == "Predecessor" and self.description is not None:
            raise ValueError(
                "description: is only valid for a non-Predecessor origin - use source: for a Predecessor's dataset.variable"
            )
        if self.type != "Predecessor" and self.source is not None:
            raise ValueError(
                "source: is only valid for a Predecessor origin - use description: for any other type"
            )
        return self


class SubClass(DefineBaseModel):
    # ItemGroupSubClass is a closed 2-value XSD enumeration (unlike AnalysisReason/
    # Purpose, which are extensible unions) - CDISC has defined only these two, so
    # Literal-enforcing it at the model layer matches the schema rather than
    # anticipating a CT list that doesn't exist.
    name: Literal["TIME-TO-EVENT", "ADVERSE EVENT"]
    # -> def:SubClass/@ParentClass; a union of ItemGroupClass and ItemGroupSubClass,
    # i.e. it may name either the enclosing top-level Class or another SubClass -
    # free text here rather than re-deriving that union.
    parent_class: str | None = None


class Leaf(DefineBaseModel):
    href: str
    title: str | None = None  # defaults to basename(href) if omitted


class Variable(DefineBaseModel):
    name: str
    label: str
    type: VariableType
    length: int | None = None
    significant_digits: int | None = None
    display_format: str | None = None
    mandatory: bool = False
    codelist: Ref | None = None
    method: Ref | None = None
    comment: Ref | None = None
    valuelist: Ref | None = None
    same_as: Ref | None = None
    role: str | None = None
    # -> ItemRef/@def:IsNonStandard; a sponsor-defined variable not part of the standard domain.
    is_non_standard: bool = False
    # -> ItemRef/@def:HasNoData; the variable is legitimately submitted with zero records.
    has_no_data: bool = False
    origin: Origin | None = None
    # -> ItemDef/@SASFieldName; defaults to name: - real ≤8-char physical SAS column,
    # which a value-level ItemDef's longer, descriptive Name can differ from (e.g.
    # Name="VSORRESU1", SASFieldName="HEIGHTOM").
    sas_field_name: str | None = None
    oid: str | None = None


class Dataset(DefineBaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    name: str
    label: str
    cls: str = Field(alias="class")
    # -> def:Class/def:SubClass*; ADaM's two-level classification, e.g.
    # OCCURRENCE DATA STRUCTURE > ADVERSE EVENT. maxOccurs is unbounded in the
    # schema, though real submissions carry at most one.
    subclasses: list[SubClass] = Field(default_factory=list)
    structure: str
    purpose: Literal["Analysis", "Tabulation"] = "Analysis"
    repeating: bool = False
    is_reference_data: bool = False
    domain: str | None = (
        None  # -> ItemGroupDef/@Domain; the 2-char SDTM domain code (SDTM only)
    )
    # -> ItemGroupDef/@def:IsNonStandard; a sponsor-defined domain not part of the standard.
    is_non_standard: bool = False
    # -> ItemGroupDef/@def:HasNoData; the domain is legitimately submitted with zero records.
    has_no_data: bool = False
    standard: Ref | None = (
        None  # -> def:StandardOID; optional in the schema, e.g. a custom domain
    )
    comment: Ref | None = None  # -> ItemGroupDef/@def:CommentOID
    leaf: Leaf | None = (
        None  # -> def:leaf; optional in the schema (e.g. a documentation-only domain)
    )
    keys: list[str] = Field(default_factory=list)
    variables: list[Variable]
    # -> ItemGroupDef/Alias*; e.g. Context="DomainDescription" naming the parent domain on
    # a SUPPQUAL-shaped domain (confirmed real on the bundled SDTM SUPPDM/SUPPVS datasets).
    aliases: list[Alias] = Field(default_factory=list)
    oid: str | None = None
