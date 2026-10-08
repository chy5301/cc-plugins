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


def run_helper(env, args=()):
    proc_env = dict(os.environ)
    for key in ("DIDA365_API_TOKEN", "DIDA365_API_DOMAIN", SERVER_ENV):
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


def test_outputs_authorization_json():
    proc = run_helper({"DIDA365_API_TOKEN": "dp_test_token", SERVER_ENV: "https://mcp.dida365.com"})
    assert proc.returncode == 0
    assert json.loads(proc.stdout) == {"Authorization": "Bearer dp_test_token"}


def test_defaults_to_official_server_url():
    proc = run_helper({"DIDA365_API_TOKEN": "dp_test_token"})
    assert proc.returncode == 0
    assert json.loads(proc.stdout)["Authorization"] == "Bearer dp_test_token"


def test_missing_token_fails_without_output():
    proc = run_helper({SERVER_ENV: "https://mcp.dida365.com"})
    assert proc.returncode != 0
    assert proc.stdout.strip() == ""


def test_international_domain_fails_without_output():
    proc = run_helper(
        {
            "DIDA365_API_TOKEN": "dp_test_token",
            "DIDA365_API_DOMAIN": "api.ticktick.com",
            SERVER_ENV: "https://mcp.dida365.com",
        }
    )
    assert proc.returncode != 0
    assert proc.stdout.strip() == ""
    assert "dp_test_token" not in proc.stdout + proc.stderr


def test_unapproved_target_fails_without_output():
    proc = run_helper({"DIDA365_API_TOKEN": "dp_test_token", SERVER_ENV: "https://evil.example/mcp"})
    assert proc.returncode != 0
    assert proc.stdout.strip() == ""
    assert "dp_test_token" not in proc.stdout + proc.stderr


def test_check_mode_reports_status_without_secrets():
    proc = run_helper({"DIDA365_API_TOKEN": "dp_test_token", SERVER_ENV: "https://mcp.dida365.com"}, ["--check"])
    assert proc.returncode == 0
    status = json.loads(proc.stdout)
    assert status["ok"] is True
    assert status["token_present"] is True
    assert status["server_url"] == "https://mcp.dida365.com"
    assert "dp_test_token" not in proc.stdout + proc.stderr


def test_check_mode_failure_is_json():
    proc = run_helper({SERVER_ENV: "https://mcp.dida365.com"}, ["--check"])
    assert proc.returncode == 1
    status = json.loads(proc.stdout)
    assert status["ok"] is False
    assert status["token_present"] is False
    assert status["error"]["code"] == "TOKEN_MISSING"
