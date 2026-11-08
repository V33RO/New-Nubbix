import random
import time
from dataclasses import dataclass

import openai
import anthropic

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

#------------Respuesta comun a todos los proveedores------------
def _llm_response (text, provider, model, input_tokens, output_tokens, latency)-> LLMResponse:
    return LLMResponse(
        text=text,
        provider=provider,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=calculate_cost(model, input_tokens, output_tokens),
        latency_s=latency
    )

def _tool_response (args, raw, provider, model, input_tokens, output_tokens, latency)-> ToolResponse:
    return ToolResponse(
        args=args,
        raw=raw,
        provider=provider,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=calculate_cost(model, input_tokens, output_tokens),
        latency_s=latency

    )
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


def _backoff(attempt: int) -> float:
    return min(2 ** attempt + random.uniform(0, 1), MAX_BACKOFF_S)

def _call_with_backoff(fn, sdk):
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
        except (sdk.APIConnectionError, sdk.APITimeoutError) as e:
            last_error = e
            wait = min(2 ** attempt + random.uniform(0, 1), MAX_BACKOFF_S)
        except sdk.APIStatusError as e:
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

def _timed(fn, sdk) :
    start= time.perf_counter()
    resp= _call_with_backoff(fn, sdk)
    return resp, time.perf_counter()-start

#_________Proveedor OpenAI_________

def _openai_client() -> openai.OpenAI:
    key = config.require(config.OPENAI_API_KEY, "OPENAI_API_KEY")
    return openai.OpenAI(api_key=key, max_retries=0)

def _openai_kwargs(prompt, system, temperature, max_tokens, model) -> dict:
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        kwargs = {"model": model, "messages": messages, "max_completion_tokens": max_tokens}
    if temperature is not None:  # algunos modelos solo aceptan el default
        kwargs["temperature"] = temperature
    if config.REASONING_EFFORT:
        kwargs["extra_body"] = {"reasoning_effort": config.REASONING_EFFORT}
    return kwargs


def _call_openai(prompt, system, temperature, max_tokens) -> LLMResponse:
    client = _openai_client()
    model = config.OPENAI_MODEL
    kwargs = _openai_kwargs(prompt, system, temperature, max_tokens, model)
    resp, latency = _timed(lambda: client.chat.completions.create(**kwargs), openai)
    return _llm_response(
        resp.choices[0].message.content or "", "openai", model,
        resp.usage.prompt_tokens, resp.usage.completion_tokens, latency,
    )

def _call_openai_tool(prompt, system, tool_name, tool_schema, temperature, max_tokens) -> ToolResponse:
    client = _openai_client()
    model = config.OPENAI_MODEL
    kwargs = _openai_kwargs(prompt, system, temperature, max_tokens, model)
    kwargs["tools"] = [{"type": "function", "function": {"name": tool_name, "parameters": tool_schema}}]
    kwargs["tool_choice"] = {"type": "function", "function": {"name": tool_name}}

    resp, latency = _timed(lambda: client.chat.completions.create(**kwargs), openai)

    msg = resp.choices[0].message
    args, raw = None, msg.content or ""
    if msg.tool_calls:
        raw = msg.tool_calls[0].function.arguments  # en OpenAI llega como STRING
        try:
            args = json.loads(raw)
        except json.JSONDecodeError:
            args = None  # típico cuando la salida se cortó por max_tokens
    return _tool_response(
        args, raw, "openai", model,
        resp.usage.prompt_tokens, resp.usage.completion_tokens, latency,
    )

#___________________Anthropic_________________

def _anthropic_client()-> anthropic. Anthropic :
    key = config.require(config.ANTHROPIC_API_KEY,"ANTHROPIC_API_KEY")
    return anthropic.Anthropic(api_key=key, max_retries=0)

def _anthropic_kwargs(prompt, system, temperature, max_tokens, model)-> dict:
    kwargs={
        "model":model,
        "max_tokens":max_tokens,
        "messages":[{"role": "user", "content": prompt}],
    }

    if system:
        kwargs["system"]= system
    if temperature is not None:
        kwargs["temperature"] = temperature
    return kwargs


def _call_anthropic(prompt, system, temperature, max_tokens) -> LLMResponse:
    client = _anthropic_client()
    model = config.ANTHROPIC_MODEL
    kwargs = _anthropic_kwargs(prompt, system, temperature, max_tokens, model)
    resp, latency = _timed(lambda: client.messages.create(**kwargs), anthropic)
    text = "".join(b.text for b in resp.content if b.type == "text")
    return _llm_response(
        text, "anthropic", model,
        resp.usage.input_tokens, resp.usage.output_tokens, latency,
    )

def _call_anthropic_tool(prompt, system, tool_name, tool_schema, temperature, max_tokens) -> ToolResponse:
    client = _anthropic_client()
    model = config.ANTHROPIC_MODEL
    kwargs = _anthropic_kwargs(prompt, system, temperature, max_tokens, model)
    kwargs["tools"] = [{
        "name": tool_name,
        "description": "Clasifica el ticket de soporte y sugiere acciones.",
        "input_schema": tool_schema,
    }]
    kwargs["tool_choice"] = {"type": "tool", "name": tool_name}

    resp, latency = _timed(lambda: client.messages.create(**kwargs), anthropic)

    block = next((b for b in resp.content if b.type == "tool_use"), None)
    if block is not None:
        args = block.input  # en Anthropic ya llega como DICT
        raw = json.dumps(args, ensure_ascii=False)
    else:
        args = None
        raw = "".join(b.text for b in resp.content if b.type == "text")
    return _tool_response(
        args, raw, "anthropic", model,
        resp.usage.input_tokens, resp.usage.output_tokens, latency,
    )


#_________Punto de entrada unico__________


_PROVIDERS = {"openai": _call_openai, "anthropic": _call_anthropic}
_TOOL_PROVIDERS = {"openai": _call_openai_tool, "anthropic": _call_anthropic_tool}


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

if __name__ == "__main__":
    r = ask("Decí 'hola' en una palabra.", system="Sos conciso.")
    print(r)

