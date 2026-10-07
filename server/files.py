from dataclasses import dataclass

from core.files import delete_temp_file, detect_source_type, save_upload_to_temp


@dataclass
class UploadedFile:
    file_id: str
    filename: str
    source_type: str
    path: str


class UploadStore:
    """上传文件登记表：file_id -> 临时路径。

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


UPLOADS = UploadStore()
