"""A local, file-scoped MCP server for DeskPaw's Excel tools."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from deskpaw.integrations.excel.tools import (
    aggregate_sheet,
    create_summary,
    inspect_workbook,
    preview_sheet,
)
from deskpaw.platform.windows_stdio import configure_mcp_stdio

PROTOCOL_VERSION = "2025-06-18"
TOOLS = [
    {
        "name": "inspect_workbook",
        "description": "查看已选择 Excel 文件的工作表、行列数和表头。处理表格任务时先调用它。",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "preview_sheet",
        "description": "读取指定工作表的前几行，以判断数据类型与任务需要的列。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "sheet_name": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 20},
            },
            "required": ["sheet_name"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "aggregate_sheet",
        "description": "按一列分组，对整张工作表计数、求和或平均，只返回结果，不生成文件。最多返回前 100 个分组。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "sheet_name": {"type": "string"},
                "group_by": {"type": "string"},
                "operation": {"type": "string", "enum": ["count", "sum", "average"]},
                "value_column": {"type": "string", "description": "sum 和 average 时必填"},
            },
            "required": ["sheet_name", "group_by", "operation"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "create_summary",
        "description": "按一列分组，对数据计数、求和或平均，生成独立的 .xlsx 汇总文件。不会修改原文件。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "sheet_name": {"type": "string"},
                "group_by": {"type": "string"},
                "operation": {"type": "string", "enum": ["count", "sum", "average"]},
                "value_column": {"type": "string", "description": "sum 和 average 时必填"},
            },
            "required": ["sheet_name", "group_by", "operation"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": False},
    },
]


def _result(value: Any) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False, default=str)}],
        "isError": False,
    }


def _call(name: str, arguments: dict[str, Any], source: Path, output: Path) -> dict[str, Any]:
    schemas = {tool["name"]: tool["inputSchema"] for tool in TOOLS}
    if name not in schemas:
        raise ValueError(f"未知工具：{name}")
    schema = schemas[name]
    if not isinstance(arguments, dict) or set(arguments) - set(schema["properties"]):
        raise ValueError("工具参数包含未知字段")
    if set(schema.get("required", [])) - set(arguments):
        raise ValueError("工具参数缺少必填字段")
    if name == "inspect_workbook":
        return _result(inspect_workbook(source))
    if name == "preview_sheet":
        return _result(preview_sheet(source, arguments["sheet_name"], arguments.get("limit", 8)))
    if name == "aggregate_sheet":
        return _result(
            aggregate_sheet(
                source,
                arguments["sheet_name"],
                arguments["group_by"],
                arguments["operation"],
                arguments.get("value_column", ""),
            )
        )
    return _result(
        create_summary(
            source,
            output,
            arguments["sheet_name"],
            arguments["group_by"],
            arguments["operation"],
            arguments.get("value_column", ""),
        )
    )


def _handle(message: dict[str, Any], source: Path, output: Path) -> dict[str, Any] | None:
    if "id" not in message:
        return None
    method = message.get("method")
    params = message.get("params") or {}
    try:
        if method == "initialize":
            result = {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "DeskPaw Excel", "version": "0.1.0"},
            }
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            try:
                result = _call(params.get("name"), params.get("arguments", {}), source, output)
            except (OSError, RuntimeError, TypeError, ValueError) as exc:
                result = {"content": [{"type": "text", "text": str(exc)}], "isError": True}
        elif method == "ping":
            result = {}
        else:
            return {
                "jsonrpc": "2.0",
                "id": message["id"],
                "error": {"code": -32601, "message": "Method not found"},
            }
        return {"jsonrpc": "2.0", "id": message["id"], "result": result}
    except (AttributeError, TypeError, ValueError) as exc:
        return {
            "jsonrpc": "2.0",
            "id": message["id"],
            "error": {"code": -32602, "message": str(exc)},
        }


def main() -> int:
    configure_mcp_stdio()
    source = Path(os.environ.get("DESKPAW_WORKBOOK_PATH", ""))
    output = Path(os.environ.get("DESKPAW_OUTPUT_PATH", ""))
    for line in sys.stdin:
        try:
            message = json.loads(line)
            if not isinstance(message, dict):
                continue
            response = _handle(message, source, output)
            if response is not None:
                sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
                sys.stdout.flush()
        except (TypeError, ValueError) as exc:
            sys.stderr.write(f"Invalid MCP request: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
