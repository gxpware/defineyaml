"""Round-trip YAML I/O via ruamel.yaml, per CLAUDE.md §1.

Comments, key order and block style survive a load-modify-dump cycle, and
code-position scalars are always re-emitted in the style §1/§7.5 mandate -
quoted for short identifiers (`code:`, `name:`, `nci_code:`, `oid:`), block
literal (`|`) for anything multi-line (derivation/programming code) -
regardless of how the source file happened to write them.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import DoubleQuotedScalarString, LiteralScalarString

_QUOTED_KEYS = {"code", "name", "nci_code", "oid"}


def _make_yaml() -> YAML:
    yaml = YAML(typ="rt")
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=2, offset=0)
    yaml.width = 100
    return yaml


def load(path: Path) -> Any:
    yaml = _make_yaml()
    with path.open("r", encoding="utf-8") as f:
        return yaml.load(f)


def _enforce_style(node: Any) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(value, str):
                if "\n" in value:
                    node[key] = LiteralScalarString(value)
                elif key in _QUOTED_KEYS:
                    node[key] = DoubleQuotedScalarString(value)
            else:
                _enforce_style(value)
    elif isinstance(node, list):
        for item in node:
            _enforce_style(item)


def dump(data: Any, path: Path) -> None:
    _enforce_style(data)
    yaml = _make_yaml()
    with path.open("w", encoding="utf-8") as f:
        yaml.dump(data, f)
