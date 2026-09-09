"""define.html via XSLT (CLAUDE.md build order step 6) - html_render.render_html() and
xml_emit.render_xml_bytes(), the two functions the webui's "View define.xml"/"View
define.html" buttons call. Both share xml_emit.build_document_tree() with
write_define_xml(), so a tree that fails to build fails identically here.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from lxml import etree

from defineyaml.html_render import (
    DEFAULT_STYLESHEET,
    STYLESHEET_PATH,
    available_stylesheets,
    render_html,
    stylesheet_label,
)
from defineyaml.linker import LinkError
from defineyaml.webui.server import create_app
from defineyaml.xml_emit import render_xml_bytes, write_define_xml
from defineyaml.xml_import import import_define_xml

FIXTURES = Path(__file__).parent / "fixtures" / "definexml"
EXAMPLES = {
    "adam": FIXTURES / "examples" / "adam.xml",
    "sdtm": FIXTURES / "examples" / "sdtm.xml",
}


def test_stylesheet_is_vendored_and_parses_as_xslt():
    assert STYLESHEET_PATH.exists()
    xslt_doc = etree.parse(str(STYLESHEET_PATH))
    etree.XSLT(xslt_doc)  # raises XSLTParseError if the file isn't valid XSLT


def test_render_xml_bytes_matches_write_define_xml(tmp_path):
    dest_tree = tmp_path / "tree"
    import_define_xml(EXAMPLES["adam"], dest_tree)
    output = tmp_path / "define.xml"
    write_define_xml(dest_tree, output)
    assert render_xml_bytes(dest_tree) == output.read_bytes()


def test_render_xml_bytes_is_well_formed(tmp_path):
    import re

    dest_tree = tmp_path / "tree"
    import_define_xml(EXAMPLES["sdtm"], dest_tree)
    # methods/bmisn.yaml: a source data-quality issue in the CDISC fixture itself, not a
    # bug here - see test_roundtrip.py's _patch_known_source_data_issues for the full story.
    bmisn = dest_tree / "methods" / "bmisn.yaml"
    patched, count = re.subn(
        r"(- context: ')", r"\1(variant 2) ", bmisn.read_text(), count=1
    )
    assert count == 1
    bmisn.write_text(patched)
    data = render_xml_bytes(dest_tree)
    root = etree.fromstring(data)
    assert etree.QName(root).localname == "ODM"


def test_render_xml_bytes_raises_link_error_on_unresolved_reference(tmp_path):
    dest_tree = tmp_path / "tree"
    import_define_xml(EXAMPLES["adam"], dest_tree)
    adsl = dest_tree / "datasets" / "adsl.yaml"
    adsl.write_text(
        adsl.read_text().replace("method: adsl-trtsdt", "method: does-not-exist")
    )
    with pytest.raises(LinkError):
        render_xml_bytes(dest_tree)


def test_render_html_produces_real_html_with_dataset_content(tmp_path):
    dest_tree = tmp_path / "tree"
    import_define_xml(EXAMPLES["adam"], dest_tree)
    html = render_html(dest_tree)
    assert html.startswith(b"<!DOCTYPE html")
    parsed = etree.fromstring(html, etree.HTMLParser())
    assert parsed.tag == "html"
    text = html.decode("utf-8", errors="replace")
    assert "ADSL" in text


def test_render_html_raises_link_error_on_unresolved_reference(tmp_path):
    dest_tree = tmp_path / "tree"
    import_define_xml(EXAMPLES["adam"], dest_tree)
    adsl = dest_tree / "datasets" / "adsl.yaml"
    adsl.write_text(
        adsl.read_text().replace("method: adsl-trtsdt", "method: does-not-exist")
    )
    with pytest.raises(LinkError):
        render_html(dest_tree)


# --- stylesheet selection -------------------------------------------------------


def test_available_stylesheets_lists_every_xsl_default_first():
    sheets = available_stylesheets()
    assert DEFAULT_STYLESHEET in sheets
    assert sheets[0] == DEFAULT_STYLESHEET  # default sorts first
    # every entry is a real file (glob stems), .LICENSE.TXT is not one
    for name in sheets:
        assert (STYLESHEET_PATH.parent / f"{name}.xsl").is_file()
    assert "define2-1.xsl" not in sheets


def test_stylesheet_label_is_human_readable():
    assert stylesheet_label(DEFAULT_STYLESHEET) == "Classic (CDISC 2019 stylesheet)"
    assert stylesheet_label("define2-1-modern") == "Modern"
    assert stylesheet_label("house-style") == "House Style"


def test_render_html_accepts_a_named_stylesheet(tmp_path):
    dest_tree = tmp_path / "tree"
    import_define_xml(EXAMPLES["adam"], dest_tree)
    for name in available_stylesheets():
        html = render_html(dest_tree, name)
        assert html[:20].lower().startswith(b"<!doctype html") or html.startswith(
            b"<html"
        )
        assert b"ADSL" in html


def test_render_html_rejects_an_unknown_stylesheet(tmp_path):
    dest_tree = tmp_path / "tree"
    import_define_xml(EXAMPLES["adam"], dest_tree)
    with pytest.raises(ValueError):
        render_html(dest_tree, "../../../etc/passwd")
    with pytest.raises(ValueError):
        render_html(dest_tree, "no-such-stylesheet")


def test_render_stylesheets_route_reports_names_and_default(tmp_path):
    import_define_xml(EXAMPLES["adam"], tmp_path / "tree")
    app = create_app(tmp_path / "tree")
    route = next(
        r for r in app.routes if getattr(r, "path", None) == "/api/render/stylesheets"
    )
    result = route.endpoint()
    names = [r["name"] for r in result]
    assert names == available_stylesheets()
    assert [r for r in result if r["default"]] == [
        {
            "name": DEFAULT_STYLESHEET,
            "label": stylesheet_label(DEFAULT_STYLESHEET),
            "default": True,
        }
    ]


def test_render_html_route_passes_the_stylesheet_through(tmp_path):
    import_define_xml(EXAMPLES["adam"], tmp_path / "tree")
    app = create_app(tmp_path / "tree")
    route = next(
        r
        for r in app.routes
        if getattr(r, "path", None) == "/api/render/html"
        and "GET" in getattr(r, "methods", set())
    )
    ok = route.endpoint(stylesheet=DEFAULT_STYLESHEET)
    assert b"ADSL" in ok.body
    with pytest.raises(Exception) as exc:  # HTTPException(400) for an unknown name
        route.endpoint(stylesheet="nope")
    assert getattr(exc.value, "status_code", None) == 400


def test_bundled_html_render_still_defaults_without_a_name(tmp_path):
    dest_tree = tmp_path / "tree"
    import_define_xml(EXAMPLES["adam"], dest_tree)
    assert render_html(dest_tree) == render_html(dest_tree, DEFAULT_STYLESHEET)
