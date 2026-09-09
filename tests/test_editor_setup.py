"""`define` with no arguments: open the web editor to a launcher screen - reopen a
recently used tree, browse to one, or create a new one (webui/config.py + server.py's
/api/setup/* routes).
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from ruamel.yaml import YAML

from defineyaml import cli
from defineyaml.webui import config as editor_config
from defineyaml.webui.server import create_app

_yaml = YAML(typ="safe")


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(editor_config, "CONFIG_PATH", tmp_path / "cfg" / "config.json")


def _route(app, path, method="GET"):
    return next(
        r
        for r in app.routes
        if getattr(r, "path", None) == path and method in getattr(r, "methods", set())
    )


# --- config -----------------------------------------------------------------


def test_recent_trees_are_mru_deduped_and_capped(tmp_path):
    assert editor_config.get_recent_trees() == []
    dirs = []
    for i in range(12):
        d = tmp_path / f"t{i}"
        d.mkdir()
        dirs.append(d.resolve())
        editor_config.remember_tree(d)
    recent = editor_config.get_recent_trees()
    assert recent == list(reversed(dirs))[: editor_config.MAX_RECENT]
    assert editor_config.get_last_tree() == dirs[-1]

    # Re-opening an older one moves it to the front, no duplicate.
    editor_config.remember_tree(dirs[2])
    assert editor_config.get_recent_trees()[0] == dirs[2]
    assert editor_config.get_recent_trees().count(dirs[2]) == 1


def test_recent_trees_drop_paths_that_are_gone(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    editor_config.remember_tree(a)
    editor_config.remember_tree(b)
    b.rmdir()
    assert editor_config.get_recent_trees() == [a.resolve()]
    assert editor_config.get_last_tree() == a.resolve()


def test_config_migrates_the_old_last_tree_key(tmp_path):
    d = tmp_path / "old"
    d.mkdir()
    import json

    editor_config.CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    editor_config.CONFIG_PATH.write_text(json.dumps({"last_tree": str(d.resolve())}))
    assert editor_config.get_recent_trees() == [d.resolve()]
    # Writing again upgrades the file to the list form and drops last_tree.
    editor_config.remember_tree(d)

    stored = json.loads(editor_config.CONFIG_PATH.read_text())
    assert "last_tree" not in stored and stored["recent_trees"] == [str(d.resolve())]


def test_bare_define_opens_the_launcher_regardless_of_history(tmp_path, monkeypatch):
    d = tmp_path / "tree"
    d.mkdir()
    editor_config.remember_tree(d)
    seen = {}
    monkeypatch.setattr(
        cli, "_serve_editor", lambda src, *a, **k: seen.setdefault("src", src)
    )
    from typer.testing import CliRunner

    result = CliRunner().invoke(cli.app, [])
    assert result.exit_code == 0
    assert seen["src"] is None  # always the launcher - the frontend offers the recents


def test_define_edit_falls_back_to_the_launcher_when_source_is_missing(
    tmp_path, monkeypatch
):
    seen = {}
    monkeypatch.setattr(
        cli, "_serve_editor", lambda src, *a, **k: seen.setdefault("src", src)
    )
    from typer.testing import CliRunner

    monkeypatch.chdir(tmp_path)  # no ./define here
    result = CliRunner().invoke(cli.app, ["edit", "--no-open"])
    assert result.exit_code == 0
    assert seen["src"] is None
    assert "not a directory" in result.output


def test_define_edit_serves_an_explicit_existing_source(tmp_path, monkeypatch):
    d = tmp_path / "mytree"
    d.mkdir()
    seen = {}
    monkeypatch.setattr(
        cli, "_serve_editor", lambda src, *a, **k: seen.setdefault("src", src)
    )
    from typer.testing import CliRunner

    result = CliRunner().invoke(cli.app, ["edit", "--source", str(d), "--no-open"])
    assert result.exit_code == 0
    assert seen["src"] == d


# --- setup status / info ----------------------------------------------------


def test_setup_status_needs_setup_when_root_is_none():
    app = create_app(None)
    assert _route(app, "/api/setup/status").endpoint() == {
        "needs_setup": True,
        "source": None,
    }
    assert _route(app, "/api/info").endpoint() == {"source": None}


def test_setup_status_satisfied_when_root_is_a_directory(tmp_path):
    app = create_app(tmp_path)
    assert _route(app, "/api/setup/status").endpoint() == {
        "needs_setup": False,
        "source": str(tmp_path.resolve()),
    }


def test_tree_last_modified_route(tmp_path):
    (tmp_path / "study.yaml").write_text("study: {}\n")
    app = create_app(tmp_path)
    out = _route(app, "/api/tree/last-modified").endpoint()
    assert out["source"] == "mtime" and out["datetime"]

    # No tree open (launcher mode) -> nothing to report, no crash.
    assert _route(create_app(None), "/api/tree/last-modified").endpoint() == {
        "datetime": None,
        "source": "none",
    }


# --- browse ---------------------------------------------------------------


def test_browse_lists_subdirs_and_flags_define_trees(tmp_path):
    (tmp_path / "plain").mkdir()
    (tmp_path / "atree").mkdir()
    (tmp_path / "atree" / "study.yaml").write_text("x\n")
    (tmp_path / ".hidden").mkdir()
    app = create_app(None)

    data = _route(app, "/api/setup/browse").endpoint(path=str(tmp_path))
    assert data["path"] == str(tmp_path)
    assert data["parent"] == str(tmp_path.parent)
    assert {e["name"]: e["is_tree"] for e in data["entries"]} == {
        "atree": True,
        "plain": False,  # ".hidden" is filtered out
    }


def test_browse_defaults_to_last_tree_parent(tmp_path):
    d = tmp_path / "somewhere" / "mystudy"
    d.mkdir(parents=True)
    editor_config.remember_tree(d)
    app = create_app(None)
    assert _route(app, "/api/setup/browse").endpoint(path=None)["path"] == str(
        d.parent.resolve()
    )


# --- recent -----------------------------------------------------------------


def test_recent_route_labels_trees_from_their_study_yaml(tmp_path):
    a = tmp_path / "a"
    a.mkdir()
    (a / "study.yaml").write_text("study:\n  name: ABC-9\n  protocol_name: PROTO-9\n")
    b = tmp_path / "b"  # no study.yaml -> folder name
    b.mkdir()
    editor_config.remember_tree(a)
    editor_config.remember_tree(b)

    app = create_app(None)
    rows = _route(app, "/api/setup/recent").endpoint()["recent"]
    assert [r["path"] for r in rows] == [str(b.resolve()), str(a.resolve())]
    assert rows[0] == {"path": str(b.resolve()), "name": "b", "protocol": None}
    assert rows[1] == {
        "path": str(a.resolve()),
        "name": "ABC-9",
        "protocol": "PROTO-9",
    }


def test_recent_route_is_empty_with_no_history():
    assert _route(create_app(None), "/api/setup/recent").endpoint() == {"recent": []}


# --- open ---------------------------------------------------------------------


def test_open_adopts_an_existing_directory_and_remembers_it(tmp_path):
    d = tmp_path / "mytree"
    d.mkdir()
    app = create_app(None)

    res = _route(app, "/api/setup/open", "POST").endpoint({"path": str(d)})
    assert res == {"source": str(d.resolve())}
    assert app.state.root == d.resolve()
    assert editor_config.get_last_tree() == d.resolve()
    assert _route(app, "/api/setup/status").endpoint()["needs_setup"] is False


def test_open_rejects_a_path_that_is_not_a_directory(tmp_path):
    app = create_app(None)
    with pytest.raises(HTTPException) as exc:
        _route(app, "/api/setup/open", "POST").endpoint(
            {"path": str(tmp_path / "nope")}
        )
    assert exc.value.status_code == 400


# --- init -------------------------------------------------------------------


def test_init_scaffolds_a_tree_derives_oids_and_adopts_it(tmp_path):
    app = create_app(None)
    res = _route(app, "/api/setup/init", "POST").endpoint(
        {
            "parent": str(tmp_path),
            "name": "define",
            "study_name": "ABC-101",
            "protocol_name": "PROTO-1",
        }
    )
    root = tmp_path / "define"
    assert res == {"source": str(root.resolve())}
    assert (root / "study.yaml").is_file() and (root / "datasets").is_dir()
    assert app.state.root == root.resolve()
    assert editor_config.get_last_tree() == root.resolve()

    study = _yaml.load((root / "study.yaml").read_text())
    assert study["study"]["name"] == "ABC-101"
    assert study["study"]["protocol_name"] == "PROTO-1"
    assert study["study"]["oid"].startswith("SDY.")
    assert study["odm"]["file_oid"].startswith("ODM.")


def test_init_requires_a_study_name(tmp_path):
    app = create_app(None)
    with pytest.raises(HTTPException) as exc:
        _route(app, "/api/setup/init", "POST").endpoint(
            {"parent": str(tmp_path), "name": "define"}
        )
    assert exc.value.status_code == 400


def test_init_refuses_to_overwrite_an_existing_folder(tmp_path):
    (tmp_path / "define").mkdir()
    app = create_app(None)
    with pytest.raises(HTTPException) as exc:
        _route(app, "/api/setup/init", "POST").endpoint(
            {"parent": str(tmp_path), "name": "define", "study_name": "X"}
        )
    assert exc.value.status_code == 400


def test_init_rejects_a_slash_in_the_folder_name(tmp_path):
    app = create_app(None)
    with pytest.raises(HTTPException) as exc:
        _route(app, "/api/setup/init", "POST").endpoint(
            {"parent": str(tmp_path), "name": "a/b", "study_name": "X"}
        )
    assert exc.value.status_code == 400
