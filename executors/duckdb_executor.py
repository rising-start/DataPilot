import json
import os

from agent.cancellation import run_blocking_with_cancel
from analysis.summarize import summarize_result
from core.sanitize import make_json_safe
from executors.base import BaseExecutor, _input
from llm.client import invoke_text
from safety.sandbox import normalize_result
from safety.sql_guard import clean_sql, is_safe_sql


def _disable_duckdb_external_access(con) -> None:
    """纵深防御：禁用 DuckDB 引擎级外部文件访问，使用户 SQL 只能查询已载入的 data 表。

    不同 DuckDB 版本语法略有差异，依次尝试；全部失败则静默忽略
    （is_safe_sql 对 read_* 表函数的拦截仍提供第一层防护）。
    """
    for stmt in ("SET enable_external_access=false", "PRAGMA disable_external_access"):
        try:
            con.execute(stmt)
            return
        except Exception:
            continue


# 资源与隔离上限，可由环境变量覆盖（纵深防御：防 OOM / CPU 耗尽 / 长查询挂死）
DUCKDB_MEMORY_LIMIT = os.environ.get("DUCKDB_MEMORY_LIMIT", "2GB")
DUCKDB_THREADS = int(os.environ.get("DUCKDB_THREADS", "4"))
DUCKDB_STATEMENT_TIMEOUT = os.environ.get("DUCKDB_STATEMENT_TIMEOUT", "30s")


def _apply_resource_limits(con) -> None:
    """建表前设置资源上限（内存/线程/语句超时），防止单条查询拖垮进程。

    各项独立 try/except：不同 DuckDB 版本语法略有差异，失败项静默忽略。
    """
    settings = [
        f"SET memory_limit='{DUCKDB_MEMORY_LIMIT}'",
        f"SET threads={DUCKDB_THREADS}",
        f"SET statement_timeout='{DUCKDB_STATEMENT_TIMEOUT}'",
    ]
    for stmt in settings:
        try:
            con.execute(stmt)
        except Exception:
            continue


class DuckDBExecutor(BaseExecutor):
    """SQL 类执行器：用 DuckDB 直接在 CSV 文件上跑只读 SQL（表名固定为 `data`）。

    与 SQLite 执行器同构：生成 SQL 经 `sql_guard` 校验，执行在父进程内完成
    （不经子进程沙箱），隔离等级与 SQL 执行器一致。
    """

    name = "duckdb"

    def supports(self, state: dict) -> bool:
        # DuckDB 核心支持 CSV（read_csv_auto）；Excel 需额外扩展，仍走 pandas
        return _input(state).get("data_source_type") == "csv"

    def _payload(self, state: dict) -> dict:
        return {
            "question": _input(state).get("user_question", ""),
            "schema_info": (state.get("dataset", {}) or {}).get("schema_info", {}),
            "analysis_plan": (state.get("plan", {}) or {}).get("analysis_plan", {}),
        }

    def generate(self, state: dict) -> dict:
        sql = invoke_text(self.generator_prompt, json.dumps(self._payload(state), ensure_ascii=False))
        sql = clean_sql(sql)

        ok, reason = is_safe_sql(sql)
        if not ok:
            return {"error": f"Unsafe SQL: {reason}", "terminal": True}

        return {"code": sql, "kind": self.artifact_kind or "duckdb", "error": ""}

    def needs_approval(self, state: dict) -> bool:
        # 执行任意 SQL 需人工审批
        return True

    def get_approval_payload(self, state: dict) -> dict:
        artifact = state.get("artifact", {}) or {}
        sql = artifact.get("code", "")
        return {
            "type": "sql_approval",
            "kind": "sql",
            "title": "DuckDB SQL 执行审批",
            "sql": sql,
            "content": sql,
            "message": "Approve this DuckDB SQL before execution?",
        }

    def repair(self, state: dict) -> dict:
        payload = self._payload(state)
        artifact = state.get("artifact", {}) or {}
        payload["bad_sql"] = artifact.get("code", "")
        payload["error"] = (state.get("run", {}) or {}).get("error", "")

        sql = invoke_text(self.repair_prompt, json.dumps(payload, ensure_ascii=False))
        sql = clean_sql(sql)

        ok, reason = is_safe_sql(sql)
        if not ok:
            return {"error": f"Unsafe repaired SQL: {reason}", "terminal": True}

        return {
            "code": sql,
            "kind": self.artifact_kind or "duckdb",
            "error": "",
            "retry_count": (state.get("execution", {}) or {}).get("retry_count", 0) + 1,
        }

    def execute(self, state: dict) -> dict:
        artifact = state.get("artifact", {}) or {}
        if not artifact.get("approved", False):
            # 用户拒绝执行是终止信号，不是可修复的错误
            return {"error": "SQL execution not approved.", "terminal": True}

        sql = clean_sql(artifact.get("code", ""))
        ok, reason = is_safe_sql(sql)
        if not ok:
            return {"error": f"Unsafe SQL: {reason}", "terminal": True}

        source_type = _input(state).get("data_source_type")
        file_path = _input(state).get("file_path")
        if source_type != "csv" or not file_path:
            return {"error": f"DuckDB executor only supports csv, got {source_type}", "terminal": True}

        # 路径转义后拼入：反斜杠改正斜杠（避免 SQL 字符串转义），单引号转义（防注入）。
        # 文件已落盘、路径由系统生成，不在 LLM 控制范围内。
        safe_path = file_path.replace("\\", "/").replace("'", "''")

        def _run() -> "pd.DataFrame":
            # 连接在此线程内创建并使用：DuckDB 连接非线程安全，必须和查询在同一线程。
            # 取消时 worker 立即返回 cancelled 并停止等待该守护线程，守护线程跑完当前查询后
            # 由 finally 自行关闭连接并退出（DB 驱动不支持中断的固有限制）。
            import duckdb

            con = duckdb.connect()
            try:
                # 先设资源上限（内存/线程/超时），再读文件，避免单条查询拖垮进程
                _apply_resource_limits(con)
                # 物化为内存表（而非视图），以便随后可安全禁用外部访问：
                # 否则查询视图会再次触发底层 read_csv_auto，被禁用策略阻断。
                con.execute(f"CREATE TABLE data AS SELECT * FROM read_csv_auto('{safe_path}')")
                # 纵深防御：锁死引擎级外部文件访问，用户 SQL 只能读已载入的 data 表，
                # 即便 is_safe_sql 漏网（如 SELECT * FROM 'other.csv' 隐式读文件）也会被引擎拒绝。
                _disable_duckdb_external_access(con)
                return con.execute(sql).df()
            finally:
                con.close()

        # 包一层取消：长查询可被取消信号中断。取消时 run_blocking_with_cancel 会
        # 抛 CancellationError（BaseException），交由 execute_artifact_node 上浮到
        # worker 置为 cancelled；不要在此 catch 成普通错误，否则会落入修复循环。
        result_df = run_blocking_with_cancel(_run)

        result_df = normalize_result(result_df)

        return make_json_safe({
            "rows": result_df.to_dict(orient="records"),
            "summary": summarize_result(result_df),
            "error": "",
            "terminal": False,
        })
