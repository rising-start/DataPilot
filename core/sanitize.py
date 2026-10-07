import math

import numpy as np
import pandas as pd


def make_json_safe(obj):
    # 1. None
    if obj is None:
        return None

    # 2. 先处理最基础的纯 Python 标量
    if isinstance(obj, (str, int, bool)):
        return obj

    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj

    # 3. numpy 标量
    if isinstance(obj, np.integer):
        return int(obj)

    if isinstance(obj, np.floating):
        val = float(obj)
        if math.isnan(val) or math.isinf(val):
            return None
        return val

    if isinstance(obj, np.bool_):
        return bool(obj)

    # 4. pandas 时间类型
    if isinstance(obj, (pd.Timestamp, pd.Timedelta)):
        return str(obj)

    # 5. numpy 数组：一定要在 pd.isna 前处理
    if isinstance(obj, np.ndarray):
        return [make_json_safe(x) for x in obj.tolist()]

    # 6. list / tuple / set
    if isinstance(obj, (list, tuple, set)):
        return [make_json_safe(x) for x in obj]

    # 7. dict：key 强制转字符串
    if isinstance(obj, dict):
        return {str(k): make_json_safe(v) for k, v in obj.items()}

    # 8. pandas 对象
    if isinstance(obj, pd.DataFrame):
        return [make_json_safe(row) for row in obj.to_dict(orient="records")]

    if isinstance(obj, pd.Series):
        return {str(k): make_json_safe(v) for k, v in obj.to_dict().items()}

    if isinstance(obj, pd.Index):
        return [make_json_safe(x) for x in obj.tolist()]

    # 9. 最后才处理“单个值”的缺失判断
    try:
        na_result = pd.isna(obj)
        if isinstance(na_result, (bool, np.bool_)):
            if na_result:
                return None
    except Exception:
        pass

    # 10. 其他对象统一转字符串
    return str(obj)