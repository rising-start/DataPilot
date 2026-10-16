import json
import re
from typing import Any


def extract_json_object(text: str) -> dict[str, Any]:
    
    text = (text or "").strip()

    candidates = [text]

    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        candidates.append(fenced.group(1).strip())

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidates.append(text[start:end + 1])

    for candidate in candidates:
        parsed = _try_loads(candidate)
        if isinstance(parsed, dict):
            return parsed

    raise ValueError("No valid JSON object found.")


def _try_loads(text: str) -> Any:
    try:
        return json.loads(text)
    except Exception:
        pass

    
    try:
        return json.loads(re.sub(r",\s*([}\]])", r"\1", text))
    except Exception:
        return None
