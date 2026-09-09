"""define.html via XSLT (CLAUDE.md build order step 6).

The bundled stylesheet (`stylesheets/define2-1.xsl`) is vendored from
https://github.com/lexjansen/define-xml-2.1-stylesheets (the `cdisc-2019/stylesheets`
tree - `STYLESHEET_VERSION` inside the file itself is "2019-02-11"), MIT-licensed
(`stylesheets/define2-1.xsl.LICENSE.TXT`), and self-contained - no `xsl:import`/
`xsl:include` of anything else, so vendoring is one file. It's XSLT 1.0, which libxslt
(lxml's `etree.XSLT`) covers directly; no Saxon dependency needed.

Drop additional `*.xsl` files next to it (a restyled fork, a sponsor's house variant)
and they become selectable: `available_stylesheets()` lists every `*.xsl` in the
folder, and the webui's "View define.html" offers a picker when more than one is
present. Each must be XSLT 1.0 and self-contained, same as the bundled one.
"""

from __future__ import annotations

from pathlib import Path

from lxml import etree

from .xml_emit import build_document_tree

STYLESHEET_DIR = Path(__file__).parent / "stylesheets"
DEFAULT_STYLESHEET = "define2-1"
STYLESHEET_PATH = STYLESHEET_DIR / f"{DEFAULT_STYLESHEET}.xsl"

_LABELS = {DEFAULT_STYLESHEET: "Classic (CDISC 2019 stylesheet)"}

_transforms: dict[str, etree.XSLT] = {}


def available_stylesheets() -> list[str]:
    """Stems of every `*.xsl` in `stylesheets/`, the default first then alphabetical."""
    stems = {p.stem for p in STYLESHEET_DIR.glob("*.xsl")}
    return sorted(stems, key=lambda s: (s != DEFAULT_STYLESHEET, s))


def stylesheet_label(name: str) -> str:
    """A short human label for a stylesheet stem, for the webui picker."""
    if name in _LABELS:
        return _LABELS[name]
    suffix = name.removeprefix("define2-1").strip("-_.")
    return suffix.replace("-", " ").replace("_", " ").strip().title() or name


def _get_transform(name: str) -> etree.XSLT:
    # Parsing a ~185KB stylesheet on every request would be wasteful for a button a
    # user might click repeatedly while iterating on their metadata - parsed once per
    # (process, stylesheet) and reused, the same way a compiled regex would be.
    if name not in available_stylesheets():
        raise ValueError(f"unknown stylesheet: {name!r}")
    cached = _transforms.get(name)
    if cached is None:
        cached = etree.XSLT(etree.parse(str(STYLESHEET_DIR / f"{name}.xsl")))
        _transforms[name] = cached
    return cached


def render_html(source: Path, stylesheet: str = DEFAULT_STYLESHEET) -> bytes:
    """file tree -> define.html, in memory, through `stylesheet` (a stem from
    `available_stylesheets()`). Raises linker.LinkError on the same conditions
    write_define_xml does (build_document_tree runs the identical linker pass) -
    there is no separate, weaker validation path for HTML rendering. Raises
    ValueError for an unknown stylesheet name.
    """
    document_tree, _table = build_document_tree(source)
    result = _get_transform(stylesheet)(document_tree)
    return bytes(result)
