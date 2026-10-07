import pandas as pd

from executors.base import CodeExecutor, _input


def load_dask_dataframe(file_path: str, data_source_type: str):
    import dask.dataframe as dd  # 惰性导入：未安装 dask 时不影响其他执行器

    if data_source_type == "csv":
        return dd.read_csv(file_path)

    if data_source_type == "excel":
        # Dask 不直接读 Excel，先用 pandas 读，再转 dask
        pdf = pd.read_excel(file_path)
        npartitions = max(1, min(8, len(pdf) // 10000 or 1))
        return dd.from_pandas(pdf, npartitions=npartitions)

    raise ValueError(f"Unsupported dask source type: {data_source_type}")


class DaskExecutor(CodeExecutor):
    name = "dask"

    def load_frame(self, state: dict):
        data_input = _input(state)
        return load_dask_dataframe(data_input["file_path"], data_input["data_source_type"])

    def extra_runtime_vars(self) -> dict:
        import dask.dataframe as dd

        return {"dd": dd, "pd": pd}
