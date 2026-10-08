#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""共享的认证与目标校验：供 API 执行器与 MCP 凭据辅助入口使用。仅标准库。"""
from __future__ import annotations

import os
from typing import Mapping
from urllib.parse import urlsplit

API_BASE_URL = "https://api.dida365.com"
MCP_SERVER_URL = "https://mcp.dida365.com"
APPROVED_API_HOSTS = frozenset({"api.dida365.com"})
APPROVED_MCP_HOSTS = frozenset({"mcp.dida365.com"})
APPROVED_DOMAINS = frozenset({"api.dida365.com"})
TOKEN_ENV = "DIDA365_API_TOKEN"
DOMAIN_ENV = "DIDA365_API_DOMAIN"


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


def resolve_token(env: Mapping[str, str] | None = None) -> str:
    token = (_env(env).get(TOKEN_ENV) or "").strip()
    if not token:
        raise AuthConfigError(
            "TOKEN_MISSING",
            f"未设置 {TOKEN_ENV}",
            "按 setup-guide 创建个人 API Token 并配置环境变量后重试",
        )
    return token


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
    if parts.port not in (None, 443):
        raise AuthConfigError("INVALID_TARGET", "目标端口不受支持")


def authorization_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
