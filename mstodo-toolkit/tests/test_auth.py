"""auth 模块单测：token 缓存的读写、权限、失效条件。"""
import json
import os
import stat

from mstodo_lib import auth

TOKEN_RESPONSE = {
    "access_token": "AT-1",
    "refresh_token": "RT-1",
    "expires_in": 3599,
    "scope": "Tasks.ReadWrite",
}


def test_cache_path_honours_env_override(cache_dir):
    assert auth.cache_path() == cache_dir / "token.json"


def test_cache_path_falls_back_to_xdg_state(tmp_path, monkeypatch):
    monkeypatch.delenv("MSTODO_TOKEN_CACHE", raising=False)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg"))
    assert auth.cache_path() == tmp_path / "xdg" / "mstodo-toolkit" / "token.json"


def test_write_cache_stores_absolute_expiry(cache_dir):
    auth.write_cache(TOKEN_RESPONSE, now=1_000_000.0)
    stored = json.loads(auth.cache_path().read_text())
    assert stored["expires_at"] == 1_000_000.0 + 3599
    assert stored["access_token"] == "AT-1"
    assert stored["refresh_token"] == "RT-1"
    assert stored["client_id"] == auth.DEFAULT_CLIENT_ID
    assert stored["tenant"] == auth.DEFAULT_TENANT


def test_write_cache_sets_0600_and_dir_0700(cache_dir):
    auth.write_cache(TOKEN_RESPONSE, now=1_000_000.0)
    assert stat.S_IMODE(os.stat(auth.cache_path()).st_mode) == 0o600
    assert stat.S_IMODE(os.stat(cache_dir).st_mode) == 0o700


def test_write_cache_is_atomic_leaving_no_tmp_file(cache_dir):
    auth.write_cache(TOKEN_RESPONSE, now=1_000_000.0)
    assert [p.name for p in cache_dir.iterdir()] == ["token.json"]


def test_read_cache_returns_none_when_absent(cache_dir):
    assert auth.read_cache() is None


def test_read_cache_roundtrips(cache_dir):
    auth.write_cache(TOKEN_RESPONSE, now=1_000_000.0)
    assert auth.read_cache()["access_token"] == "AT-1"


def test_read_cache_invalidated_by_client_id_change(cache_dir, monkeypatch):
    auth.write_cache(TOKEN_RESPONSE, now=1_000_000.0)
    monkeypatch.setenv("MSTODO_CLIENT_ID", "other-client")
    assert auth.read_cache() is None


def test_read_cache_invalidated_by_tenant_change(cache_dir, monkeypatch):
    auth.write_cache(TOKEN_RESPONSE, now=1_000_000.0)
    monkeypatch.setenv("MSTODO_TENANT", "consumers")
    assert auth.read_cache() is None


def test_read_cache_returns_none_on_corrupt_json(cache_dir):
    auth.cache_path().parent.mkdir(parents=True, exist_ok=True)
    auth.cache_path().write_text("{ not json")
    assert auth.read_cache() is None


def test_clear_cache_reports_whether_anything_was_removed(cache_dir):
    assert auth.clear_cache() is False
    auth.write_cache(TOKEN_RESPONSE, now=1_000_000.0)
    assert auth.clear_cache() is True
    assert not auth.cache_path().exists()
