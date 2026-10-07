"""前后端类型契约测试：前端 TS 接口字段必须与后端 Pydantic 模型一致。

后端 `server/schemas.py` 的 Pydantic 模型是「单一真源」；前端 `web/src/types.ts`
的 `TaskView` / `Approval` 接口必须与其字段逐一对应。任一侧增删字段后，
必须同步另一侧并让本测试通过，否则视为契约被破坏（schema 漂移）。
"""
import re
from pathlib import Path

from server.schemas import Approval, TaskView

ROOT = Path(__file__).resolve().parents[1]
TYPES_TS = ROOT / "web" / "src" / "types.ts"


def _extract_interface_fields(text: str, name: str) -> set[str]:
    """从 TS 源码提取 `interface <name> { ... }` 的顶层字段名集合。"""
    m = re.search(rf"export\s+interface\s+{name}\s*\{{", text)
    if not m:
        raise AssertionError(f"interface {name} not found in types.ts")
    start = m.end() - 1  # 指向 '{'
    depth = 0
    end = start
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    body = text[start + 1 : end]
    fields: set[str] = set()
    for line in body.splitlines():
        line = line.strip()
        m2 = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*[:?]", line)
        if m2:
            fields.add(m2.group(1))
    return fields


def test_taskview_fields_match_backend():
    text = TYPES_TS.read_text(encoding="utf-8")
    fe = _extract_interface_fields(text, "TaskView")
    be = set(TaskView.model_fields.keys())
    assert fe == be, (
        f"TaskView 字段与后端不一致:\n  前端多出 {sorted(fe - be)}\n  后端多出 {sorted(be - fe)}"
    )


def test_approval_fields_match_backend():
    text = TYPES_TS.read_text(encoding="utf-8")
    fe = _extract_interface_fields(text, "Approval")
    be = set(Approval.model_fields.keys())
    assert fe == be, (
        f"Approval 字段与后端不一致:\n  前端多出 {sorted(fe - be)}\n  后端多出 {sorted(be - fe)}"
    )
