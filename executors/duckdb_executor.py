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
    
    for stmt in ("SET enable_external_access=false", "PRAGMA disable_external_access"):
        try:
            con.execute(stmt)
            return
        except Exception:
            continue



DUCKDB_MEMORY_LIMIT = os.environ.get("DUCKDB_MEMORY_LIMIT", "2GB")
DUCKDB_THREADS = int(os.environ.get("DUCKDB_THREADS", "4"))
DUCKDB_STATEMENT_TIMEOUT = os.environ.get("DUCKDB_STATEMENT_TIMEOUT", "30s")


def _apply_resource_limits(con) -> None:
    
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
    

    name = "duckdb"

    def supports(self, state: dict) -> bool:
        
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
            
            return {"error": "SQL execution not approved.", "terminal": True}

        sql = clean_sql(artifact.get("code", ""))
        ok, reason = is_safe_sql(sql)
        if not ok:
            return {"error": f"Unsafe SQL: {reason}", "terminal": True}

        source_type = _input(state).get("data_source_type")
        file_path = _input(state).get("file_path")
        if source_type != "csv" or not file_path:
            return {"error": f"DuckDB executor only supports csv, got {source_type}", "terminal": True}

        
        
        safe_path = file_path.replace("\\", "/").replace("'", "''")

        def _run() -> "pd.DataFrame":
            
            
            
            import duckdb

            con = duckdb.connect()
            try:
                
                _apply_resource_limits(con)
                
                
                con.execute(f"CREATE TABLE data AS SELECT * FROM read_csv_auto('{safe_path}')")
                
                
                _disable_duckdb_external_access(con)
                return con.execute(sql).df()
            finally:
                con.close()

        
        
        
        result_df = run_blocking_with_cancel(_run)

        result_df = normalize_result(result_df)

        return make_json_safe({
            "rows": result_df.to_dict(orient="records"),
            "summary": summarize_result(result_df),
            "error": "",
            "terminal": False,
        })
