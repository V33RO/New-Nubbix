from dataclasses import dataclass
from pathlib import Path

import yaml

from src.schemas import CATEGORIES, Action

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
COMPANY = "Nubbix"


@dataclass(frozen=True)
class Prompt:
    version: str
    technique: str
    system: str
    user_template: str

    def build_user(self, ticket: str) -> str:
        """Inserta el ticket en la plantilla. Se hace al final y una sola vez, así el
        contenido del ticket nunca se reinterpreta como variable de la plantilla."""
        return self.user_template.replace("{ticket}", ticket.strip())


def available_versions() -> list[str]:
    return sorted(p.stem.replace("triage_", "") for p in PROMPTS_DIR.glob("triage_*.yaml"))


def load_prompt(version: str) -> Prompt:
    path = PROMPTS_DIR / f"triage_{version}.yaml"
    if not path.exists():
        raise FileNotFoundError(
            f"No existe el prompt '{version}'. Disponibles: {available_versions()}"
        )
    data = yaml.safe_load(path.read_text(encoding="utf-8"))

    # Variables que salen de la misma fuente de verdad que el contrato (schemas.py)
    variables = {
        "{company}": COMPANY,
        "{categories}": ", ".join(CATEGORIES),
        "{actions}": ", ".join(a.value for a in Action),
    }
    system = data["system"].strip()
    for key, value in variables.items():
        system = system.replace(key, value)

    return Prompt(
        version=data["version"],
        technique=data["technique"],
        system=system,
        user_template=data["user_template"],
    )


if __name__ == "__main__":
    print("Versiones:", available_versions())
    p = load_prompt("v3")
    print(f"\n=== {p.version} ({p.technique}) ===\n")
    print(p.system)
    print("\n--- user ---")
    print(p.build_user("Me cobraron dos veces este mes"))