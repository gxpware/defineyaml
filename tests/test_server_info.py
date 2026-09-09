"""/api/info: the frontend's only way to tell two `define edit` tabs on different
studies apart (webui/static/app.js's applyTreeIdentity(), which sets the browser tab
title and sidebar header from this plus study.yaml). Calls the route's endpoint
function directly rather than through an HTTP client - this repo doesn't otherwise
test server.py over real HTTP (httpx isn't a dependency), and the handler here takes
no request/path parameters, so there's nothing an ASGI round-trip would exercise that
a direct call doesn't.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from defineyaml.webui.server import create_app

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "define"


@pytest.fixture()
def scratch_tree(tmp_path: Path) -> Path:
    dest = tmp_path / "define"
    shutil.copytree(FIXTURE_ROOT, dest)
    return dest


def _call(app, path: str):
    route = next(r for r in app.routes if getattr(r, "path", None) == path)
    return route.endpoint()


def test_info_returns_absolute_resolved_source_path(scratch_tree: Path):
    app = create_app(scratch_tree)
    result = _call(app, "/api/info")
    assert result == {"source": str(scratch_tree.resolve())}


def test_info_resolves_a_relative_source_path(tmp_path, monkeypatch):
    dest = tmp_path / "define"
    shutil.copytree(FIXTURE_ROOT, dest)
    monkeypatch.chdir(tmp_path)
    app = create_app(Path("define"))
    result = _call(app, "/api/info")
    assert result["source"] == str(dest.resolve())
    assert Path(result["source"]).is_absolute()
