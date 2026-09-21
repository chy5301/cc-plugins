"""auth 模块单测：token 缓存的读写、权限、失效条件。"""
import json
import os
import stat

import httpx
import pytest
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


def _transport(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_device_code_start_posts_scope_and_client_id(cache_dir):
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["body"] = request.content.decode()
        return httpx.Response(200, json={
            "device_code": "DC-1", "user_code": "ABCD1234",
            "verification_uri": "https://microsoft.com/link",
            "expires_in": 900, "interval": 5})

    with _transport(handler) as http:
        result = auth.device_code_start(http=http)

    assert result["user_code"] == "ABCD1234"
    assert result["interval"] == 5
    assert seen["url"].endswith("/common/oauth2/v2.0/devicecode")
    assert "Tasks.ReadWrite+offline_access" in seen["body"] or \
           "Tasks.ReadWrite%20offline_access" in seen["body"]
    assert auth.DEFAULT_CLIENT_ID in seen["body"]


def test_device_code_poll_returns_token_after_pending(cache_dir):
    replies = [
        httpx.Response(400, json={"error": "authorization_pending"}),
        httpx.Response(400, json={"error": "authorization_pending"}),
        httpx.Response(200, json={"access_token": "AT-9", "refresh_token": "RT-9",
                                  "expires_in": 3599, "scope": "Tasks.ReadWrite"}),
    ]
    clock = {"t": 0.0}
    slept = []

    with _transport(lambda r: replies.pop(0)) as http:
        token = auth.device_code_poll(
            "DC-1", interval=5, timeout_s=90, http=http,
            now=lambda: clock["t"],
            sleep=lambda s: (slept.append(s), clock.__setitem__("t", clock["t"] + s)))

    assert token["access_token"] == "AT-9"
    assert slept == [5, 5, 5]


def test_device_code_poll_backs_off_on_slow_down(cache_dir):
    replies = [
        httpx.Response(400, json={"error": "slow_down"}),
        httpx.Response(200, json={"access_token": "AT-9", "expires_in": 3599}),
    ]
    clock = {"t": 0.0}
    slept = []

    with _transport(lambda r: replies.pop(0)) as http:
        auth.device_code_poll(
            "DC-1", interval=5, timeout_s=90, http=http,
            now=lambda: clock["t"],
            sleep=lambda s: (slept.append(s), clock.__setitem__("t", clock["t"] + s)))

    assert slept == [5, 10]   # slow_down 之后 interval += 5


def test_device_code_poll_returns_none_on_timeout(cache_dir):
    clock = {"t": 0.0}

    def handler(request):
        return httpx.Response(400, json={"error": "authorization_pending"})

    with _transport(handler) as http:
        result = auth.device_code_poll(
            "DC-1", interval=5, timeout_s=12, http=http,
            now=lambda: clock["t"],
            sleep=lambda s: clock.__setitem__("t", clock["t"] + s))

    assert result is None


def test_device_code_poll_raises_on_declined(cache_dir):
    with _transport(lambda r: httpx.Response(400, json={
            "error": "authorization_declined",
            "error_description": "用户拒绝了请求"})) as http, \
            pytest.raises(auth.DeviceCodeError) as exc:
        auth.device_code_poll("DC-1", interval=1, timeout_s=90, http=http,
                              now=lambda: 0.0, sleep=lambda s: None)
    assert exc.value.kind == "declined"


def test_device_code_poll_raises_on_expired_token(cache_dir):
    with _transport(lambda r: httpx.Response(400, json={
            "error": "expired_token"})) as http, \
            pytest.raises(auth.DeviceCodeError) as exc:
        auth.device_code_poll("DC-1", interval=1, timeout_s=90, http=http,
                              now=lambda: 0.0, sleep=lambda s: None)
    assert exc.value.kind == "expired"
