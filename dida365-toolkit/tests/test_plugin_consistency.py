import json
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PLUGIN_ROOT.parent
SKILL_NAMES = [
    "setup-guide",
    "task-crud",
    "task-complete",
    "task-organize",
    "task-query",
    "project-management",
    "daily-review",
]


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_plugin_manifest_version_and_marketplace_sync():
    plugin = load_json(PLUGIN_ROOT / ".claude-plugin" / "plugin.json")
    market = load_json(REPO_ROOT / ".claude-plugin" / "marketplace.json")
    entry = next(item for item in market["plugins"] if item["name"] == "dida365-toolkit")
    assert plugin["version"] == "0.6.1"
    assert plugin["description"] == entry["description"]


def test_all_skills_are_migrated():
    for name in SKILL_NAMES:
        text = (PLUGIN_ROOT / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
        assert "tool-conventions.md" in text, f"{name} 未引用 tool-conventions.md"
        for forbidden in ["dida365_cli.py", "cli-conventions.md", "tools: Bash"]:
            assert forbidden not in text, f"{name} 仍包含：{forbidden}"


def test_references_layout():
    refs = PLUGIN_ROOT / "references"
    assert (refs / "tool-conventions.md").is_file()
    assert not (refs / "cli-conventions.md").exists()
