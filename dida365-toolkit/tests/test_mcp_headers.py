import json
import os
import subprocess
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
HELPER = PLUGIN_ROOT / "scripts" / "mcp_headers.py"
AUTH_SOURCE = (PLUGIN_ROOT / "scripts" / "dida365_auth.py").read_text(encoding="utf-8")
HELPER_SOURCE = HELPER.read_text(encoding="utf-8")

SERVER_ENV = "CLAUDE_CODE_MCP_SERVER_URL"
TOKEN_FILE_ENV = "DIDA365_TOKEN_FILE"
HOME_ENVS = ("USERPROFILE", "HOME")


def sandbox_home(tmp_path, token=None):
    """沙箱 home：MCP 形态的用例只经默认凭据文件提供凭据，绝不读真实 ~/.dida365/token。"""
    home = tmp_path / "home"
    env = {name: str(home) for name in HOME_ENVS}
    if token is None:
        home.mkdir(parents=True, exist_ok=True)
    else:
        token_dir = home / ".dida365"
        token_dir.mkdir(parents=True, exist_ok=True)
        (token_dir / "token").write_text(token, encoding="utf-8")
    return env


def run_helper(env, args=()):
    proc_env = dict(os.environ)
    for key in ("DIDA365_API_TOKEN", TOKEN_FILE_ENV, "DIDA365_API_DOMAIN", SERVER_ENV, *HOME_ENVS):
        proc_env.pop(key, None)
    proc_env.update(env)
    return subprocess.run(
        [sys.executable, str(HELPER), *args],
        capture_output=True,
        text=True,
        env=proc_env,
        timeout=20,
    )


def test_sources_never_import_httpx():
    assert "httpx" not in AUTH_SOURCE
    assert "httpx" not in HELPER_SOURCE


def test_outputs_authorization_json(tmp_path):
    # 生产形态：插件级 helpers 拿不到 DIDA365_API_TOKEN 与 DIDA365_TOKEN_FILE，凭据来自默认文件
    proc = run_helper({**sandbox_home(tmp_path, "dp_file_token\n"), SERVER_ENV: "https://mcp.dida365.com"})
    assert proc.returncode == 0
    assert json.loads(proc.stdout) == {"Authorization": "Bearer dp_file_token"}


def test_defaults_to_official_server_url(tmp_path):
    proc = run_helper(sandbox_home(tmp_path, "dp_default_file_token\n"))
    assert proc.returncode == 0
    assert json.loads(proc.stdout)["Authorization"] == "Bearer dp_default_file_token"


def test_missing_token_fails_without_output(tmp_path):
    proc = run_helper({**sandbox_home(tmp_path), SERVER_ENV: "https://mcp.dida365.com"})
    assert proc.returncode != 0
    assert proc.stdout.strip() == ""


def test_international_domain_fails_without_output(tmp_path):
    proc = run_helper(
        {
            **sandbox_home(tmp_path, "dp_file_token\n"),
            "DIDA365_API_DOMAIN": "api.ticktick.com",
            SERVER_ENV: "https://mcp.dida365.com",
        }
    )
    assert proc.returncode != 0
    assert proc.stdout.strip() == ""
    assert "dp_file_token" not in proc.stdout + proc.stderr


def test_unapproved_target_fails_without_output(tmp_path):
    proc = run_helper(
        {
            **sandbox_home(tmp_path, "dp_file_token\n"),
            SERVER_ENV: "https://evil.example/mcp",
        }
    )
    assert proc.returncode != 0
    assert proc.stdout.strip() == ""
    assert "dp_file_token" not in proc.stdout + proc.stderr


def test_check_mode_reports_status_without_secrets(tmp_path):
    proc = run_helper(
        {**sandbox_home(tmp_path, "dp_file_token"), SERVER_ENV: "https://mcp.dida365.com"}, ["--check"]
    )
    assert proc.returncode == 0
    status = json.loads(proc.stdout)
    assert status["ok"] is True
    assert status["token_present"] is True
    assert status["token_source"] == "file"
    assert status["mcp_file_present"] is True
    assert status["server_url"] == "https://mcp.dida365.com"
    assert "dp_file_token" not in proc.stdout + proc.stderr


def test_check_mode_failure_is_json(tmp_path):
    proc = run_helper({**sandbox_home(tmp_path), SERVER_ENV: "https://mcp.dida365.com"}, ["--check"])
    assert proc.returncode == 1
    status = json.loads(proc.stdout)
    assert status["ok"] is False
    assert status["token_present"] is False
    assert status["token_source"] is None
    assert status["mcp_file_present"] is False
    assert status["error"]["code"] == "TOKEN_MISSING"


def test_override_is_local_only_and_check_reports_mcp_file(tmp_path):
    # 对照用例：DIDA365_TOKEN_FILE 覆盖只在本地/API 执行生效——直接运行 helper 仍能成功，
    # 但插件级 helper 环境里该变量会被移除，故 --check 的 mcp_file_present 必须报 false
    override = tmp_path / "override" / "token"
    override.parent.mkdir(parents=True, exist_ok=True)
    override.write_text("dp_override_token", encoding="utf-8")
    env = {**sandbox_home(tmp_path), TOKEN_FILE_ENV: str(override), SERVER_ENV: "https://mcp.dida365.com"}

    proc = run_helper(env)
    assert proc.returncode == 0
    assert json.loads(proc.stdout) == {"Authorization": "Bearer dp_override_token"}

    check = run_helper(env, ["--check"])
    assert check.returncode == 0
    status = json.loads(check.stdout)
    assert status["ok"] is True
    assert status["token_source"] == "file"
    assert status["mcp_file_present"] is False
    assert "dp_override_token" not in check.stdout + check.stderr
