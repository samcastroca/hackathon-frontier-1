"""Gateway de modelos OpenRouter: decide la acción, valida el JSON, normaliza coordenadas y cuenta costo."""
import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Literal

import httpx
from pydantic import BaseModel, Field, ValidationError

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Cómo devuelve coordenadas cada modelo con una captura de 1280×800, medido con
# scripts/calibrate.py (clic y comprobación en la captura siguiente). Los tres devolvieron
# píxeles de la imagen con 1–2 px de error (2026-10-10, captura 1280×800 sin reescalar).
#   "pixels"   → píxeles de la imagen enviada
#   "norm1000" → 0..1000 en cada eje
#   "norm1"    → 0..1 en cada eje
COORD_MODE: dict[str, str] = {
    "anthropic/claude-haiku-5.5": "pixels",
    "anthropic/claude-sonnet-5.5": "pixels",
    "openai/gpt-6-luna": "pixels",
}

# Esfuerzo de razonamiento más bajo que acepta OpenRouter para cada modelo ("none" lo desactiva).
REASONING: dict[str, str] = {
    "anthropic/claude-haiku-5.5": "none",
    "anthropic/claude-sonnet-5.5": "minimal",  # no permite desactivarlo
    "openai/gpt-6-luna": "none",
}


class Resultado(BaseModel):
    verificado: bool = False
    respuesta: str | None = None
    razon: str = ""
    claves: list[str] = Field(default_factory=list)


class Conteo(BaseModel):
    """Filas que cumplen la condición en la página visible; el sistema las cuenta y suma."""
    pagina: str = "1"
    ids: list[str] = Field(default_factory=list)


class Accion(BaseModel):
    pensamiento: str = ""
    plan: str | None = None
    fase: Literal["orientar", "localizar", "actuar", "verificar", "reportar"] = "orientar"
    accion: Literal["click", "double_click", "type", "key", "scroll", "zoom", "wait", "done", "fail"]
    x: float | None = None
    y: float | None = None
    texto: str | None = None
    teclas: list[str] = Field(default_factory=list)
    dy: int = 0
    confirma_cambio: bool = False
    hechos_nuevos: list[str] = Field(default_factory=list)
    evento: str | None = None
    conteo: Conteo | None = None
    resultado: Resultado = Field(default_factory=Resultado)


@dataclass
class Llamada:
    modelo: str
    prompt_tokens: int
    completion_tokens: int
    usd: float
    latencia: float


@dataclass
class LLM:
    api_key: str = field(default_factory=lambda: os.environ["OPENROUTER_API_KEY"])
    calls: list[Llamada] = field(default_factory=list)

    def __post_init__(self):
        self._http = httpx.AsyncClient(timeout=60, headers={"Authorization": f"Bearer {self.api_key}"})

    @property
    def usd_total(self) -> float:
        return sum(c.usd for c in self.calls)

    async def close(self) -> None:
        await self._http.aclose()

    async def chat(self, modelo: str, messages: list[dict], max_tokens: int = 1200) -> str:
        """Una llamada a chat completions en modo JSON; registra tokens, USD y latencia."""
        body = {
            "model": modelo,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "reasoning": {"effort": REASONING.get(modelo, "none")},
        }
        t = time.perf_counter()
        r = await self._http.post(OPENROUTER_URL, json=body)
        latencia = time.perf_counter() - t
        if r.status_code != 200:
            raise RuntimeError(f"OpenRouter {r.status_code}: {r.text[:300]}")
        data = r.json()
        usage = data.get("usage") or {}
        self.calls.append(Llamada(
            modelo, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0),
            float(usage.get("cost") or 0.0), latencia,
        ))
        return data["choices"][0]["message"].get("content") or ""

    async def decidir(
        self, modelo: str, system: str, memoria: str, imagen_b64: str,
        extra_b64: str | None = None, size: tuple[int, int] = (1280, 800),
    ) -> Accion:
        content = [{"type": "text", "text": memoria},
                   {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{imagen_b64}"}}]
        if extra_b64:
            content += [{"type": "text", "text": "Zoom pedido en el paso anterior:"},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{extra_b64}"}}]
        messages = [{"role": "system", "content": system}, {"role": "user", "content": content}]

        for intento in range(2):
            raw = await self.chat(modelo, messages)
            try:
                accion = Accion.model_validate(parse_json(raw))
                return normalizar(accion, modelo, size)
            except (ValueError, ValidationError) as e:
                if intento == 0:
                    messages += [{"role": "assistant", "content": raw},
                                 {"role": "user", "content": f"JSON inválido: {str(e)[:400]}. "
                                                             "Responde solo el objeto JSON corregido."}]
        return Accion(pensamiento="JSON inválido dos veces", accion="wait")


def parse_json(raw: str) -> dict:
    """Extrae el primer objeto JSON del texto (tolera ```json ... ```)."""
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        raise ValueError("no hay objeto JSON en la respuesta")
    return json.loads(m.group(0))


def normalizar(accion: Accion, modelo: str, size: tuple[int, int]) -> Accion:
    """Convierte x, y del modo del modelo a píxeles reales de la pantalla."""
    if accion.x is None or accion.y is None:
        return accion
    w, h = size
    mode = COORD_MODE.get(modelo, "pixels")
    if mode == "norm1000":
        accion.x, accion.y = accion.x * w / 1000, accion.y * h / 1000
    elif mode == "norm1":
        accion.x, accion.y = accion.x * w, accion.y * h
    accion.x, accion.y = round(accion.x), round(accion.y)
    return accion
