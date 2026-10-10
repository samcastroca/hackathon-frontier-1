# Notas de avance

| Fase | Estado | Hora | Resultado | Plan B |
| ---- | ------ | ---- | --------- | ------ |
| 0 · Setup del repo | hecha | | Esqueleto, docs y `scripts/check_desktop.py` | — |
| 1 · Conexión RFB | hecha | 2026-10-10 | `demo_rfb.py` OK a 1280×800: handshake 1.2–2.0 s, primer frame 0.9–1.6 s, `wait_stable` ~0.7 s, clic 0.16 s. Ctrl+A + `type_text` verificado en un campo real: «Papelería # ñ Ñandú €» exacto y sin concatenar | Playwright + noVNC si el handshake no sale (no hizo falta) |
| 2 · Agente | hecha | 16:45 | Tema v4.2 desde 16:24. Tras el guardrail de doble confirmación, haiku pasa E1 (2/2) y E5. Recomendado MODEL_MAIN = haiku-5.5 (ver `INCIDENTE.md`) | Si haiku vuelve a fallar en el tema nuevo: sonnet-5.5 como MAIN |
| 3 · API + worker | hecha | 2026-10-10 | Vía API: POST /tasks en 6–19 ms; sin token / token malo → 401; id inexistente → 404; cuerpo vacío → 422. E1 pasa (15 pasos, ~70 s, USD 0.0068), E5 `fallida` con las dos cédulas (7 pasos, ~35 s, USD 0.0031). Error de configuración (MODEL_MAIN vacío) → `fallida` con razón, sin colgarse | — |
| 4 · Harness | hecha | 18:11 | `harness/run.py`. Final: 5/5 correctas, 0 falsos éxitos, p50/p95 60/85 s, USD 0.074 (E3 0.052 por el conteo con sonnet). Detalle abajo | Reconexión VNC si se repiten caídas (E2, 1 de ~30) |
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

## Fase 4 · Causas y arreglos (2026-10-10, 17:16–18:11)

- **E3 (respuesta 34/37/44 o `fallida` en vez de 45).** Contaba filas a ojo entre 3 páginas:
  filtraba solo por cliente, asignaba el conteo a la página equivocada, volvía atrás, se saltaba
  filas al transcribir y respondía `done` en el mismo paso en que registraba la última página.
  Arreglo genérico: un filtro por cada condición; campo `conteo {pagina, ids}` (el modelo
  transcribe y el código cuenta los ids únicos); `done` rechazado si llega con un conteo nuevo; los
  pasos con conteo los rehace MODEL_STRONG. Resultado: 4/4 y luego 3/3 en las suites.
- **E1 (`fallida` con la app correcta).** Creó el cliente y, al verificar, encontró su propio
  registro y lo tomó por uno preexistente. Arreglo: hecho persistente «en el paso N TÚ
  confirmaste un cambio» y guardrail que rechaza una vez un `fail` posterior a una confirmación.
  3/3 después del arreglo.
- **E2 (1 vez).** Se cayó la conexión VNC (`ConnectionClosedError`) en el paso 2; no es del
  agente. Sin reconexión todavía.
- En Windows el harness usa `127.0.0.1`: con `localhost` el POST tardaba 2 s (prueba IPv6 primero).

## Harness · corridas
- 2026-10-10 17:16 · E1,E2,E3,E4,E5 · correctas 4/5 · falsos éxitos 0 · p50/p95 70/95 s · USD 0.0319 · anthropic/claude-haiku-5.5
- 2026-10-10 17:20 · E3 · correctas 1/2 · falsos éxitos 0 · p50/p95 55/90 s · USD 0.0155 · anthropic/claude-haiku-5.5
- 2026-10-10 17:24 · E3 · correctas 1/3 · falsos éxitos 2 · p50/p95 65/80 s · USD 0.0206 · anthropic/claude-haiku-5.5
- 2026-10-10 17:28 · E3 · correctas 2/3 · falsos éxitos 1 · p50/p95 62/65 s · USD 0.0181 · anthropic/claude-haiku-5.5
- 2026-10-10 17:32 · E3 · correctas 2/3 · falsos éxitos 0 · p50/p95 60/70 s · USD 0.0198 · anthropic/claude-haiku-5.5
- 2026-10-10 17:43 · E1,E2,E3,E4,E5 · correctas 9/10 · falsos éxitos 1 · p50/p95 55/120 s · USD 0.0674 · anthropic/claude-haiku-5.5
- 2026-10-10 17:50 · E3 · correctas 4/4 · falsos éxitos 0 · p50/p95 85/85 s · USD 0.2247 · anthropic/claude-haiku-5.5
- 2026-10-10 18:00 · E1,E2,E3,E4,E5 · correctas 8/10 · falsos éxitos 0 · p50/p95 50/90 s · USD 0.1456 · anthropic/claude-haiku-5.5
- 2026-10-10 18:06 · E1 · correctas 3/3 · falsos éxitos 0 · p50/p95 85/105 s · USD 0.0296 · anthropic/claude-haiku-5.5
- 2026-10-10 18:11 · E1,E2,E3,E4,E5 · correctas 5/5 · falsos éxitos 0 · p50/p95 60/85 s · USD 0.0740 · anthropic/claude-haiku-5.5
