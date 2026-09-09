"""Small per-machine, per-tree editor state - last-opened object, autosave
preference. Not part of the define/ file tree itself: this is IDE-window state,
not submission content, so it lives in the user's config directory rather than
inside (and potentially git-committed alongside) the tree it's remembering a view
of. Keyed by the tree's resolved absolute path, so editing several trees from the
same machine doesn't mix up their last-opened views.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

STATE_PATH = Path.home() / ".config" / "defineyaml" / "editor-state.json"


def _load_all() -> dict:
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _save_all(data: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(data, indent=2))


def get_state(source: Path) -> dict:
    return _load_all().get(str(source.resolve()), {})


def update_state(source: Path, updates: dict[str, Any]) -> dict:
    all_data = _load_all()
    key = str(source.resolve())
    entry = dict(all_data.get(key, {}))
    entry.update(updates)
    all_data[key] = entry
    _save_all(all_data)
    return entry
