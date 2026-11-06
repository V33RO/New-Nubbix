Fecha pricing.json-04-11-26
El modelo gpt-6-Luna no admite temperature distinta del default; se omite el parámetro y la consistencia se mide en los evals.

extra="forbid": si el modelo agrega un campo inventado, falla en vez de pasar en silencio.
actions como enum cerrado: un consumidor automático (otro sistema, un dashboard) puede hacer if action == ... sin parsear texto libre. El costo es que tenés que elegir bien la lista; si un caso real no encaja, existe request_more_info y escalate_to_human como válvula.
min_length=1 en actions: nunca queda vacía; si no hay nada para hacer, el modelo tiene que decirlo explícitamente con no_action

gpt-6-luna requiere reasoning_effort=none para usar tool calling en chat completions.

