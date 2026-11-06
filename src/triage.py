from dataclasses import dataclass

from pydantic import ValidationError

from src.errors import InvalidContractError, InvalidQueryError
from src.llm_client import ask_tool
from src.prompt_loader import load_prompt
from src.schemas import TriageResult

TOOL_NAME = "classify_ticket"

TOOL_SCHEMA = TriageResult.model_json_schema()

CONTRACT_INSTRUCTION = f"\n\nRespondé SIEMPRE invocando la función {TOOL_NAME}."


@dataclass
class ClassificationRun:
    """Resultado validado + todo lo que hace falta para métricas  y evals ."""
    result: TriageResult
    prompt_version: str
    provider: str
    model: str
    attempts: int
    input_tokens: int      
    output_tokens: int
    cost_usd: float
    latency_s: float


def _summarize_error(e: ValidationError) -> str:
    """Campo + motivo, sin devolverle al modelo todo su propio output."""
    return "; ".join(
        f"{'.'.join(str(p) for p in err['loc']) or 'raíz'}: {err['msg']}" for err in e.errors()
    )


def classify(
    ticket: str,
    prompt_version: str = "v3",
    provider: str | None = None,
    max_attempts: int = 3,
) -> ClassificationRun:
    
    if not ticket or not ticket.strip():
        raise InvalidQueryError("La consulta no puede estar vacía.")

    prompt = load_prompt(prompt_version)
    user = prompt.build_user(ticket)

    previous_error: str | None = None
    totals = {"input": 0, "output": 0, "cost": 0.0, "latency": 0.0}

    for attempt in range(1, max_attempts + 1):
        system = prompt.system + CONTRACT_INSTRUCTION
        if previous_error:
            
            system += (
                f"\n\nTu respuesta anterior fue inválida: {previous_error}. "
                "Corregila respetando exactamente el contrato."
            )

        r = ask_tool(user, system, TOOL_NAME, TOOL_SCHEMA, provider=provider)
        totals["input"] += r.input_tokens
        totals["output"] += r.output_tokens
        totals["cost"] += r.cost_usd
        totals["latency"] += r.latency_s

        if r.args is not None:
            try:
                result = TriageResult.model_validate(r.args)
                return ClassificationRun(
                    result=result,
                    prompt_version=prompt.version,
                    provider=r.provider,
                    model=r.model,
                    attempts=attempt,
                    input_tokens=totals["input"],
                    output_tokens=totals["output"],
                    cost_usd=totals["cost"],
                    latency_s=totals["latency"],
                )
            except ValidationError as e:
                previous_error = _summarize_error(e)
        else:
            previous_error = f"no se pudo parsear la respuesta como JSON: {r.raw[:80]!r}"

    raise InvalidContractError(
        f"Se agotaron los {max_attempts} intentos. Último error: {previous_error}"
    )


if __name__ == "__main__":
    import sys

    ticket = " ".join(sys.argv[1:]) or "Me cobraron dos veces la suscripción de este mes."
    run = classify(ticket)
    print(run.result.model_dump_json(indent=2))
    print(f"\nintentos={run.attempts} tokens={run.input_tokens}+{run.output_tokens} "
          f"costo=${run.cost_usd:.6f} latencia={run.latency_s:.2f}s")