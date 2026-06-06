"""dida365_cli 纯逻辑单测（无网络）。
运行：uv run --with pytest --with httpx pytest dida365-toolkit/tests/test_cli.py -v
"""
import sys
import pathlib
import pytest

# 让测试能 import 单文件脚本 dida365_cli
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

import dida365_cli as cli  # noqa: E402


def test_schemas_cover_all_body_operations():
    assert set(cli.OPERATION_SCHEMAS) == {
        "create-task", "update-task", "create-project", "update-project",
        "filter-tasks", "query-completed", "move-tasks",
    }


def test_get_schema_returns_fields_for_create_task():
    schema = cli.get_schema("create-task")
    assert schema["method"] == "POST"
    assert schema["path"] == "/task"
    assert "reminders" in schema["fields"]
    assert schema["fields"]["priority"]["enum"] == [0, 1, 3, 5]


def test_get_schema_unknown_operation_raises():
    with pytest.raises(KeyError):
        cli.get_schema("nonexistent-op")


def test_cmd_schema_single(capsys):
    import argparse, json
    cli.cmd_schema(argparse.Namespace(operation="create-task", all=False))
    out = json.loads(capsys.readouterr().out)
    assert out["success"] is True
    assert "reminders" in out["data"]["fields"]


def test_cmd_schema_all(capsys):
    import argparse, json
    cli.cmd_schema(argparse.Namespace(operation=None, all=True))
    out = json.loads(capsys.readouterr().out)
    assert set(out["data"]) == set(cli.OPERATION_SCHEMAS)


def test_cmd_schema_unknown_exits_usage(capsys):
    import argparse, pytest
    with pytest.raises(SystemExit) as e:
        cli.cmd_schema(argparse.Namespace(operation="bogus", all=False))
    assert e.value.code == cli.EXIT_USAGE
