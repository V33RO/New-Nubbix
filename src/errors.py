class InvalidQueryError (Exception):
    """La consulta no se puede procesar (ej. texto vacío). No se reintenta: es culpa del caller."""

class InvalidContractError(Exception):
    """Se agotaron los reintentos sin obtener una salida que cumpla el contrato."""
