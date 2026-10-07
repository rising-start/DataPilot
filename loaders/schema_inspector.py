from typing import Any

import pandas as pd


def inspect_dataframe(df: pd.DataFrame) -> dict[str, Any]:
    return {
        "row_count": int(len(df)),
        "column_count": int(len(df.columns)),
        "columns": [
            {
                "name": col,
                "dtype": str(df[col].dtype),
                "null_count": int(df[col].isna().sum()),
                "sample_values": df[col].dropna().astype(str).head(3).tolist(),
            }
            for col in df.columns
        ],
    }