import argparse
import json
import sys

from src import config
from src.errors import InvalidContractError, InvalidQueryError
from src.metrics import log_metrics
from src.prompt_loader import available_versions
from src.triage import classify

def build_parser() -> argparse.ArgumentParser:
    p= argparse.ArgumentParser(
        prog="python -m src.main",
        description="Triage de tickets de soporte de Nubbix: devuelve JSON validado.",
    )

    p.add_argument("query", nargs="*", help="Consulta del cliente (si se omite, se lee de stdin)")
    p.add_argument("--prompt", default="v3", choices=available_versions(), help="Versión del prompt")
    p.add_argument("--provider", default=None, help=f"Proveedor (default: {config.LLM_PROVIDER})")
    p.add_argument("-v", "--verbose", action="store_true", help="Resumen de tokens/costo por stderr")
    return p 

def main(argv: list[str] | None= None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    args= build_parser().parse_args(argv)
    ticket= " ".join(args.query) if args.query else (sys.stdin.read() if not sys.stdin.isatty() else "")

    try:
        run = classify(ticket, prompt_version=args.prompt, provider=args.provider)
    except InvalidQueryError as e:
        log_metrics(ticket=ticket, status="error", prompt_version=args.prompt, error="InvalidQueryError")
        print(f"Error: {e}", file=sys.stderr)
        return 2
    except InvalidContractError as e:
        log_metrics(ticket=ticket, status="error", prompt_version=args.prompt, error="InvalidContractError")
        print(f"Error: {e}", file=sys.stderr)
        return 3
    except Exception as e:
        log_metrics(ticket=ticket, status="error", prompt_version=args.prompt, error=type(e).__name__)
        print(f"Error inesperado ({type(e).__name__}): {e}", file=sys.stderr)
        return 1
    
    log_metrics(
        ticket=ticket, status="ok", prompt_version=run.prompt_version,
        provider=run.provider, model=run.model,
        input_tokens=run.input_tokens, output_tokens=run.output_tokens,
        latency_s=run.latency_s, cost_usd=run.cost_usd,
        attempts=run.attempts, category=run.result.category,
        blocked_by=run.blocked_by,
    )

    print(json.dumps(run.result.model_dump(mode="json"), ensure_ascii=False, indent=2))

    if args.verbose:
        if run.blocked_by:
            print(f"[BLOQUEADO por {run.blocked_by}]", file=sys.stderr)
            print(f"[{run.provider}/{run.model} · prompt {run.prompt_version} · intentos={run.attempts} · "
              f"tokens={run.input_tokens}+{run.output_tokens} · ${run.cost_usd:.6f} · {run.latency_s:.2f}s]",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
