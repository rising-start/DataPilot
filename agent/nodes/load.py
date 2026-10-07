from contextlib import closing

from agent.state import AgentState
from agent.support.tracing import run_update
from core.sanitize import make_json_safe
from loaders.csv_loader import load_csv
from loaders.excel_loader import load_excel
from loaders.schema_inspector import inspect_dataframe
from loaders.sqlite_loader import (
    get_sqlite_connection,
    get_table_schema,
    list_tables,
    preview_table,
)


def load_data_node(state: AgentState) -> AgentState:
    try:
        data_input = state.get("input", {})
        file_path = data_input.get("file_path")
        data_source_type = data_input.get("data_source_type")

        if not file_path:
            return make_json_safe(run_update(
                state, "Load data failed: missing file_path.", "load_data", "error",
                {"reason": "missing file_path"},
                error="Missing file_path in state.", last_error_stage="load_data",
            ))

        if not data_source_type:
            return make_json_safe(run_update(
                state, "Load data failed: missing data_source_type.", "load_data", "error",
                {"reason": "missing data_source_type"},
                error="Missing data_source_type in state.", last_error_stage="load_data",
            ))

        if data_source_type == "csv":
            df = load_csv(file_path)
            profile = inspect_dataframe(df)
            return make_json_safe({
                "dataset": {
                    "dataset_profile": profile,
                    "schema_info": profile,
                    "sample_rows": df.head(5).to_dict(orient="records"),
                },
                **run_update(
                    state, "Loaded CSV data.", "load_data", "ok",
                    {"source": "csv", "rows": len(df), "cols": len(df.columns)},
                ),
            })

        if data_source_type == "excel":
            df = load_excel(file_path)
            profile = inspect_dataframe(df)
            return make_json_safe({
                "dataset": {
                    "dataset_profile": profile,
                    "schema_info": profile,
                    "sample_rows": df.head(5).to_dict(orient="records"),
                },
                **run_update(
                    state, "Loaded Excel data.", "load_data", "ok",
                    {"source": "excel", "rows": len(df), "cols": len(df.columns)},
                ),
            })

        if data_source_type == "sqlite":
            with closing(get_sqlite_connection(file_path)) as conn:
                tables = list_tables(conn)
                schema = {
                    "tables": [
                        {
                            "table_name": table,
                            "schema": get_table_schema(conn, table),
                            "preview": preview_table(conn, table).to_dict(orient="records"),
                        }
                        for table in tables
                    ]
                }
            return make_json_safe({
                "dataset": {
                    "dataset_profile": {"table_count": len(tables), "tables": tables},
                    "schema_info": schema,
                    "sample_rows": [],
                },
                **run_update(
                    state, "Loaded SQLite data.", "load_data", "ok",
                    {"source": "sqlite", "tables": tables},
                ),
            })

        return make_json_safe(run_update(
            state, "Unsupported data source.", "load_data", "error",
            {"reason": f"unsupported {data_source_type}"},
            error=f"Unsupported source type: {data_source_type}",
            last_error_stage="load_data",
        ))

    except Exception as e:
        return make_json_safe(run_update(
            state, f"Load data failed: {e}", "load_data", "error", {"reason": str(e)},
            error=f"Load data failed: {e}", last_error_stage="load_data",
        ))
