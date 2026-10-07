from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from core.files import detect_source_type
from service import AnalysisService, RunResult

# =========================
# 1. 测试集
# =========================
TEST_CASES: List[Dict[str, Any]] = [
    {
        "case_id": 1,
        "question": "最近三个月各地区销售额对比，请给我图表和结论。",
        "data_file": "sales_60k_demo.csv",
        "expected_tool": "dask",
        "expect_chart": True,
    },
    {
        "case_id": 2,
        "question": "退款率最高的地区是哪个？请排序展示并给我结论。",
        "data_file": "sales_60k_demo.csv",
        "expected_tool": "dask",
        "expect_chart": True,
    },
    {
        "case_id": 3,
        "question": "各渠道销售额排名，给我柱状图和总结。",
        "data_file": "sales_60k_demo.csv",
        "expected_tool": "dask",
        "expect_chart": True,
    },
    {
        "case_id": 4,
        "question": "各品类毛利额对比，找出毛利最高的品类。",
        "data_file": "sales_60k_demo.csv",
        "expected_tool": "dask",
        "expect_chart": True,
    },
    {
        "case_id": 5,
        "question": "最近三个月每个月的销售额趋势图。",
        "data_file": "sales_60k_demo.csv",
        "expected_tool": "dask",
        "expect_chart": True,
    },
]


# =========================
# 2. 工具函数
# =========================
def resolve_data_file(filename: str) -> str:
    """优先在当前目录找，再在 data/ 下找。"""
    candidates = [
        Path(filename),
        Path.cwd() / filename,
        Path.cwd() / "data" / filename,
    ]
    for path in candidates:
        if path.exists():
            return str(path)
    raise FileNotFoundError(f"Cannot find data file: {filename}")


def run_turn(
    service: AnalysisService,
    file_path: str,
    source_type: str,
    question: str,
    followup: bool = False,
    memory: Optional[dict] = None,
    max_resumes: int = 3,
) -> RunResult:
    """评估环境自动批准审批中断，跑到没有待审批为止。"""
    result = service.start_analysis(
        file_path, source_type, question, followup=followup, memory=memory
    )
    for _ in range(max_resumes):
        if result.pending is None:
            break
        result = service.resume(result.thread_id, approved=True)
    return result


def summarize_result(case: Dict[str, Any], result: RunResult) -> Dict[str, Any]:
    error = result.error or ""
    final_report = str(result.report or "")

    return {
        "case_id": case["case_id"],
        "question": case["question"],
        "data_file": case["data_file"],
        "expected_tool": case.get("expected_tool", ""),
        "actual_tool": result.tool,
        "tool_match": result.tool == case.get("expected_tool", ""),
        "expect_chart": bool(case.get("expect_chart", False)),
        "chart_ready": result.chart_ready,
        "chart_match": result.chart_ready == bool(case.get("expect_chart", False)),
        "success": result.status == "completed" and error == "",
        "has_error": bool(error) or result.status != "completed",
        "error": error or result.status,
        "result_row_count": len(result.rows),
        "has_report": bool(final_report.strip()),
        "has_insights": len(result.insights) > 0,
        "report_preview": final_report[:120],
        "insights_count": len(result.insights),
        "trace_steps": len(result.trace),
    }


def _failure_record(case: Dict[str, Any], error: str) -> Dict[str, Any]:
    return {
        "case_id": case["case_id"],
        "question": case.get("question", ""),
        "data_file": case.get("data_file", ""),
        "expected_tool": case.get("expected_tool", ""),
        "actual_tool": "",
        "tool_match": False,
        "expect_chart": bool(case.get("expect_chart", False)),
        "chart_ready": False,
        "chart_match": False,
        "success": False,
        "has_error": True,
        "error": error,
        "result_row_count": 0,
        "has_report": False,
        "has_insights": False,
        "report_preview": "",
        "insights_count": 0,
        "trace_steps": 0,
    }


# =========================
# 3. 单轮评估
# =========================
def run_single_turn_eval(service: AnalysisService, cases: List[Dict[str, Any]]) -> pd.DataFrame:
    records: List[Dict[str, Any]] = []

    for case in cases:
        try:
            file_path = resolve_data_file(case["data_file"])
            result = run_turn(
                service,
                file_path,
                detect_source_type(file_path),
                case["question"],
            )
            records.append(summarize_result(case, result))
        except Exception as e:
            records.append(_failure_record(case, str(e)))

    return pd.DataFrame(records)


# =========================
# 4. 多轮评估
# =========================
MULTI_TURN_CASES = [
    {
        "case_id": "M1",
        "data_file": "sales_60k_demo.csv",
        "turns": [
            "退款率最高的地区",
            "看看这个地区的销售额",
            "再看这个地区的渠道分布并绘制饼状图",
        ],
    }
]


def run_multi_turn_eval(service: AnalysisService, cases: List[Dict[str, Any]]) -> pd.DataFrame:
    records: List[Dict[str, Any]] = []

    for case in cases:
        try:
            file_path = resolve_data_file(case["data_file"])
            source_type = detect_source_type(file_path)

            result: Optional[RunResult] = None

            for idx, turn in enumerate(case["turns"], start=1):
                result = run_turn(
                    service,
                    file_path,
                    source_type,
                    turn,
                    followup=idx > 1,
                    memory=result.memory if result else None,
                )

                records.append(
                    {
                        "case_id": case["case_id"],
                        "turn_index": idx,
                        "turn_question": turn,
                        "actual_tool": result.tool,
                        "has_error": bool(result.error) or result.status != "completed",
                        "error": result.error or result.status,
                        "chart_ready": result.chart_ready,
                        "has_report": bool(str(result.report or "").strip()),
                        "memory_focus_entities": str(result.memory.get("focus_entities", {})),
                        "memory_last_result": str(result.memory.get("last_result", {})),
                        "trace_steps": len(result.trace),
                    }
                )
        except Exception as e:
            records.append(
                {
                    "case_id": case["case_id"],
                    "turn_index": -1,
                    "turn_question": "EXCEPTION",
                    "actual_tool": "",
                    "has_error": True,
                    "error": str(e),
                    "chart_ready": False,
                    "has_report": False,
                    "memory_focus_entities": "",
                    "memory_last_result": "",
                    "trace_steps": 0,
                }
            )

    return pd.DataFrame(records)


# =========================
# 5. 主程序
# =========================
def main():
    service = AnalysisService()

    single_df = run_single_turn_eval(service, TEST_CASES)
    multi_df = run_multi_turn_eval(service, MULTI_TURN_CASES)

    single_out = "eval_single_turn_results.csv"
    multi_out = "eval_multi_turn_results.csv"

    single_df.to_csv(single_out, index=False, encoding="utf-8-sig")
    multi_df.to_csv(multi_out, index=False, encoding="utf-8-sig")

    print("=" * 60)
    print("单轮评估完成")
    print(single_df[[
        "case_id", "expected_tool", "actual_tool", "tool_match",
        "success", "chart_ready", "has_report", "error"
    ]])
    print("=" * 60)
    print("多轮评估完成")
    print(multi_df[[
        "case_id", "turn_index", "turn_question", "actual_tool",
        "has_error", "chart_ready", "has_report", "memory_focus_entities"
    ]])
    print("=" * 60)
    print(f"已导出: {single_out}")
    print(f"已导出: {multi_out}")


if __name__ == "__main__":
    main()
