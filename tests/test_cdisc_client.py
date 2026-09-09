"""defineyaml.cdisc.client: HTTP calls to a CDISC Library-compatible server. Mocked at
urllib.request.urlopen - no live network dependency, so the suite doesn't depend on
library.cdisc.org being reachable or on any real API key. (The 401-not-404,
JSON-error-body behaviour these mocks reproduce was confirmed live against the real
API while building this, not guessed at.)
"""

from __future__ import annotations

import json
import urllib.error
from io import BytesIO
from unittest.mock import patch

import pytest

from defineyaml.cdisc import cache as cache_module
from defineyaml.cdisc import client, config as config_module


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(config_module, "CONFIG_PATH", tmp_path / "cdisc.json")
    monkeypatch.setattr(cache_module, "CACHE_DIR", tmp_path / "cdisc-cache")


class _FakeResponse:
    def __init__(self, status: int, body: bytes):
        self.status = status
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _json_bytes(obj) -> bytes:
    return json.dumps(obj).encode()


def test_check_status_not_configured_when_proxy_has_no_base_url():
    config_module.update_config({"provider": "proxy"})
    result = client.check_status()
    assert result.state == "not_configured"


def test_check_status_online_on_200():
    config_module.update_config({"official": {"api_key": "sk-good"}})
    with patch(
        "urllib.request.urlopen",
        return_value=_FakeResponse(200, _json_bytes({"ok": True})),
    ):
        result = client.check_status()
    assert result.state == "online"
    assert result.http_status == 200


def test_check_status_unauthorized_on_401_with_message():
    with patch(
        "urllib.request.urlopen",
        side_effect=urllib.error.HTTPError(
            "url",
            401,
            "Unauthorized",
            {},
            BytesIO(
                _json_bytes({"statusCode": 401, "message": "missing subscription key"})
            ),
        ),
    ):
        result = client.check_status()
    assert result.state == "unauthorized"
    assert "missing subscription key" in result.detail
    assert result.http_status == 401


def test_check_status_offline_on_connection_failure():
    with patch(
        "urllib.request.urlopen",
        side_effect=urllib.error.URLError("Name or service not known"),
    ):
        result = client.check_status()
    assert result.state == "offline"
    assert "Name or service not known" in result.detail


def test_check_status_error_on_unexpected_status():
    with patch(
        "urllib.request.urlopen",
        side_effect=urllib.error.HTTPError(
            "url", 500, "Server Error", {}, BytesIO(b"oops")
        ),
    ):
        result = client.check_status()
    assert result.state == "error"
    assert result.http_status == 500


def test_check_status_404_gets_a_missing_path_prefix_hint():
    # Confirmed real on a sponsor proxy while building this: the same server 404s at
    # http://host/mdr/products and 200s at http://host/api/mdr/products - a base URL
    # missing its path prefix is exactly what a 404 here means, so this gets a
    # specific, actionable message instead of the generic "unexpected status" one.
    with patch(
        "urllib.request.urlopen",
        side_effect=urllib.error.HTTPError(
            "url", 404, "Not Found", {}, BytesIO(b"Not Found")
        ),
    ):
        result = client.check_status()
    assert result.state == "error"
    assert result.http_status == 404
    assert "path prefix" in result.detail
    assert client.STATUS_CHECK_PATH in result.detail


def test_query_404_gets_a_missing_path_prefix_hint():
    with patch(
        "urllib.request.urlopen",
        side_effect=urllib.error.HTTPError(
            "url", 404, "Not Found", {}, BytesIO(b"Not Found")
        ),
    ):
        with pytest.raises(client.CdiscApiError, match="path prefix"):
            client.query("/mdr/products")


def test_query_error_carries_upstream_http_status_401():
    # Accessibility probing (the CDISC viewer's "Check access") needs to tell a real
    # 401 (members-only / needs a key this one doesn't have) apart from a 404 (wrong
    # path) apart from anything else - the message alone doesn't disambiguate that.
    with patch(
        "urllib.request.urlopen",
        side_effect=urllib.error.HTTPError(
            "url",
            401,
            "Unauthorized",
            {},
            BytesIO(_json_bytes({"message": "Members-only content."})),
        ),
    ):
        with pytest.raises(client.CdiscApiError) as exc_info:
            client.query("/mdr/ct/packages/adamct-2014-09-26")
    assert exc_info.value.http_status == 401
    assert "Members-only" in str(exc_info.value)


def test_query_error_carries_upstream_http_status_404():
    with patch(
        "urllib.request.urlopen",
        side_effect=urllib.error.HTTPError(
            "url", 404, "Not Found", {}, BytesIO(b"Not Found")
        ),
    ):
        with pytest.raises(client.CdiscApiError) as exc_info:
            client.query("/mdr/products")
    assert exc_info.value.http_status == 404


def test_query_connection_failure_has_no_http_status():
    with patch(
        "urllib.request.urlopen", side_effect=urllib.error.URLError("unreachable")
    ):
        with pytest.raises(client.CdiscApiError) as exc_info:
            client.query("/mdr/products")
    assert exc_info.value.http_status is None


def test_query_raises_when_nothing_configured():
    config_module.update_config({"provider": "proxy"})
    with pytest.raises(client.CdiscApiError):
        client.query("/mdr/products")


def test_query_returns_data_and_caches_it():
    with patch(
        "urllib.request.urlopen",
        return_value=_FakeResponse(200, _json_bytes({"products": ["SDTM"]})),
    ):
        result1 = client.query("/mdr/products")
    assert result1["data"] == {"products": ["SDTM"]}
    assert result1["from_cache"] is False

    # Second call hits the cache - urlopen must not be called again.
    with patch("urllib.request.urlopen") as m2:
        result2 = client.query("/mdr/products")
    m2.assert_not_called()
    assert result2["from_cache"] is True
    assert result2["data"] == {"products": ["SDTM"]}


def test_query_force_refresh_bypasses_cache():
    with patch(
        "urllib.request.urlopen", return_value=_FakeResponse(200, _json_bytes({"v": 1}))
    ):
        client.query("/mdr/products")
    with patch(
        "urllib.request.urlopen", return_value=_FakeResponse(200, _json_bytes({"v": 2}))
    ) as m:
        result = client.query("/mdr/products", force_refresh=True)
    m.assert_called_once()
    assert result["data"] == {"v": 2}


def test_query_raises_cdisc_api_error_on_non_200():
    with patch(
        "urllib.request.urlopen",
        side_effect=urllib.error.HTTPError(
            "url", 401, "Unauthorized", {}, BytesIO(_json_bytes({"message": "no key"}))
        ),
    ):
        with pytest.raises(client.CdiscApiError, match="no key"):
            client.query("/mdr/products")


def test_query_raises_cdisc_api_error_on_connection_failure():
    with patch(
        "urllib.request.urlopen", side_effect=urllib.error.URLError("unreachable")
    ):
        with pytest.raises(client.CdiscApiError, match="unreachable"):
            client.query("/mdr/products")


def test_query_sends_api_key_header_when_configured():
    config_module.update_config({"official": {"api_key": "sk-secret"}})
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["headers"] = dict(req.header_items())
        return _FakeResponse(200, _json_bytes({}))

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        client.query("/mdr/products")
    assert captured["headers"].get("Api-key") == "sk-secret"


def test_query_omits_api_key_header_when_not_configured():
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["headers"] = dict(req.header_items())
        return _FakeResponse(200, _json_bytes({}))

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        client.query("/mdr/products")
    assert "Api-key" not in captured["headers"]
