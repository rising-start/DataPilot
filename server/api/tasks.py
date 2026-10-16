import asyncio
import json
import threading
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from agent.cancellation import CancellationError, cancel_context
from agent.progress import register_progress, unregister_progress
from core.files import delete_temp_file
from server.event_hub import HUB
from server.files import UPLOADS
from server.schemas import CreateTaskRequest, ResumeRequest, TaskView
from server.task_store import InMemoryTaskStore, TaskRecord, get_task_store
from service import AnalysisService, RunResult

router = APIRouter(prefix="/api")

STORE = get_task_store()
SERVICE = AnalysisService()
EXECUTOR = ThreadPoolExecutor(max_workers=4)



STORE.recover()

STORE.start_cancel_subscriber()


def _emit_stage(record: TaskRecord, stage: str) -> None:
    
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
    
    record.cancel_event = threading.Event()
    epoch = record.epoch

    def run() -> None:
        
        register_progress(record.task_id, lambda s: _emit_stage(record, s))
        with cancel_context(record.cancel_event):
            try:
                result = call()
                if result is None:
                    raise RuntimeError("service returned no result")
                record.merge_result(result)
            except CancellationError:
                
                record.status = "cancelled"
                record.error = "任务已被用户取消"
                record.result = None
            except Exception as e:  
                record.status = "failed"
                record.error = str(e)
                
                record.result = None
            finally:
                
                if record.status in ("completed", "failed", "cancelled"):
                    unregister_progress(record.task_id)

        
        
        _apply_cancel_precedence(record)

        if STORE.get(record.task_id) is record and record.epoch == epoch:
            STORE.set(record)
            HUB.signal(record.task_id)

    EXECUTOR.submit(run)


def _apply_cancel_precedence(record: TaskRecord) -> None:
    
    if record.cancel_event is not None and record.cancel_event.is_set():
        record.status = "cancelled"
        record.error = "任务已被用户取消"
        record.result = None


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

    
    record.epoch += 1
    record.status = "running"
    STORE.set(record)
    HUB.signal(task_id)

    _spawn(
        record,
        lambda: SERVICE.resume(
            thread_id,
            payload.approved,
            modified_content=payload.modified_content,
            task_id=record.task_id,
        ),
    )
    return {"task_id": task_id, "status": "running"}


@router.delete("/tasks/{task_id}")
def delete_task(task_id: str):
    record = STORE.get(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="task not found")

    
    
    
    
    
    if record.status == "running":
        if record.cancel_event is not None:
            record.cancel_event.set()
        record.status = "cancelled"
        record.error = "任务已被用户取消"
        STORE.set(record)
        
        STORE.publish_cancel(task_id)
        
        unregister_progress(task_id)
        HUB.signal(task_id)
        return {"deleted": True, "cancelled": True}

    
    STORE.delete(task_id)
    unregister_progress(task_id)

    still_used = any(
        r.file_id == record.file_id and r.task_id != task_id for r in STORE.list()
    )
    if not still_used:
        delete_temp_file(record.file_path)
        UPLOADS.delete(record.file_id)

    return {"deleted": True}


def _sse(payload: dict) -> str:
    
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


_TERMINAL_STATES = {"completed", "failed", "cancelled"}


@router.get("/tasks/{task_id}/events")
async def task_events(task_id: str):
    
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
