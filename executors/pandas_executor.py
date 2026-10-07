import pandas as pd

from executors.base import CodeExecutor, _input
from loaders.csv_loader import load_csv
from loaders.excel_loader import load_excel


def load_dataframe_by_type(file_path: str, data_source_type: str) -> pd.DataFrame:
    if data_source_type == "csv":
        return load_csv(file_path)
    if data_source_type == "excel":
        return load_excel(file_path)
    raise ValueError(f"Unsupported dataframe source type: {data_source_type}")


class PandasExecutor(CodeExecutor):
    name = "pandas"

    def load_frame(self, state: dict) -> pd.DataFrame:
        data_input = _input(state)
        return load_dataframe_by_type(data_input["file_path"], data_input["data_source_type"])

    def extra_runtime_vars(self) -> dict:
        return {"pd": pd}
