import json
from pathlib import Path

_PRICING_PATH = Path(__file__).resolve().parent.parent / "pricing.json"
_PRICING = json.loads(_PRICING_PATH.read_text(encoding="utf-8"))

def calculate_cost(model:str, inputs_tokens: int, outputs_tokens: int) -> float:
    """costo = in/1M × precio_in + out/1M × precio_out (USD)."""

    if model not in _PRICING:
        raise KeyError(f"Model '{model}' not found in pricing.json")

    p = _PRICING[model]
    return (inputs_tokens / 1_000_000) * p["input"] + (outputs_tokens / 1_000_000) * p["output"]