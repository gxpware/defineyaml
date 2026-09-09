"""File-based response cache, keyed by request URL, with a TTL - "downloaded to local
cache and kept for a limited time" per the feature request (default 12h). Deliberately
does not cache the online/offline status check itself: that has to reflect right-now
reachability, not what it was up to 12 hours ago. Only actual query results (product
lists, codelist content, ...) go through this.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

CACHE_DIR = Path.home() / ".cache" / "defineyaml" / "cdisc"
DEFAULT_TTL_SECONDS = 12 * 60 * 60


def _cache_path(key: str) -> Path:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return CACHE_DIR / f"{digest}.json"


def get(key: str, *, ttl_seconds: float = DEFAULT_TTL_SECONDS) -> Any | None:
    """The cached payload for `key` if it exists and is younger than `ttl_seconds`,
    else None. A corrupt or unreadable cache entry is treated as a miss, not an error -
    caching is an optimisation, never something a query should fail over.
    """
    path = _cache_path(key)
    if not path.is_file():
        return None
    try:
        entry = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(entry, dict) or "cached_at" not in entry:
        return None
    age = time.time() - entry["cached_at"]
    # >= so an entry is "younger than ttl_seconds" strictly: with ttl_seconds=0 (or a
    # coarse clock where set and get land in the same tick, age == 0.0) it's a miss.
    if age >= ttl_seconds:
        return None
    return entry.get("payload")


def set(key: str, payload: Any) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _cache_path(key)
    path.write_text(
        json.dumps({"cached_at": time.time(), "key": key, "payload": payload})
    )


def entry_age_seconds(key: str) -> float | None:
    """How old the cached entry for `key` is, regardless of TTL - for surfacing
    "cached N minutes ago" in the viewer. None if there's no entry at all.
    """
    path = _cache_path(key)
    if not path.is_file():
        return None
    try:
        entry = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(entry, dict) or "cached_at" not in entry:
        return None
    return time.time() - entry["cached_at"]


def clear() -> int:
    """Removes every cached entry. Returns how many files were removed."""
    if not CACHE_DIR.is_dir():
        return 0
    removed = 0
    for path in CACHE_DIR.glob("*.json"):
        try:
            path.unlink()
            removed += 1
        except OSError:
            pass
    return removed
