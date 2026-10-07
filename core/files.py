"""数据源文件相关的公共工具。"""

from __future__ import annotations

import os
import tempfile

CSV_SUFFIXES = (".csv",)
EXCEL_SUFFIXES = (".xlsx", ".xls")
SQLITE_SUFFIXES = (".sqlite", ".db")


def detect_source_type(filename: str) -> str:
    lower = str(filename).lower()
    if lower.endswith(CSV_SUFFIXES):
        return "csv"
    if lower.endswith(EXCEL_SUFFIXES):
        return "excel"
    if lower.endswith(SQLITE_SUFFIXES):
        return "sqlite"
    raise ValueError(f"Unsupported file type: {filename}")


def save_upload_to_temp(filename: str, data: bytes) -> str:
    """把上传内容写入临时文件，返回临时路径（调用方负责清理）。"""
    suffix = os.path.splitext(filename)[1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(data)
        return tmp.name


def delete_temp_file(path: str | None) -> None:
    """删除临时文件，失败时静默（文件可能已被占用或已删除）。"""
    if not path:
        return
    try:
        os.unlink(path)
    except OSError:
        pass
