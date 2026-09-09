"""Which CDISC Library server to query, and with what credential - per-machine
configuration, not per-tree and never part of the define/ file tree itself: an API key
must never land in a file that could plausibly get git-committed alongside submission
content. Lives in its own file, separate from webui/state.py's editor-state.json (last-
opened object, autosave preference) - that file has no reason to ever hold a credential,
and keeping this one physically separate means a "here, look at my editor state" request
can't accidentally hand over an API key too.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Literal

OFFICIAL_BASE_URL = "https://library.cdisc.org/api"

CONFIG_PATH = Path.home() / ".config" / "defineyaml" / "cdisc.json"

Provider = Literal["official", "proxy"]

_DEFAULT: dict = {
    "provider": "official",
    "official": {"api_key": None},
    "proxy": {"base_url": None, "api_key": None},
}


def _load() -> dict:
    if not CONFIG_PATH.exists():
        return json.loads(json.dumps(_DEFAULT))  # deep copy
    try:
        data = json.loads(CONFIG_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return json.loads(json.dumps(_DEFAULT))
    if not isinstance(data, dict):
        return json.loads(json.dumps(_DEFAULT))
    merged = json.loads(json.dumps(_DEFAULT))
    merged.update({k: v for k, v in data.items() if k in _DEFAULT})
    merged["official"] = {**_DEFAULT["official"], **(data.get("official") or {})}
    merged["proxy"] = {**_DEFAULT["proxy"], **(data.get("proxy") or {})}
    return merged


def _save(data: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(data, indent=2))
    # Best-effort - an API key lives in this file. Not fully meaningful on every
    # platform (Windows ACLs, some network filesystems), but on a normal POSIX home
    # directory this keeps it from being group/world-readable by default.
    try:
        os.chmod(CONFIG_PATH, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


def get_config() -> dict:
    """The full stored config, real API keys included - for server-side use
    (resolve_active) only. Never return this directly from an HTTP endpoint; see
    get_config_masked below for what the frontend actually gets.
    """
    return _load()


def mask_key(key: str | None) -> str | None:
    if not key:
        return None
    tail = key[-4:] if len(key) > 4 else key
    return "•" * max(0, len(key) - len(tail)) + tail


def get_config_masked() -> dict:
    """Same shape, api_key replaced by a masked tail (or null if unset) plus a plain
    has_api_key flag - what /api/cdisc/config actually returns. The real key never
    round-trips back out to the browser once saved.
    """
    data = _load()
    return {
        "provider": data["provider"],
        "official": {
            "has_api_key": bool(data["official"].get("api_key")),
            "api_key_masked": mask_key(data["official"].get("api_key")),
        },
        "proxy": {
            "base_url": data["proxy"].get("base_url"),
            "has_api_key": bool(data["proxy"].get("api_key")),
            "api_key_masked": mask_key(data["proxy"].get("api_key")),
        },
    }


def update_config(updates: dict) -> dict:
    """Merges `updates` into the stored config. An omitted or blank api_key leaves the
    existing one untouched (so saving the base_url doesn't force re-entering the key);
    an explicit empty-string api_key clears it. `provider`, if given, must be "official"
    or "proxy".
    """
    data = _load()
    if "provider" in updates:
        provider = updates["provider"]
        if provider not in ("official", "proxy"):
            raise ValueError(
                f"provider must be 'official' or 'proxy', got {provider!r}"
            )
        data["provider"] = provider
    for section in ("official", "proxy"):
        if section not in updates or not isinstance(updates[section], dict):
            continue
        incoming = updates[section]
        if "base_url" in incoming and section == "proxy":
            data["proxy"]["base_url"] = incoming["base_url"] or None
        if "api_key" in incoming:
            key = incoming["api_key"]
            if key:  # non-empty string sets it; explicit "" clears it; absent leaves it
                data[section]["api_key"] = key
            elif key == "":
                data[section]["api_key"] = None
    _save(data)
    return get_config_masked()


def resolve_active() -> tuple[str | None, str | None]:
    """(base_url, api_key) for whichever provider is currently selected. base_url is
    None only when provider is "proxy" and none has been configured yet.
    """
    data = get_config()
    if data["provider"] == "proxy":
        proxy = data["proxy"]
        return proxy.get("base_url"), proxy.get("api_key")
    return OFFICIAL_BASE_URL, data["official"].get("api_key")
