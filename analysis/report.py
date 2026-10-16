import json
import logging
from typing import Any

import pandas as pd

from core.columns import pick_dimension_column, pick_metric_column
from core.config import LLM_REPORT_ENABLED, LLM_REPORT_MAX_ROWS

logger = logging.getLogger(__name__)


def _fmt_value(v: Any) -> str:
    if isinstance(v, float):
        if abs(v) < 1:
            return f"{v:.4f}"
        return f"{v:.2f}"
    return str(v)


def _fmt_pct(v: float | None) -> str | None:
    if v is None:
        return None
    return f"{v * 100:.1f}%"


def _share(values: "pd.Series", idx: int, total: float) -> float | None:
    
    if total <= 0:
        return None
    v = float(values.iloc[idx])
    if pd.isna(v):
        return None
    return v / total


def build_report(
    user_question: str,
    analysis_plan: dict[str, Any],
    result_df: pd.DataFrame,
) -> tuple[list[str], str]:
    insights: list[str] = []

    if len(result_df) == 0:
        insights.append("查询结果为空，当前筛选条件下没有可用数据。")
        insights.append("建议优先检查时间范围、筛选条件或原始数据完整性。")
        insights.append("若问题依赖某个字段，请确认该字段在数据中真实存在。")
        report = (
            f"针对问题“{user_question}”，系统已完成分析，但当前结果为空。"
            f"这通常意味着筛选条件过严、时间范围不匹配，或原始数据存在缺失。"
            f"建议先放宽条件后重新分析。"
        )
        return insights, report

    dim_col = pick_dimension_column(result_df, analysis_plan)
    metric_col = pick_metric_column(result_df, analysis_plan)

    if dim_col and metric_col:
        sorted_df = result_df.sort_values(metric_col, ascending=False).reset_index(drop=True)
        metric_values = pd.to_numeric(sorted_df[metric_col], errors="coerce")
        total = float(metric_values.sum()) if not metric_values.empty else 0.0

        top1 = sorted_df.iloc[0]
        top1_dim = top1[dim_col]
        top1_metric = top1[metric_col]
        top1_share = _share(metric_values, 0, total)

        insights.append(
            f"结果共返回 {len(result_df)} 行、{len(result_df.columns)} 列，"
            f"覆盖 {len(sorted_df)} 个{dim_col}。"
        )

        top1_share_txt = _fmt_pct(top1_share)
        top1_desc = f"{top1_dim} 的 {metric_col} 最高，为 {_fmt_value(top1_metric)}"
        if top1_share_txt:
            top1_desc += f"，占总量的 {top1_share_txt}"
        insights.append(f"{dim_col}维度中，{top1_desc}。")

        report = (
            f"针对问题“{user_question}”，共统计 {len(sorted_df)} 个{dim_col}，"
            f"{metric_col} 合计 {_fmt_value(total)}。"
        )
        report += f"从结果看，{top1_desc}。"

        if len(sorted_df) >= 2:
            top2 = sorted_df.iloc[1]
            top2_share = _share(metric_values, 1, total)
            top2_share_txt = _fmt_pct(top2_share)

            bottom1 = sorted_df.iloc[-1]
            bottom1_dim = bottom1[dim_col]
            bottom1_metric = bottom1[metric_col]
            bottom1_share = _share(metric_values, len(sorted_df) - 1, total)
            bottom1_share_txt = _fmt_pct(bottom1_share)

            top2_desc = f"{metric_col} 为 {_fmt_value(top2[metric_col])}"
            if top2_share_txt:
                top2_desc += f"，占比 {top2_share_txt}"
            insights.append(f"排名第二的是 {top2[dim_col]}，{top2_desc}。")

            bottom1_desc = f"{metric_col} 为 {_fmt_value(bottom1_metric)}"
            if bottom1_share_txt:
                bottom1_desc += f"，占比仅 {bottom1_share_txt}"
            insights.append(f"相对较低的是 {bottom1_dim}，{bottom1_desc}。")

            report += (
                f"其次是 {top2[dim_col]}（{top2_desc}）；"
                f"最低的 {bottom1_dim}（{bottom1_desc}）。"
            )

            
            try:
                bottom_val = float(bottom1_metric)
                top_val = float(top1_metric)
                if pd.notna(bottom_val) and pd.notna(top_val) and bottom_val > 0 and top_val > 0:
                    multiple = top_val / bottom_val
                    insights.append(f"头尾差距约 {multiple:.1f} 倍。")
                    report += f"两者相差约 {multiple:.1f} 倍，"
            except (TypeError, ValueError):
                pass

            
            report += (
                f"建议优先巩固 {top1_dim} 的优势，"
                f"并重点排查 {bottom1_dim} 明显偏低的原因。"
            )
        else:
            insights.append("当前结果仅包含一个维度值，暂时无法做更多横向对比。")
            report += "当前结果仅包含一个维度值，建议扩大统计范围后再做横向对比。"

        return insights, report

    if metric_col:
        max_value = result_df[metric_col].max()
        min_value = result_df[metric_col].min()
        mean_value = result_df[metric_col].mean()
        median_value = result_df[metric_col].median()

        insights.append(f"{metric_col} 的最大值为 {_fmt_value(max_value)}。")
        insights.append(f"{metric_col} 的最小值为 {_fmt_value(min_value)}。")
        insights.append(f"{metric_col} 的平均水平约为 {_fmt_value(mean_value)}。")
        insights.append(f"{metric_col} 的中位数为 {_fmt_value(median_value)}。")

        report = (
            f"针对问题“{user_question}”，系统已完成分析。"
            f"当前结果中，{metric_col} 的最大值为 {_fmt_value(max_value)}，"
            f"最小值为 {_fmt_value(min_value)}，"
            f"平均值约为 {_fmt_value(mean_value)}，中位数为 {_fmt_value(median_value)}。"
            f"建议结合时间或业务场景进一步分析其波动原因。"
        )
        return insights, report

    insights.append("结果已生成，但当前缺少明确的数值指标列。")
    insights.append("建议结合结果表中的字段含义进一步人工解读。")
    insights.append("若需要自动结论，建议在分析计划中显式指定核心指标。")

    report = (
        f"针对问题“{user_question}”，系统已完成分析，"
        f"但当前结果更适合人工进一步解读。"
        f"建议补充明确的指标字段后再次分析，以生成更具体的业务结论。"
    )
    return insights, report


_LLM_REPORT_SYSTEM_PROMPT = """你是资深数据分析师，负责撰写面向业务人员的分析结论。要求：
1. 直接回应用户的问题，先给结论，再给数据依据；
2. 只使用提供数据中的真实数字，严禁编造、估算数据里没有的数值；
3. 用自然、专业的中文叙述（3~5 句话），避免“系统已完成分析”这类机器腔和空泛套话；
4. 结尾给一条具体、可执行的建议，指明具体对象（如某个渠道/地区），不要泛泛而谈；
5. 直接输出结论正文，不要任何前后缀、标题或 markdown 格式。"""


def build_llm_report(
    user_question: str,
    analysis_plan: dict[str, Any],
    result_df: pd.DataFrame,
    fallback_report: str,
) -> str:
    
    if not LLM_REPORT_ENABLED or result_df.empty:
        return fallback_report

    try:
        from llm.client import invoke_text
    except Exception as e:  
        logger.warning("LLM 报告不可用（缺依赖或配置），回退模板报告：%s", e)
        return fallback_report

    try:
        preview = json.loads(
            result_df.head(LLM_REPORT_MAX_ROWS).to_json(orient="records", force_ascii=False)
        )
        payload = {
            "user_question": user_question,
            "analysis_plan": analysis_plan,
            "total_rows": len(result_df),
            "data": preview,
            "baseline_summary": fallback_report,
        }
        text = invoke_text(
            _LLM_REPORT_SYSTEM_PROMPT, json.dumps(payload, ensure_ascii=False)
        ).strip()
        return text or fallback_report
    except Exception as e:  
        logger.warning(
            "LLM 报告生成失败（%s），已回退模板报告：%s",
            type(e).__name__,
            e,
        )
        return fallback_report
