import math

import numpy as np
import pandas as pd


def make_json_safe(obj):
    
    if obj is None:
        return None

    
    if isinstance(obj, (str, int, bool)):
        return obj

    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj

    
    if isinstance(obj, np.integer):
        return int(obj)

    if isinstance(obj, np.floating):
        val = float(obj)
        if math.isnan(val) or math.isinf(val):
            return None
        return val

    if isinstance(obj, np.bool_):
        return bool(obj)

    
    if isinstance(obj, (pd.Timestamp, pd.Timedelta)):
        return str(obj)

    
    if isinstance(obj, np.ndarray):
        return [make_json_safe(x) for x in obj.tolist()]

    
    if isinstance(obj, (list, tuple, set)):
        return [make_json_safe(x) for x in obj]

    
    if isinstance(obj, dict):
        return {str(k): make_json_safe(v) for k, v in obj.items()}

    
    if isinstance(obj, pd.DataFrame):
        return [make_json_safe(row) for row in obj.to_dict(orient="records")]

    if isinstance(obj, pd.Series):
        return {str(k): make_json_safe(v) for k, v in obj.to_dict().items()}

    if isinstance(obj, pd.Index):
        return [make_json_safe(x) for x in obj.tolist()]

    
    try:
        na_result = pd.isna(obj)
        if isinstance(na_result, (bool, np.bool_)):
            if na_result:
                return None
    except Exception:
        pass

    
    return str(obj)