import json

import pytest

from dida365_api import (
    UsageError,
    apply_fields,
    build_request_url,
    main,
    validate_path,
)


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
