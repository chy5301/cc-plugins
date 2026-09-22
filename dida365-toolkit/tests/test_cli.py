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


def test_validate_body_accepts_valid_create_task():
    errs = cli.validate_body("create-task", {"title": "x", "projectId": "p", "priority": 3})
    assert errs == []


def test_validate_body_rejects_unknown_field():
    errs = cli.validate_body("create-task", {"title": "x", "projectId": "p", "foo": 1})
    assert any("foo" in e for e in errs)


def test_validate_body_rejects_bad_enum():
    errs = cli.validate_body("create-task", {"title": "x", "projectId": "p", "priority": 2})
    assert any("priority" in e for e in errs)


def test_validate_body_rejects_wrong_type():
    errs = cli.validate_body("create-task", {"title": "x", "projectId": "p", "reminders": "TRIGGER:PT0S"})
    assert any("reminders" in e for e in errs)


def test_validate_body_reports_missing_required():
    errs = cli.validate_body("create-task", {"projectId": "p"})
    assert any("title" in e for e in errs)


def test_load_body_parses_json():
    assert cli.load_body('{"title":"x"}') == {"title": "x"}


def test_load_body_none_returns_empty():
    assert cli.load_body(None) == {}


def test_validate_body_rejects_bool_as_int():
    # priority 的 schema 类型为 int；传入 bool（True/False）应被拒绝，
    # 因为 Python 中 bool 是 int 的子类，若无专门守卫会被误判为合法 int。
    errs = cli.validate_body("create-task", {"title": "x", "projectId": "p", "priority": True})
    assert any("priority" in e for e in errs)


def test_assemble_body_injects_project_for_create_task():
    body = cli.assemble_body("create-task", {"project": "P1"}, {"title": "x"})
    assert body == {"title": "x", "projectId": "P1"}


def test_assemble_body_injects_id_and_project_for_update_task():
    body = cli.assemble_body("update-task", {"task_id": "T1", "project": "P1"}, {"title": "x"})
    assert body == {"title": "x", "id": "T1", "projectId": "P1"}


def test_assemble_body_skips_none_locator_for_update_project():
    # project_id 仅用于 path（映射为 _URL_ONLY/None），不应进入 body
    body = cli.assemble_body("update-project", {"project_id": "P1"}, {"name": "n"})
    assert body == {"name": "n"}


class _FakeResp:
    status_code = 200
    content = b'{"ok":1}'
    def json(self):
        return {"ok": 1}

class _FakeClient:
    last = {}
    def __init__(self, *a, **k):
        pass
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False
    def request(self, method, path, json=None):
        _FakeClient.last = {"method": method, "path": path, "json": json}
        return _FakeResp()


def test_run_body_command_builds_request(monkeypatch, capsys):
    import argparse
    monkeypatch.setattr(cli, "get_client", lambda: _FakeClient())
    args = argparse.Namespace(project="P1", body='{"title":"买菜","reminders":["TRIGGER:PT0S"]}')
    cli.run_body_command("create-task", args, {"project": "P1"})
    sent = _FakeClient.last
    assert sent["method"] == "POST"
    assert sent["path"] == "/task"
    assert sent["json"] == {"title": "买菜", "reminders": ["TRIGGER:PT0S"], "projectId": "P1"}


def test_run_body_command_rejects_invalid_field(monkeypatch):
    import argparse, pytest
    monkeypatch.setattr(cli, "get_client", lambda: _FakeClient())
    args = argparse.Namespace(project="P1", body='{"title":"x","bogus":1}')
    with pytest.raises(SystemExit) as e:
        cli.run_body_command("create-task", args, {"project": "P1"})
    assert e.value.code == cli.EXIT_USAGE


def test_filter_tasks_body_passthrough(monkeypatch):
    import argparse
    monkeypatch.setattr(cli, "get_client", lambda: _FakeClient())
    args = argparse.Namespace(body='{"priority":[3,5],"status":[0]}')
    cli.run_body_command("filter-tasks", args, {})
    assert _FakeClient.last["path"] == "/task/filter"
    assert _FakeClient.last["json"] == {"priority": [3, 5], "status": [0]}


def test_update_project_path_locator_not_in_body(monkeypatch):
    import argparse
    monkeypatch.setattr(cli, "get_client", lambda: _FakeClient())
    args = argparse.Namespace(project_id="P9", body='{"name":"改名"}')
    cli.run_body_command("update-project", args, {"project_id": "P9"})
    assert _FakeClient.last["path"] == "/project/P9"
    assert _FakeClient.last["json"] == {"name": "改名"}


def test_move_tasks_array_body(monkeypatch):
    import argparse
    monkeypatch.setattr(cli, "get_client", lambda: _FakeClient())
    payload = '[{"fromProjectId":"A","toProjectId":"B","taskId":"T1"}]'
    args = argparse.Namespace(body=payload)
    cli.cmd_move_tasks(args)
    assert _FakeClient.last["path"] == "/task/move"
    assert _FakeClient.last["json"] == [
        {"fromProjectId": "A", "toProjectId": "B", "taskId": "T1"}
    ]


def test_move_tasks_rejects_non_array(monkeypatch):
    import argparse, pytest
    monkeypatch.setattr(cli, "get_client", lambda: _FakeClient())
    args = argparse.Namespace(body='{"taskId":"T1"}')
    with pytest.raises(SystemExit) as e:
        cli.cmd_move_tasks(args)
    assert e.value.code == cli.EXIT_USAGE


def test_raw_passthrough(monkeypatch):
    import argparse
    monkeypatch.setattr(cli, "get_client", lambda: _FakeClient())
    args = argparse.Namespace(method="post", path="/task/T1", body='{"id":"T1","isAllDay":true}')
    cli.cmd_raw(args)
    assert _FakeClient.last["method"] == "POST"
    assert _FakeClient.last["path"] == "task/T1"
    assert _FakeClient.last["json"] == {"id": "T1", "isAllDay": True}


def test_raw_get_without_body(monkeypatch):
    import argparse
    monkeypatch.setattr(cli, "get_client", lambda: _FakeClient())
    args = argparse.Namespace(method="get", path="/project", body=None)
    cli.cmd_raw(args)
    assert _FakeClient.last["method"] == "GET"
    assert _FakeClient.last["json"] is None


def test_main_parser_epilog_mentions_schema():
    parser = cli.build_parser()
    assert "schema" in (parser.epilog or "")
    assert "--body" in (parser.epilog or "")


# ── C1: reject empty update bodies ───────────────────────────────────────────


def test_update_project_rejects_empty_body(monkeypatch):
    import argparse, pytest
    monkeypatch.setattr(cli, "get_client", lambda: _FakeClient())
    args = argparse.Namespace(project_id="P1", body=None)
    with pytest.raises(SystemExit) as e:
        cli.run_body_command("update-project", args, {"project_id": "P1"})
    assert e.value.code == cli.EXIT_USAGE


def test_update_task_rejects_empty_body(monkeypatch):
    import argparse, pytest
    monkeypatch.setattr(cli, "get_client", lambda: _FakeClient())
    args = argparse.Namespace(task_id="T1", project="P1", body=None)
    with pytest.raises(SystemExit) as e:
        cli.run_body_command("update-task", args, {"task_id": "T1", "project": "P1"})
    assert e.value.code == cli.EXIT_USAGE


def test_update_task_with_field_passes(monkeypatch):
    import argparse
    monkeypatch.setattr(cli, "get_client", lambda: _FakeClient())
    args = argparse.Namespace(task_id="T1", project="P1", body='{"title":"x"}')
    cli.run_body_command("update-task", args, {"task_id": "T1", "project": "P1"})
    assert _FakeClient.last["json"] == {"title": "x", "id": "T1", "projectId": "P1"}


def test_update_project_empty_string_body_rejected(monkeypatch):
    import argparse, pytest
    monkeypatch.setattr(cli, "get_client", lambda: _FakeClient())
    args = argparse.Namespace(project_id="P1", body="")
    with pytest.raises(SystemExit) as e:
        cli.run_body_command("update-project", args, {"project_id": "P1"})
    assert e.value.code == cli.EXIT_USAGE


# ── C2: move-tasks validate each element has required keys ───────────────────


def test_move_tasks_rejects_missing_required_field(monkeypatch):
    import argparse, pytest
    monkeypatch.setattr(cli, "get_client", lambda: _FakeClient())
    args = argparse.Namespace(body='[{"fromProjectId":"A"}]')
    with pytest.raises(SystemExit) as e:
        cli.cmd_move_tasks(args)
    assert e.value.code == cli.EXIT_USAGE


# ── C6: raw --method accept any case ─────────────────────────────────────────


def test_raw_method_accepts_mixed_case():
    parser = cli.build_parser()
    args = parser.parse_args(["raw", "--method", "Post", "--path", "/task"])
    assert args.method == "POST"


# ── C3: validate array element types ─────────────────────────────────────────


def test_validate_body_rejects_wrong_array_element_type():
    errs = cli.validate_body("filter-tasks", {"priority": ["high"]})
    assert any("priority" in e for e in errs)


def test_validate_body_rejects_int_array_with_string_elements():
    errs = cli.validate_body("create-task", {"title": "x", "projectId": "p", "tags": [1, 2]})
    assert any("tags" in e for e in errs)


def test_validate_body_accepts_correct_array_elements():
    errs = cli.validate_body("filter-tasks", {"priority": [3, 5], "status": [0]})
    assert errs == []


def test_validate_body_rejects_bool_in_int_array():
    errs = cli.validate_body("filter-tasks", {"priority": [True]})
    assert any("priority" in e for e in errs)


def test_validate_body_items_field_still_exempt():
    # items (subtasks) is an array of objects, intentionally not element-type-checked
    errs = cli.validate_body("create-task", {"title": "x", "projectId": "p", "items": [{"title": "sub"}]})
    assert errs == []


# ── C7: schema --all + operation must conflict ────────────────────────────────


def test_cmd_schema_all_with_operation_conflicts(capsys):
    import argparse, pytest
    with pytest.raises(SystemExit) as e:
        cli.cmd_schema(argparse.Namespace(operation="create-task", all=True))
    assert e.value.code == cli.EXIT_USAGE


# ── Task A：--fields 顶层字段掩码 ─────────────────────────────────────────────


def test_apply_fields_filters_each_item_of_a_list():
    data = [{"id": "1", "title": "a", "noise": "x"}, {"id": "2", "title": "b", "noise": "y"}]
    assert cli.apply_fields(data, "id,title") == [
        {"id": "1", "title": "a"}, {"id": "2", "title": "b"},
    ]


def test_apply_fields_filters_keys_of_a_dict():
    assert cli.apply_fields({"id": "1", "title": "a", "noise": "x"}, "id") == {"id": "1"}


def test_apply_fields_silently_drops_unknown_keys():
    assert cli.apply_fields([{"id": "1"}], "id,nope") == [{"id": "1"}]


def test_apply_fields_none_or_empty_means_no_trim():
    data = [{"id": "1", "title": "a"}]
    assert cli.apply_fields(data, None) == data
    assert cli.apply_fields(data, "") == data


def test_apply_fields_preserves_non_dict_items_in_list_as_is():
    """list 中混有非 dict 元素时，非 dict 项原样保留不被裁剪（不对它调 .items()）。"""
    data = [{"id": "1", "title": "a"}, "raw-string", {"id": "2"}]
    result = cli.apply_fields(data, "id")
    assert result == [{"id": "1"}, "raw-string", {"id": "2"}]


def test_fields_trims_real_response_via_run_body_command(monkeypatch, capsys):
    import argparse
    import json

    class _FakeRespFields:
        status_code = 200
        content = b'{"id":"T1","title":"x","extra":"y"}'

        def json(self):
            return {"id": "T1", "title": "x", "extra": "y"}

    class _FakeClientFields:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def request(self, method, path, json=None):
            return _FakeRespFields()

    monkeypatch.setattr(cli, "get_client", lambda: _FakeClientFields())
    args = argparse.Namespace(project="P1", body='{"title":"x"}', dry_run=False, fields="id,title")
    cli.run_body_command("create-task", args, {"project": "P1"})
    out = json.loads(capsys.readouterr().out)
    assert out["data"] == {"id": "T1", "title": "x"}


def test_fields_and_dry_run_available_on_schema_and_raw():
    parser = cli.build_parser()
    args = parser.parse_args(["schema", "create-task", "--fields", "type", "--dry-run"])
    assert args.fields == "type"
    assert args.dry_run is True
    args2 = parser.parse_args(
        ["raw", "--method", "GET", "--path", "/project", "--dry-run", "--fields", "id"]
    )
    assert args2.dry_run is True
    assert args2.fields == "id"


# ── Task A：--dry-run 预演 ────────────────────────────────────────────────────


def _boom_get_client():
    raise AssertionError("dry-run 不应调用 get_client()/发出真实请求")


def test_dry_run_create_task_would_call_shape(monkeypatch, capsys):
    import argparse
    import json

    import pytest
    monkeypatch.setattr(cli, "get_client", _boom_get_client)
    args = argparse.Namespace(project="P1", body='{"title":"买菜"}', dry_run=True, fields=None)
    with pytest.raises(SystemExit) as e:
        cli.run_body_command("create-task", args, {"project": "P1"})
    assert e.value.code == cli.EXIT_DRY_RUN
    out = json.loads(capsys.readouterr().out)
    assert out["success"] is True
    assert out["data"]["would_call"] == "POST /open/v1/task"
    assert out["data"]["body"] == {"title": "买菜", "projectId": "P1"}
    assert out["metadata"]["dry_run"] is True
    assert out["metadata"]["command"] == "dida365_cli create-task"


def test_dry_run_update_task_would_call_shape(monkeypatch, capsys):
    import argparse
    import json

    import pytest
    monkeypatch.setattr(cli, "get_client", _boom_get_client)
    args = argparse.Namespace(task_id="T1", project="P1", body='{"title":"新标题"}',
                              dry_run=True, fields=None)
    with pytest.raises(SystemExit) as e:
        cli.run_body_command("update-task", args, {"task_id": "T1", "project": "P1"})
    assert e.value.code == cli.EXIT_DRY_RUN
    out = json.loads(capsys.readouterr().out)
    assert out["data"]["would_call"] == "POST /open/v1/task/T1"


def test_dry_run_move_tasks(monkeypatch, capsys):
    import argparse
    import json

    import pytest
    monkeypatch.setattr(cli, "get_client", _boom_get_client)
    payload = '[{"fromProjectId":"A","toProjectId":"B","taskId":"T1"}]'
    args = argparse.Namespace(body=payload, dry_run=True, fields=None)
    with pytest.raises(SystemExit) as e:
        cli.cmd_move_tasks(args)
    assert e.value.code == cli.EXIT_DRY_RUN
    out = json.loads(capsys.readouterr().out)
    assert out["data"]["would_call"] == "POST /open/v1/task/move"
    assert out["data"]["body"] == [{"fromProjectId": "A", "toProjectId": "B", "taskId": "T1"}]


def test_dry_run_raw(monkeypatch, capsys):
    import argparse
    import json

    import pytest
    monkeypatch.setattr(cli, "get_client", _boom_get_client)
    args = argparse.Namespace(method="post", path="/task/T1", body='{"id":"T1"}',
                              dry_run=True, fields=None)
    with pytest.raises(SystemExit) as e:
        cli.cmd_raw(args)
    assert e.value.code == cli.EXIT_DRY_RUN
    out = json.loads(capsys.readouterr().out)
    assert out["data"]["would_call"] == "POST /open/v1/task/T1"
    assert out["data"]["body"] == {"id": "T1"}


def test_dry_run_delete_task_returns_would_call_and_exits_10(monkeypatch, capsys):
    import argparse
    import json

    import pytest
    monkeypatch.setattr(cli, "get_client", _boom_get_client)
    args = argparse.Namespace(project_id="P1", task_id="T1", dry_run=True, fields=None)
    with pytest.raises(SystemExit) as e:
        cli.cmd_delete_task(args)
    assert e.value.code == cli.EXIT_DRY_RUN
    out = json.loads(capsys.readouterr().out)
    assert out["data"]["would_call"] == "DELETE /open/v1/project/P1/task/T1"
    assert out["data"]["body"] is None
    assert out["metadata"]["dry_run"] is True


def test_dry_run_available_on_list_projects(monkeypatch, capsys):
    import pytest
    monkeypatch.setattr(cli, "get_client", _boom_get_client)
    parser = cli.build_parser()
    args = parser.parse_args(["list-projects", "--dry-run"])
    with pytest.raises(SystemExit) as e:
        cli.cmd_list_projects(args)
    assert e.value.code == cli.EXIT_DRY_RUN


def test_dry_run_does_not_require_token(monkeypatch, capsys):
    """dry-run 必须在取 token 之前返回：即使没有设置 DIDA365_API_TOKEN 也应正常预演。"""
    import argparse

    import pytest
    monkeypatch.setattr(cli, "TOKEN", "")
    monkeypatch.setattr(cli, "get_client", _boom_get_client)
    args = argparse.Namespace(project_id="P1", task_id="T1", dry_run=True, fields=None)
    with pytest.raises(SystemExit) as e:
        cli.cmd_delete_task(args)
    assert e.value.code == cli.EXIT_DRY_RUN


# ── Task A：metadata 四字段出现条件 ───────────────────────────────────────────


def test_exit_dry_run_constant_value():
    assert cli.EXIT_DRY_RUN == 10


def test_metadata_command_always_present(capsys):
    import json
    cli.output({"id": "1"}, command="get-task")
    out = json.loads(capsys.readouterr().out)
    assert out["metadata"]["command"] == "dida365_cli get-task"


def test_metadata_took_ms_only_when_real_call(capsys):
    import json
    cli.output({"id": "1"}, command="get-project")
    out = json.loads(capsys.readouterr().out)
    assert "took_ms" not in out["metadata"]
    cli.output({"id": "1"}, command="get-project", took_ms=42)
    out2 = json.loads(capsys.readouterr().out)
    assert out2["metadata"]["took_ms"] == 42


def test_metadata_result_count_only_for_list(capsys):
    import json
    cli.output([{"id": "1"}, {"id": "2"}], command="list-projects")
    out = json.loads(capsys.readouterr().out)
    assert out["metadata"]["result_count"] == 2
    cli.output({"id": "1"}, command="get-project")
    out2 = json.loads(capsys.readouterr().out)
    assert "result_count" not in out2["metadata"]


def test_metadata_dry_run_only_when_dry_run(capsys):
    import json

    import pytest
    cli.output({"id": "1"}, command="get-project")
    out = json.loads(capsys.readouterr().out)
    assert "dry_run" not in out["metadata"]
    with pytest.raises(SystemExit) as e:
        cli.output({"would_call": "x"}, command="delete-task", dry_run=True,
                   exit_code=cli.EXIT_DRY_RUN)
    assert e.value.code == cli.EXIT_DRY_RUN
    out2 = json.loads(capsys.readouterr().out)
    assert out2["metadata"]["dry_run"] is True


def test_output_without_exit_code_does_not_exit(capsys):
    """未显式传 exit_code 时 output() 不主动退出（保持既有行为，回归安全）。"""
    import json
    cli.output({"id": "1"}, command="get-project")
    out = json.loads(capsys.readouterr().out)
    assert out["success"] is True
