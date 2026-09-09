"""Per-machine editor config - the recently opened trees, most-recent first. Lives
next to editor-state.json in the user's config dir (IDE-window state, not submission
content), but as a single flat file: "which trees has this machine opened" is one
list for the machine, not something per tree.
"""

from __future__ import annotations

import json
from pathlib import Path

CONFIG_PATH = Path.home() / ".config" / "defineyaml" / "config.json"
MAX_RECENT = 10


def _load() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _save(data: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(data, indent=2))


def _stored_paths() -> list[str]:
    data = _load()
    raw = data.get("recent_trees")
    if isinstance(raw, list):
        return [p for p in raw if isinstance(p, str) and p]
    # Migrate the old single-value form.
    last = data.get("last_tree")
    return [last] if isinstance(last, str) and last else []


def get_recent_trees() -> list[Path]:
    """Recently opened trees, most-recent first, filtered to the ones that are still
    a directory (a moved/deleted tree just drops off the list) and de-duplicated.
    """
    seen: set[str] = set()
    out: list[Path] = []
    for raw in _stored_paths():
        if raw in seen:
            continue
        seen.add(raw)
        path = Path(raw)
        if path.is_dir():
            out.append(path)
    return out[:MAX_RECENT]


def get_last_tree() -> Path | None:
    """The single most recently opened tree that's still reachable, or None."""
    recent = get_recent_trees()
    return recent[0] if recent else None


def remember_tree(source: Path) -> None:
    """Move `source` to the front of the recent list, cap it, and persist."""
    resolved = str(Path(source).resolve())
    kept = [p for p in _stored_paths() if p != resolved]
    data = _load()
    data.pop("last_tree", None)
    data["recent_trees"] = [resolved, *kept][:MAX_RECENT]
    _save(data)
