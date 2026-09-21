"""client 模块单测：退出码映射、OData 剥噪、错误解析。"""
import httpx
import pytest
from mstodo_lib import client
from mstodo_lib import envelope as env


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler),
                        base_url=client.GRAPH_BASE)


def test_status_to_exit_maps_auth_failures_to_permission():
    assert client.status_to_exit(401) == env.EXIT_PERMISSION
    assert client.status_to_exit(403) == env.EXIT_PERMISSION


def test_status_to_exit_maps_404_to_not_found():
    assert client.status_to_exit(404) == env.EXIT_NOT_FOUND


def test_status_to_exit_defaults_to_generic_error():
    assert client.status_to_exit(429) == env.EXIT_ERROR
    assert client.status_to_exit(500) == env.EXIT_ERROR


def test_strip_item_odata_removes_etag_and_context_from_dict():
    obj = {"id": "1", "title": "a", "@odata.etag": "W/\"x\"", "@odata.context": "ctx"}
    assert client.strip_item_odata(obj) == {"id": "1", "title": "a"}


def test_strip_item_odata_recurses_into_lists():
    obj = [{"id": "1", "@odata.etag": "e"}, {"id": "2", "@odata.etag": "e"}]
    assert client.strip_item_odata(obj) == [{"id": "1"}, {"id": "2"}]


def test_strip_item_odata_keeps_collection_control_fields():
    """spec §6.6：nextLink 是分页的唯一信号，绝不能被剥掉。"""
    obj = {"@odata.context": "ctx",
           "@odata.nextLink": "https://graph.microsoft.com/v1.0/next",
           "@odata.count": 85,
           "value": [{"id": "1", "@odata.etag": "e"}]}
    result = client.strip_item_odata(obj)
    assert result["@odata.nextLink"] == "https://graph.microsoft.com/v1.0/next"
    assert result["@odata.count"] == 85
    assert "@odata.context" not in result
    assert result["value"] == [{"id": "1"}]


def test_handle_response_returns_stripped_payload():
    resp = httpx.Response(200, json={"id": "1", "@odata.etag": "e"})
    assert client.handle_response(resp) == {"id": "1"}


def test_handle_response_returns_none_for_204():
    assert client.handle_response(httpx.Response(204)) is None


def test_handle_response_raises_graph_error_with_code_and_message():
    resp = httpx.Response(404, json={"error": {
        "code": "ItemNotFound", "message": "指定的任务不存在"}})
    with pytest.raises(client.GraphError) as exc:
        client.handle_response(resp)
    assert exc.value.status == 404
    assert exc.value.code == "ItemNotFound"
    assert exc.value.message == "指定的任务不存在"


def test_handle_response_captures_retry_after_header():
    resp = httpx.Response(429, json={"error": {"code": "TooManyRequests", "message": "慢点"}},
                          headers={"Retry-After": "37"})
    with pytest.raises(client.GraphError) as exc:
        client.handle_response(resp)
    assert exc.value.retry_after == 37


def test_handle_response_tolerates_non_json_error_body():
    resp = httpx.Response(502, text="<html>bad gateway</html>")
    with pytest.raises(client.GraphError) as exc:
        client.handle_response(resp)
    assert exc.value.status == 502
    assert "bad gateway" in exc.value.message


def test_request_sends_bearer_token_and_joins_path():
    seen = {}

    def handler(request):
        seen["auth"] = request.headers["Authorization"]
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"value": []})

    with _client(handler) as http:
        client.request("GET", "/me/todo/lists", http=http, token="AT-1")

    assert seen["auth"] == "Bearer AT-1"
    assert seen["url"] == f"{client.GRAPH_BASE}/me/todo/lists"


def test_handle_response_tolerates_error_field_as_string():
    """错误体的 error 字段是字符串而非对象时，不抛 AttributeError。"""
    resp = httpx.Response(500, json={"error": "Internal Server Error"})
    with pytest.raises(client.GraphError) as exc:
        client.handle_response(resp)
    assert exc.value.status == 500
    assert exc.value.code == "HTTP_500"


def test_handle_response_tolerates_non_dict_top_level():
    """响应顶层是数组而非对象时，不抛 AttributeError。"""
    resp = httpx.Response(502, json=[1, 2, 3])
    with pytest.raises(client.GraphError) as exc:
        client.handle_response(resp)
    assert exc.value.status == 502
    assert exc.value.code == "HTTP_502"


def test_handle_response_tolerates_error_field_as_null():
    """错误体的 error 字段显式为 null 时，不抛 AttributeError。"""
    resp = httpx.Response(503, json={"error": None})
    with pytest.raises(client.GraphError) as exc:
        client.handle_response(resp)
    assert exc.value.status == 503
    assert exc.value.code == "HTTP_503"


def _paged_handler(pages):
    """pages 是 [(items, next_url_or_None), ...]，按请求顺序返回。"""
    state = {"i": 0}

    def handler(request):
        items, next_url = pages[state["i"]]
        state["i"] += 1
        body = {"value": items}
        if next_url:
            body["@odata.nextLink"] = next_url
        return httpx.Response(200, json=body)

    return handler


def test_get_collection_returns_single_page_untouched():
    with _client(_paged_handler([([{"id": "1"}, {"id": "2"}], None)])) as http:
        items, meta = client.get_collection("/me/todo/lists", http=http, token="AT")
    assert items == [{"id": "1"}, {"id": "2"}]
    assert meta == {"pages_fetched": 1, "truncated": False}


def test_get_collection_follows_next_link_to_exhaustion():
    pages = [
        ([{"id": "1"}], f"{client.GRAPH_BASE}/me/todo/lists?$skiptoken=A"),
        ([{"id": "2"}], f"{client.GRAPH_BASE}/me/todo/lists?$skiptoken=B"),
        ([{"id": "3"}], None),
    ]
    with _client(_paged_handler(pages)) as http:
        items, meta = client.get_collection("/me/todo/lists", http=http, token="AT")
    assert [i["id"] for i in items] == ["1", "2", "3"]
    assert meta == {"pages_fetched": 3, "truncated": False}


def test_get_collection_requests_next_link_as_absolute_url():
    seen = []

    def handler(request):
        seen.append(str(request.url))
        if len(seen) == 1:
            return httpx.Response(200, json={
                "value": [{"id": "1"}],
                "@odata.nextLink": f"{client.GRAPH_BASE}/me/todo/lists?$skiptoken=XYZ"})
        return httpx.Response(200, json={"value": [{"id": "2"}]})

    with _client(handler) as http:
        client.get_collection("/me/todo/lists", http=http, token="AT")

    assert seen[1] == f"{client.GRAPH_BASE}/me/todo/lists?$skiptoken=XYZ"


def test_get_collection_marks_truncated_when_max_pages_hit():
    pages = [
        ([{"id": "1"}], f"{client.GRAPH_BASE}/next1"),
        ([{"id": "2"}], f"{client.GRAPH_BASE}/next2"),
    ]
    with _client(_paged_handler(pages)) as http:
        items, meta = client.get_collection("/me/todo/lists", http=http,
                                            token="AT", max_pages=2)
    assert [i["id"] for i in items] == ["1", "2"]
    assert meta == {"pages_fetched": 2, "truncated": True}


def test_get_collection_not_truncated_when_last_page_has_no_next_link():
    pages = [([{"id": "1"}], f"{client.GRAPH_BASE}/next1"), ([{"id": "2"}], None)]
    with _client(_paged_handler(pages)) as http:
        _, meta = client.get_collection("/me/todo/lists", http=http,
                                        token="AT", max_pages=2)
    assert meta["truncated"] is False


def test_get_collection_strips_item_odata_from_every_page():
    pages = [
        ([{"id": "1", "@odata.etag": "e"}], f"{client.GRAPH_BASE}/next"),
        ([{"id": "2", "@odata.etag": "e"}], None),
    ]
    with _client(_paged_handler(pages)) as http:
        items, _ = client.get_collection("/me/todo/lists", http=http, token="AT")
    assert items == [{"id": "1"}, {"id": "2"}]
