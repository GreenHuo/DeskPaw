"""Bounded Excel operations exposed to the pet's MCP tool server."""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any


def _openpyxl():
    try:
        import openpyxl
    except ImportError as exc:
        raise RuntimeError("缺少 Excel 支持，请安装 requirements.txt 中的 openpyxl") from exc
    return openpyxl


def check_workbook(path: Path) -> Path:
    path = path.expanduser().resolve()
    if path.suffix.lower() != ".xlsx":
        raise ValueError("目前只支持 .xlsx 文件")
    if not path.is_file():
        raise ValueError("找不到已选择的 Excel 文件")
    if path.stat().st_size > 25 * 1024 * 1024:
        raise ValueError("目前只支持不超过 25 MB 的 Excel 文件")
    return path


def output_path_for(path: Path) -> Path:
    path = check_workbook(path)
    candidate = path.with_name(f"{path.stem}-DeskPaw汇总.xlsx")
    number = 2
    while candidate.exists():
        candidate = path.with_name(f"{path.stem}-DeskPaw汇总-{number}.xlsx")
        number += 1
    return candidate


def _cell(value: Any) -> str | int | float | None:
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)):
        return str(value)[:200] if isinstance(value, str) else value
    return str(value)[:200]


def _sheet(book: Any, name: str) -> Any:
    if name not in book.sheetnames:
        raise ValueError(f"找不到工作表：{name}")
    return book[name]


def _headers(sheet: Any) -> list[str]:
    row = next(sheet.iter_rows(min_row=1, max_row=1, values_only=True), ())
    headers = [str(value).strip() if value is not None else "" for value in row]
    if not any(headers):
        raise ValueError("第一行没有列名")
    if len([value for value in headers if value]) != len(set(value for value in headers if value)):
        raise ValueError("第一行有重复列名，请先整理表头")
    return headers


def inspect_workbook(path: Path) -> dict[str, Any]:
    book = _openpyxl().load_workbook(check_workbook(path), read_only=True, data_only=True)
    try:
        return {
            "file": path.name,
            "sheets": [
                {
                    "name": sheet.title,
                    "rows": sheet.max_row,
                    "columns": sheet.max_column,
                    "headers": _headers(sheet)[:40] if sheet.max_row else [],
                }
                for sheet in book.worksheets
            ],
        }
    finally:
        book.close()


def preview_sheet(path: Path, sheet_name: str, limit: int = 8) -> dict[str, Any]:
    if not isinstance(limit, int) or not 1 <= limit <= 20:
        raise ValueError("预览行数必须在 1 到 20 之间")
    book = _openpyxl().load_workbook(check_workbook(path), read_only=True, data_only=True)
    try:
        sheet = _sheet(book, sheet_name)
        headers = _headers(sheet)
        if len(headers) > 40:
            raise ValueError("目前只支持不超过 40 列的工作表")
        rows = []
        for row in sheet.iter_rows(min_row=2, max_row=limit + 1, values_only=True):
            rows.append([_cell(value) for value in row[: len(headers)]])
        return {
            "sheet": sheet_name,
            "headers": headers,
            "rows": rows,
            "note": "公式单元格显示文件中保存的计算结果；没有缓存的公式可能显示为空。",
        }
    finally:
        book.close()


def _aggregate(
    path: Path, sheet_name: str, group_by: str, operation: str, value_column: str = ""
) -> tuple[list[tuple[str, int | float]], int]:
    source = check_workbook(path)
    if operation not in {"count", "sum", "average"}:
        raise ValueError("汇总方式只能是 count、sum 或 average")
    book = _openpyxl().load_workbook(source, read_only=True, data_only=True)
    try:
        sheet = _sheet(book, sheet_name)
        headers = _headers(sheet)
        if len(headers) > 40:
            raise ValueError("目前只支持不超过 40 列的工作表")
        if group_by not in headers or not group_by:
            raise ValueError(f"找不到分组列：{group_by}")
        if operation != "count" and (value_column not in headers or not value_column):
            raise ValueError(f"找不到数值列：{value_column}")
        group_index = headers.index(group_by)
        value_index = headers.index(value_column) if operation != "count" else -1
        totals: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
        skipped = 0
        for row_number, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
            if row_number > 100_001:
                raise ValueError("目前只支持十万条数据行")
            if not any(value is not None for value in row):
                continue
            group = (
                str(row[group_index])
                if group_index < len(row) and row[group_index] is not None
                else "(空白)"
            )
            if operation == "count":
                totals[group][0] += 1
                continue
            value = row[value_index] if value_index < len(row) else None
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
            ):
                skipped += 1
                continue
            totals[group][0] += float(value)
            totals[group][1] += 1
        if not totals:
            raise ValueError("没有可汇总的数据")
    finally:
        book.close()

    rows = []
    for group, (total, count) in sorted(totals.items()):
        result = total / count if operation == "average" and count else total
        rows.append((group, int(result) if result.is_integer() else result))
    return rows, skipped


def aggregate_sheet(
    path: Path, sheet_name: str, group_by: str, operation: str, value_column: str = ""
) -> dict[str, Any]:
    rows, skipped = _aggregate(path, sheet_name, group_by, operation, value_column)
    return {
        "sheet": sheet_name,
        "group_by": group_by,
        "operation": operation,
        "value_column": value_column,
        "groups": len(rows),
        "rows": rows[:100],
        "truncated": len(rows) > 100,
        "skipped_non_numeric": skipped,
    }


def create_summary(
    path: Path,
    output_path: Path,
    sheet_name: str,
    group_by: str,
    operation: str,
    value_column: str = "",
) -> dict[str, Any]:
    source = check_workbook(path)
    target = output_path.expanduser().resolve()
    if (
        target == source
        or target.exists()
        or target.parent != source.parent
        or target.suffix.lower() != ".xlsx"
    ):
        raise ValueError("输出文件位置无效，或文件已存在")
    rows, skipped = _aggregate(source, sheet_name, group_by, operation, value_column)

    output_book = _openpyxl().Workbook()
    output_sheet = output_book.active
    output_sheet.title = "汇总"
    metric = (
        "行数"
        if operation == "count"
        else f"{value_column}的{'合计' if operation == 'sum' else '平均值'}"
    )
    output_sheet.append([group_by, metric])
    output_sheet["A1"].data_type = "s"
    output_sheet["B1"].data_type = "s"
    for group, result in rows:
        output_sheet.append([group, result])
        output_sheet.cell(output_sheet.max_row, 1).data_type = "s"
    output_sheet.freeze_panes = "A2"
    output_sheet.auto_filter.ref = output_sheet.dimensions
    output_sheet.column_dimensions["A"].width = 30
    output_sheet.column_dimensions["B"].width = 22
    output_book.save(target)
    return {
        "output_file": str(target),
        "groups": len(rows),
        "skipped_non_numeric": skipped,
        "source_file": source.name,
        "sheet": sheet_name,
        "operation": operation,
    }
