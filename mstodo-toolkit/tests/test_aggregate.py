"""aggregate 模块单测：$batch 分批、归属注入、状态过滤、部分失败。"""
import httpx
from mstodo_lib import aggregate, client


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_chunk_splits_at_batch_limit():
    assert list(aggregate.chunk(list(range(45)), 20)) == [
        list(range(20)), list(range(20, 40)), list(range(40, 45))]


def test_inject_list_identity_adds_both_fields():
    out = aggregate.inject_list_identity([{"id": "T1"}], list_id="L1", display_name="工作")
    assert out == [{"id": "T1", "listId": "L1", "listDisplayName": "工作"}]


def test_inject_list_identity_does_not_mutate_input():
    src = [{"id": "T1"}]
    aggregate.inject_list_identity(src, list_id="L1", display_name="工作")
    assert src == [{"id": "T1"}]


def test_filter_by_status_keeps_only_requested_values():
    items = [{"id": "1", "status": "notStarted"}, {"id": "2", "status": "completed"},
             {"id": "3", "status": "waitingOnOthers"}]
    out = aggregate.filter_by_status(items, "notStarted,waitingOnOthers")
    assert [i["id"] for i in out] == ["1", "3"]


def test_filter_by_status_none_means_no_filter():
    items = [{"id": "1", "status": "completed"}]
    assert aggregate.filter_by_status(items, None) == items


def test_batch_get_packs_requests_and_correlates_by_id():
    seen = {}

    def handler(request):
        seen["body"] = request.read().decode()
        return httpx.Response(200, json={"responses": [
            {"id": "L2", "status": 200, "body": {"value": [{"id": "T2"}]}},
            {"id": "L1", "status": 200, "body": {"value": [{"id": "T1"}]}},
        ]})

    with _client(handler) as http:
        out = aggregate.batch_get({"L1": "/me/todo/lists/L1/tasks",
                                   "L2": "/me/todo/lists/L2/tasks"},
                                  http=http, token="AT")

    # 响应顺序可能与请求不同，必须靠 id 关联
    assert out["L1"]["body"]["value"] == [{"id": "T1"}]
    assert out["L2"]["body"]["value"] == [{"id": "T2"}]
    assert "/me/todo/lists/L1/tasks" in seen["body"]


def test_batch_get_splits_beyond_twenty_requests():
    calls = []

    def handler(request):
        payload = request.read().decode()
        calls.append(payload.count('"method"'))
        import json as _j
        ids = [r["id"] for r in _j.loads(payload)["requests"]]
        return httpx.Response(200, json={"responses": [
            {"id": i, "status": 200, "body": {"value": []}} for i in ids]})

    paths = {f"L{n}": f"/me/todo/lists/L{n}/tasks" for n in range(25)}
    with _client(handler) as http:
        out = aggregate.batch_get(paths, http=http, token="AT")

    assert calls == [20, 5]
    assert len(out) == 25


def test_batch_get_records_per_request_status_and_retry_after():
    def handler(request):
        return httpx.Response(200, json={"responses": [
            {"id": "L1", "status": 200, "body": {"value": []}},
            {"id": "L2", "status": 429, "headers": {"Retry-After": "30"},
             "body": {"error": {"code": "TooManyRequests", "message": "慢点"}}},
        ]})

    with _client(handler) as http:
        out = aggregate.batch_get({"L1": "/a", "L2": "/b"}, http=http, token="AT")

    assert out["L1"]["status"] == 200
    assert out["L2"]["status"] == 429
    assert out["L2"]["retry_after"] == 30


def test_aggregate_tasks_injects_identity_and_counts_sources():
    lists = [{"id": "L1", "displayName": "工作"}, {"id": "L2", "displayName": "个人"}]

    def handler(request):
        return httpx.Response(200, json={"responses": [
            {"id": "L1", "status": 200, "body": {"value": [{"id": "T1"}]}},
            {"id": "L2", "status": 200, "body": {"value": [{"id": "T2"}]}},
        ]})

    with _client(handler) as http:
        items, meta = aggregate.aggregate_tasks(lists, http=http, token="AT")

    assert {i["id"]: i["listDisplayName"] for i in items} == {"T1": "工作", "T2": "个人"}
    assert meta["aggregated_from"] == 2
    assert meta["partial_failures"] == []


def test_aggregate_tasks_follows_second_page_of_one_list():
    """二维分页：$batch 只压首页，带 nextLink 的清单要另行续页。"""
    lists = [{"id": "L1", "displayName": "工作"}]
    calls = []

    def handler(request):
        calls.append(str(request.url))
        if request.url.path.endswith("/$batch"):
            return httpx.Response(200, json={"responses": [{
                "id": "L1", "status": 200,
                "body": {"value": [{"id": "T1"}],
                         "@odata.nextLink": f"{client.GRAPH_BASE}/more"}}]})
        return httpx.Response(200, json={"value": [{"id": "T2"}]})

    with _client(handler) as http:
        items, meta = aggregate.aggregate_tasks(lists, http=http, token="AT")

    assert [i["id"] for i in items] == ["T1", "T2"]
    assert calls[1].endswith("/more")
    assert meta["partial_failures"] == []


def test_aggregate_tasks_records_partial_failure_with_max_retry_after():
    lists = [{"id": "L1", "displayName": "工作"},
             {"id": "L2", "displayName": "个人"},
             {"id": "L3", "displayName": "杂项"}]

    def handler(request):
        return httpx.Response(200, json={"responses": [
            {"id": "L1", "status": 200, "body": {"value": [{"id": "T1"}]}},
            {"id": "L2", "status": 429, "headers": {"Retry-After": "12"},
             "body": {"error": {"code": "TooManyRequests", "message": "慢"}}},
            {"id": "L3", "status": 429, "headers": {"Retry-After": "47"},
             "body": {"error": {"code": "TooManyRequests", "message": "慢"}}},
        ]})

    with _client(handler) as http:
        items, meta = aggregate.aggregate_tasks(lists, http=http, token="AT")

    assert [i["id"] for i in items] == ["T1"]
    assert meta["retry_after_seconds"] == 47
    assert {f["listId"] for f in meta["partial_failures"]} == {"L2", "L3"}
    assert meta["partial_failures"][0]["displayName"] in ("个人", "杂项")


def test_aggregate_tasks_flags_all_auth_failures():
    """spec §6.5：整批 401/403 是认证问题，不是部分失败。"""
    lists = [{"id": "L1", "displayName": "工作"}, {"id": "L2", "displayName": "个人"}]

    def handler(request):
        return httpx.Response(200, json={"responses": [
            {"id": "L1", "status": 403, "body": {"error": {"code": "ErrorAccessDenied",
                                                           "message": "无权"}}},
            {"id": "L2", "status": 403, "body": {"error": {"code": "ErrorAccessDenied",
                                                           "message": "无权"}}},
        ]})

    with _client(handler) as http:
        _, meta = aggregate.aggregate_tasks(lists, http=http, token="AT")

    assert meta["all_auth_failed"] is True


def test_aggregate_tasks_does_not_flag_auth_when_mixed():
    lists = [{"id": "L1", "displayName": "工作"}, {"id": "L2", "displayName": "个人"}]

    def handler(request):
        return httpx.Response(200, json={"responses": [
            {"id": "L1", "status": 200, "body": {"value": []}},
            {"id": "L2", "status": 403, "body": {"error": {"code": "ErrorAccessDenied",
                                                           "message": "无权"}}},
        ]})

    with _client(handler) as http:
        _, meta = aggregate.aggregate_tasks(lists, http=http, token="AT")

    assert meta["all_auth_failed"] is False


def test_aggregate_tasks_marks_truncated_when_list_pagination_hits_max_pages():
    """某清单有续页，但达到 --max-pages 上限：标顶层 truncated，且保留已取到的首页数据。

    与硬失败（reason="error"）区分开——这个清单没有"失败"，只是没取完。
    """
    lists = [{"id": "L1", "displayName": "工作"}]

    def handler(request):
        if request.url.path.endswith("/$batch"):
            return httpx.Response(200, json={"responses": [{
                "id": "L1", "status": 200,
                "body": {"value": [{"id": "T1"}],
                         "@odata.nextLink": f"{client.GRAPH_BASE}/more"}}]})
        return httpx.Response(200, json={"value": [{"id": "T2"}]})

    with _client(handler) as http:
        items, meta = aggregate.aggregate_tasks(lists, http=http, token="AT", max_pages=1)

    assert [i["id"] for i in items] == ["T1"]
    assert meta["truncated"] is True
    assert meta["partial_failures"] == [
        {"listId": "L1", "displayName": "工作", "status": 0, "retry_after": None,
         "reason": "truncated"}]


def test_aggregate_tasks_tags_hard_failures_with_error_reason_not_truncated():
    """硬失败（无数据）必须打 reason="error"，且不应把顶层 truncated 标为真。"""
    lists = [{"id": "L1", "displayName": "工作"}]

    def handler(request):
        return httpx.Response(200, json={"responses": [
            {"id": "L1", "status": 429, "headers": {"Retry-After": "5"},
             "body": {"error": {"code": "TooManyRequests", "message": "慢"}}}]})

    with _client(handler) as http:
        _, meta = aggregate.aggregate_tasks(lists, http=http, token="AT")

    assert meta["partial_failures"] == [
        {"listId": "L1", "displayName": "工作", "status": 429, "retry_after": 5,
         "reason": "error"}]
    assert meta["truncated"] is False


def test_aggregate_tasks_follow_up_page_error_is_partial_failure_not_crash():
    """续页请求失败（429/503）只算这一个清单失败，不能让整个聚合抛异常丢掉其他清单。

    该清单已取到的首页数据一并丢弃：reason="error" 的语义是"此清单无数据"，
    混入残缺数据会让调用方误以为它是完整的。
    """
    lists = [{"id": "L1", "displayName": "工作"}, {"id": "L2", "displayName": "个人"}]

    def handler(request):
        if request.url.path.endswith("/$batch"):
            return httpx.Response(200, json={"responses": [
                {"id": "L1", "status": 200,
                 "body": {"value": [{"id": "T1"}],
                          "@odata.nextLink": f"{client.GRAPH_BASE}/more"}},
                {"id": "L2", "status": 200, "body": {"value": [{"id": "T9"}]}}]})
        return httpx.Response(429, headers={"Retry-After": "12"},
                              json={"error": {"code": "TooManyRequests", "message": "慢"}})

    with _client(handler) as http:
        items, meta = aggregate.aggregate_tasks(lists, http=http, token="AT")

    assert [i["id"] for i in items] == ["T9"]
    assert meta["partial_failures"] == [
        {"listId": "L1", "displayName": "工作", "status": 429, "retry_after": 12,
         "reason": "error"}]
    assert meta["retry_after_seconds"] == 12


def test_aggregate_tasks_follow_up_page_network_error_is_partial_failure():
    lists = [{"id": "L1", "displayName": "工作"}]

    def handler(request):
        if request.url.path.endswith("/$batch"):
            return httpx.Response(200, json={"responses": [
                {"id": "L1", "status": 200,
                 "body": {"value": [{"id": "T1"}],
                          "@odata.nextLink": f"{client.GRAPH_BASE}/more"}}]})
        raise httpx.ConnectError("boom")

    with _client(handler) as http:
        items, meta = aggregate.aggregate_tasks(lists, http=http, token="AT")

    assert items == []
    assert meta["partial_failures"][0]["reason"] == "error"
    assert meta["partial_failures"][0]["status"] == 0


def test_aggregate_tasks_whole_batch_failure_only_fails_that_batch():
    """清单超过 20 个时分多批。某一批的 $batch 请求本身被限流，只能让这一批的清单
    记为失败，不能抛出去连带丢掉其他批次已取到的结果。"""
    lists = [{"id": f"L{i}", "displayName": f"清单{i}"} for i in range(21)]
    batches = []

    def handler(request):
        batches.append(request)
        if len(batches) == 1:
            ids = [r["id"] for r in __import__("json").loads(request.content)["requests"]]
            return httpx.Response(200, json={"responses": [
                {"id": i, "status": 200, "body": {"value": [{"id": f"T-{i}"}]}} for i in ids]})
        return httpx.Response(429, headers={"Retry-After": "9"},
                              json={"error": {"code": "TooManyRequests", "message": "慢"}})

    with _client(handler) as http:
        items, meta = aggregate.aggregate_tasks(lists, http=http, token="AT")

    assert len(items) == 20
    assert meta["partial_failures"] == [
        {"listId": "L20", "displayName": "清单20", "status": 429, "retry_after": 9,
         "reason": "error"}]
    assert meta["retry_after_seconds"] == 9


def test_aggregate_tasks_batch_network_error_is_failure_not_empty_success():
    """整批网络错误记 status=0。0 不是 2xx，不能被当成"成功但没有任务"。"""
    lists = [{"id": "L1", "displayName": "工作"}]

    def handler(request):
        raise httpx.ConnectError("boom")

    with _client(handler) as http:
        items, meta = aggregate.aggregate_tasks(lists, http=http, token="AT")

    assert items == []
    assert meta["partial_failures"] == [
        {"listId": "L1", "displayName": "工作", "status": 0, "retry_after": None,
         "reason": "error"}]
