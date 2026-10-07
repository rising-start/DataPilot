import json
from abc import ABC, abstractmethod
from typing import Any, Dict

from analysis.summarize import summarize_result
from core.config import CODE_APPROVAL_ENABLED, CODE_EXEC_TIMEOUT
from core.sanitize import make_json_safe
from core.schema import build_schema_summary_for_llm
from llm.client import invoke_text
from safety.sandbox import (
    SandboxExecError,
    SandboxValidationError,
    clean_code,
    run_generated_code_subprocess,
)


def _input(state: dict) -> dict:
    return state.get("input", {}) or {}


class BaseExecutor(ABC):
    name: str = "base"

    def __init__(self, generator_prompt: str = "", repair_prompt: str = "", artifact_kind: str = ""):
        # prompt 由外部注入，避免执行器反向依赖 agent.prompts
        self.generator_prompt = generator_prompt
        self.repair_prompt = repair_prompt
        self.artifact_kind = artifact_kind

    @abstractmethod
    def supports(self, state: dict) -> bool:
        raise NotImplementedError

    @abstractmethod
    def generate(self, state: dict) -> Dict[str, Any]:
        """返回 {"code": str, "error": str}（可选 terminal）。"""
        raise NotImplementedError

    def needs_approval(self, state: dict) -> bool:
        return CODE_APPROVAL_ENABLED

    def get_approval_payload(self, state: dict) -> Dict[str, Any]:
        artifact = state.get("artifact", {}) or {}
        content = artifact.get("code", "") or ""
        return {
            "type": f"{self.name}_approval",
            "kind": self.name,
            "title": f"{self.name} 执行审批",
            "content": content,
            "message": f"Approve this {self.name} artifact before execution?",
        }

    def repair(self, state: dict) -> Dict[str, Any]:
        return {"error": f"{self.name} executor does not support repair.", "terminal": True}

    @abstractmethod
    def execute(self, state: dict) -> Dict[str, Any]:
        """返回 {"rows": list, "summary": dict, "error": str, "terminal": bool}。"""
        raise NotImplementedError


class CodeExecutor(BaseExecutor):
    """生成并执行 Python 代码的执行器模板（pandas / dask 共用）。"""

    @abstractmethod
    def load_frame(self, state: dict):
        raise NotImplementedError

    def extra_runtime_vars(self) -> Dict[str, Any]:
        return {}

    def supports(self, state: dict) -> bool:
        return _input(state).get("data_source_type") in {"csv", "excel"}

    def build_payload(self, state: dict) -> Dict[str, Any]:
        return {
            "question": _input(state).get("user_question", ""),
            "schema_info": build_schema_summary_for_llm(state),
            "analysis_plan": (state.get("plan", {}) or {}).get("analysis_plan", {}),
        }

    def generate(self, state: dict) -> Dict[str, Any]:
        code = invoke_text(
            self.generator_prompt,
            json.dumps(self.build_payload(state), ensure_ascii=False),
        )
        return {"code": clean_code(code), "kind": self.artifact_kind, "error": ""}

    def repair(self, state: dict) -> Dict[str, Any]:
        payload = self.build_payload(state)
        artifact = state.get("artifact", {}) or {}
        payload["bad_code"] = artifact.get("code", "")
        payload["error"] = (state.get("run", {}) or {}).get("error", "")

        code = invoke_text(self.repair_prompt, json.dumps(payload, ensure_ascii=False))

        return {
            "code": clean_code(code),
            "kind": self.artifact_kind,
            "error": "",
            "retry_count": (state.get("execution", {}) or {}).get("retry_count", 0) + 1,
        }

    def execute(self, state: dict) -> Dict[str, Any]:
        artifact = state.get("artifact", {}) or {}
        # 需要审批但被拒绝 = 终止性错误，不能继续 exec（与 SQL 执行器行为一致）
        if artifact.get("approval_required", False) and not artifact.get("approved", False):
            return {"error": "Code execution not approved.", "terminal": True}

        try:
            result_df = run_generated_code_subprocess(
                code=(state.get("artifact", {}) or {}).get("code", ""),
                file_path=_input(state)["file_path"],
                source_type=_input(state)["data_source_type"],
                executor_name=self.name,
                timeout=CODE_EXEC_TIMEOUT,
            )
        except SandboxValidationError as e:
            return {"error": str(e), "terminal": True}
        except SandboxExecError as e:
            return {"error": str(e), "terminal": False}

        return make_json_safe({
            "rows": result_df.to_dict(orient="records"),
            "summary": summarize_result(result_df),
            "error": "",
            "terminal": False,
        })
