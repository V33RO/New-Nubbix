import os
from dotenv import load_dotenv

load_dotenv()

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-nano")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5")


_temp = os.getenv("TEMPERATURE", "").strip()
TEMPERATURE: float | None = float(_temp) if _temp else None
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "2000"))

REASONING_EFFORT = os.getenv("REASONING_EFFORT", "").strip() or None

def require(value: str | None, name: str) -> str:
    if value is None:
        raise ValueError(f"{name} is required but not set in environment variables.")
    return value