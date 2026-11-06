import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

METRICS_PATH = Path(__file__).resolve().parent.parent / "data" / "metrics.jsonl"


def ticket_hash(ticket: str) -> str:
    return hashlib.sha256(ticket.strip().encode("utf-8")).hexdigest()[:16]


def log_metrics(
    *,
    ticket: str,
    status: str,                      
    prompt_version: str,
    provider: str | None = None,
    model: str | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    latency_s: float = 0.0,
    cost_usd: float = 0.0,
    attempts: int = 0,
    category: str | None = None,
    error: str | None = None,
    blocked_by: str | None = None,
    path: Path = METRICS_PATH,
) -> dict:
    """Agrega UNA línea al .jsonl. Nunca reescribe lo anterior."""
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": status,
        "prompt_version": prompt_version,
        "provider": provider,
        "model": model,
        "prompt_tokens": input_tokens,
        "completion_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "latency_s": round(latency_s, 3),
        "cost_usd": round(cost_usd, 8),
        "attempts": attempts,
        "category": category,
        "ticket_hash": ticket_hash(ticket),
        "error": str(error) if error is not None else None,
        "blocked_by": blocked_by,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record