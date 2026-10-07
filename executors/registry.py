from __future__ import annotations

from typing import Dict, List

from executors.base import BaseExecutor

_EXECUTOR_REGISTRY: Dict[str, BaseExecutor] = {}


def register_executor(executor: BaseExecutor) -> None:
    _EXECUTOR_REGISTRY[executor.name] = executor


def get_executor(name: str) -> BaseExecutor:
    if name not in _EXECUTOR_REGISTRY:
        raise ValueError(f"Unknown executor: {name}")
    return _EXECUTOR_REGISTRY[name]


def list_executors() -> List[str]:
    return list(_EXECUTOR_REGISTRY.keys())