from __future__ import annotations

from .common import DefineBaseModel, Ref
from .dataset import Variable
from .whereclause import RangeCheck


class ValueListEntry(DefineBaseModel):
    name: str
    where: Ref | list[RangeCheck]
    comment: Ref | None = None
    item: Variable


class ValueListDef(DefineBaseModel):
    dataset: str
    variable: str
    entries: list[ValueListEntry]
    oid: str | None = None
