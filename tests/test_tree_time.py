"""tree_time.latest_modification - the value an empty odm.creation_datetime builds
with: the git-history date when the tree is version-controlled, otherwise the newest
YAML file's mtime.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from datetime import datetime

import pytest

from defineyaml.tree_time import latest_modification, now_iso

_HAS_GIT = shutil.which("git") is not None
requires_git = pytest.mark.skipif(not _HAS_GIT, reason="git not installed")


def _git(cwd, *args, date=None):
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "T",
        "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "T",
        "GIT_COMMITTER_EMAIL": "t@example.com",
    }
    if date:
        env["GIT_AUTHOR_DATE"] = date
        env["GIT_COMMITTER_DATE"] = date
    subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True, env=env
    )


def _set_mtime(path, epoch):
    os.utime(path, (epoch, epoch))


def test_now_iso_is_whole_seconds_iso8601():
    v = now_iso()
    assert datetime.fromisoformat(v).microsecond == 0 and "T" in v


def test_falls_back_to_newest_yaml_mtime_without_git(tmp_path):
    (tmp_path / "study.yaml").write_text("study: {}\n")
    older = tmp_path / "codelists" / "a.yaml"
    older.parent.mkdir()
    older.write_text("x\n")
    newer = tmp_path / "datasets" / "b.yaml"
    newer.parent.mkdir()
    newer.write_text("y\n")
    _set_mtime(tmp_path / "study.yaml", 1_500_000_000)
    _set_mtime(older, 1_500_000_000)
    _set_mtime(newer, 1_700_000_000)

    stamp, source = latest_modification(tmp_path)
    assert source == "mtime"
    assert datetime.fromisoformat(stamp) == datetime.fromtimestamp(
        1_700_000_000
    ).astimezone().replace(microsecond=0)


def test_mtime_scan_ignores_non_yaml_and_dot_dirs(tmp_path):
    (tmp_path / "study.yaml").write_text("a\n")
    _set_mtime(tmp_path / "study.yaml", 1_600_000_000)
    (tmp_path / ".cache").mkdir()
    (tmp_path / ".cache" / "huge.yaml").write_text("z\n")  # newer, but in a dot-dir
    (tmp_path / "notes.txt").write_text("z\n")  # newer, but not YAML
    stamp, source = latest_modification(tmp_path)
    assert source == "mtime"
    assert (
        datetime.fromisoformat(stamp).year == datetime.fromtimestamp(1_600_000_000).year
    )


def test_returns_none_when_no_yaml_and_no_git(tmp_path):
    (tmp_path / "readme.txt").write_text("x\n")
    assert latest_modification(tmp_path) == (None, "none")


@requires_git
def test_uses_the_last_commit_date_including_a_later_delete(tmp_path):
    _git(tmp_path, "init", "-q")
    (tmp_path / "study.yaml").write_text("v1\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "one", date="2022-06-15T12:00:00+00:00")

    (tmp_path / "extra.yaml").write_text("x\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "add extra", date="2023-03-20T09:30:00+00:00")

    (tmp_path / "extra.yaml").unlink()
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "delete extra", date="2024-11-01T18:00:00+00:00")

    # mtime of study.yaml is "now" (much newer) - the git date must still win.
    stamp, source = latest_modification(tmp_path)
    assert source == "git"
    assert stamp == "2024-11-01T18:00:00+00:00"


@requires_git
def test_untracked_subtree_inside_a_repo_falls_back_to_mtime(tmp_path):
    _git(tmp_path, "init", "-q")
    (tmp_path / "other.txt").write_text("x\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "unrelated", date="2020-01-01T00:00:00+00:00")

    sub = tmp_path / "define"
    sub.mkdir()
    (sub / "study.yaml").write_text("x\n")
    _set_mtime(sub / "study.yaml", 1_650_000_000)

    stamp, source = latest_modification(sub)
    assert source == "mtime"
    assert (
        datetime.fromisoformat(stamp).year == datetime.fromtimestamp(1_650_000_000).year
    )


@requires_git
def test_build_fills_creation_datetime_from_git(tmp_path):
    from defineyaml.scaffold import scaffold_tree
    from defineyaml.xml_emit import render_xml_bytes

    dest = tmp_path / "define"
    scaffold_tree(
        dest,
        file_oid="F",
        study_oid="S",
        study_name="S",
        protocol_name="P",
        metadata_version_oid="M",
        metadata_version_name="M",
    )
    _git(dest, "init", "-q")
    _git(dest, "add", "-A")
    _git(dest, "commit", "-qm", "init", date="2021-07-01T08:00:00+00:00")

    xml = render_xml_bytes(dest).decode()
    assert 'CreationDateTime="2021-07-01T08:00:00+00:00"' in xml
