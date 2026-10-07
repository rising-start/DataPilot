import json

from analysis.summarize import summarize_result
from core.sanitize import make_json_safe
from executors.base import BaseExecutor, _input
from llm.client import invoke_text
from loaders.sqlite_loader import get_sqlite_connection
from safety.sandbox import normalize_result
from safety.sql_guard import clean_sql, is_safe_sql, run_sql


class SQLExecutor(BaseExecutor):
    name = "sql"

    def supports(self, state: dict) -> bool:
        return _input(state).get("data_source_type") == "sqlite"

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

        return {"code": sql, "kind": self.artifact_kind or "sql", "error": ""}

    def needs_approval(self, state: dict) -> bool:
        return True

    def get_approval_payload(self, state: dict) -> dict:
        artifact = state.get("artifact", {}) or {}
        sql = artifact.get("code", "")
        return {
            "type": "sql_approval",
            "kind": "sql",
            "title": "SQL 执行审批",
            "sql": sql,
            "content": sql,
            "message": "Approve this SQL before execution?",
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
            "kind": self.artifact_kind or "sql",
            "error": "",
            "retry_count": (state.get("execution", {}) or {}).get("retry_count", 0) + 1,
        }

    def execute(self, state: dict) -> dict:
        if not (state.get("artifact", {}) or {}).get("approved", False):
            # 用户拒绝执行是终止信号，不是可修复的错误
            return {"error": "SQL execution not approved.", "terminal": True}

        conn = get_sqlite_connection(_input(state)["file_path"])
        try:
            result_df = run_sql(conn, (state.get("artifact", {}) or {}).get("code", ""))
        finally:
            conn.close()

        result_df = normalize_result(result_df)

        return make_json_safe({
            "rows": result_df.to_dict(orient="records"),
            "summary": summarize_result(result_df),
            "error": "",
            "terminal": False,
        })
