import asyncio
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from agent.progress import register_progress, unregister_progress
from core.files import delete_temp_file
from server.event_hub import HUB
from server.files import UPLOADS
from server.schemas import CreateTaskRequest, ResumeRequest, TaskView
from server.task_store import InMemoryTaskStore, TaskRecord
from service import AnalysisService, RunResult

router = APIRouter(prefix="/api")

STORE = InMemoryTaskStore()
SERVICE = AnalysisService()
EXECUTOR = ThreadPoolExecutor(max_workers=4)


def _emit_stage(record: TaskRecord, stage: str) -> None:
    """把后端执行阶段写回任务并推送 SSE（线程安全）。"""
    record.stage = stage
    STORE.set(record)
    HUB.signal(record.task_id)


def _to_view(record: TaskRecord) -> TaskView:
    result = record.result
    if result is None:
        return TaskView(
            task_id=record.task_id,
            thread_id=record.thread_id,
            status=record.status,
            stage=record.stage,
            error=record.error,
        )

    approval = None
    if result.pending is not None:
        approval = {
            "kind": result.pending.kind,
            "title": result.pending.title,
            "content": result.pending.content,
            "language": result.pending.language,
        }

    return TaskView(
        task_id=record.task_id,
        thread_id=result.thread_id,
        status=record.status,
        tool=result.tool,
        plan=result.plan,
        approval=approval,
        artifact_kind=result.artifact_kind,
        artifact_code=result.artifact_code,
        rows=result.rows,
        chart_spec=result.chart_spec,
        insights=result.insights,
        report=result.report,
        trace=result.trace,
        logs=result.logs,
        memory=result.memory,
        error=result.error or record.error,
        stage=record.stage,
        )


def _spawn(record: TaskRecord, call: Callable[[], RunResult]) -> None:
    """在线程池执行 service 调用。

    epoch 用于丢弃过期线程的写回：重复点击审批或任务已被删除时，
    旧线程的结果不能覆盖当前状态。
    """
    epoch = record.epoch

    def run() -> None:
        # 注册进度回调：节点凭 task_id 从注册表取出，上报当前执行阶段
        register_progress(record.task_id, lambda s: _emit_stage(record, s))
        try:
            result = call()
            if result is None:
                raise RuntimeError("service returned no result")
            record.merge_result(result)
        except Exception as e:  # noqa: BLE001 - 业务失败用状态表达，不抛 5xx
            record.status = "failed"
            record.error = str(e)
            # 清掉上一轮结果，避免失败状态带着陈旧的业务数据
            record.result = None
        finally:
            # 终态后清理回调，避免注册表随任务累积；awaiting_approval 时保留以等待 resume
            if record.status in ("completed", "failed"):
                unregister_progress(record.task_id)

        if STORE.get(record.task_id) is record and record.epoch == epoch:
            STORE.set(record)
            HUB.signal(record.task_id)

    EXECUTOR.submit(run)


@router.get("/health")
def health():
    return {"status": "ok"}


@router.post("/files")
def upload_file(file: UploadFile = File(...)):
    file_id = str(uuid.uuid4())
    data = file.file.read()
    uploaded = UPLOADS.save(file_id, file.filename or "upload", data)
    return {
        "file_id": file_id,
        "filename": uploaded.filename,
        "source_type": uploaded.source_type,
    }


@router.post("/tasks")
def create_task(payload: CreateTaskRequest):
    uploaded = UPLOADS.get(payload.file_id)
    if uploaded is None:
        raise HTTPException(status_code=404, detail="file_id not found")

    task_id = str(uuid.uuid4())
    record = TaskRecord(
        task_id=task_id,
        thread_id="",
        file_id=payload.file_id,
        status="running",
        file_path=uploaded.path,
    )
    STORE.set(record)

    _spawn(
        record,
        lambda: SERVICE.start_analysis(
            uploaded.path,
            uploaded.source_type,
            payload.question,
            followup=payload.followup,
            memory=payload.memory,
            task_id=record.task_id,
        ),
    )
    HUB.signal(task_id)
    return {"task_id": task_id, "status": "running"}


@router.get("/tasks/{task_id}")
def get_task(task_id: str):
    record = STORE.get(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="task not found")
    return _to_view(record)


@router.post("/tasks/{task_id}/resume")
def resume_task(task_id: str, payload: ResumeRequest):
    record = STORE.get(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="task not found")

    if record.status != "awaiting_approval":
        raise HTTPException(
            status_code=409,
            detail=f"task is not awaiting approval (status={record.status})",
        )

    thread_id = record.thread_id or (record.result.thread_id if record.result else "")
    if not thread_id:
        raise HTTPException(status_code=409, detail="task has no thread to resume")

    # 递增 epoch：让可能仍在运行的旧线程写回失效
    record.epoch += 1
    record.status = "running"
    STORE.set(record)
    HUB.signal(task_id)

    _spawn(
        record,
        lambda: SERVICE.resume(
            thread_id, payload.approved, task_id=record.task_id
        ),
    )
    return {"task_id": task_id, "status": "running"}


@router.delete("/tasks/{task_id}")
def delete_task(task_id: str):
    record = STORE.get(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="task not found")

    STORE.delete(task_id)
    # 清理可能残留的进度回调（终态通常会自行注销，这里双保险）
    unregister_progress(task_id)

    # 没有其他任务（例如同一会话的上一轮）引用该文件时才真正删除临时文件
    still_used = any(
        r.file_id == record.file_id and r.task_id != task_id for r in STORE.list()
    )
    if not still_used:
        delete_temp_file(record.file_path)
        UPLOADS.delete(record.file_id)

    return {"deleted": True}


def _sse(payload: dict) -> str:
    """把事件序列化为 SSE `data:` 帧（一行 JSON）。"""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


_TERMINAL_STATES = {"completed", "failed"}


@router.get("/tasks/{task_id}/events")
async def task_events(task_id: str):
    """SSE 流：实时推送任务状态变化，替代前端轮询。

    连接建立即推送当前快照；之后每次任务状态变化（线程池中的 `_spawn`
    经 `HUB.signal` 通知）推送增量。终态（completed/failed）推送后关闭流；
    任务不存在返回 404。
    """
    record = STORE.get(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="task not found")

    HUB.attach_loop(asyncio.get_running_loop())
    event = HUB.subscribe(task_id)

    async def event_stream():
        try:
            while True:
                rec = STORE.get(task_id)
                if rec is None:
                    yield _sse({"type": "gone"})
                    return
                yield _sse({"type": "update", "view": _to_view(rec).model_dump()})
                if rec.status in _TERMINAL_STATES:
                    return
                event.clear()
                await event.wait()
        finally:
            HUB.unsubscribe(task_id, event)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
