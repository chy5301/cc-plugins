import json
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]


def load_config():
    return json.loads((PLUGIN_ROOT / ".mcp.json").read_text(encoding="utf-8"))


def test_mcp_config_registers_official_server_with_helper():
    server = load_config()["dida365"]
    assert server["type"] == "http"
    assert server["url"] == "https://mcp.dida365.com"
    assert "mcp_headers.py" in server["headersHelper"]
    assert "${CLAUDE_PLUGIN_ROOT}" in server["headersHelper"]


def test_mcp_config_has_no_static_authorization():
    server = load_config()["dida365"]
    assert "headers" not in server
    assert "headersHelper" in server
