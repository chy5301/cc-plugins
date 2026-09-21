"""CLI 入口单测：argparse 装配、认证子命令、错误信封。"""
import json

import mstodo_cli as cli
import pytest
from mstodo_lib import auth
from mstodo_lib import envelope as env


def run(argv, capsys):
    """跑一次 main，返回 (exit_code, 解析后的信封)。"""
    with pytest.raises(SystemExit) as exc:
        cli.main(argv)
    return exc.value.code, json.loads(capsys.readouterr().out)


def test_unknown_subcommand_yields_json_envelope_not_bare_text(cache_dir, capsys):
    code, parsed = run(["no-such-command"], capsys)
    assert code == env.EXIT_USAGE
    assert parsed["success"] is False
    assert parsed["error"]["code"] == "INVALID_PARAMETER"


def test_missing_required_option_yields_json_envelope(cache_dir, capsys):
    code, parsed = run(["get-list"], capsys)
    assert code == env.EXIT_USAGE
    assert parsed["error"]["code"] == "INVALID_PARAMETER"


def test_auth_status_reports_not_logged_in_as_config_error(cache_dir, capsys):
    code, parsed = run(["auth-status"], capsys)
    assert code == env.EXIT_USAGE
    assert parsed["error"]["code"] == "CONFIG_ERROR"
    assert "auth-start" in parsed["error"]["suggestion"]


def test_auth_status_reports_remaining_lifetime(cache_dir, capsys, monkeypatch):
    auth.write_cache({"access_token": "AT-1", "refresh_token": "RT-1",
                      "expires_in": 3599, "scope": "Tasks.ReadWrite"}, now=1_000_000.0)
    monkeypatch.setattr(cli.time, "time", lambda: 1_000_000.0 + 599)
    code, parsed = run(["auth-status"], capsys)
    assert code == env.EXIT_OK
    assert parsed["data"]["logged_in"] is True
    assert parsed["data"]["expires_in_seconds"] == 3000
    assert parsed["data"]["tenant"] == auth.DEFAULT_TENANT
    assert parsed["data"]["cache_path"].endswith("token.json")
    assert "access_token" not in json.dumps(parsed)   # 绝不回显 token 本体


def test_auth_logout_is_idempotent(cache_dir, capsys):
    code, parsed = run(["auth-logout"], capsys)
    assert code == env.EXIT_OK
    assert parsed["data"]["removed"] is False


def test_auth_start_returns_user_code_immediately(cache_dir, capsys, monkeypatch):
    monkeypatch.setattr(auth, "device_code_start", lambda **kw: {
        "device_code": "DC-1", "user_code": "ABCD1234",
        "verification_uri": "https://microsoft.com/link",
        "expires_in": 900, "interval": 5})
    code, parsed = run(["auth-start"], capsys)
    assert code == env.EXIT_OK
    assert parsed["data"]["user_code"] == "ABCD1234"
    assert parsed["data"]["device_code"] == "DC-1"


def test_auth_complete_writes_cache_on_success(cache_dir, capsys, monkeypatch):
    monkeypatch.setattr(auth, "device_code_poll", lambda dc, **kw: {
        "access_token": "AT-9", "refresh_token": "RT-9",
        "expires_in": 3599, "scope": "Tasks.ReadWrite"})
    code, parsed = run(["auth-complete", "--device-code", "DC-1"], capsys)
    assert code == env.EXIT_OK
    assert parsed["data"]["logged_in"] is True
    assert auth.read_cache()["access_token"] == "AT-9"


def test_auth_complete_timeout_yields_auth_pending(cache_dir, capsys, monkeypatch):
    """spec §4.1：超时是契约不是意外，Agent 用同一 device_code 重试。"""
    auth.write_cache({"access_token": "OLD", "refresh_token": "RT-OLD",
                      "expires_in": 3599, "scope": "Tasks.ReadWrite"}, now=1e12)
    monkeypatch.setattr(auth, "device_code_poll", lambda dc, **kw: None)
    code, parsed = run(["auth-complete", "--device-code", "DC-1"], capsys)
    assert code == env.EXIT_AUTH_PENDING
    assert parsed["error"]["code"] == "AUTH_PENDING"
    assert "DC-1" in parsed["error"]["suggestion"]
    # 超时不得破坏已有登录态
    assert auth.read_cache()["access_token"] == "OLD"


def test_auth_complete_declined_is_a_plain_error(cache_dir, capsys, monkeypatch):
    def boom(dc, **kw):
        raise auth.DeviceCodeError("declined", "用户拒绝了请求")
    monkeypatch.setattr(auth, "device_code_poll", boom)
    code, parsed = run(["auth-complete", "--device-code", "DC-1"], capsys)
    assert code == env.EXIT_ERROR
    assert parsed["error"]["code"] == "AUTH_DECLINED"


def test_auth_complete_expired_device_code_tells_user_to_restart(cache_dir, capsys, monkeypatch):
    def boom(dc, **kw):
        raise auth.DeviceCodeError("expired", "device_code 已过期")
    monkeypatch.setattr(auth, "device_code_poll", boom)
    code, parsed = run(["auth-complete", "--device-code", "DC-1"], capsys)
    assert code == env.EXIT_ERROR
    assert parsed["error"]["code"] == "AUTH_CODE_EXPIRED"
    assert "auth-start" in parsed["error"]["suggestion"]


def test_auth_complete_default_timeout_is_90_seconds(cache_dir, capsys, monkeypatch):
    seen = {}

    def spy(dc, **kw):
        seen.update(kw)
        return {"access_token": "AT", "expires_in": 3599}

    monkeypatch.setattr(auth, "device_code_poll", spy)
    run(["auth-complete", "--device-code", "DC-1"], capsys)
    assert seen["timeout_s"] == 90


def test_auth_complete_fails_if_cache_unreadable_after_write(cache_dir, capsys, monkeypatch):
    """写入后读回失败（client_id/tenant 中途变更）应当响亮失败，而非静默降级。"""
    monkeypatch.setattr(auth, "device_code_poll", lambda dc, **kw: {
        "access_token": "AT", "refresh_token": "RT",
        "expires_in": 3599, "scope": "Tasks.ReadWrite"})
    # 模拟 read_cache 返回 None（如 client_id/tenant 中途改变）
    monkeypatch.setattr(auth, "read_cache", lambda: None)
    code, parsed = run(["auth-complete", "--device-code", "DC-1"], capsys)
    assert code == env.EXIT_ERROR
    assert parsed["success"] is False
    assert parsed["error"]["code"] == "AUTH_CACHE_CORRUPT"
    assert "logged_in" not in parsed.get("data", {})


@pytest.mark.xfail(reason="list-lists 在 Task 9 加入")
def test_resolve_token_maps_auth_expired_to_permission(cache_dir, capsys, monkeypatch):
    def boom(**kw):
        raise auth.AuthExpiredError("AADSTS700082: refresh token 已过期")
    monkeypatch.setattr(auth, "get_access_token", boom)
    code, parsed = run(["list-lists"], capsys)
    assert code == env.EXIT_PERMISSION
    assert parsed["error"]["code"] == "AUTH_EXPIRED"
    assert "AADSTS700082" in parsed["error"]["message"]
