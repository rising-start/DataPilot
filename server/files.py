import json
import logging
import threading
from dataclasses import dataclass

from core.config import REDIS_URL
from core.files import delete_temp_file, detect_source_type, save_upload_to_temp

logger = logging.getLogger(__name__)

_KEY_PREFIX = "datapilot:upload:"


@dataclass
class UploadedFile:
    file_id: str
    filename: str
    source_type: str
    path: str


class UploadStore:
    """上传文件登记表：file_id -> 临时路径（内存实现）。

    多轮追问会复用同一个 file_id，因此任务到达终态时不得删除临时文件；
    只在 DELETE 任务或重新上传时清理。
    """

    def __init__(self) -> None:
        self._files: dict[str, UploadedFile] = {}

    def save(self, file_id: str, filename: str, data: bytes) -> UploadedFile:
        path = save_upload_to_temp(filename, data)

        old = self._files.get(file_id)
        if old and old.path != path:
            delete_temp_file(old.path)

        uploaded = UploadedFile(file_id, filename, detect_source_type(filename), path)
        self._files[file_id] = uploaded
        return uploaded

    def get(self, file_id: str) -> UploadedFile | None:
        return self._files.get(file_id)

    def delete(self, file_id: str) -> None:
        uploaded = self._files.pop(file_id, None)
        if uploaded:
            delete_temp_file(uploaded.path)


# --------------------------------------------------------------------------- #
# Redis 实现：文件字节仍在本地临时目录，这里只外置「file_id -> 元数据」登记表，
# 使进程重启 / 多副本能通过 file_id 找回已上传文件（前提是临时目录跨副本共享，
# 如挂载同一卷；否则多副本仍需改为对象存储）。
# --------------------------------------------------------------------------- #

class RedisUploadStore:
    def __init__(self, url: str) -> None:
        import redis

        self._client = redis.Redis.from_url(url)
        self._cache: dict[str, UploadedFile] = {}

    @staticmethod
    def _to_dict(u: UploadedFile) -> dict:
        return {
            "file_id": u.file_id,
            "filename": u.filename,
            "source_type": u.source_type,
            "path": u.path,
        }

    @staticmethod
    def _from_dict(d: dict) -> UploadedFile:
        return UploadedFile(
            file_id=d.get("file_id", ""),
            filename=d.get("filename", ""),
            source_type=d.get("source_type", ""),
            path=d.get("path", ""),
        )

    def save(self, file_id: str, filename: str, data: bytes) -> UploadedFile:
        path = save_upload_to_temp(filename, data)

        old = self._cache.get(file_id)
        if old and old.path != path:
            delete_temp_file(old.path)

        uploaded = UploadedFile(file_id, filename, detect_source_type(filename), path)
        self._cache[file_id] = uploaded
        self._client.set(_KEY_PREFIX + file_id, json.dumps(self._to_dict(uploaded), ensure_ascii=False))
        return uploaded

    def get(self, file_id: str) -> UploadedFile | None:
        cached = self._cache.get(file_id)
        if cached is not None:
            return cached
        raw = self._client.get(_KEY_PREFIX + file_id)
        if raw is None:
            return None
        uploaded = self._from_dict(json.loads(raw))
        self._cache[file_id] = uploaded
        return uploaded

    def delete(self, file_id: str) -> None:
        uploaded = self._cache.pop(file_id, None)
        self._client.delete(_KEY_PREFIX + file_id)
        if uploaded:
            delete_temp_file(uploaded.path)


def get_upload_store():
    """按配置返回上传登记表实现：有 REDIS_URL 且可用则 Redis，否则内存。"""
    if not REDIS_URL:
        return UploadStore()
    try:
        store = RedisUploadStore(REDIS_URL)
        store._client.ping()
        logger.info("使用 Redis 上传登记表：%s", REDIS_URL)
        return store
    except Exception as e:  # noqa: BLE001
        logger.warning("Redis 不可用（%s），回落内存上传登记表", e)
        return UploadStore()


UPLOADS = get_upload_store()
