"""'When was this define tree last modified' - the value the ODM header's
`CreationDateTime` falls back to when `study.yaml` leaves `odm.creation_datetime`
blank (which a freshly scaffolded tree does).

Git-aware, because a `git clone` / `git checkout` rewrites every file's mtime to the
checkout time - useless as a "last modified" signal. So:

- **tree under version control** (in a git repo, with at least one tracked file under
  it): the committer date of the most recent commit that touched the tree path.
  `git log` on a directory pathspec already counts adds, edits, deletes and renames,
  so nothing extra is needed for those.
- **otherwise**: the newest mtime among the tree's `*.yaml` / `*.yml` files (dot-dirs
  like `.git` / `.cache` skipped).

`git` not being installed, or the tree being untracked / fully git-ignored inside a
repo, both fall through to the mtime scan.
"""

from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path


def now_iso() -> str:
    """Local time, ISO 8601, whole seconds - the shape every timestamp this tool
    writes uses (e.g. 2026-09-08T15:58:51+01:00)."""
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def latest_modification(tree_root: Path) -> tuple[str | None, str]:
    """`(iso_datetime, source)` for the tree's last change. `source` is `"git"`,
    `"mtime"`, or `"none"` (with `iso_datetime` None) when it can't be determined.
    """
    root = Path(tree_root).resolve()
    git = _git_last_commit_iso(root)
    if git is not None:
        return git, "git"
    mtime = _newest_yaml_mtime(root)
    if mtime is not None:
        return mtime, "mtime"
    return None, "none"


def _git_last_commit_iso(root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "log", "-1", "--format=%cI", "--", "."],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (FileNotFoundError, OSError):
        return None  # git not installed / not runnable
    if result.returncode != 0:
        return None  # not a git repo
    line = result.stdout.strip()
    if not line:
        return None  # in a repo, but nothing under the tree is tracked
    return _to_iso_seconds(line)


def _newest_yaml_mtime(root: Path) -> str | None:
    newest = 0.0
    for pattern in ("*.yaml", "*.yml"):
        for path in root.rglob(pattern):
            parents = path.relative_to(root).parts[:-1]
            if any(part.startswith(".") for part in parents):
                continue  # .git / .cache / other dot-dirs aren't tree content
            try:
                newest = max(newest, path.stat().st_mtime)
            except OSError:
                continue
    if newest == 0.0:
        return None
    return _to_iso_seconds(
        datetime.fromtimestamp(newest).astimezone().replace(microsecond=0).isoformat()
    )


def _to_iso_seconds(value: str) -> str:
    try:
        return datetime.fromisoformat(value).replace(microsecond=0).isoformat()
    except ValueError:
        return value
