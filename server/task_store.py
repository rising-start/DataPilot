"""任务记录存储。

两种实现共享同一接口（get/set/delete/list），路由层不感知差异：

- `InMemoryTaskStore`：进程内存，单副本、重启即丢（默认 / 未配置 Redis 时回落）。
- `RedisTaskStore`：以 Redis 为后端，跨重启与多副本共享任务状态。

`TaskRecord` 中 `cancel_event`（`threading.Event`）是进程内信号，无法跨进程
序列化，因此 `RedisTaskStore` 把它留在内存映射里，只把其余字段写入 Redis；
同时为避免破坏路由层 `STORE.get(task_id) is record` 的竞态校验语义，
`RedisTaskStore` 在内存里缓存一份「活对象」并镜像写 Redis。
"""

import json
import logging
import threading
from dataclasses import dataclass, field

from core.config import REDIS_TASK_TTL, REDIS_URL
from service import PendingApproval, RunResult

logger = logging.getLogger(__name__)

_KEY_PREFIX = "datapilot:task:"
_CANCEL_CHANNEL = "datapilot:cancel"


@dataclass
class TaskRecord:
    task_id: str
    thread_id: str
    file_id: str = ""
    status: str = "running"
    file_path: str = ""
    result: RunResult | None = None
    error: str = ""
    # 后端当前执行阶段（load/plan/generate/...），供 SSE 实时推送
    stage: str = ""
    # 每次发起新的执行（建任务 / resume）递增；过期线程的写回据此丢弃
    epoch: int = 0
    # 取消事件：任务 running 时由 DELETE 置位，worker 轮询以中断执行。
    # 不进入 checkpoint（非可序列化对象），仅存活于进程内的 record 实例上。
    cancel_event: threading.Event | None = field(default=None)

    def merge_result(self, result: RunResult) -> None:
        """把 service 返回的结果写回任务记录。"""
        self.thread_id = result.thread_id
        self.status = result.status
        self.result = result
        self.error = result.error


class InMemoryTaskStore:
    """内存任务存储。

    接口按 Redis 语义设计（get/set/delete/list），后续替换实现时路由无需改动。
    """

    def __init__(self) -> None:
        self._records: dict[str, TaskRecord] = {}

    def get(self, task_id: str) -> TaskRecord | None:
        return self._records.get(task_id)

    def set(self, record: TaskRecord) -> None:
        self._records[record.task_id] = record

    def delete(self, task_id: str) -> None:
        self._records.pop(task_id, None)

    def list(self) -> list[TaskRecord]:
        return list(self._records.values())

    def recover(self) -> int:
        # 内存实现无遗留状态问题，无需恢复
        return 0

    def publish_cancel(self, task_id: str) -> None:
        # 单进程无需跨进程广播
        return None

    def start_cancel_subscriber(self) -> None:
        # 单进程无需订阅
        return None


# --------------------------------------------------------------------------- #
# Redis 实现
# --------------------------------------------------------------------------- #

def _pending_to_dict(p: PendingApproval) -> dict:
    return {"kind": p.kind, "title": p.title, "content": p.content, "language": p.language}


def _result_to_dict(r: RunResult) -> dict:
    return {
        "thread_id": r.thread_id,
        "status": r.status,
        "tool": r.tool,
        "plan": r.plan,
        "pending": _pending_to_dict(r.pending) if r.pending is not None else None,
        "artifact_kind": r.artifact_kind,
        "artifact_code": r.artifact_code,
        "rows": r.rows,
        "chart_spec": r.chart_spec,
        "chart_ready": r.chart_ready,
        "insights": r.insights,
        "report": r.report,
        "trace": r.trace,
        "logs": r.logs,
        "memory": r.memory,
        "error": r.error,
    }


def _record_to_dict(rec: TaskRecord) -> dict:
    # 注意：cancel_event 不序列化，仅存于进程内映射
    return {
        "task_id": rec.task_id,
        "thread_id": rec.thread_id,
        "file_id": rec.file_id,
        "status": rec.status,
        "file_path": rec.file_path,
        "error": rec.error,
        "stage": rec.stage,
        "epoch": rec.epoch,
        "result": _result_to_dict(rec.result) if rec.result is not None else None,
    }


def _pending_from_dict(d: dict | None) -> PendingApproval | None:
    if not d:
        return None
    return PendingApproval(
        kind=d.get("kind", ""),
        title=d.get("title", "执行审批"),
        content=d.get("content", ""),
        language=d.get("language", "python"),
    )


def _result_from_dict(d: dict | None) -> RunResult | None:
    if not d:
        return None
    return RunResult(
        thread_id=d.get("thread_id", ""),
        status=d.get("status", ""),
        tool=d.get("tool", ""),
        plan=d.get("plan", {}) or {},
        pending=_pending_from_dict(d.get("pending")),
        artifact_kind=d.get("artifact_kind", ""),
        artifact_code=d.get("artifact_code", ""),
        rows=d.get("rows", []) or [],
        chart_spec=d.get("chart_spec", {}) or {},
        chart_ready=bool(d.get("chart_ready", False)),
        insights=d.get("insights", []) or [],
        report=d.get("report", ""),
        trace=d.get("trace", []) or [],
        logs=d.get("logs", []) or [],
        memory=d.get("memory", {}) or {},
        error=d.get("error", ""),
    )


def _record_from_dict(d: dict, cancel_event: threading.Event | None) -> TaskRecord:
    return TaskRecord(
        task_id=d.get("task_id", ""),
        thread_id=d.get("thread_id", ""),
        file_id=d.get("file_id", ""),
        status=d.get("status", "running"),
        file_path=d.get("file_path", ""),
        result=_result_from_dict(d.get("result")),
        error=d.get("error", ""),
        stage=d.get("stage", ""),
        epoch=int(d.get("epoch", 0)),
        cancel_event=cancel_event,
    )


class RedisTaskStore:
    """以 Redis 为后端的任务存储。

    写入：更新内存缓存（保持对象身份，满足 `is` 竞态校验）+ 镜像写 Redis（JSON）。
    读取：优先内存缓存，未命中才回源 Redis（进程重启后首读即回填缓存）。
    `cancel_event` 仅驻留内存映射，跨进程不传递（取消语义依赖同进程 worker）。
    """

    def __init__(self, url: str, ttl: int = 0) -> None:
        import redis

        self._client = redis.Redis.from_url(url)
        self._ttl = ttl or None
        self._cache: dict[str, TaskRecord] = {}
        self._cancel_events: dict[str, threading.Event] = {}

    def get(self, task_id: str) -> TaskRecord | None:
        rec = self._cache.get(task_id)
        if rec is not None:
            return rec
        raw = self._client.get(_KEY_PREFIX + task_id)
        if raw is None:
            return None
        rec = _record_from_dict(json.loads(raw), self._cancel_events.get(task_id))
        self._cache[task_id] = rec
        return rec

    def set(self, record: TaskRecord) -> None:
        # 保存 / 还原 cancel_event（不进 Redis）
        if record.cancel_event is not None:
            self._cancel_events[record.task_id] = record.cancel_event
        elif record.task_id in self._cancel_events:
            record.cancel_event = self._cancel_events[record.task_id]

        self._cache[record.task_id] = record
        payload = json.dumps(_record_to_dict(record), ensure_ascii=False)
        self._client.set(_KEY_PREFIX + record.task_id, payload, ex=self._ttl)

    def delete(self, task_id: str) -> None:
        self._cache.pop(task_id, None)
        self._cancel_events.pop(task_id, None)
        self._client.delete(_KEY_PREFIX + task_id)

    def list(self) -> list[TaskRecord]:
        results = list(self._cache.values())
        for key in self._client.scan_iter(match=_KEY_PREFIX + "*"):
            task_id = key.decode().split(_KEY_PREFIX, 1)[1]
            if task_id in self._cache:
                continue
            raw = self._client.get(key)
            if not raw:
                continue
            rec = _record_from_dict(json.loads(raw), self._cancel_events.get(task_id))
            self._cache[task_id] = rec
            results.append(rec)
        return results

    def recover(self) -> int:
        """启动恢复：把遗留的 running 任务（进程重启导致 worker 消失）标记为失败。

        返回被修正的任务数。多副本各自启动时都会跑一遍，幂等。
        """
        fixed = 0
        for rec in self.list():
            if rec.status == "running":
                rec.status = "failed"
                rec.error = "服务重启，运行中任务已中断"
                rec.result = None
                self.set(rec)
                fixed += 1
        if fixed:
            logger.warning("RedisTaskStore 恢复 %d 个遗留 running 任务为 failed", fixed)
        return fixed

    # ------------------------------------------------------------------ #
    # 跨进程取消：DELETE 打到任意副本时，向频道广播 task_id；
    # 真正持有 worker 的副本（其缓存里是带 cancel_event 的活对象）收到后
    # 置位 cancel_event，中断执行。单进程部署下本地已直接置位，广播为冗余但无害。
    # ------------------------------------------------------------------ #

    def publish_cancel(self, task_id: str) -> None:
        try:
            self._client.publish(_CANCEL_CHANNEL, task_id)
        except Exception as e:  # noqa: BLE001
            logger.warning("发布取消信号失败（%s）：%s", task_id, e)

    def _apply_remote_cancel(self, task_id: str) -> None:
        rec = self.get(task_id)
        if rec is None:
            return
        # 仅当本副本持有该任务的活对象（带 worker 用的 cancel_event）时才置位；
        # 否则只是别的副本的登记，无需动作。
        if rec.cancel_event is not None:
            rec.cancel_event.set()

    def start_cancel_subscriber(self) -> None:
        if getattr(self, "_subscriber_started", False):
            return
        self._subscriber_started = True
        threading.Thread(
            target=self._cancel_loop, daemon=True, name="redis-cancel-subscriber"
        ).start()

    def _cancel_loop(self) -> None:
        import time

        while True:
            try:
                pubsub = self._client.pubsub()
                pubsub.subscribe(_CANCEL_CHANNEL)
                for message in pubsub.listen():
                    if message.get("type") != "message":
                        continue
                    data = message.get("data")
                    task_id = data.decode() if isinstance(data, bytes) else str(data)
                    self._apply_remote_cancel(task_id)
            except Exception as e:  # noqa: BLE001 - 断线后重连，避免静默失活
                logger.warning("Redis 取消订阅循环异常，2s 后重连：%s", e)
                time.sleep(2)


def get_task_store():
    """按配置返回任务存储实现：有 REDIS_URL 且 redis 可用则 Redis，否则内存。"""
    if not REDIS_URL:
        return InMemoryTaskStore()
    try:
        store = RedisTaskStore(REDIS_URL, ttl=REDIS_TASK_TTL)
        # 探活：确保 Redis 真能连上，连不上就回落内存，避免运行时才炸
        store._client.ping()
        logger.info("使用 Redis 任务存储：%s", REDIS_URL)
        return store
    except Exception as e:  # noqa: BLE001 - 任何连接/导入问题都回落内存
        logger.warning("Redis 不可用（%s），回落内存任务存储", e)
        return InMemoryTaskStore()
