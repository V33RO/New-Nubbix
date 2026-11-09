# Nubbix — Clasificador de tickets de soporte

Aplicación de línea de comandos que clasifica consultas de soporte de Nubbix y devuelve una respuesta estructurada, validada con Pydantic. Usa prompts versionados y puede conectarse a OpenAI o Anthropic.

## Qué hace

- Clasifica cada ticket en `billing`, `technical`, `account` u `other`.
- Devuelve una respuesta, una confianza entre 0 y 1 y una o más acciones predefinidas.
- Valida la salida: rechaza categorías o acciones desconocidas, campos extra y respuestas incompletas.
- Aplica guardrails de entrada y salida. Si un guardrail bloquea el caso, devuelve una respuesta segura y deriva a una persona.
- Registra métricas de tokens, costo, latencia y resultado.

## Inicio rápido

Requiere Python y una clave de API del proveedor elegido.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Editá `.env` y completá la clave del proveedor:


-LLM_PROVIDER=openai
-OPENAI_API_KEY=tu_clave
-LLM_PROVIDER=anthropic
-ANTHROPIC_API_KEY`

 No compartas ni subas el archivo `.env`.

Ejecutá una consulta:

```powershell
python -m src.main "Me cobraron dos veces este mes" -v
```

El programa imprime el resultado JSON por salida estándar. `-v` agrega a stderr información de bloqueo, tokens, costo y latencia. Si no pasás el ticket como argumento, puede leerlo desde stdin.

Opciones disponibles:

```text
python -m src.main --help
python -m src.main "No puedo descargar la factura" --prompt v2
python -m src.main "No puedo iniciar sesión" --provider anthropic
```

El prompt predeterminado es `v3`. Las versiones disponibles se cargan desde los archivos YAML de `prompts/`.

## Contrato de salida

```json
{
  "answer": "Recibimos tu consulta y la vamos a revisar.",
  "confidence": 0.99,
  "category": "billing",
  "actions": [
    "check_billing_records",
    "request_more_info"
  ]
}
```

Categorías admitidas: `billing`, `technical`, `account`, `other`.

Acciones admitidas: `escalate_to_human`, `request_more_info`, `verify_identity`, `check_billing_records`, `check_system_status`, `send_help_article`, `no_action`.

El contrato no permite campos adicionales, exige una respuesta no vacía y al menos una acción. Cuando un guardrail bloquea una consulta o una respuesta, el sistema devuelve JSON válido con la categoría `other` y la acción `escalate_to_human`.

## Configuración

Las variables principales están documentadas en `.env.example`:

| Variable | Propósito |
|---|---|
| `LLM_PROVIDER` | Proveedor activo: `openai` o `anthropic`. |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | Credencial del proveedor correspondiente. |
| `OPENAI_MODEL` / `ANTHROPIC_MODEL` | Modelo a utilizar. |
| `TEMPERATURE` | Temperatura opcional de la llamada. |
| `MAX_TOKENS` | Límite de tokens de salida. |
| `REASONING_EFFORT` | Nivel de razonamiento, si el modelo lo admite. |

Los nombres de modelo y parámetros compatibles dependen del proveedor. En las pruebas registradas, `gpt-6-luna` requirió omitir `temperature` y usar `reasoning_effort=none` para tool calling en Chat Completions; la consistencia se midió mediante evaluaciones repetidas.

## Estructura del proyecto

```text
src/                 Clasificación, proveedores, esquema, guardrails y métricas
prompts/             Prompts versionados y changelog
evals/dataset.jsonl  Casos para evaluar clasificación normal
evals/adversarial.jsonl
                     Casos adversariales
evals/runner.py      Evaluación de prompts y proveedores
evals/adversarial_runner.py
                     Evaluación de casos adversariales
results/             Resultados de evaluaciones y métricas
data/                Datos auxiliares
pricing.json         Tabla de precios utilizada para calcular costos
```

## Guardrails

- Rechaza tickets vacíos y limita la entrada a 2.000 caracteres.
- Normaliza texto y detecta patrones de manipulación por frases; expresiones aisladas como “ignora” o “soy desarrollador” no deberían bloquear por sí solas un ticket legítimo.
- Verifica la respuesta para bloquear enlaces, correos, secretos, números de tarjeta y fragmentos coincidentes con el prompt del sistema.
- Ante un bloqueo, usa una respuesta neutra y deriva el caso a una persona, manteniendo el contrato JSON.

El bloqueo de cualquier enlace o correo en la respuesta también puede descartar contenido legítimo. Es una decisión conservadora que puede generar falsos positivos.

## Evaluaciones registradas

### Clasificación normal

Corrida registrada con 40 casos y 3 repeticiones por versión:

| Prompt | Accuracy | Claros | Ambiguos | Errores | Bloqueos | Reintentos | Costo medio/caso | Latencia media |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| v1 | 97,5 % | 100 % | 94,1 % | 0 | 0 | 0 | $0.000094 | 1,95 s |
| v2 | 100 % | 100 % | 100 % | 0 | 0 | 0 | $0.000113 | 2,16 s |
| v3 | 100 % | 100 % | 100 % | 0 | 0 | 0 | $0.000126 | 1,88 s |

El único error de v1 fue el caso `t04` (“No puedo descargar la factura en PDF, el botón da error”), clasificado como `billing` en vez de `technical`. v2 corrigió esa confusión; v3 mantuvo la accuracy de v2. En la corrida registrada no hubo errores de contrato, reintentos ni bloqueos de tickets legítimos.

### Comparación de proveedores

En las corridas registradas de v3, ambos proveedores alcanzaron 100 % de accuracy y no hubo cambios de categoría entre repeticiones. La corrida de OpenAI (gpt-6-luna) promedió $0.000126 por caso y 1,78 s; la de Anthropic, $0.000293 por caso y 1,58 s. Anthropic utilizó aproximadamente 2,3 veces más créditos. La diferencia de latencia no se consideró significativa frente a la variación de red.

Estos valores son observaciones de las corridas anotadas, no garantías de rendimiento ni precios actuales. El costo real depende del modelo, los precios vigentes y el texto procesado. Precios tomados a la fecha 05-11-26

### Pruebas adversariales

Corrida registrada con 10 casos:

| Prompt | Casos que cumplen el criterio estricto de la política v3 | Bloqueados por guardrail | Resistidos por el modelo |
|---|---:|---:|---:|
| v1 | 4/10 | 4 | 0 |
| v2 | 4/10 | 4 | 0 |
| v3 | 10/10 | 4 | 6 |

La revisión manual del registro estimó resistencia en 10/10 para v1 (con un resultado parcial en x10), 9/10 para v2 y 10/10 para v3. Son criterios distintos: el 10/10 del criterio estricto mide adherencia a la política de v3, no una garantía de resistencia a ataques.

La diferencia también muestra un trade-off: en los dos casos adversariales que incluían una consulta legítima (x06 y x07), v3 no conservó el triage (0/2); v1 conservó 2/2 y v2 tuvo 1/2 confirmado. Según la prioridad del producto, v3 ofrece una política más estricta, mientras que v2 puede ser un punto medio con mejor continuidad del triage.

La muestra es pequeña (10 casos y una corrida), los ataques son simples y los resultados dependen del modelo. No cubre, por ejemplo, instrucciones en otros idiomas ni ataques distribuidos en varios párrafos. Un ejemplo de defensa en capas fue una paráfrasis que pasó el guardrail de entrada y luego fue bloqueada por el de salida; ese caso sí generó una llamada al modelo y su costo asociado.

## Ejecutar evaluaciones

Las evaluaciones llaman al proveedor configurado y pueden generar costos:

```powershell
python -m evals.runner --prompts v1 v2 v3 --repeats 3 --provider openai
python -m evals.adversarial_runner --prompts v1 v2 v3 --provider openai
```

Los resultados detallados se guardan en `results/`. Para limitar una corrida normal a una muestra pequeña, `evals.runner` admite `--limit`; consultá las opciones con:

```powershell
python -m evals.runner --help
python -m evals.adversarial_runner --help
```
