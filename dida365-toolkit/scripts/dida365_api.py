#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["httpx>=0.28"]
# ///
"""通用滴答 Open API 执行器：单次请求、固定出口、统一信封。不是端点专用 CLI。"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dida365_auth as auth  # noqa: E402

import httpx  # noqa: E402

ALLOWED_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")
PATH_PREFIX = "/open/v1/"
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_NOT_FOUND = 3
EXIT_AUTH = 4
EXIT_DRY_RUN = 10
TIMEOUT_SECONDS = 30.0

_FORBIDDEN_PATH_CHARS = re.compile(r"[\\?#\x00-\x1f\x7f]")
_ENCODED_DANGEROUS = re.compile(r"%(?:2e|2f|5c|00|0a|0d)", re.IGNORECASE)


class UsageError(Exception):
    def __init__(self, code: str, message: str, suggestion: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.suggestion = suggestion


def validate_path(path: str) -> str:
    if not path or not path.startswith(PATH_PREFIX):
        raise UsageError("INVALID_PATH", f"--path 必须以 {PATH_PREFIX} 开头")
    if "//" in path or _FORBIDDEN_PATH_CHARS.search(path) or _ENCODED_DANGEROUS.search(path):
        raise UsageError("INVALID_PATH", "--path 包含不允许的字符或编码")
    if any(segment in (".", "..") for segment in path.split("/")):
        raise UsageError("INVALID_PATH", "--path 不得包含相对路径段")
    return path


def parse_json_argument(raw: str | None, expected: type | tuple[type, ...], label: str) -> Any:
    if raw is None:
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise UsageError("INVALID_JSON", f"{label} 不是合法 JSON：{exc.msg}") from None
    if not isinstance(value, expected):
        names = expected.__name__ if isinstance(expected, type) else "/".join(t.__name__ for t in expected)
        raise UsageError("INVALID_JSON", f"{label} 必须是 {names}")
    return value


def normalize_query(query: dict) -> dict[str, str | list[str]]:
    normalized: dict[str, str | list[str]] = {}
    for key, value in query.items():
        if not isinstance(key, str):
            raise UsageError("INVALID_JSON", "--query 的键必须是字符串")
        if isinstance(value, list):
            items: list[str] = []
            for item in value:
                if isinstance(item, bool) or item is None or isinstance(item, (dict, list)):
                    raise UsageError("INVALID_JSON", f"--query[{key}] 仅支持字符串/数字或其数组")
                items.append(str(item))
            normalized[key] = items
        elif isinstance(value, bool):
            normalized[key] = "true" if value else "false"
        elif isinstance(value, (str, int, float)):
            normalized[key] = str(value)
        else:
            raise UsageError("INVALID_JSON", f"--query[{key}] 仅支持字符串/数字或其数组")
    return normalized


def build_request_url(path: str, query: dict | None) -> str:
    url = auth.API_BASE_URL + path
    if query:
        url = url + "?" + urlencode(query, doseq=True)
    return url


def apply_fields(data: Any, fields: list[str] | None) -> Any:
    if not fields:
        return data
    if isinstance(data, list):
        return [apply_fields(item, fields) for item in data]
    if isinstance(data, dict):
        return {key: data[key] for key in fields if key in data}
    return data


def emit_success(data: Any, metadata: dict, exit_code: int = EXIT_OK) -> int:
    payload = {"success": True, "data": data, "metadata": metadata}
    print(json.dumps(payload, ensure_ascii=False))
    return exit_code


def emit_error(
    code: str,
    message: str,
    metadata: dict | None = None,
    suggestion: str = "",
    exit_code: int = EXIT_ERROR,
) -> int:
    error: dict[str, str] = {"code": code, "message": message}
    if suggestion:
        error["suggestion"] = suggestion
    payload = {"success": False, "error": error, "metadata": metadata or {}}
    print(json.dumps(payload, ensure_ascii=False))
    return exit_code


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="滴答 Open API 通用执行器（单次请求，不重试）")
    parser.add_argument("--method", required=True, choices=ALLOWED_METHODS)
    parser.add_argument("--path", required=True, help=f"必须以 {PATH_PREFIX} 开头的相对路径")
    parser.add_argument("--query", help="查询参数 JSON 对象")
    parser.add_argument("--body", help="请求体 JSON 对象或数组")
    parser.add_argument("--fields", help="响应 data 的顶层字段裁剪，逗号分隔")
    parser.add_argument("--dry-run", action="store_true", help="只输出请求概要，不发送请求")
    return parser.parse_args(argv)


def build_metadata(method: str, path: str) -> dict:
    return {"command": "dida365_api", "method": method, "path": path}


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        path = validate_path(args.path)
        query = parse_json_argument(args.query, dict, "--query")
        body = parse_json_argument(args.body, (dict, list), "--body")
        fields = [item.strip() for item in (args.fields or "").split(",") if item.strip()] or None
        url = build_request_url(path, normalize_query(query) if query else None)
    except UsageError as exc:
        return emit_error(exc.code, exc.message, build_metadata(args.method, args.path), exc.suggestion, EXIT_USAGE)

    metadata = build_metadata(args.method, path)
    if args.dry_run:
        would_request = {"method": args.method, "url": url, "body": body}
        return emit_success({"would_request": would_request}, {**metadata, "dry_run": True}, EXIT_DRY_RUN)

    return run_request(args.method, url, body, fields, metadata)


def create_client() -> httpx.Client:
    return httpx.Client(timeout=TIMEOUT_SECONDS, follow_redirects=False)


def _redact(text: str, *secrets: str) -> str:
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[REDACTED]")
    return text


def _error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        for key in ("error", "errorMessage", "message", "error_description"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()[:300]
    text = response.text.strip()
    return text[:300] if text else "(无响应正文)"


def _decode_success_body(response: httpx.Response, fields: list[str] | None) -> Any:
    if response.status_code == 204 or not response.content:
        return {"status": "ok"}
    try:
        data = response.json()
    except ValueError:
        text = response.text
        wrapped = {
            "text": text[:2000],
            "truncated": len(text) > 2000,
            "content_type": response.headers.get("content-type", ""),
        }
        return wrapped
    return apply_fields(data, fields)


def run_request(method: str, url: str, body: Any, fields: list[str] | None, metadata: dict) -> int:
    try:
        auth.validate_origin(url, auth.APPROVED_API_HOSTS)
        if not url.startswith(auth.API_BASE_URL + PATH_PREFIX):
            raise auth.AuthConfigError("INVALID_TARGET", "请求路径前缀不受支持")
        token = auth.resolve_config()
    except auth.AuthConfigError as exc:
        return emit_error(exc.code, exc.message, metadata, exc.suggestion, EXIT_USAGE)

    headers = auth.authorization_header(token)
    started = time.time()
    try:
        with create_client() as client:
            request = client.build_request(method, url, json=body, headers=headers)
            response = client.send(request, follow_redirects=False)
    except httpx.TimeoutException:
        return emit_error("TIMEOUT", "请求超时；本入口不自动重试", metadata, exit_code=EXIT_ERROR)
    except httpx.RequestError as exc:
        return emit_error(
            "NETWORK_ERROR",
            f"网络错误（{exc.__class__.__name__}）；本入口不自动重试",
            metadata,
            exit_code=EXIT_ERROR,
        )

    metadata = {
        **metadata,
        "http_status": response.status_code,
        "took_ms": int((time.time() - started) * 1000),
    }
    status = response.status_code
    detail = _redact(_error_detail(response), token)

    if 300 <= status < 400:
        return emit_error("REDIRECT_BLOCKED", f"服务端返回重定向（{status}），本入口不跟随重定向", metadata, exit_code=EXIT_ERROR)
    if status == 401:
        return emit_error("UNAUTHORIZED", f"凭据无效或已过期：{detail}", metadata, exit_code=EXIT_AUTH)
    if status == 403:
        return emit_error("FORBIDDEN", f"权限不足：{detail}", metadata, exit_code=EXIT_AUTH)
    if status == 404:
        return emit_error("NOT_FOUND", f"资源不存在：{detail}", metadata, exit_code=EXIT_NOT_FOUND)
    if status == 429:
        return emit_error("RATE_LIMITED", f"触发限流，请稍后重试：{detail}", metadata, exit_code=EXIT_ERROR)
    if status >= 500:
        return emit_error("SERVER_ERROR", f"服务端错误（{status}）：{detail}", metadata, exit_code=EXIT_ERROR)
    if status >= 400:
        return emit_error("HTTP_ERROR", f"请求失败（{status}）：{detail}", metadata, exit_code=EXIT_ERROR)

    data = _decode_success_body(response, fields)
    if isinstance(data, list):
        metadata["result_count"] = len(data)
    return emit_success(data, metadata)


if __name__ == "__main__":
    sys.exit(main())
