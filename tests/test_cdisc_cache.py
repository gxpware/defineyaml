"""defineyaml.cdisc.cache: the 12h-default file cache for CDISC Library query results.
Every test points CACHE_DIR at a tmp_path directory."""

from __future__ import annotations

import pytest

from defineyaml.cdisc import cache


@pytest.fixture(autouse=True)
def isolated_cache_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path / "cdisc-cache")


def test_miss_on_empty_cache():
    assert cache.get("k") is None


def test_set_then_get_round_trips_arbitrary_json_payload():
    payload = {"products": [{"name": "SDTM"}, {"name": "ADaM"}]}
    cache.set("k", payload)
    assert cache.get("k") == payload


def test_different_keys_do_not_collide():
    cache.set("a", {"v": 1})
    cache.set("b", {"v": 2})
    assert cache.get("a") == {"v": 1}
    assert cache.get("b") == {"v": 2}


def test_entry_older_than_ttl_is_a_miss():
    cache.set("k", {"v": 1})
    assert cache.get("k", ttl_seconds=0) is None


def test_entry_within_ttl_is_a_hit():
    cache.set("k", {"v": 1})
    assert cache.get("k", ttl_seconds=cache.DEFAULT_TTL_SECONDS) == {"v": 1}


def test_default_ttl_is_twelve_hours():
    assert cache.DEFAULT_TTL_SECONDS == 12 * 60 * 60


def test_entry_age_seconds_is_small_just_after_set():
    cache.set("k", {"v": 1})
    age = cache.entry_age_seconds("k")
    assert age is not None
    assert 0 <= age < 5


def test_entry_age_seconds_is_none_for_missing_key():
    assert cache.entry_age_seconds("nope") is None


def test_corrupt_cache_file_is_treated_as_a_miss(tmp_path):
    cache.set("k", {"v": 1})
    path = cache._cache_path("k")
    path.write_text("not json")
    assert cache.get("k") is None


def test_clear_removes_every_entry_and_reports_count():
    cache.set("a", 1)
    cache.set("b", 2)
    removed = cache.clear()
    assert removed == 2
    assert cache.get("a") is None
    assert cache.get("b") is None


def test_clear_on_empty_cache_dir_returns_zero():
    assert cache.clear() == 0
