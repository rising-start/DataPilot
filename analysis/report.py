from typing import Any, Dict, List

import pandas as pd

from core.columns import pick_dimension_column, pick_metric_column


def _fmt_value(v: Any) -> str:
    if isinstance(v, float):
        if abs(v) < 1:
            return f"{v:.4f}"
        return f"{v:.2f}"
    return str(v)


def build_report(
    user_question: str,
    analysis_plan: Dict[str, Any],
    result_df: pd.DataFrame,
) -> tuple[List[str], str]:
    insights: List[str] = []

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

    insights.append(f"结果共返回 {len(result_df)} 行、{len(result_df.columns)} 列。")

    if dim_col and metric_col:
        sorted_df = result_df.sort_values(metric_col, ascending=False).reset_index(drop=True)

        top1 = sorted_df.iloc[0]
        top1_dim = top1[dim_col]
        top1_metric = top1[metric_col]

        insights.append(
            f"{dim_col}维度中，{top1_dim} 的 {metric_col} 最高，为 {_fmt_value(top1_metric)}。"
        )

        if len(sorted_df) >= 2:
            top2 = sorted_df.iloc[1]
            insights.append(
                f"排名第二的是 {top2[dim_col]}，{metric_col} 为 {_fmt_value(top2[metric_col])}。"
            )
        else:
            insights.append("当前结果仅包含一个维度值，暂时无法做更多横向对比。")

        if len(sorted_df) >= 2:
            bottom1 = sorted_df.iloc[-1]
            insights.append(
                f"相对较低的是 {bottom1[dim_col]}，{metric_col} 为 {_fmt_value(bottom1[metric_col])}。"
            )
        else:
            insights.append("当前结果不足以判断最低值或尾部差异。")

        report = (
            f"针对问题“{user_question}”，系统已完成数据分析。"
            f"从结果看，{top1_dim} 在 {metric_col} 上表现最突出，"
            f"数值为 {_fmt_value(top1_metric)}。"
        )

        if len(sorted_df) >= 2:
            bottom1 = sorted_df.iloc[-1]
            report += (
                f" 相比之下，{bottom1[dim_col]} 处于较低水平，"
                f"{metric_col} 为 {_fmt_value(bottom1[metric_col])}，"
                f"说明不同{dim_col}之间存在明显差异。"
            )

        report += "建议结合业务背景进一步分析差异原因，并优先关注表现异常或风险较高的维度。"
        return insights, report

    if metric_col:
        max_value = result_df[metric_col].max()
        min_value = result_df[metric_col].min()
        mean_value = result_df[metric_col].mean()

        insights.append(f"{metric_col} 的最大值为 {_fmt_value(max_value)}。")
        insights.append(f"{metric_col} 的最小值为 {_fmt_value(min_value)}。")
        insights.append(f"{metric_col} 的平均水平约为 {_fmt_value(mean_value)}。")

        report = (
            f"针对问题“{user_question}”，系统已完成分析。"
            f"当前结果中，{metric_col} 的最大值为 {_fmt_value(max_value)}，"
            f"最小值为 {_fmt_value(min_value)}，平均值约为 {_fmt_value(mean_value)}。"
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
