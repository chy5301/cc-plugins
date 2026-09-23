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


def test_device_code_poll_respects_timeout_exactly(cache_dir):
    """绝不 sleep 超过 deadline；返回时刻必须 <= 起始时刻 + timeout_s。"""
    clock = {"t": 0.0}
    start_time = 0.0

    def handler(request):
        return httpx.Response(400, json={"error": "authorization_pending"})

    with _transport(handler) as http:
        result = auth.device_code_poll(
            "DC-1", interval=5, timeout_s=12, http=http,
            now=lambda: clock["t"],
            sleep=lambda s: clock.__setitem__("t", clock["t"] + s))

    assert result is None
    assert clock["t"] <= start_time + 12  # 绝不冲过 deadline


def test_device_code_poll_slow_down_respects_timeout(cache_dir):
    """slow_down 导致 wait 膨胀时，仍在 deadline 处返回。"""
    clock = {"t": 0.0}
    slept = []

    def handler(request):
        # 连续返回 slow_down，导致 wait 不断膨胀
        return httpx.Response(400, json={"error": "slow_down"})

    with _transport(handler) as http:
        result = auth.device_code_poll(
            "DC-1", interval=5, timeout_s=12, http=http,
            now=lambda: clock["t"],
            sleep=lambda s: (slept.append(s), clock.__setitem__("t", clock["t"] + s)))

    assert result is None
    assert clock["t"] <= 12  # 绝不冲过 deadline


def test_get_access_token_raises_when_never_logged_in(cache_dir):
    with pytest.raises(auth.NotLoggedInError):
        auth.get_access_token(now=lambda: 1_000_000.0)


def test_get_access_token_uses_cache_when_still_fresh(cache_dir):
    auth.write_cache(TOKEN_RESPONSE, now=1_000_000.0)

    def handler(request):  # 不该被调用
        raise AssertionError("token 仍新鲜时不应发起刷新")

    with _transport(handler) as http:
        token = auth.get_access_token(http=http, now=lambda: 1_000_000.0 + 100)
    assert token == "AT-1"


def test_get_access_token_refreshes_within_skew_window(cache_dir):
    auth.write_cache(TOKEN_RESPONSE, now=1_000_000.0)
    # expires_at = 1_000_000 + 3599；剩余 200 秒 < 300 秒阈值，应触发刷新
    at = 1_000_000.0 + 3599 - 200
    seen = {}

    def handler(request):
        seen["body"] = request.content.decode()
        return httpx.Response(200, json={"access_token": "AT-2", "refresh_token": "RT-2",
                                         "expires_in": 3599, "scope": "Tasks.ReadWrite"})

    with _transport(handler) as http:
        token = auth.get_access_token(http=http, now=lambda: at)

    assert token == "AT-2"
    assert "refresh_token" in seen["body"] and "RT-1" in seen["body"]
    # 新 token 已写回缓存
    assert auth.read_cache()["access_token"] == "AT-2"
    assert auth.read_cache()["refresh_token"] == "RT-2"


def test_refresh_failure_raises_auth_expired_not_http_401(cache_dir):
    """spec §4.4：token 端点返回 400 invalid_grant，不是 401。"""
    auth.write_cache(TOKEN_RESPONSE, now=1_000_000.0)
    at = 1_000_000.0 + 3599 - 200

    def handler(request):
        return httpx.Response(400, json={
            "error": "invalid_grant",
            "error_description": "AADSTS700082: The refresh token has expired."})

    with _transport(handler) as http, pytest.raises(auth.AuthExpiredError) as exc:
        auth.get_access_token(http=http, now=lambda: at)
    assert "AADSTS700082" in exc.value.detail


def test_refresh_keeps_old_refresh_token_when_response_omits_it(cache_dir):
    auth.write_cache(TOKEN_RESPONSE, now=1_000_000.0)
    at = 1_000_000.0 + 3599 - 200

    with _transport(lambda r: httpx.Response(200, json={
            "access_token": "AT-3", "expires_in": 3599})) as http:
        auth.get_access_token(http=http, now=lambda: at)

    assert auth.read_cache()["refresh_token"] == "RT-1"


def test_refresh_keeps_old_refresh_token_when_response_returns_null(cache_dir):
    """响应显式返回 null 也应沿用旧值，不应静默覆盖。"""
    auth.write_cache(TOKEN_RESPONSE, now=1_000_000.0)
    at = 1_000_000.0 + 3599 - 200

    with _transport(lambda r: httpx.Response(200, json={
            "access_token": "AT-4", "refresh_token": None, "expires_in": 3599})) as http:
        auth.get_access_token(http=http, now=lambda: at)

    assert auth.read_cache()["refresh_token"] == "RT-1"


def test_refresh_keeps_old_refresh_token_when_response_returns_empty_string(cache_dir):
    """响应显式返回空字符串也应沿用旧值，不应静默覆盖。"""
    auth.write_cache(TOKEN_RESPONSE, now=1_000_000.0)
    at = 1_000_000.0 + 3599 - 200

    with _transport(lambda r: httpx.Response(200, json={
            "access_token": "AT-5", "refresh_token": "", "expires_in": 3599})) as http:
        auth.get_access_token(http=http, now=lambda: at)

    assert auth.read_cache()["refresh_token"] == "RT-1"


def test_refresh_keeps_old_scope_when_response_returns_null(cache_dir):
    """scope 也应与 refresh_token 同样对待：假值时沿用旧值。"""
    auth.write_cache(TOKEN_RESPONSE, now=1_000_000.0)
    at = 1_000_000.0 + 3599 - 200

    with _transport(lambda r: httpx.Response(200, json={
            "access_token": "AT-6", "refresh_token": "RT-NEW", "scope": None,
            "expires_in": 3599})) as http:
        auth.get_access_token(http=http, now=lambda: at)

    assert auth.read_cache()["scope"] == "Tasks.ReadWrite"


def test_get_access_token_raises_auth_expired_when_cache_has_no_refresh_token(cache_dir):
    auth.write_cache({"access_token": "AT-1", "expires_in": 10}, now=1_000_000.0)
    with pytest.raises(auth.AuthExpiredError):
        auth.get_access_token(now=lambda: 1_000_000.0 + 5)


def test_concurrent_refresh_leaves_cache_usable(cache_dir):
    """spec §9：官方明确旧 refresh token 不被吊销，故并发刷新是良性的。

    两个会话同时刷新，最坏结果是旧 token 覆盖新 token——缓存仍然可用，
    下次调用自动再刷。这里把这个结论钉死，防止有人事后"优化"成文件锁。
    """
    auth.write_cache(TOKEN_RESPONSE, now=1_000_000.0)
    at = 1_000_000.0 + 3599 - 200
    issued = iter(["AT-A", "AT-B"])

    def handler(request):
        return httpx.Response(200, json={
            "access_token": next(issued), "refresh_token": "RT-NEW",
            "expires_in": 3599, "scope": "Tasks.ReadWrite"})

    with _transport(handler) as http:
        auth.get_access_token(http=http, now=lambda: at)
        auth.get_access_token(http=http, now=lambda: at)

    cached = auth.read_cache()
    assert cached["access_token"] in {"AT-A", "AT-B"}
    assert cached["refresh_token"] == "RT-NEW"
    assert [f.name for f in auth.cache_path().parent.iterdir()] == ["token.json"]


def test_refresh_server_error_is_transient_not_expired(cache_dir):
    """认证服务 5xx/429 时 refresh token 仍然有效，不能让 Agent 引导用户重新登录。"""
    auth.write_cache(TOKEN_RESPONSE, now=1_000_000.0)
    at = 1_000_000.0 + 3599 - 200

    with _transport(lambda r: httpx.Response(503, json={
            "error": "temporarily_unavailable"})) as http, \
            pytest.raises(auth.AuthTransientError):
        auth.get_access_token(http=http, now=lambda: at)
    # 缓存原样保留，下次还能用同一个 refresh token 重试
    assert auth.read_cache()["refresh_token"] == TOKEN_RESPONSE["refresh_token"]


def test_refresh_non_json_error_is_transient_not_traceback(cache_dir):
    auth.write_cache(TOKEN_RESPONSE, now=1_000_000.0)
    at = 1_000_000.0 + 3599 - 200

    with _transport(lambda r: httpx.Response(502, text="<html>Bad Gateway</html>")) as http, \
            pytest.raises(auth.AuthTransientError):
        auth.get_access_token(http=http, now=lambda: at)


def test_device_code_start_non_json_error_raises_device_code_error(cache_dir):
    with _transport(lambda r: httpx.Response(502, text="<html>Bad Gateway</html>")) as http, \
            pytest.raises(auth.DeviceCodeError) as exc:
        auth.device_code_start(http=http)
    assert exc.value.kind == "other"
    assert "502" in exc.value.detail


def test_device_code_poll_non_json_error_raises_device_code_error(cache_dir):
    with _transport(lambda r: httpx.Response(502, text="<html>Bad Gateway</html>")) as http, \
            pytest.raises(auth.DeviceCodeError):
        auth.device_code_poll("DC", interval=0, timeout_s=5, http=http,
                              sleep=lambda s: None)


def test_write_cache_file_is_never_world_readable(cache_dir, monkeypatch):
    """临时文件必须以 0600 创建，而不是先按 umask 创建再 chmod。"""
    seen = []
    real_replace = os.replace

    def spy(src, dst):
        seen.append(os.stat(src).st_mode & 0o777)
        return real_replace(src, dst)

    old = os.umask(0o022)
    try:
        monkeypatch.setattr(auth.os, "replace", spy)
        monkeypatch.setattr(auth.os, "chmod", lambda *a, **k: None)  # 去掉事后补救
        auth.write_cache(TOKEN_RESPONSE, now=1_000_000.0)
    finally:
        os.umask(old)
    assert seen == [0o600]
