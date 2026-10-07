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


def build_graph(executors_list=None):
    if executors_list is None:
        init_executors()
    else:
        for executor in executors_list:
            register_executor(executor)

    builder = StateGraph(AgentState)

    builder.add_node("load_data", load_data_node)
    builder.add_node("plan_analysis", plan_analysis_node)
    builder.add_node("generate_artifact", generate_artifact_node)
    builder.add_node("approval", approval_node)
    builder.add_node("repair_artifact", repair_artifact_node)
    builder.add_node("execute_artifact", execute_artifact_node)
    builder.add_node("build_chart", build_chart_node)
    builder.add_node("report", report_node)
    builder.add_node("error", error_node)

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
