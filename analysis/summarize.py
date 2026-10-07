from typing import Any, Dict

import pandas as pd

from core.sanitize import make_json_safe


def summarize_result(result_df: pd.DataFrame) -> Dict[str, Any]:
    summary = {
        "row_count": int(len(result_df)),
        "column_count": int(len(result_df.columns)),
        "columns": [str(c) for c in result_df.columns],
        "preview": make_json_safe(result_df.head(10).to_dict(orient="records")),
    }

    numeric_cols = result_df.select_dtypes(include="number").columns.tolist()
    if numeric_cols:
        desc = result_df[numeric_cols].describe()
        summary["numeric_summary"] = make_json_safe(desc.to_dict())

    return make_json_safe(summary)
