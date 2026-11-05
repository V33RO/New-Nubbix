from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CATEGORIES = ["billing","technical","account","other"]
CategoryValue = Literal[tuple(CATEGORIES)]

class Action(str, Enum):

    ESCALATE_TO_HUMAN = "escalate_to_human"
    REQUEST_MORE_INFO = "request_more_info"
    VERIFY_IDENTITY = "verify_identity"
    CHECK_BILLING_RECORDS = "check_billing_records"
    CHECK_SYSTEM_STATUS = "check_system_status"
    SEND_HELP_ARTICLE = "send_help_article"
    NO_ACTION = "no_action"


class TriageResult(BaseModel):
    model_config = ConfigDict(extra="forbid") 
    answer: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    category: CategoryValue
    actions: list[Action] = Field(min_length=1)


if __name__ == "__main__":
    from pydantic import ValidationError

    ok ={
        "answer": "Detectamos el doble cobro; lo derivamos a facturación para el reintegro.",
        "confidence": 0.92,
        "category": "billing",
        "actions": ["check_billing_records", "escalate_to_human"],
    }

    print("OK:", TriageResult.model_validate(ok).model_dump())


    malos={
        "categoría inventada": {**ok, "category": "factura"},
        "confidence fuera de rango": {**ok, "confidence": 47.0},
        "confidence como string": {**ok, "confidence": "alta"},
        "acción inexistente": {**ok, "actions": ["hacer_magia"]},
        "actions vacía": {**ok, "actions": []},
        "campo extra": {**ok, "mood": "feliz"},
    }

    for nombre, data in malos.items():
        try:
            TriageResult.model_validate(data)      # <- data, no ok
            print(f"❌ {nombre}: pasó la validación (no debería)")
        except ValidationError as e:
            print(f"✅ {nombre}: rechazado -> {e.errors()[0]['loc']}")
