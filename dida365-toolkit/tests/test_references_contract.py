from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
REFS = PLUGIN_ROOT / "references"


def test_tool_conventions_replaces_cli_conventions():
    assert (REFS / "tool-conventions.md").is_file()
    assert not (REFS / "cli-conventions.md").exists()


def test_tool_conventions_states_core_rules():
    text = (REFS / "tool-conventions.md").read_text(encoding="utf-8")
    for needle in [
        "dida365_api.py",
        "mcp_headers.py --check",
        "dry-run",
        "结果未知",
        "不自动",
        "仅支持国内",
        "mcp__plugin_dida365-toolkit_dida365__",
    ]:
        assert needle in text, f"tool-conventions.md 缺少：{needle}"


def test_api_reference_keeps_sources_and_drops_unverified_claims():
    text = (REFS / "api-reference.md").read_text(encoding="utf-8")
    assert "https://developer.dida365.com/docs/openapi.md" in text
    assert "本版本仅支持国内" in text
    assert "dida365_cli.py" not in text
    assert "自动补" not in text
