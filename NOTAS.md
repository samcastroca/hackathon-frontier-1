# Notas de avance

| Fase | Estado | Hora | Resultado | Plan B |
| ---- | ------ | ---- | --------- | ------ |
| 0 · Setup del repo | hecha | | Esqueleto, docs y `scripts/check_desktop.py` | — |
| 1 · Conexión RFB | hecha | 2026-10-10 | `demo_rfb.py` OK a 1280×800: handshake 1.2–2.0 s, primer frame 0.9–1.6 s, `wait_stable` ~0.7 s, clic 0.16 s. Ctrl+A + `type_text` verificado en un campo real: «Papelería # ñ Ñandú €» exacto y sin concatenar | Playwright + noVNC si el handshake no sale (no hizo falta) |
| 2 · Agente | hecha | 16:45 | Tema v4.2 desde 16:24. Tras el guardrail de doble confirmación, haiku pasa E1 (2/2) y E5. Recomendado MODEL_MAIN = haiku-5.5 (ver `INCIDENTE.md`) | Si haiku vuelve a fallar en el tema nuevo: sonnet-5.5 como MAIN |
| 3 · API + worker | hecha | 2026-10-10 | Vía API: POST /tasks en 6–19 ms; sin token / token malo → 401; id inexistente → 404; cuerpo vacío → 422. E1 pasa (15 pasos, ~70 s, USD 0.0068), E5 `fallida` con las dos cédulas (7 pasos, ~35 s, USD 0.0031). Error de configuración (MODEL_MAIN vacío) → `fallida` con razón, sin colgarse | — |
| 4 · Harness | pendiente | | | |
| 5 · Despliegue | pendiente | | | |

## Fase 2 · Comparación de modelos (2026-10-10, 15:35–15:40)

Calibración (`scripts/calibrate.py`): los 3 devuelven **píxeles** (error 1–2 px), sin normalizar.
Razonamiento: `none` en haiku-5.5 y gpt-6-luna; sonnet-5.5 no deja desactivarlo → `minimal`.
MODEL_STRONG = sonnet-5.5 en todas las corridas (no hizo falta escalar: 0 atascos).

**Ojo:** estas corridas son sobre el **tema anterior** (v3.9). Las del tema nuevo (v4.2) están
en `INCIDENTE.md`.

| Modelo | Prueba | Pasa | Pasos | Segundos | Latencia/paso | USD |
| ------ | ------ | ---- | ----- | -------- | ------------- | --- |
| claude-haiku-5.5 | E1 | sí | 17 | 80.3 | 2.56 s | 0.0077 |
| gpt-6-luna | E1 | sí | 18 | 144.7 | 3.02 s | 0.0094 |
| claude-sonnet-5.5 | E1 | sí | 13 | 71.3 | 3.30 s | 0.1065 |
| claude-haiku-5.5 | E5 | sí | 6 | 28.0 | 2.75 s | 0.0026 |
| gpt-6-luna | E5 | sí | 6 | 51.3 | 3.31 s | 0.0032 |
| claude-sonnet-5.5 | E5 | sí | 6 | 34.7 | 3.91 s | 0.0505 |

Recomendación: **MODEL_MAIN = anthropic/claude-haiku-5.5**. Todos pasan; en tiempo haiku y
sonnet empatan (108 s vs 106 s sumando E1+E5, una corrida cada uno, dentro del ruido) y haiku
cuesta ~15× menos. gpt-6-luna es el más lento.
