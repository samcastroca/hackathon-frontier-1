"""Resumen determinista por plantilla desde datos estructurados, con redacción de secretos."""
from app.llm import Resultado


def redact(text: str, secrets) -> str:
    for s in secrets:
        if s:
            text = text.replace(s, "[oculto]")
    return text


def build_summary(estado: str, resultado: Resultado, eventos=(), secrets=()) -> str:
    """Primera línea `respuesta:` solo en tareas terminadas con respuesta; luego razón, datos y eventos."""
    lines = []
    if estado == "terminada" and resultado.respuesta:
        lines.append(f"respuesta: {resultado.respuesta}")
    if resultado.razon:
        lines.append(f"{'Hecho' if estado == 'terminada' else 'No se completó'}: {resultado.razon}")
    if resultado.claves:
        lines.append("datos: " + "; ".join(resultado.claves))
    if eventos:
        lines.append("eventos: " + "; ".join(list(eventos)[-3:]))
    return redact("\n".join(lines) or estado, secrets)
