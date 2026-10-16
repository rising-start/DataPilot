import logging

from executors.pandas_executor import PandasExecutor
from executors.registry import register_executor
from executors.sql_executor import SQLExecutor

logger = logging.getLogger(__name__)


def init_executors() -> None:
    
    from agent.prompts import (
        DASK_GENERATOR_PROMPT,
        DASK_REPAIR_PROMPT,
        DUCKDB_GENERATOR_PROMPT,
        DUCKDB_REPAIR_PROMPT,
        PANDAS_GENERATOR_PROMPT,
        PANDAS_REPAIR_PROMPT,
        SQL_GENERATOR_PROMPT,
        SQL_REPAIR_PROMPT,
    )

    register_executor(SQLExecutor(
        generator_prompt=SQL_GENERATOR_PROMPT,
        repair_prompt=SQL_REPAIR_PROMPT,
        artifact_kind="sql",
    ))
    register_executor(PandasExecutor(
        generator_prompt=PANDAS_GENERATOR_PROMPT,
        repair_prompt=PANDAS_REPAIR_PROMPT,
        artifact_kind="pandas",
    ))

    
    
    try:
        import dask.dataframe  

        from executors.dask_executor import DaskExecutor

        register_executor(DaskExecutor(
            generator_prompt=DASK_GENERATOR_PROMPT,
            repair_prompt=DASK_REPAIR_PROMPT,
            artifact_kind="dask",
        ))
    except ImportError as e:
        logger.warning("Dask executor disabled: %s", e)

    
    try:
        import duckdb  

        from executors.duckdb_executor import DuckDBExecutor

        register_executor(DuckDBExecutor(
            generator_prompt=DUCKDB_GENERATOR_PROMPT,
            repair_prompt=DUCKDB_REPAIR_PROMPT,
            artifact_kind="duckdb",
        ))
    except ImportError as e:
        logger.warning("DuckDB executor disabled: %s", e)
