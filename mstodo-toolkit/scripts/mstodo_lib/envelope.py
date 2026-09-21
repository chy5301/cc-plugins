"""统一响应信封、退出码与字段掩码。

本模块是最底层，不得 import 任何其他 mstodo_lib 模块。
"""

from __future__ import annotations

import json
import sys
from typing import Any, NoReturn

# 结果类退出码（0-9）：命令真的调用了 API，这是调用的结局
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_NOT_FOUND = 3
EXIT_PERMISSION = 4
EXIT_PARTIAL = 5
EXIT_AUTH_PENDING = 6

# 模式类退出码（10+）：命令未真正调用 API，这是特殊模式的产物
EXIT_DRY_RUN = 10


def apply_fields(data: Any, fields: str | None) -> Any:
    """顶层字段掩码。list 逐项裁剪，dict 保留指定 key，未知字段静默丢弃。"""
    if not fields:
        return data
    keep = [k.strip() for k in fields.split(",") if k.strip()]
    if not keep:
        return data
    if isinstance(data, list):
        return [{k: v for k, v in item.items() if k in keep}
                if isinstance(item, dict) else item for item in data]
    if isinstance(data, dict):
        return {k: v for k, v in data.items() if k in keep}
    return data


def build_envelope(data: Any, *, command: str, took_ms: int | None = None,
                   dry_run: bool = False, extra: dict | None = None) -> dict:
    """构造成功信封。metadata 的 command 总是存在。"""
    metadata: dict[str, Any] = {"command": f"mstodo_cli {command}"}
    if took_ms is not None:
        metadata["took_ms"] = took_ms
    if isinstance(data, list):
        metadata["result_count"] = len(data)
    if dry_run:
        metadata["dry_run"] = True
    if extra:
        metadata.update(extra)
    return {"success": True, "data": data, "metadata": metadata}


def _emit(envelope: dict, exit_code: int) -> NoReturn:
    print(json.dumps(envelope, ensure_ascii=False, indent=2))
    sys.exit(exit_code)


def output(data: Any, *, command: str, took_ms: int | None = None,
           dry_run: bool = False, extra: dict | None = None,
           fields: str | None = None, exit_code: int = EXIT_OK) -> NoReturn:
    """输出成功信封并退出。字段掩码在此处生效。"""
    _emit(build_envelope(apply_fields(data, fields), command=command,
                         took_ms=took_ms, dry_run=dry_run, extra=extra), exit_code)


def fail(code: str, message: str, *, suggestion: str = "",
         exit_code: int = EXIT_ERROR, data: Any = None,
         extra: dict | None = None) -> NoReturn:
    """输出错误信封并退出。

    data 仅在 PARTIAL_FAILURE 这一种情况下非 None——这是全仓唯一一种
    success:false 仍携带 data 的信封（spec §6.5）。
    """
    error: dict[str, Any] = {"code": code, "message": message}
    if suggestion:
        error["suggestion"] = suggestion
    envelope: dict[str, Any] = {"success": False, "error": error}
    if data is not None:
        envelope["data"] = data
    if extra:
        envelope["metadata"] = dict(extra)
    _emit(envelope, exit_code)
