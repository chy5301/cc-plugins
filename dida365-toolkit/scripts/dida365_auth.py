#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""共享的认证与目标校验：供 API 执行器与 MCP 凭据辅助入口使用。仅标准库。"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping
from urllib.parse import urlsplit

API_BASE_URL = "https://api.dida365.com"
MCP_SERVER_URL = "https://mcp.dida365.com"
APPROVED_API_HOSTS = frozenset({"api.dida365.com"})
APPROVED_MCP_HOSTS = frozenset({"mcp.dida365.com"})
APPROVED_DOMAINS = frozenset({"api.dida365.com"})
TOKEN_ENV = "DIDA365_API_TOKEN"
DOMAIN_ENV = "DIDA365_API_DOMAIN"
TOKEN_FILE_ENV = "DIDA365_TOKEN_FILE"
DEFAULT_TOKEN_FILE = Path.home() / ".dida365" / "token"


class AuthConfigError(Exception):
    """配置或目标校验失败。message 与 suggestion 中不得包含 Token。"""

    def __init__(self, code: str, message: str, suggestion: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.suggestion = suggestion

    def __str__(self) -> str:
        return self.message


def _env(env: Mapping[str, str] | None) -> Mapping[str, str]:
    return os.environ if env is None else env


def token_file_path(env: Mapping[str, str] | None = None) -> Path:
    override = (_env(env).get(TOKEN_FILE_ENV) or "").strip()
    if override:
        return Path(override).expanduser()
    return DEFAULT_TOKEN_FILE


def _read_file(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, ValueError):
        return None
    token = text.strip()
    return token or None


def read_token_file(env: Mapping[str, str] | None = None) -> str | None:
    return _read_file(token_file_path(env))


def read_default_token_file() -> str | None:
    """读取默认凭据文件，忽略 `DIDA365_TOKEN_FILE` 覆盖，供 MCP 相关自检使用。

    插件级 helper 环境中名称含 TOKEN 的环境变量（含覆盖变量本身）同样会被移除，
    覆盖只对本地/API 执行有效；MCP 固定读取默认路径，故自检需单独暴露默认文件是否有凭据。
    """
    return _read_file(DEFAULT_TOKEN_FILE)


def token_source(env: Mapping[str, str] | None = None) -> str | None:
    if (_env(env).get(TOKEN_ENV) or "").strip():
        return "env"
    if read_token_file(env) is not None:
        return "file"
    return None


def resolve_token(env: Mapping[str, str] | None = None) -> str:
    token = (_env(env).get(TOKEN_ENV) or "").strip()
    if token:
        return token
    file_token = read_token_file(env)
    if file_token:
        return file_token
    raise AuthConfigError(
        "TOKEN_MISSING",
        f"未设置 {TOKEN_ENV}，且凭据文件不存在：{token_file_path(env)}",
        f"按 setup-guide 将个人 API Token 写入凭据文件（默认 ~/.dida365/token），或设置 {TOKEN_ENV} 环境变量",
    )


def check_domain_config(env: Mapping[str, str] | None = None) -> None:
    domain = (_env(env).get(DOMAIN_ENV) or "").strip().lower()
    if domain and domain not in APPROVED_DOMAINS:
        raise AuthConfigError(
            "REGION_UNSUPPORTED",
            f"本版本仅支持国内滴答服务，当前 {DOMAIN_ENV}={domain} 不受支持",
            f"移除 {DOMAIN_ENV} 或改为 api.dida365.com；国际 TickTick 暂不支持",
        )


def resolve_config(env: Mapping[str, str] | None = None) -> str:
    check_domain_config(env)
    return resolve_token(env)


def validate_origin(url: str, approved_hosts: frozenset[str]) -> None:
    try:
        parts = urlsplit(url)
    except ValueError as exc:
        raise AuthConfigError("INVALID_TARGET", f"目标地址无法解析：{exc}") from None
    if parts.scheme != "https":
        raise AuthConfigError("INVALID_TARGET", "目标地址必须使用 https")
    if parts.username or parts.password:
        raise AuthConfigError("INVALID_TARGET", "目标地址不得包含用户信息")
    host = (parts.hostname or "").lower()
    if host not in approved_hosts:
        raise AuthConfigError("INVALID_TARGET", f"目标主机不在批准列表：{host or '(空)'}")
    try:
        port = parts.port
    except ValueError as exc:
        raise AuthConfigError("INVALID_TARGET", f"目标地址无法解析：{exc}") from None
    if port not in (None, 443):
        raise AuthConfigError("INVALID_TARGET", "目标端口不受支持")


def authorization_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
