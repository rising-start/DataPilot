from dataclasses import dataclass
from typing import Dict, List, Optional

from service import RunResult


@dataclass
class TaskRecord:
    task_id: str
    thread_id: str
    file_id: str = ""
    status: str = "running"
    file_path: str = ""
    result: Optional[RunResult] = None
    error: str = ""
    # 后端当前执行阶段（load/plan/generate/...），供 SSE 实时推送
    stage: str = ""
    # 每次发起新的执行（建任务 / resume）递增；过期线程的写回据此丢弃
    epoch: int = 0

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
        self._records: Dict[str, TaskRecord] = {}

    def get(self, task_id: str) -> Optional[TaskRecord]:
        return self._records.get(task_id)

    def set(self, record: TaskRecord) -> None:
        self._records[record.task_id] = record

    def delete(self, task_id: str) -> None:
        self._records.pop(task_id, None)

    def list(self) -> List[TaskRecord]:
        return list(self._records.values())
