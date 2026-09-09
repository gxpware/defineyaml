"""HTTP calls to a CDISC Library-compatible server - the official
https://library.cdisc.org/api, or a sponsor-run proxy presenting the same request
shape. stdlib `urllib` only; this is a handful of simple authenticated GETs, not
enough to justify a new dependency (requests/httpx) the rest of the project doesn't
otherwise need.

Endpoint shape confirmed live against the real official API and a real sponsor proxy
while building this: `GET /mdr/products` (and `/mdr/ct/packages`) require an `api-key`
header and return 401 - not 404 - when it's missing or wrong, with a JSON body
`{"statusCode": ..., "message": "..."}`. That 401-not-404 distinction is what makes
`/mdr/products` usable as a status-check endpoint: a response at all (even a 401)
already proves the server is up, and the status code separately says whether the
*key* is any good - the two are genuinely different facts this reports separately.

The base URL is not assumed to be just a host - confirmed on a real proxy that mounts
the API under a path prefix: `http://host/mdr/products` 404s, `http://host/api/mdr/
products` 200s. `base_url` is opaque, whatever-the-user-configures, joined with the
request path as a plain string (`base_url.rstrip("/") + "/" + path.lstrip("/")`); a 404
gets a specific, actionable message pointing at a likely missing path segment rather
than falling into the generic "unexpected status" bucket, since that's exactly the
failure mode a wrong base URL produces.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from . import cache as cache_module
from . import config as config_module

DEFAULT_TIMEOUT_SECONDS = 8
STATUS_CHECK_PATH = "/mdr/products"


class CdiscApiError(Exception):
    """A real query failed: nothing configured, unreachable, or a non-2xx response.
    `http_status` is None for "nothing configured"/connection failures (there was no
    HTTP response to have a status), and the real upstream status otherwise - callers
    that need to tell "members-only" (401) apart from "wrong/removed path" (404) need
    this, not just the message (client.py's accessibility-probing use in the CDISC
    viewer is exactly that: bulk-checking which of a list of packages a given key can
    actually reach).
    """

    def __init__(self, message: str, *, http_status: int | None = None) -> None:
        super().__init__(message)
        self.http_status = http_status


@dataclass
class StatusResult:
    state: str  # "online" | "unauthorized" | "not_configured" | "offline" | "error"
    detail: str
    http_status: int | None = None

    def to_dict(self) -> dict:
        return {
            "state": self.state,
            "detail": self.detail,
            "http_status": self.http_status,
        }


def _request(
    base_url: str,
    path: str,
    api_key: str | None,
    *,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> tuple[int, bytes]:
    url = base_url.rstrip("/") + "/" + path.lstrip("/")
    headers = {"Accept": "application/json"}
    if api_key:
        headers["api-key"] = api_key
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (fixed http(s) scheme, user-configured host)
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        raise ConnectionError(str(reason)) from exc


def _error_message(body: bytes) -> str | None:
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    if isinstance(data, dict):
        return data.get("message") or data.get("error")
    return None


_MISSING_PATH_HINT = (
    "Got a 404 for {path} under this base URL. The base URL needs to include whatever "
    "path prefix the server actually mounts the API under - confirmed on a real proxy "
    "while building this: http://host/mdr/products 404s, http://host/api/mdr/products "
    "200s. Check the base URL includes that prefix (e.g. .../api)."
)


def check_status() -> StatusResult:
    """A live check, never cached - "is it online right now" has to mean right now,
    unlike a data query where 12-hour-old content is exactly what was asked for.
    """
    base_url, api_key = config_module.resolve_active()
    if not base_url:
        return StatusResult("not_configured", "No proxy base URL is configured yet.")
    try:
        status, body = _request(base_url, STATUS_CHECK_PATH, api_key)
    except ConnectionError as exc:
        return StatusResult("offline", f"Could not reach {base_url}: {exc}")
    if status == 200:
        return StatusResult("online", "Reachable and authenticated.", status)
    if status == 401:
        message = _error_message(body) or "Unauthorized."
        return StatusResult(
            "unauthorized",
            f"Server is online, but the API key was rejected: {message}",
            status,
        )
    if status == 404:
        return StatusResult(
            "error", _MISSING_PATH_HINT.format(path=STATUS_CHECK_PATH), status
        )
    return StatusResult(
        "error", _error_message(body) or f"Unexpected HTTP {status}.", status
    )


def query(
    path: str,
    *,
    ttl_seconds: float = cache_module.DEFAULT_TTL_SECONDS,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """GET `path` against the configured server, through the local cache
    (cache.py - default 12h TTL). Raises CdiscApiError on anything that stops a real
    query from returning data; unlike check_status, there's no meaningful "status
    object" to hand back instead.
    """
    base_url, api_key = config_module.resolve_active()
    if not base_url:
        raise CdiscApiError("No CDISC API server is configured.")
    cache_key = f"{base_url}|{path}"
    if not force_refresh:
        cached = cache_module.get(cache_key, ttl_seconds=ttl_seconds)
        if cached is not None:
            return {
                "data": cached,
                "from_cache": True,
                "cache_age_seconds": cache_module.entry_age_seconds(cache_key),
            }
    try:
        status, body = _request(base_url, path, api_key)
    except ConnectionError as exc:
        raise CdiscApiError(f"Could not reach {base_url}: {exc}") from exc
    if status == 404:
        raise CdiscApiError(_MISSING_PATH_HINT.format(path=path), http_status=404)
    if status != 200:
        raise CdiscApiError(
            _error_message(body) or f"Unexpected HTTP {status} from {base_url}{path}",
            http_status=status,
        )
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise CdiscApiError(
            f"Response from {base_url}{path} wasn't valid JSON"
        ) from exc
    cache_module.set(cache_key, data)
    return {"data": data, "from_cache": False, "cache_age_seconds": 0}
