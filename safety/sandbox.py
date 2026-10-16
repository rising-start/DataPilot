from __future__ import annotations
import ast
import re
import time
from typing import Any
import pandas as pd
from agent.cancellation import CancellationError
from core.config import MAX_RESULT_ROWS
_ALLOWED_BUILTINS: dict[str, Any] = {'abs': abs, 'all': all, 'any': any, 'bool': bool, 'dict': dict, 'enumerate': enumerate, 'float': float, 'int': int, 'isinstance': isinstance, 'len': len, 'list': list, 'max': max, 'min': min, 'range': range, 'round': round, 'set': set, 'sorted': sorted, 'str': str, 'sum': sum, 'tuple': tuple, 'zip': zip}
_FORBIDDEN_NAMES = {'os', 'sys', 'subprocess', 'socket', 'shutil', 'pathlib', 'requests', 'urllib', 'pickle', 'importlib', 'builtins', 'globals', 'locals', 'vars'}
_FORBIDDEN_CALLS = {'open', 'eval', 'exec', 'compile', '__import__', 'input', 'getattr', 'setattr', 'delattr', 'dir', 'exit', 'quit', 'breakpoint', 'help'}
_FORBIDDEN_IO_METHODS = {'read_csv', 'read_excel', 'read_table', 'read_fwf', 'read_json', 'read_html', 'read_pickle', 'read_parquet', 'read_feather', 'read_orc', 'read_hdf', 'read_sql', 'read_sql_query', 'read_sql_table', 'read_clipboard', 'read_gbq', 'to_csv', 'to_excel', 'to_json', 'to_pickle', 'to_parquet', 'to_feather', 'to_hdf', 'to_sql', 'to_clipboard'}

def clean_code(code: str) -> str:
    code = (code or '').strip()
    fenced = re.search('```(?:python|py)?\\s*(.*?)\\s*```', code, re.DOTALL | re.IGNORECASE)
    if fenced:
        code = fenced.group(1).strip()
    kept_lines = []
    for line in code.splitlines():
        stripped = line.strip()
        if stripped.startswith('import '):
            continue
        if stripped.startswith('from ') and ' import ' in stripped:
            continue
        if stripped.startswith(('下面是', '这是', '以下是', '说明：', '注意：')):
            continue
        kept_lines.append(line)
    return '\n'.join(kept_lines).strip()

def validate_code(code: str) -> None:
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise ValueError(f'生成代码存在语法错误: {e}') from e
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            raise ValueError('生成代码不允许 import。')
        if isinstance(node, ast.While):
            raise ValueError('生成代码不允许 while 循环。')
        if isinstance(node, ast.Attribute) and node.attr.startswith('__'):
            raise ValueError(f'生成代码不允许访问属性 {node.attr}。')
        if isinstance(node, ast.Name):
            if node.id.startswith('__'):
                raise ValueError(f'生成代码不允许引用 {node.id}。')
            if node.id in _FORBIDDEN_NAMES:
                raise ValueError(f'生成代码不允许引用模块 {node.id}。')
        if isinstance(node, ast.Call):
            func = node.func
            name = getattr(func, 'id', None) or getattr(func, 'attr', None)
            if name in _FORBIDDEN_CALLS:
                raise ValueError(f'生成代码不允许调用 {name}()。')
            if isinstance(func, ast.Attribute) and func.attr in _FORBIDDEN_IO_METHODS:
                raise ValueError(f'生成代码不允许进行文件/网络 IO：{func.attr}()。')

def build_safe_globals(extra: dict[str, Any] | None=None) -> dict[str, Any]:
    namespace: dict[str, Any] = {'__builtins__': dict(_ALLOWED_BUILTINS)}
    if extra:
        namespace.update(extra)
    return namespace

def normalize_result(result: Any) -> pd.DataFrame:
    if result is None:
        raise ValueError('生成代码必须把最终结果赋值给 result_df。')
    if hasattr(result, 'compute'):
        result = result.compute()
    if isinstance(result, pd.Series):
        series_name = result.name or 'value'
        result = result.reset_index(name=series_name)
    if not isinstance(result, pd.DataFrame):
        raise ValueError('result_df 必须是 pandas DataFrame 或 Series。')
    return result.head(MAX_RESULT_ROWS).copy()

class SandboxValidationError(ValueError):
    pass

class SandboxExecError(RuntimeError):
    pass

def _execute_code_impl(code: str, variables: dict[str, Any] | None=None) -> pd.DataFrame:
    code = clean_code(code)
    if not code:
        raise SandboxValidationError('生成代码为空。')
    try:
        validate_code(code)
    except ValueError as e:
        raise SandboxValidationError(str(e)) from e
    namespace = build_safe_globals(variables)
    namespace.setdefault('result_df', None)
    try:
        exec(code, namespace, namespace)
    except Exception as e:
        raise SandboxExecError(f'代码执行出错: {e}') from e
    return normalize_result(namespace.get('result_df'))

def run_generated_code(code: str, variables: dict[str, Any] | None=None) -> pd.DataFrame:
    return _execute_code_impl(code, variables)

def _read_err_path(err_path: str) -> dict[str, Any]:
    import json
    try:
        with open(err_path, encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {'error': '子进程异常退出（无错误详情）', 'terminal': False}

def run_generated_code_subprocess(code: str, file_path: str, source_type: str, executor_name: str, timeout: float, cancel_event=None) -> pd.DataFrame:
    import json
    import os
    import pickle
    import subprocess
    import sys
    import tempfile
    import uuid
    base = tempfile.gettempdir()
    token = uuid.uuid4().hex
    req_path = os.path.join(base, f'datapilot_req_{token}.json')
    res_path = os.path.join(base, f'datapilot_res_{token}.pkl')
    err_path = os.path.join(base, f'datapilot_err_{token}.json')
    req = {'code': code, 'file_path': file_path, 'source_type': source_type, 'executor_name': executor_name}
    with open(req_path, 'w', encoding='utf-8') as f:
        json.dump(req, f, ensure_ascii=False)
    try:
        try:
            proc = subprocess.Popen([sys.executable, '-m', 'safety.code_runner', req_path, res_path, err_path], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            deadline = time.monotonic() + timeout
            poll_interval = 0.2
            while True:
                try:
                    proc.wait(timeout=poll_interval)
                    break
                except subprocess.TimeoutExpired:
                    if cancel_event is not None and cancel_event.is_set():
                        proc.kill()
                        proc.wait()
                        raise CancellationError('任务已取消') from None
                    if time.monotonic() >= deadline:
                        proc.kill()
                        proc.wait()
                        raise SandboxExecError(f'执行超时（>{timeout}s），已强制终止。') from None
        except CancellationError:
            raise
        except subprocess.TimeoutExpired:
            raise SandboxExecError(f'执行超时（>{timeout}s），已强制终止。') from None
        if proc.returncode != 0:
            err = _read_err_path(err_path)
            detail = ''
            if proc.stderr is not None:
                detail = proc.stderr.read().decode('utf-8', 'replace').strip()
            if bool(err.get('terminal', False)):
                msg = err.get('error', '代码校验失败。')
                raise SandboxValidationError(msg + _stderr_suffix(detail))
            msg = err.get('error', '子进程执行失败。')
            raise SandboxExecError(msg + _stderr_suffix(detail))
        try:
            with open(res_path, 'rb') as f:
                return pickle.load(f)
        except (pickle.UnpicklingError, EOFError, OSError) as e:
            raise SandboxExecError(f'读取子进程结果失败：{e}') from e
    finally:
        for p in (req_path, res_path, err_path):
            if os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass

def _stderr_suffix(detail: str) -> str:
    if not detail:
        return ''
    return '\n子进程 stderr: ' + detail[-2000:]