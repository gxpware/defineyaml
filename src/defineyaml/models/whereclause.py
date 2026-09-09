from __future__ import annotations

from typing import Literal

from pydantic import model_validator

from .common import DefineBaseModel, Ref

Comparator = Literal["EQ", "NE", "LT", "LE", "GT", "GE", "IN", "NOTIN"]


class RangeCheck(DefineBaseModel):
    variable: Ref
    comparator: Comparator
    values: list[str]

    @model_validator(mode="after")
    def _multi_value_requires_in(self) -> "RangeCheck":
        if len(self.values) > 1 and self.comparator not in ("IN", "NOTIN"):
            raise ValueError("multiple values: require an IN or NOTIN comparator")
        return self


class WhereClauseDef(DefineBaseModel):
    conditions: list[RangeCheck]
    comment: Ref | None = None  # required when conditions span more than one dataset
    oid: str | None = None
