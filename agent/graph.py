import logging
import os
from functools import wraps

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

logger = logging.getLogger(__name__)

from agent.cancellation import CancellationError, is_cancelled
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
    """节点包装：进入时先检查取消，再上报执行阶段（供 SSE 推送中间进度）。

    取消检查放在节点入口：当前节点一旦结束，下一个节点进入前就会被拦下，
    抛出 `CancellationError` 直达 worker 终态处理（状态置为 cancelled），
    避免已取消的分析继续空跑 LLM / exec。
    """
    @wraps(fn)
    def wrapper(state, *args, **kwargs):
        if is_cancelled():
            raise CancellationError("任务已取消")
        report_progress(state, stage)
        return fn(state, *args, **kwargs)
    return wrapper


def _resolve_checkpointer():
    """按 REDIS_URL 选择持久化 checkpointer。

    未配置或不可用 → InMemorySaver（单进程、重启丢会话）；
    配置且可达 → RedisSaver（跨重启 / 多副本共享 LangGraph 状态，支持 resume 与多轮记忆）。
    """
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        return InMemorySaver()
    try:
        from langgraph.checkpoint.redis import RedisSaver

        # 兼容不同版本的 API：优先 from_conn_string，缺失时退到构造器传 client
        try:
            saver = RedisSaver.from_conn_string(redis_url)
        except (AttributeError, TypeError):
            import redis as _redis

            saver = RedisSaver(_redis.Redis.from_url(redis_url))

        # setup() 负责建索引/流，新版本可能已隐式完成
        if hasattr(saver, "setup"):
            saver.setup()
        logger.info("使用 Redis checkpointer：%s", redis_url)
        return saver
    except Exception as e:  # noqa: BLE001 - 回落内存，避免硬失败
        logger.warning("Redis checkpointer 不可用（%s），回落 InMemorySaver", e)
        return InMemorySaver()


def build_graph(executors_list=None, checkpointer=None):
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

    if checkpointer is None:
        checkpointer = _resolve_checkpointer()
    return builder.compile(checkpointer=checkpointer)
