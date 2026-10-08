# DataPilot

用自然语言分析数据文件的 Agent 系统。上传 CSV / Excel / SQLite，用中文提问，自动完成
**加载 → 规划 → 生成 SQL/Python → 人工审批 → 执行 → 出图 → 出结论**，并支持多轮追问。

- 前端：Vue 3 + TypeScript + Vite + Element Plus + ECharts（`web/`）
- 后端：FastAPI + LangGraph（`server/` + `agent/`）
- 执行引擎：pandas / SQL / dask / DuckDB（`executors/`），按数据源与规模自动选择

## 快速开始

### 本地运行

```bash
pip install -r requirements.txt
cp .env.example .env          # 编辑 .env，填入 KIMI_API_KEY
uvicorn server.main:app --reload --port 8000   # 终端 1

cd web && npm install && npm run dev           # 终端 2，http://localhost:5173
```

不启前端也可访问 `http://localhost:8000/docs` 调试接口。

### Docker

```bash
cp .env.example .env
docker compose up -d --build   # http://localhost:8000
docker compose down            # 停止
```

## 配置

复制 `.env.example` 为 `.env`，关键变量：

| 变量 | 说明 | 默认值 |
|---|---|---|
| `KIMI_API_KEY` | **必需**，模型服务密钥 | — |
| `KIMI_MODEL` | 模型名（平台会上下架，务必显式配置） | `kimi-k2-0905-preview` |
| `KIMI_BASE_URL` | 模型服务地址 | `https://api.moonshot.cn/v1` |
| `CODE_APPROVAL_ENABLED` | 代码/SQL 执行前是否需人工审批 | `true` |
| `DASK_ROW_THRESHOLD` | 超过此行数优先选 dask | `50000` |

其余可选项见 `.env.example`。

## 项目结构

```
server/    FastAPI 接口层（任务 / 文件 / SSE）
web/       Vue 3 前端（上传、提问、审批、出图）
agent/     LangGraph 流程编排
executors/ 执行引擎（pandas / sql / dask / duckdb）
loaders/   数据加载（csv / excel / sqlite）
analysis/  report / memory / summarize
viz/       chart_spec 生成
safety/    代码沙箱 / SQL 校验
llm/       LLM 客户端
core/      配置与通用工具
tests/     后端 pytest
```

## 开发

```bash
python -m pytest tests -q     # 后端测试（不联网）
cd web && npm run test         # 前端测试
cd web && npm run build        # 构建
```

## 设计文档

详细设计见 `docs/` 与 `.superpowers/`。
