from __future__ import annotations

from typing import Union

from pydantic import BaseModel, ConfigDict


class DefineBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Alias(DefineBaseModel):
    """The generic ODM Alias element (Context/Name, both required free text). CodeList and
    Term give one specific Context ("nci:ExtCodeID") special meaning via their own
    nci_code: field rather than this model, since that's the only context this tool
    currently assigns semantics to. This model is for everything else - an arbitrary
    sponsor- or CDISC-defined (context, name) pair with no assumed meaning, e.g.
    ItemGroupDef's Context="DomainDescription" on a SUPPQUAL-shaped domain, naming the
    parent domain it supplements.
    """

    context: str
    name: str


class RefByOid(DefineBaseModel):
    """A cross-reference given as a literal OID instead of a symbolic name.

    Every reference field that the linker (CLAUDE.md §3, "the linker pass")
    would otherwise resolve by name through the symbol table accepts this as
    an alternative: `field: race` resolves as normal, `field: {oid: CL.RACE}`
    is emitted as-is with no symbol table lookup. This is the reference-side
    counterpart to the `oid:` override already available on every definition
    - both exist for the same reason, round-tripping a define.xml whose OIDs
    don't follow this tool's derivation scheme, and together they make OID
    definition and reference resolution fully optional rather than mandatory.
    """

    oid: str


Ref = Union[str, RefByOid]


def ref_oid(ref: Ref) -> str | None:
    """The literal OID of a reference, if it was given as one, else None."""
    return ref.oid if isinstance(ref, RefByOid) else None


def ref_name(ref: Ref) -> str | None:
    """The symbolic name of a reference, if it was given as one, else None."""
    return ref if isinstance(ref, str) else None
