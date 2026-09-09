"""defineyaml.cdisc.config: per-machine CDISC Library server config. Never touches the
real ~/.config/defineyaml/cdisc.json - every test points CONFIG_PATH at a tmp_path file.
"""

from __future__ import annotations

import os
import stat

import pytest

from defineyaml.cdisc import config as cfg


@pytest.fixture(autouse=True)
def isolated_config_path(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "CONFIG_PATH", tmp_path / "cdisc.json")


def test_default_config_is_official_with_no_key():
    data = cfg.get_config_masked()
    assert data["provider"] == "official"
    assert data["official"]["has_api_key"] is False
    assert data["proxy"]["base_url"] is None


def test_setting_official_api_key_masks_all_but_the_tail():
    cfg.update_config({"official": {"api_key": "sk-abcdefgh1234"}})
    data = cfg.get_config_masked()
    assert data["official"]["has_api_key"] is True
    assert (
        data["official"]["api_key_masked"]
        == "•" * (len("sk-abcdefgh1234") - 4) + "1234"
    )
    # The real key never round-trips back to a caller of the masked accessor.
    assert "sk-abcdefgh1234" not in str(data)


def test_real_key_is_retrievable_server_side_via_resolve_active():
    cfg.update_config({"official": {"api_key": "sk-real-key"}})
    base_url, api_key = cfg.resolve_active()
    assert base_url == cfg.OFFICIAL_BASE_URL
    assert api_key == "sk-real-key"


def test_switching_to_proxy_uses_proxy_base_url_and_key():
    cfg.update_config(
        {
            "provider": "proxy",
            "proxy": {"base_url": "http://10.0.0.5/api", "api_key": "proxykey"},
        }
    )
    base_url, api_key = cfg.resolve_active()
    assert base_url == "http://10.0.0.5/api"
    assert api_key == "proxykey"


def test_proxy_with_no_api_key_resolves_to_none():
    cfg.update_config(
        {"provider": "proxy", "proxy": {"base_url": "http://10.0.0.5/api"}}
    )
    base_url, api_key = cfg.resolve_active()
    assert base_url == "http://10.0.0.5/api"
    assert api_key is None


def test_saving_without_api_key_field_leaves_existing_key_untouched():
    cfg.update_config({"official": {"api_key": "sk-original"}})
    cfg.update_config({"official": {}})  # e.g. saving other fields, key field omitted
    _, api_key = cfg.resolve_active()
    assert api_key == "sk-original"


def test_explicit_empty_string_clears_the_api_key():
    cfg.update_config({"official": {"api_key": "sk-original"}})
    cfg.update_config({"official": {"api_key": ""}})
    _, api_key = cfg.resolve_active()
    assert api_key is None


def test_switching_provider_back_and_forth_preserves_both_configs():
    cfg.update_config({"official": {"api_key": "off-key"}})
    cfg.update_config(
        {
            "provider": "proxy",
            "proxy": {"base_url": "http://p/api", "api_key": "prox-key"},
        }
    )
    cfg.update_config({"provider": "official"})
    assert cfg.resolve_active() == (cfg.OFFICIAL_BASE_URL, "off-key")
    cfg.update_config({"provider": "proxy"})
    assert cfg.resolve_active() == ("http://p/api", "prox-key")


def test_invalid_provider_raises():
    with pytest.raises(ValueError):
        cfg.update_config({"provider": "something-else"})


@pytest.mark.skipif(
    os.name == "nt", reason="POSIX mode bits; Windows uses ACLs, chmod is a no-op here"
)
def test_config_file_is_not_group_or_world_readable(tmp_path):
    cfg.update_config({"official": {"api_key": "sk-secret"}})
    mode = stat.S_IMODE(cfg.CONFIG_PATH.stat().st_mode)
    assert mode & (stat.S_IRWXG | stat.S_IRWXO) == 0


def test_corrupt_config_file_falls_back_to_default(tmp_path):
    cfg.CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    cfg.CONFIG_PATH.write_text("{not valid json")
    assert cfg.get_config_masked()["provider"] == "official"
