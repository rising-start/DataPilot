# Ruff 规则扩展计划：启用 UP（pyupgrade）+ B（bugbear）

## 1. 背景与目标
当前 `ruff.toml` 仅启用 `E` / `F` / `I`（基础语法、未使用、import 排序），并忽略 `E501`。
目标：渐进开启 `UP`（PEP585/604 现代化注解）与 `B`（常见 bug 风险），消除已弃用的
`typing` 别名、统一注解风格，且不引入大范围人工重写风险。

## 2. 影响面（实测 `ruff 0.16.10`，`target-version=py311`）
开启 `--select UP,B` 共 **161** 处命中，**128** 可 `--fix` 自动修复：

| 规则 | 含义 | 数量 | 可自动修复 | 处理 |
|---|---|---:|---|---|
| UP006 | `typing.List/Dict/...` → 内置 `list/dict/...`（PEP585） | 106 | ✅ | autofix |
| UP035 | 弃用的 typing 导入（如 `from typing import List`） | 34 | ❌ | 手动 / 随 F401 消解 |
| UP045 | `Optional[X]` → `X \| None`（PEP604） | 17 | ✅ | autofix |
| UP015 | `open` 冗余模式（`'r'`/`'rt'`） | 2 | ✅ | autofix |
| UP037 | 冗余引号注解 | 1 | ✅ | autofix |
| B008 | 默认参数中的函数调用（FastAPI `Depends()` 误报） | 1 | ❌ | per-file ignore |

约 33 处需人工/配置处理（UP035 弃用导入 + B008）。

## 3. 执行步骤（分阶段、每步可独立回滚）

### 阶段 0：安全基线
当前工作区已提交（HEAD `4746776`），直接在其上改；每阶段后单独 commit。

### 阶段 1：配置开启 UP + B
`ruff.toml` 改为：
```toml
select = ["E", "F", "I", "UP", "B"]
ignore = ["E501"]
```
并为 FastAPI 默认参数误报加 per-file 忽略（B008 在本项目几乎都是 `Depends`/`Header`
默认参数，属误报，不应全局忽略以免掩盖 server 外真实问题）：
```toml
[lint.per-file-ignores]
"server/**" = ["B008"]
"tests/test_smoke_import.py" = ["F401"]
"tests/*" = ["E402"]
```

### 阶段 2：自动修复可修复项
```
ruff check --select UP006,UP045,UP015,UP037 --fix
```
≈126 处注解现代化（纯语法等价，零语义风险，py311 已支持）。

### 阶段 3：清理因阶段 2 产生的未使用导入
UP006 把 `List`→`list` 后，`from typing import List` 等会变未使用（F401）：
```
ruff check --select F401 --fix
```
（F401 已属当前启用规则，autofix 安全。**必须在阶段 2 之后执行**，避免误删仍在用的导入。）

### 阶段 4：手动处理 UP035 残留
- 运行 `ruff check --select UP035` 列出剩余弃用导入；
- 逐文件将确未再用的 `from typing import X`（X 为弃用别名）整行删除，或改为标准导入；
- 若某 name 仍被遗留用法引用（极少数未被 UP006 覆盖），先改为内置 `list`/`dict` 再删导入。

### 阶段 5：验证
- `ruff check .` 全绿（仅剩 `E501` 忽略项）；
- `python -m pytest tests -q` 仍 117 passed（确认语法改写未破坏运行时）。

## 4. 风险与缓解
- **风险低**：UP006/UP045/UP015/UP037 均为纯语法升级、等价改写；
- **F401 误删**：阶段 3 仅在阶段 2 之后执行；ruff 对动态引用的极少数情况会警告，逐文件核对；
- **回滚**：每阶段独立 commit，出问题 `git revert` 单阶段；
- **B008**：用 `server/**` per-file ignore 而非全局 ignore。

## 5. 明确不做
- 不动 `E501`（行长度）—— 避免大范围换行改写；
- 不引入 `SIM` / `C4` / `RUF` / `N` 等其他规则集（超出本次范围）；
- 不改变测试以外的运行时行为。

## 6. 预计改动规模
- 涉及文件：全仓多数 `.py`（后端 + tests + executors / agent / web 构建脚本等），
  以注解与 import 行改动为主；
- 自动修复 ≈126 行；手动 UP035 ≈34 处（多为删除多余 import 行）。

## 7. 建议提交切分
1. `chore: ruff 配置开启 UP/B 规则并忽略 server 下 B008` （阶段 1）
2. `style: 应用 UP 规则自动修复（PEP585/604 注解现代化）+ 清理 F401` （阶段 2+3）
3. `style: 手动消解 UP035 弃用导入` （阶段 4）
