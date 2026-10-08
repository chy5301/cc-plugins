from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SKILLS = PLUGIN_ROOT / "skills"


def read_skill(name: str) -> str:
    return (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")


def test_setup_guide_token_first_then_oauth():
    text = read_skill("setup-guide")
    for needle in [
        "DIDA365_API_TOKEN",
        "mcp_headers.py --check",
        "OAuth",
        "本版本仅支持国内",
        "tool-conventions.md",
        "不自动",
    ]:
        assert needle in text, f"setup-guide 缺少：{needle}"
    for forbidden in ["dida365_cli.py", "cli-conventions.md", "tools: Bash"]:
        assert forbidden not in text, f"setup-guide 仍包含：{forbidden}"


def test_query_skills_use_mcp_protocol():
    for name, needles in {
        "task-query": ["tool-conventions.md", "截止", "时区"],
        "daily-review": ["tool-conventions.md", "inbox", "只读", "覆盖"],
    }.items():
        text = read_skill(name)
        for needle in needles:
            assert needle in text, f"{name} 缺少：{needle}"
        for forbidden in ["dida365_cli.py", "cli-conventions.md", "--body", "退出码 10", "tools: Bash"]:
            assert forbidden not in text, f"{name} 仍包含：{forbidden}"


def test_write_skills_cover_status_and_partial_failure():
    for name, needles in {
        "task-crud": ["tool-conventions.md", "放弃", "恢复"],
        "task-complete": ["tool-conventions.md", "部分失败", "确认"],
    }.items():
        text = read_skill(name)
        for needle in needles:
            assert needle in text, f"{name} 缺少：{needle}"
        for forbidden in ["dida365_cli.py", "cli-conventions.md", "退出码 10", "tools: Bash"]:
            assert forbidden not in text, f"{name} 仍包含：{forbidden}"


def test_organize_skills_reference_discovery_protocol():
    for name, needles in {
        "task-organize": ["tool-conventions.md", "预演", "确认"],
        "project-management": ["tool-conventions.md", "dry-run", "DELETE /open/v1/project"],
    }.items():
        text = read_skill(name)
        for needle in needles:
            assert needle in text, f"{name} 缺少：{needle}"
        for forbidden in ["dida365_cli.py", "cli-conventions.md", "退出码 10", "tools: Bash"]:
            assert forbidden not in text, f"{name} 仍包含：{forbidden}"
