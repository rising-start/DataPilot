from functools import wraps

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from agent.nodes import (
    approval_node,
    build_chart_node,
    error_node,
    execute_artifact_node,
    generate_artifact_node,
    load_data_node,
    plan_analysis_node,
    repair_artifact_node,
    report_node,
)
from agent.progress import report_progress
from agent.routing import (
    after_approval,
    after_build_chart,
    after_execute_artifact,
    after_generate_artifact,
    after_load_data,
    after_plan,
    after_repair_artifact,
)
from agent.state import AgentState
from executors import init_executors
from executors.registry import register_executor


def _with_progress(fn, stage):
    """节点包装：进入时上报执行阶段，供 SSE 推送中间进度。"""
    @wraps(fn)
    def wrapper(state, *args, **kwargs):
        report_progress(state, stage)
        return fn(state, *args, **kwargs)
    return wrapper


def build_graph(executors_list=None):
    if executors_list is None:
        init_executors()
    else:
        for executor in executors_list:
            register_executor(executor)

    builder = StateGraph(AgentState)

    builder.add_node("load_data", _with_progress(load_data_node, "load"))
    builder.add_node("plan_analysis", _with_progress(plan_analysis_node, "plan"))
    builder.add_node("generate_artifact", _with_progress(generate_artifact_node, "generate"))
    builder.add_node("approval", _with_progress(approval_node, "approval"))
    builder.add_node("repair_artifact", _with_progress(repair_artifact_node, "repair"))
    builder.add_node("execute_artifact", _with_progress(execute_artifact_node, "execute"))
    builder.add_node("build_chart", _with_progress(build_chart_node, "chart"))
    builder.add_node("report", _with_progress(report_node, "report"))
    builder.add_node("error", _with_progress(error_node, "error"))

    builder.add_edge(START, "load_data")

    builder.add_conditional_edges(
        "load_data",
        after_load_data,
        {
            "plan_analysis": "plan_analysis",
            "error": "error",
        },
    )

    builder.add_conditional_edges(
        "plan_analysis",
        after_plan,
        {
            "generate_artifact": "generate_artifact",
            "error": "error",
        },
    )

    builder.add_conditional_edges(
        "generate_artifact",
        after_generate_artifact,
        {
            "approval": "approval",
            "execute_artifact": "execute_artifact",
            "error": "error",
        },
    )

    builder.add_conditional_edges(
        "approval",
        after_approval,
        {
            "execute_artifact": "execute_artifact",
            "error": "error",
        },
    )

    builder.add_conditional_edges(
        "execute_artifact",
        after_execute_artifact,
        {
            "repair_artifact": "repair_artifact",
            "build_chart": "build_chart",
            "report": "report",
            "error": "error",
        },
    )

    builder.add_conditional_edges(
        "repair_artifact",
        after_repair_artifact,
        {
            "approval": "approval",
            "execute_artifact": "execute_artifact",
            "error": "error",
        },
    )

    builder.add_conditional_edges(
        "build_chart",
        after_build_chart,
        {
            "report": "report",
            "error": "error",
        },
    )

    builder.add_edge("report", END)
    builder.add_edge("error", END)

    return builder.compile(checkpointer=InMemorySaver())
