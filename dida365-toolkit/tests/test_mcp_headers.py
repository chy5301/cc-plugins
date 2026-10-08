import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from uuid import uuid4

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
HELPER = PLUGIN_ROOT / "scripts" / "mcp_headers.py"
AUTH_SOURCE = (PLUGIN_ROOT / "scripts" / "dida365_auth.py").read_text(encoding="utf-8")
HELPER_SOURCE = HELPER.read_text(encoding="utf-8")

SERVER_ENV = "CLAUDE_CODE_MCP_SERVER_URL"
TOKEN_FILE_ENV = "DIDA365_TOKEN_FILE"

# 保证不存在的凭据文件：父目录随机且从不创建，测试绝不读取真实 ~/.dida365/token
MISSING_TOKEN_FILE = str(Path(tempfile.gettempdir()) / f"dida365-tests-{uuid4().hex}" / "token")


def run_helper(env, args=()):
    proc_env = dict(os.environ)
    for key in ("DIDA365_API_TOKEN", TOKEN_FILE_ENV, "DIDA365_API_DOMAIN", SERVER_ENV):
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
    # 生产形态：插件级 helpers 拿不到 DIDA365_API_TOKEN，凭据来自凭据文件
    token_file = tmp_path / "token"
    token_file.write_text("dp_file_token\n", encoding="utf-8")
    proc = run_helper({TOKEN_FILE_ENV: str(token_file), SERVER_ENV: "https://mcp.dida365.com"})
    assert proc.returncode == 0
    assert json.loads(proc.stdout) == {"Authorization": "Bearer dp_file_token"}


def test_defaults_to_official_server_url():
    proc = run_helper({"DIDA365_API_TOKEN": "dp_test_token", TOKEN_FILE_ENV: MISSING_TOKEN_FILE})
    assert proc.returncode == 0
    assert json.loads(proc.stdout)["Authorization"] == "Bearer dp_test_token"


def test_missing_token_fails_without_output():
    proc = run_helper({TOKEN_FILE_ENV: MISSING_TOKEN_FILE, SERVER_ENV: "https://mcp.dida365.com"})
    assert proc.returncode != 0
    assert proc.stdout.strip() == ""


def test_international_domain_fails_without_output():
    proc = run_helper(
        {
            "DIDA365_API_TOKEN": "dp_test_token",
            TOKEN_FILE_ENV: MISSING_TOKEN_FILE,
            "DIDA365_API_DOMAIN": "api.ticktick.com",
            SERVER_ENV: "https://mcp.dida365.com",
        }
    )
    assert proc.returncode != 0
    assert proc.stdout.strip() == ""
    assert "dp_test_token" not in proc.stdout + proc.stderr


def test_unapproved_target_fails_without_output():
    proc = run_helper(
        {
            "DIDA365_API_TOKEN": "dp_test_token",
            TOKEN_FILE_ENV: MISSING_TOKEN_FILE,
            SERVER_ENV: "https://evil.example/mcp",
        }
    )
    assert proc.returncode != 0
    assert proc.stdout.strip() == ""
    assert "dp_test_token" not in proc.stdout + proc.stderr


def test_check_mode_reports_status_without_secrets(tmp_path):
    token_file = tmp_path / "token"
    token_file.write_text("dp_test_token", encoding="utf-8")
    proc = run_helper(
        {TOKEN_FILE_ENV: str(token_file), SERVER_ENV: "https://mcp.dida365.com"}, ["--check"]
    )
    assert proc.returncode == 0
    status = json.loads(proc.stdout)
    assert status["ok"] is True
    assert status["token_present"] is True
    assert status["token_source"] == "file"
    assert status["server_url"] == "https://mcp.dida365.com"
    assert "dp_test_token" not in proc.stdout + proc.stderr


def test_check_mode_failure_is_json():
    proc = run_helper({TOKEN_FILE_ENV: MISSING_TOKEN_FILE, SERVER_ENV: "https://mcp.dida365.com"}, ["--check"])
    assert proc.returncode == 1
    status = json.loads(proc.stdout)
    assert status["ok"] is False
    assert status["token_present"] is False
    assert status["token_source"] is None
    assert status["error"]["code"] == "TOKEN_MISSING"
