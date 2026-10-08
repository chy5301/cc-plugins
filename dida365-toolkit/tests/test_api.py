import json
import tempfile
from pathlib import Path
from uuid import uuid4

import dida365_api
import httpx
import pytest
from dida365_api import (
    UsageError,
    apply_fields,
    build_request_url,
    main,
    validate_path,
)

# 保证不存在的凭据文件：父目录随机且从不创建，测试绝不读取真实 ~/.dida365/token
MISSING_TOKEN_FILE = str(Path(tempfile.gettempdir()) / f"dida365-tests-{uuid4().hex}" / "token")


def run_main(argv, capsys):
    code = main(argv)
    out = capsys.readouterr().out
    return code, (json.loads(out) if out.strip() else None)


def test_validate_path_ok():
    assert validate_path("/open/v1/project") == "/open/v1/project"
    assert validate_path("/open/v1/project/p1/task/t1") == "/open/v1/project/p1/task/t1"


@pytest.mark.parametrize(
    "path",
    [
        "",
        "open/v1/project",
        "/open/v2/project",
        "https://api.dida365.com/open/v1/project",
        "//api.dida365.com/open/v1/project",
        "/open/v1/../project",
        "/open/v1/%2e%2e/project",
        "/open/v1/%2Fproject",
        "/open/v1/%5cproject",
        "/open/v1/%00project",
        "/open/v1/project?x=1",
        "/open/v1/project#frag",
        "/open/v1/proj\\ect",
        "/open/v1/proj\rect",
        "/open/v1//project",
    ],
)
def test_validate_path_rejects(path):
    with pytest.raises(UsageError) as excinfo:
        validate_path(path)
    assert excinfo.value.code in {"INVALID_PATH"}


def test_build_request_url_encodes_query():
    url = build_request_url(
        "/open/v1/project",
        {"name": "测试 项目", "ids": ["a b", "c"]},
    )
    assert url.startswith("https://api.dida365.com/open/v1/project?")
    assert "%E6%B5%8B%E8%AF%95" in url
    assert "a+b" in url


def test_apply_fields_top_level_only():
    data = [{"id": "1", "title": "t", "nested": {"id": "x"}}]
    assert apply_fields(data, ["id"]) == [{"id": "1"}]
    assert apply_fields({"id": "1", "extra": 2}, ["id", "missing"]) == {"id": "1"}
    assert apply_fields(data, None) == data


def test_dry_run_needs_no_token_and_no_client(monkeypatch, capsys):
    monkeypatch.delenv("DIDA365_API_TOKEN", raising=False)
    monkeypatch.delenv("DIDA365_API_DOMAIN", raising=False)

    def boom(*args, **kwargs):
        raise AssertionError("dry-run 不得创建 HTTP client")

    monkeypatch.setattr("dida365_api.create_client", boom, raising=False)
    code, envelope = run_main(
        ["--method", "DELETE", "--path", "/open/v1/project/p1", "--dry-run"],
        capsys,
    )
    assert code == 10
    assert envelope["success"] is True
    assert envelope["metadata"]["dry_run"] is True
    assert envelope["data"]["would_request"]["method"] == "DELETE"
    assert envelope["data"]["would_request"]["url"] == "https://api.dida365.com/open/v1/project/p1"
    assert "Authorization" not in json.dumps(envelope)


def test_invalid_path_returns_usage_error(capsys):
    code, envelope = run_main(["--method", "GET", "--path", "/open/v2/x"], capsys)
    assert code == 2
    assert envelope["success"] is False
    assert envelope["error"]["code"] == "INVALID_PATH"


def test_invalid_json_body_returns_usage_error(capsys):
    code, envelope = run_main(
        ["--method", "POST", "--path", "/open/v1/task", "--body", "{bad"],
        capsys,
    )
    assert code == 2
    assert envelope["error"]["code"] == "INVALID_JSON"


def test_query_must_be_object(capsys):
    code, envelope = run_main(
        ["--method", "GET", "--path", "/open/v1/project", "--query", "[1]"],
        capsys,
    )
    assert code == 2
    assert envelope["error"]["code"] == "INVALID_JSON"


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)


def run_with_transport(monkeypatch, capsys, handler, argv, token="dp_test_token", domain=None):
    monkeypatch.setenv("DIDA365_API_TOKEN", token)
    if domain is None:
        monkeypatch.delenv("DIDA365_API_DOMAIN", raising=False)
    else:
        monkeypatch.setenv("DIDA365_API_DOMAIN", domain)
    monkeypatch.setattr(dida365_api, "create_client", lambda: _client(handler))
    return run_main(argv, capsys)


GET_PROJECT = ["--method", "GET", "--path", "/open/v1/project"]


def test_get_success_envelope(monkeypatch, capsys):
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json=[{"id": "p1", "name": "清单"}])

    code, envelope = run_with_transport(monkeypatch, capsys, handler, GET_PROJECT + ["--fields", "id"])
    assert code == 0
    assert envelope["success"] is True
    assert envelope["data"] == [{"id": "p1"}]
    assert envelope["metadata"]["http_status"] == 200
    assert envelope["metadata"]["result_count"] == 1
    assert seen["url"].startswith("https://api.dida365.com/open/v1/project")
    assert seen["auth"] == "Bearer dp_test_token"


def test_post_body_and_query_reach_server(monkeypatch, capsys):
    seen = {}

    def handler(request):
        seen["query"] = str(request.url.query, "utf-8")
        seen["body"] = request.content.decode("utf-8")
        return httpx.Response(200, json={"ok": True})

    code, envelope = run_with_transport(
        monkeypatch,
        capsys,
        handler,
        ["--method", "POST", "--path", "/open/v1/task", "--query", '{"limit": 10}', "--body", '{"title": "x"}'],
    )
    assert code == 0
    assert "limit=10" in seen["query"]
    assert json.loads(seen["body"]) == {"title": "x"}
    assert envelope["data"] == {"ok": True}


def test_empty_and_204_become_explicit_success(monkeypatch, capsys):
    code, envelope = run_with_transport(monkeypatch, capsys, lambda request: httpx.Response(204), GET_PROJECT)
    assert code == 0 and envelope["data"] == {"status": "ok"}


def test_non_json_success_is_wrapped(monkeypatch, capsys):
    def handler(request):
        return httpx.Response(200, text="<html>ok</html>", headers={"content-type": "text/html"})

    code, envelope = run_with_transport(monkeypatch, capsys, handler, GET_PROJECT)
    assert code == 0
    assert envelope["data"]["text"] == "<html>ok</html>"
    assert envelope["data"]["content_type"].startswith("text/html")


@pytest.mark.parametrize(
    "status,error_code,exit_code",
    [
        (302, "REDIRECT_BLOCKED", 1),
        (400, "HTTP_ERROR", 1),
        (401, "UNAUTHORIZED", 4),
        (403, "FORBIDDEN", 4),
        (404, "NOT_FOUND", 3),
        (429, "RATE_LIMITED", 1),
        (500, "SERVER_ERROR", 1),
    ],
)
def test_error_mapping(monkeypatch, capsys, status, error_code, exit_code):
    def handler(request):
        return httpx.Response(status, json={"error": "boom"})

    code, envelope = run_with_transport(monkeypatch, capsys, handler, GET_PROJECT)
    assert code == exit_code
    assert envelope["success"] is False
    assert envelope["error"]["code"] == error_code
    assert envelope["metadata"]["http_status"] == status
    assert "dp_test_token" not in json.dumps(envelope)


def test_unauthorized_body_token_is_redacted(monkeypatch, capsys):
    def handler(request):
        return httpx.Response(401, json={"error": "invalid token dp_test_token supplied"})

    code, envelope = run_with_transport(monkeypatch, capsys, handler, GET_PROJECT)
    assert code == 4
    assert envelope["error"]["code"] == "UNAUTHORIZED"
    assert "[REDACTED]" in envelope["error"]["message"]
    assert "dp_test_token" not in json.dumps(envelope)


@pytest.mark.parametrize("json_body", [True, False])
@pytest.mark.parametrize("prefix_length", [290, 296, 310])
def test_error_body_redacts_token_before_truncation(monkeypatch, capsys, json_body, prefix_length):
    token = "dp_boundary_secret_token"
    detail = "x" * prefix_length + token + " supplied"

    def handler(request):
        if json_body:
            return httpx.Response(401, json={"error": detail})
        return httpx.Response(401, text=detail)

    code, envelope = run_with_transport(monkeypatch, capsys, handler, GET_PROJECT, token=token)
    assert code == 4
    message = envelope["error"]["message"]
    assert message == "凭据无效或已过期：" + ("x" * prefix_length + "[REDACTED] supplied")[:300]
    assert "dp_boundary" not in json.dumps(envelope)


def test_timeout_no_retry(monkeypatch, capsys):
    calls = []

    def handler(request):
        calls.append(1)
        raise httpx.ConnectTimeout("boom")

    code, envelope = run_with_transport(monkeypatch, capsys, handler, GET_PROJECT)
    assert code == 1
    assert envelope["error"]["code"] == "TIMEOUT"
    assert len(calls) == 1


def test_connection_error_no_retry(monkeypatch, capsys):
    calls = []

    def handler(request):
        calls.append(1)
        raise httpx.ConnectError("boom")

    code, envelope = run_with_transport(monkeypatch, capsys, handler, GET_PROJECT)
    assert code == 1
    assert envelope["error"]["code"] == "NETWORK_ERROR"
    assert len(calls) == 1


def test_token_missing_fails_before_client(monkeypatch, capsys):
    monkeypatch.delenv("DIDA365_API_TOKEN", raising=False)
    monkeypatch.setenv("DIDA365_TOKEN_FILE", MISSING_TOKEN_FILE)

    def boom():
        raise AssertionError("缺 Token 时不得创建 client")

    monkeypatch.setattr(dida365_api, "create_client", boom)
    code, envelope = run_main(GET_PROJECT, capsys)
    assert code == 2
    assert envelope["error"]["code"] == "TOKEN_MISSING"


def test_utf8_bom_file_sends_normalized_bearer(monkeypatch, capsys, tmp_path):
    token_file = tmp_path / "token"
    token_file.write_text("dp_file_token\n", encoding="utf-8-sig")
    monkeypatch.delenv("DIDA365_API_TOKEN", raising=False)
    monkeypatch.delenv("DIDA365_API_DOMAIN", raising=False)
    monkeypatch.setenv("DIDA365_TOKEN_FILE", str(token_file))

    def handler(request):
        assert request.headers["authorization"] == "Bearer dp_file_token"
        return httpx.Response(200, json=[])

    monkeypatch.setattr(dida365_api, "create_client", lambda: _client(handler))
    code, envelope = run_main(GET_PROJECT, capsys)
    assert code == 0
    assert envelope["success"] is True


@pytest.mark.parametrize("token", ["dp_中文_token", "dp_test\ninjected"])
def test_invalid_token_fails_before_client(monkeypatch, capsys, token):
    monkeypatch.setenv("DIDA365_API_TOKEN", token)
    monkeypatch.delenv("DIDA365_API_DOMAIN", raising=False)

    def boom():
        raise AssertionError("非法 Token 时不得创建 client")

    monkeypatch.setattr(dida365_api, "create_client", boom)
    code, envelope = run_main(GET_PROJECT, capsys)
    assert code == 2
    assert envelope["error"]["code"] == "TOKEN_INVALID"
    assert token not in json.dumps(envelope, ensure_ascii=False)


def test_international_domain_fails_before_client(monkeypatch, capsys):
    monkeypatch.setenv("DIDA365_API_TOKEN", "dp_test_token")
    monkeypatch.setenv("DIDA365_API_DOMAIN", "api.ticktick.com")

    def boom():
        raise AssertionError("国际配置时不得创建 client")

    monkeypatch.setattr(dida365_api, "create_client", boom)
    code, envelope = run_main(GET_PROJECT, capsys)
    assert code == 2
    assert envelope["error"]["code"] == "REGION_UNSUPPORTED"
