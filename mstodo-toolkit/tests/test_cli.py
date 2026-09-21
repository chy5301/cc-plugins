"""CLI 入口单测：argparse 装配、认证子命令、错误信封。"""
import json

import httpx
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


def test_resolve_token_maps_auth_expired_to_permission(cache_dir, capsys, monkeypatch):
    def boom(**kw):
        raise auth.AuthExpiredError("AADSTS700082: refresh token 已过期")
    monkeypatch.setattr(auth, "get_access_token", boom)
    code, parsed = run(["list-lists"], capsys)
    assert code == env.EXIT_PERMISSION
    assert parsed["error"]["code"] == "AUTH_EXPIRED"
    assert "AADSTS700082" in parsed["error"]["message"]


@pytest.fixture
def logged_in(cache_dir):
    auth.write_cache({"access_token": "AT-1", "refresh_token": "RT-1",
                      "expires_in": 3599, "scope": "Tasks.ReadWrite"}, now=1e12)
    return cache_dir


@pytest.fixture
def graph(monkeypatch):
    """拦截所有 Graph 请求，记录并按预置回放。"""
    calls = []
    replies = []

    def handler(request):
        calls.append((request.method, str(request.url),
                      json.loads(request.content) if request.content else None))
        return replies.pop(0) if replies else httpx.Response(200, json={"value": []})

    monkeypatch.setattr(cli.client, "make_client",
                        lambda **kw: httpx.Client(transport=httpx.MockTransport(handler)))
    return {"calls": calls, "replies": replies}


def test_resource_command_table_has_exactly_the_specced_15(logged_in):
    assert set(cli.RESOURCE_COMMANDS) == {
        "list-lists", "get-list", "create-list", "update-list", "delete-list",
        "list-tasks", "get-task", "create-task", "update-task", "delete-task",
        "list-checklist-items", "get-checklist-item", "create-checklist-item",
        "update-checklist-item", "delete-checklist-item",
    }


def test_move_tasks_and_complete_task_are_absent(logged_in):
    """spec §3.2 / §5.1：这两个子命令明令禁止实现。"""
    assert "move-tasks" not in cli.RESOURCE_COMMANDS
    assert "complete-task" not in cli.RESOURCE_COMMANDS
    assert "move-tasks" not in cli.COMMAND_MAP
    assert "complete-task" not in cli.COMMAND_MAP


def test_list_lists_follows_pagination(logged_in, graph, capsys):
    graph["replies"].extend([
        httpx.Response(200, json={"value": [{"id": "L1", "@odata.etag": "e"}],
                                  "@odata.nextLink": f"{cli.client.GRAPH_BASE}/next"}),
        httpx.Response(200, json={"value": [{"id": "L2"}]}),
    ])
    code, parsed = run(["list-lists"], capsys)
    assert code == env.EXIT_OK
    assert [item["id"] for item in parsed["data"]] == ["L1", "L2"]
    assert parsed["metadata"]["result_count"] == 2
    assert parsed["metadata"]["pages_fetched"] == 2
    assert "@odata.etag" not in json.dumps(parsed["data"])


def test_truncated_collection_exits_with_partial(logged_in, graph, capsys):
    """spec §6.7：触发 --max-pages 上限必须标 truncated 并走退出码 5。"""
    graph["replies"].append(httpx.Response(200, json={
        "value": [{"id": "L1"}], "@odata.nextLink": f"{cli.client.GRAPH_BASE}/next"}))
    code, parsed = run(["list-lists", "--max-pages", "1"], capsys)
    assert code == env.EXIT_PARTIAL
    assert parsed["error"]["code"] == "PARTIAL_FAILURE"
    assert parsed["data"] == [{"id": "L1"}]
    assert parsed["metadata"]["truncated"] is True


def test_get_list_substitutes_locator_into_path(logged_in, graph, capsys):
    graph["replies"].append(httpx.Response(200, json={"id": "L1", "displayName": "任务"}))
    code, parsed = run(["get-list", "--list", "L1"], capsys)
    assert code == env.EXIT_OK
    assert graph["calls"][0][1].endswith("/me/todo/lists/L1")
    assert parsed["data"]["displayName"] == "任务"


def test_create_task_expands_date_and_body_before_sending(logged_in, graph, capsys):
    graph["replies"].append(httpx.Response(201, json={"id": "T1"}))
    run(["create-task", "--list", "L1",
         "--body", '{"title":"写周报","dueDateTime":"2026-04-05","body":"覆盖三个里程碑"}'],
        capsys)
    method, url, sent = graph["calls"][0]
    assert method == "POST"
    assert url.endswith("/me/todo/lists/L1/tasks")
    assert sent["dueDateTime"] == {"dateTime": "2026-04-05T00:00:00",
                                   "timeZone": "Asia/Shanghai"}
    assert sent["body"] == {"content": "覆盖三个里程碑", "contentType": "text"}


def test_create_task_rejects_missing_title_before_any_request(logged_in, graph, capsys):
    code, parsed = run(["create-task", "--list", "L1", "--body", '{"importance":"high"}'],
                       capsys)
    assert code == env.EXIT_USAGE
    assert parsed["error"]["code"] == "INVALID_PARAMETER"
    assert "title" in parsed["error"]["message"]
    assert graph["calls"] == []


def test_update_task_rejects_illegal_status_enum(logged_in, graph, capsys):
    code, parsed = run(["update-task", "--list", "L1", "--task", "T1",
                        "--body", '{"status":"done"}'], capsys)
    assert code == env.EXIT_USAGE
    assert "waitingOnOthers" in parsed["error"]["message"]
    assert graph["calls"] == []


def test_malformed_body_json_is_a_usage_error(logged_in, graph, capsys):
    code, parsed = run(["create-task", "--list", "L1", "--body", "{not json"], capsys)
    assert code == env.EXIT_USAGE
    assert parsed["error"]["code"] == "INVALID_PARAMETER"


def test_malformed_date_is_a_usage_error_not_a_traceback(logged_in, graph, capsys):
    """Task 7 修复轮次引入 InvalidDatetimeFormat；它必须被转成信封而非穿透。"""
    code, parsed = run(["create-task", "--list", "L1",
                        "--body", '{"title":"T","dueDateTime":"not-a-date"}'], capsys)
    assert code == env.EXIT_USAGE
    assert parsed["error"]["code"] == "INVALID_PARAMETER"
    assert graph["calls"] == []


def test_delete_task_returns_no_content_envelope(logged_in, graph, capsys):
    graph["replies"].append(httpx.Response(204))
    code, parsed = run(["delete-task", "--list", "L1", "--task", "T1"], capsys)
    assert code == env.EXIT_OK
    assert graph["calls"][0][0] == "DELETE"
    assert parsed["data"]["deleted"] is True


def test_graph_404_maps_to_not_found_exit(logged_in, graph, capsys):
    graph["replies"].append(httpx.Response(404, json={"error": {
        "code": "ItemNotFound", "message": "指定的任务不存在"}}))
    code, parsed = run(["get-task", "--list", "L1", "--task", "NOPE"], capsys)
    assert code == env.EXIT_NOT_FOUND
    assert parsed["error"]["code"] == "ItemNotFound"


def test_graph_403_maps_to_permission_exit(logged_in, graph, capsys):
    graph["replies"].append(httpx.Response(403, json={"error": {
        "code": "ErrorAccessDenied", "message": "无权访问"}}))
    code, _ = run(["list-lists"], capsys)
    assert code == env.EXIT_PERMISSION


def test_checklist_item_path_uses_all_three_locators(logged_in, graph, capsys):
    graph["replies"].append(httpx.Response(200, json={"id": "C1"}))
    run(["get-checklist-item", "--list", "L1", "--task", "T1", "--item", "C1"], capsys)
    assert graph["calls"][0][1].endswith(
        "/me/todo/lists/L1/tasks/T1/checklistItems/C1")


def test_fields_mask_trims_each_item(logged_in, graph, capsys):
    graph["replies"].append(httpx.Response(200, json={"value": [
        {"id": "L1", "displayName": "任务", "isOwner": True, "wellknownListName": "defaultList"}]}))
    _, parsed = run(["list-lists", "--fields", "id,displayName"], capsys)
    assert parsed["data"] == [{"id": "L1", "displayName": "任务"}]


def test_schema_all_lists_every_body_operation(logged_in, capsys):
    """自省应列出全部 6 个有请求体的操作。"""
    _, parsed = run(["schema", "--all"], capsys)
    assert set(parsed["data"]) == {
        "create-list", "update-list", "create-task", "update-task",
        "create-checklist-item", "update-checklist-item"}


def test_schema_single_operation_shows_union_and_enum(logged_in, capsys):
    """单操作查询应展示方法、字段类型（含 union）与枚举。"""
    _, parsed = run(["schema", "create-task"], capsys)
    assert parsed["data"]["method"] == "POST"
    assert parsed["data"]["fields"]["body"]["type"] == ["str", "object"]
    assert parsed["data"]["fields"]["importance"]["enum"] == ["low", "normal", "high"]


def test_schema_unknown_operation_is_a_usage_error(logged_in, capsys):
    """未知操作应被转成 EXIT_USAGE + UNKNOWN_COMMAND。"""
    code, parsed = run(["schema", "move-tasks"], capsys)
    assert code == env.EXIT_USAGE
    assert parsed["error"]["code"] == "UNKNOWN_COMMAND"


def test_schema_needs_no_login(cache_dir, capsys):
    """自省是纯本地操作，不该要求先登录。"""
    code, _ = run(["schema", "--all"], capsys)
    assert code == env.EXIT_OK


def test_raw_passes_path_and_body_through(logged_in, graph, capsys):
    """raw 应原样透传路径与请求体。"""
    graph["replies"].append(httpx.Response(200, json={"value": [{"id": "X"}]}))
    run(["raw", "--method", "POST", "--path", "/me/todo/lists/L1/tasks/T1/linkedResources",
         "--body", '{"applicationName":"demo"}'], capsys)
    method, url, sent = graph["calls"][0]
    assert method == "POST"
    assert url.endswith("/me/todo/lists/L1/tasks/T1/linkedResources")
    assert sent == {"applicationName": "demo"}


def test_raw_does_not_strip_odata_noise(logged_in, graph, capsys):
    """逃生舱必须原样返回，包括 @odata 噪音。"""
    graph["replies"].append(httpx.Response(200, json={"id": "X", "@odata.etag": "W/\"e\""}))
    _, parsed = run(["raw", "--method", "GET", "--path", "/me/todo/lists/L1"], capsys)
    assert parsed["data"]["@odata.etag"] == 'W/"e"'


def test_raw_dry_run_reports_the_call(logged_in, graph, capsys):
    """raw 的 --dry-run 应报告预期的 API 调用。"""
    code, parsed = run(["raw", "--method", "DELETE", "--path", "/me/todo/lists/L1",
                        "--dry-run"], capsys)
    assert code == env.EXIT_DRY_RUN
    assert parsed["data"]["would_call"] == "DELETE /me/todo/lists/L1"
    assert parsed["metadata"]["dry_run"] is True
    assert graph["calls"] == []


def test_delete_list_dry_run_does_not_call_graph(logged_in, graph, capsys):
    """资源命令的 --dry-run 也应报告预期调用，不真正发请求。"""
    code, parsed = run(["delete-list", "--list", "L1", "--dry-run"], capsys)
    assert code == env.EXIT_DRY_RUN
    assert parsed["data"]["would_call"] == "DELETE /me/todo/lists/L1"
    assert graph["calls"] == []


def test_raw_non_json_2xx_response_outputs_error_envelope(logged_in, graph, capsys):
    """raw 碰到 2xx 但非 JSON 响应应输出信封而非裸异常。"""
    graph["replies"].append(httpx.Response(200, text="<html>not json</html>"))
    code, parsed = run(["raw", "--method", "GET", "--path", "/me/todo/lists/L1"], capsys)
    assert code == env.EXIT_ERROR
    assert parsed["success"] is False
    assert parsed["error"]["code"] == "RAW_RESPONSE_NOT_JSON"
    assert "非 JSON" in parsed["error"]["message"]
    assert "<html>" in parsed["error"]["suggestion"]


def test_list_tasks_all_aggregates_across_lists(logged_in, graph, capsys):
    graph["replies"].extend([
        httpx.Response(200, json={"value": [
            {"id": "L1", "displayName": "工作"}, {"id": "L2", "displayName": "个人"}]}),
        httpx.Response(200, json={"responses": [
            {"id": "L1", "status": 200, "body": {"value": [{"id": "T1"}]}},
            {"id": "L2", "status": 200, "body": {"value": [{"id": "T2"}]}}]}),
    ])
    code, parsed = run(["list-tasks", "--list", "all"], capsys)
    assert code == env.EXIT_OK
    assert parsed["metadata"]["aggregated_from"] == 2
    assert {i["listDisplayName"] for i in parsed["data"]} == {"工作", "个人"}


def test_list_tasks_all_partial_failure_carries_data_and_exits_5(logged_in, graph, capsys):
    graph["replies"].extend([
        httpx.Response(200, json={"value": [
            {"id": "L1", "displayName": "工作"}, {"id": "L2", "displayName": "个人"}]}),
        httpx.Response(200, json={"responses": [
            {"id": "L1", "status": 200, "body": {"value": [{"id": "T1"}]}},
            {"id": "L2", "status": 429, "headers": {"Retry-After": "30"},
             "body": {"error": {"code": "TooManyRequests", "message": "慢"}}}]}),
    ])
    code, parsed = run(["list-tasks", "--list", "all"], capsys)
    assert code == env.EXIT_PARTIAL
    assert parsed["success"] is False
    assert parsed["error"]["code"] == "PARTIAL_FAILURE"
    assert parsed["data"] == [{"id": "T1", "listId": "L1", "listDisplayName": "工作"}]
    assert parsed["metadata"]["retry_after_seconds"] == 30
    assert "30" in parsed["error"]["suggestion"]


def test_list_tasks_all_auth_failure_exits_4_not_5(logged_in, graph, capsys):
    graph["replies"].extend([
        httpx.Response(200, json={"value": [{"id": "L1", "displayName": "工作"}]}),
        httpx.Response(200, json={"responses": [
            {"id": "L1", "status": 403, "body": {"error": {"code": "ErrorAccessDenied",
                                                           "message": "无权"}}}]}),
    ])
    code, _ = run(["list-tasks", "--list", "all"], capsys)
    assert code == env.EXIT_PERMISSION


def test_single_list_also_injects_list_id(logged_in, graph, capsys):
    """spec §6.4 / D6：两种模式都注入，否则 --fields listId 静默失效。"""
    graph["replies"].extend([
        httpx.Response(200, json={"id": "L1", "displayName": "工作"}),
        httpx.Response(200, json={"value": [{"id": "T1"}]}),
    ])
    _, parsed = run(["list-tasks", "--list", "L1", "--fields", "id,listId"], capsys)
    assert parsed["data"] == [{"id": "T1", "listId": "L1"}]


def test_status_filter_runs_after_pagination(logged_in, graph, capsys):
    """spec §5.4 / D4：首页全是 completed，未完成任务在第二页。"""
    graph["replies"].extend([
        httpx.Response(200, json={"id": "L1", "displayName": "工作"}),
        httpx.Response(200, json={
            "value": [{"id": "T1", "status": "completed"}],
            "@odata.nextLink": f"{cli.client.GRAPH_BASE}/more"}),
        httpx.Response(200, json={"value": [{"id": "T2", "status": "notStarted"}]}),
    ])
    _, parsed = run(["list-tasks", "--list", "L1", "--status", "notStarted"], capsys)
    assert [i["id"] for i in parsed["data"]] == ["T2"]
