from __future__ import annotations

from typing import Literal, Union

from pydantic import Field, model_validator

from .common import Alias, DefineBaseModel, Ref

CodeListDataType = Literal["text", "integer", "float"]


def _check_no_nci_alias(aliases: list[Alias], *, where: str) -> None:
    # nci_code: is the only Alias this tool gives special meaning to and is the sole
    # supported way to write Context="nci:ExtCodeID" - allowing it in aliases: too would
    # be a second, redundant spelling of the same thing, with no rule for which wins if
    # they ever disagreed.
    for a in aliases:
        if a.context == "nci:ExtCodeID":
            raise ValueError(
                f'{where}: use nci_code: for a Context="nci:ExtCodeID" Alias, not aliases:'
            )


class Term(DefineBaseModel):
    code: str
    decode: str | None = None
    # -> CodeListItem|EnumeratedItem/@Rank (xs:float in ODM; kept as int when the value is
    # integral, which every real CDISC rank is). "Numeric significance of the item relative
    # to the others" - it does NOT imply display order (that's OrderNumber, derived from
    # terms: position). Optional, but all-or-none across a codelist and, when present,
    # distinct - enforced by EnumeratedCodeList._check_ranks.
    rank: int | float | None = None
    nci_code: str | None = None
    # -> CodeListItem|EnumeratedItem/@def:ExtendedValue; this specific term was added by the
    # sponsor to an otherwise-standard, extensible codelist - distinct from the codelist-wide
    # extended: below, which flags the whole codelist as non-standard. A codelist can carry
    # this on individual terms while itself staying unflagged (confirmed real: the bundled
    # SDTM LBRESU unit codelist has two sponsor-added units, each ExtendedValue="Yes", while
    # the codelist itself has no def:IsNonStandard).
    extended: bool = False
    # -> CodeListItem|EnumeratedItem/Alias*, any Context other than "nci:ExtCodeID" (that one
    # is nci_code: above). Confirmed real on the bundled SDTM submission: e.g. CL.XSTEST's
    # EnumeratedItems each carry a single Context="Sponsor" alias (an internal test-code
    # cross-reference).
    aliases: list[Alias] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_aliases(self) -> "Term":
        _check_no_nci_alias(self.aliases, where="terms[].aliases")
        return self


class ExternalCodeList(DefineBaseModel):
    dictionary: str
    version: str


class EnumeratedCodeList(DefineBaseModel):
    name: str
    label: str
    type: CodeListDataType = "text"
    nci_code: str | None = None
    extended: bool = False
    terms: list[Term]
    standard: Ref | None = (
        None  # -> def:StandardOID; which CT version the terms are drawn from
    )
    sas_format_name: str | None = None  # -> CodeList/@SASFormatName, e.g. "$AGEGR1."
    comment: Ref | None = None  # -> def:CommentOID
    # -> CodeList/Alias*, any Context other than "nci:ExtCodeID" (that one is nci_code:
    # above). Confirmed real on the bundled SDTM submission, e.g. CL.XSRESU carries a
    # codelist-level Context="Sponsor" alias alongside its per-term NCI aliases.
    aliases: list[Alias] = Field(default_factory=list)
    oid: str | None = None

    @model_validator(mode="after")
    def _check_decode_uniform(self) -> "EnumeratedCodeList":
        # ODM's CodeList content model is a choice: CodeListItem* (has Decode) XOR
        # EnumeratedItem* (no Decode) XOR ExternalCodeList - never a mix of the first two
        # within one CodeList. A term with no decode: emits as EnumeratedItem (a coded value
        # with no human-readable label - CDISC uses this for lists like age groups or arm
        # names where the code is already self-explanatory); every term must agree.
        has_decode = [t.decode is not None for t in self.terms]
        if len(set(has_decode)) > 1:
            raise ValueError(
                "terms: cannot mix entries with decode: and without it - a CodeList emits "
                "as either CodeListItem (Decode required) or EnumeratedItem (no Decode), "
                "never both"
            )
        # @Rank - Define-XML business rule: "if provided for any CodeListItem it must be
        # present for all". This tool adds that it must also be distinct (a rank is a
        # relative ordering key; two terms sharing one is almost always a mistake).
        ranks = [t.rank for t in self.terms]
        set_ranks = [r for r in ranks if r is not None]
        if set_ranks and len(set_ranks) != len(ranks):
            raise ValueError(
                "terms: rank: must be set on every term or none - Define-XML requires "
                "@Rank on all CodeListItems of a codelist once it's on any"
            )
        if len(set(set_ranks)) != len(set_ranks):
            raise ValueError("terms: rank: values must be distinct across the codelist")
        # CodedValue is case-sensitive per ODM - "PA" and "Pa" are distinct terms - so
        # compare exactly (whitespace-trimmed only).
        seen: set[str] = set()
        for term in self.terms:
            key = (term.code or "").strip()
            if key and key in seen:
                raise ValueError(
                    f"terms: duplicate code {term.code!r} - two CodeListItems with the "
                    "same CodedValue is invalid Define-XML"
                )
            seen.add(key)
        _check_no_nci_alias(self.aliases, where="aliases")
        return self


class ExternalCodeListDef(DefineBaseModel):
    name: str
    label: str
    type: CodeListDataType = "text"
    external: ExternalCodeList
    oid: str | None = None


CodeList = Union[EnumeratedCodeList, ExternalCodeListDef]


def parse_codelist(data: dict) -> CodeList:
    """Discriminated on the presence of `external:` - the two shapes can't mix (§7.2)."""
    if "external" in data:
        return ExternalCodeListDef.model_validate(data)
    return EnumeratedCodeList.model_validate(data)
