import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from src.metrics import log_metrics
from src.prompt_loader import available_versions
from src.schemas import CATEGORIES
from src.triage import classify


ROOT = Path(__file__).resolve().parent.parent
DATASET = ROOT / "evals" / "dataset.jsonl"
RESULTS_DIR = ROOT / "results"


def load_dataset(path: Path) -> list[dict]:
    cases = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    bad = [c["id"] for c in cases if c["expected_category"] not in CATEGORIES]
    if bad:
        raise ValueError(f"Casos con categoría esperada inválida: {bad}")
    return cases

def run_case(case: dict, version: str) -> dict:
    row = {"id": case["id"], "tipo": case.get("tipo"), "expected": case["expected_category"]}
    try:
        run = classify(case["ticket"], prompt_version=version)
        row.update(
            predicted=run.result.category, confidence=run.result.confidence,
            attempts=run.attempts, input_tokens=run.input_tokens, output_tokens=run.output_tokens,
            cost_usd=run.cost_usd, latency_s=run.latency_s, blocked_by=run.blocked_by, error=None,
        )
        log_metrics(
            ticket=case["ticket"], status="blocked" if run.blocked_by else "ok",
            prompt_version=run.prompt_version, provider=run.provider, model=run.model,
            input_tokens=run.input_tokens, output_tokens=run.output_tokens,
            latency_s=run.latency_s, cost_usd=run.cost_usd, attempts=run.attempts,
            category=run.result.category, blocked_by=run.blocked_by,
        )
    except Exception as e:  # un error del sistema cuenta como respuesta incorrecta
        row.update(predicted=None, confidence=None, attempts=0, input_tokens=0, output_tokens=0,
                   cost_usd=0.0, latency_s=0.0, blocked_by=None, error=type(e).__name__)
        log_metrics(ticket=case["ticket"], status="error", prompt_version=version, error=type(e).__name__)
    row["correct"] = row["predicted"] == row["expected"]
    return row

def summarize(version: str, rows: list[dict]) -> dict:
    n = len(rows)
    by_cat, by_tipo = defaultdict(list), defaultdict(list)
    for r in rows:
        by_cat[r["expected"]].append(r["correct"])
        by_tipo[r["tipo"]].append(r["correct"])
    confusion = Counter((r["expected"], r["predicted"]) for r in rows if not r["correct"])

   
    preds = defaultdict(set)
    for r in rows:
        preds[r["id"]].add(r["predicted"])
    inconsistent = sorted(i for i, s in preds.items() if len(s) > 1)

    return {
        "prompt_version": version,
        "n_runs": n,
        "accuracy": sum(r["correct"] for r in rows) / n,
        "accuracy_by_category": {c: sum(v) / len(v) for c, v in by_cat.items()},
        "accuracy_by_tipo": {t: sum(v) / len(v) for t, v in by_tipo.items()},
        "errors": sum(1 for r in rows if r["error"]),
        "blocked": sum(1 for r in rows if r["blocked_by"]),
        "retried": sum(1 for r in rows if r["attempts"] > 1),
        "inconsistent_cases": inconsistent,
        "total_cost_usd": sum(r["cost_usd"] for r in rows),
        "avg_cost_usd": sum(r["cost_usd"] for r in rows) / n,
        "avg_latency_s": sum(r["latency_s"] for r in rows) / n,
        "top_confusions": [{"expected": e, "predicted": p, "count": c} for (e, p), c in confusion.most_common(5)],
        "failed_ids": sorted({r["id"] for r in rows if not r["correct"]}),
    }
def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(prog="python -m evals.runner", description="Evalúa versiones de prompt.")
    ap.add_argument("--prompts", nargs="+", default=available_versions(), choices=available_versions())
    ap.add_argument("--dataset", type=Path, default=DATASET)
    ap.add_argument("--repeats", type=int, default=1, help="Veces que se corre cada caso (mide consistencia)")
    ap.add_argument("--limit", type=int, default=None, help="Solo los primeros N casos (para probar barato)")
    args = ap.parse_args()

    cases = load_dataset(args.dataset)[: args.limit]
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    RESULTS_DIR.mkdir(exist_ok=True)
    summaries = []

    for version in args.prompts:
        print(f"\n>> {version}: {len(cases)} casos x {args.repeats}")
        rows = []
        for case in cases:
            for _ in range(args.repeats):
                rows.append(run_case(case, version))
            print(f"   {case['id']} {'ok' if rows[-1]['correct'] else 'FALLA'}", end="\r")
        s = summarize(version, rows)
        summaries.append(s)
        (RESULTS_DIR / f"{stamp}_{version}.json").write_text(
            json.dumps({"summary": s, "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    print("\n\n=== COMPARACIÓN ===")
    print(f"{'prompt':<8}{'accuracy':>10}{'claros':>9}{'ambiguos':>10}{'errores':>9}{'bloq.':>7}{'retry':>7}{'$/caso':>11}{'lat(s)':>8}")
    for s in summaries:
        t = s["accuracy_by_tipo"]
        print(f"{s['prompt_version']:<8}{s['accuracy']:>10.1%}{t.get('claro', 0):>9.1%}{t.get('ambiguo', 0):>10.1%}"
              f"{s['errors']:>9}{s['blocked']:>7}{s['retried']:>7}{s['avg_cost_usd']:>11.6f}{s['avg_latency_s']:>8.2f}")
    for s in summaries:
        print(f"\n{s['prompt_version']}: por categoría {({k: f'{v:.0%}' for k, v in s['accuracy_by_category'].items()})}")
        print(f"   confusiones: {s['top_confusions']}")
        print(f"   casos fallados: {s['failed_ids']}")
        if s["inconsistent_cases"]:
            print(f"   inconsistentes entre repeticiones: {s['inconsistent_cases']}")
    print(f"\nDetalle guardado en results/{stamp}_*.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())