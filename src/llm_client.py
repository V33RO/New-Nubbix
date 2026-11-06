import random
import time
from dataclasses import dataclass

import openai

from src import config
from src.pricing import calculate_cost

import json

MAX_RETRIES = 5
MAX_BACKOFF_S = 30

@dataclass
class LLMResponse:
    """Contrato único: no importa qué proveedor respondió."""
    text: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_s: float


    #____________Reintentos_________

def _retry_after_seconds(error: openai.RateLimitError) -> float | None:
    """Si el proveedor manda Retry-After, tiene prioridad sobre nuestro cálculo."""
    try:
        value = error.response.headers.get("Retry-After")
        return float(value) if value is not None else None
    except (AttributeError, ValueError):
        return None
    
def _is_quota_error(e: openai.RateLimitError) -> bool:
    """429 por falta de saldo: reintentar no sirve."""
    return getattr(e, "code", None) == "insufficient_quota" or "insufficient_quota" in str(e)


def _call_with_backoff(fn):
    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            return fn()
        except openai.RateLimitError as e:  # 429
            if _is_quota_error(e):
                raise  # sin saldo: fallar ya, con el mensaje original
            last_error = e
            wait = _retry_after_seconds(e)
            if wait is None:
                wait = min(2 ** attempt + random.uniform(0, 1), MAX_BACKOFF_S)
        except (openai.APIConnectionError, openai.APITimeoutError) as e:
            last_error = e
            wait = min(2 ** attempt + random.uniform(0, 1), MAX_BACKOFF_S)
        except openai.APIStatusError as e:
            if e.status_code >= 500:  # 5xx: transitorio
                last_error = e
                wait = min(2 ** attempt + random.uniform(0, 1), MAX_BACKOFF_S)
            else:  # 4xx: reintentar no sirve
                raise
        if attempt == MAX_RETRIES - 1:
            break
        time.sleep(wait)
    raise RuntimeError(
        f"Se agotaron los {MAX_RETRIES} reintentos contra el proveedor: {last_error!r}"
    ) from last_error

#_________Proveedor OpenAI_________

def _openai_client() -> openai.OpenAI:
    key = config.require(config.OPENAI_API_KEY, "OPENAI_API_KEY")
    return openai.OpenAI(api_key=key, max_retries=0)


def _call_openai(prompt: str, system: str | None, temperature: float | None, max_tokens: int) -> LLMResponse:
    client = _openai_client()
    model = config.OPENAI_MODEL

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    kwargs = {
        "model": model,
        "messages": messages,
        "max_completion_tokens": max_tokens,
    }
    if temperature is not None:
        kwargs["temperature"] = temperature

    if config.REASONING_EFFORT:
        kwargs["extra_body"] = {"reasoning_effort": config.REASONING_EFFORT}

    start = time.perf_counter()
    resp = _call_with_backoff(lambda: client.chat.completions.create(**kwargs))
    latency = time.perf_counter() - start

    usage = resp.usage
    return LLMResponse(
        text=resp.choices[0].message.content or "",
        provider="openai",
        model=model,
        input_tokens=usage.prompt_tokens,
        output_tokens=usage.completion_tokens,
        cost_usd=calculate_cost(model, usage.prompt_tokens, usage.completion_tokens),
        latency_s=latency,
    )

@dataclass
class ToolResponse:
   """Igual que LLMResponse, pero con los argumentos de la tool ya normalizados a dict."""
   args: dict | None
   raw: str
   provider: str
   model: str
   input_tokens: int
   output_tokens: int
   cost_usd: float
   latency_s: float


def _call_openai_tool(
        prompt:str,
        system: str | None,
        tool_name: str,
        tool_schema: dict,
        temperature: float | None,
        max_tokens: int,

) -> ToolResponse:
    client = _openai_client()
    model = config.OPENAI_MODEL

    messages = []
    if system:
        messages.append({"role":"system", "content":system})

    messages.append({"role":"user", "content": prompt})

    kwargs = {
        "model": model,
        "messages": messages,
        "max_completion_tokens":max_tokens,
        "tools":[{
            "type":"function",
            "function": {"name": tool_name, "parameters":tool_schema},
        }],

        "tool_choice":{"type":"function","function":{"name":tool_name}},
    }
    if temperature is not None:
        kwargs["temperature"] = temperature

    if config.REASONING_EFFORT:
        kwargs["extra_body"] = {"reasoning_effort": config.REASONING_EFFORT}


    start = time.perf_counter()
    resp = _call_with_backoff(lambda: client.chat.completions.create(**kwargs))
    latency = time.perf_counter() - start

    msg = resp.choices[0].message
    args, raw = None, msg.content or ""
    if msg.tool_calls:
        raw = msg.tool_calls[0].function.arguments
        try:
            args = json.loads (raw)
        except json. JSONDecodeError:
            args = None
    usage = resp.usage

    return ToolResponse(
        args=args,
        raw=raw,
        provider="openai",
        model=model,
        input_tokens=usage.prompt_tokens,
        output_tokens=usage.completion_tokens,
        cost_usd=calculate_cost(model, usage.prompt_tokens, usage.completion_tokens),
        latency_s=latency,
    )

_TOOL_PROVIDERS ={
    "openai": _call_openai_tool,

}

def ask_tool(
        prompt: str,
        system: str | None,
        tool_name: str,
        tool_schema: dict,
        provider: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
) -> ToolResponse:
     provider = provider or config.LLM_PROVIDER
     if provider not in _TOOL_PROVIDERS:
         raise ValueError(f"Proveedor '{provider}' no soportado. Opciones {list(_TOOL_PROVIDERS)}")
     return _TOOL_PROVIDERS[provider](
         prompt,
         system,
         tool_name,
         tool_schema,
         config.TEMPERATURE if temperature is None else temperature,
         config.MAX_TOKENS if max_tokens is None else max_tokens,
     )  
#_________Punto de entrada unico__________

_PROVIDERS = {
    "openai": _call_openai,}

def ask(
    prompt: str,
    system: str | None = None,
    provider: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> LLMResponse:
    provider = provider or config.LLM_PROVIDER
    if provider not in _PROVIDERS:
        raise ValueError(f"Proveedor '{provider}' no soportado. Opciones: {list(_PROVIDERS)}")
    return _PROVIDERS[provider](
        prompt,
        system,
        config.TEMPERATURE if temperature is None else temperature,
        config.MAX_TOKENS if max_tokens is None else max_tokens,
    )

if __name__ == "__main__":
    r = ask("Decí 'hola' en una palabra.", system="Sos conciso.")
    print(r)

