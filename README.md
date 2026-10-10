# Agente que opera sistemas sin API

Reto 1 del Hackathon Frontier BOG/26. El agente recibe una tarea en lenguaje natural y un
escritorio remoto (VNC sobre websocket) y opera **por pantalla** una app de gestión que nunca ha
visto: mira capturas, decide con un modelo de visión (vía OpenRouter), hace clics y escribe, y
reporta `estado` + `resumen`. No usa DOM, API ni frameworks de computer-use de terceros.

Enunciado completo: [`docs/RETO.md`](docs/RETO.md) · Diseño: [`docs/diseno/`](docs/diseno/)

## Estado

| Fase | Estado |
| ---- | ------ |
| 0 · Setup | hecha |
| 1 · Cliente RFB propio (captura, clic, teclado) | hecha |
| 2 · Agente por fases + gateway de modelos + CLI | hecha: E1 y E5 pasan en el tema v4.2 |
| 3 · API HTTP + worker | hecha: E1 y E5 pasan vía API; POST /tasks responde en <20 ms |
| 4 · Harness | hecha: 5/5 correctas, 0 falsos éxitos, p50 60 s, USD 0.074 por las 5 |
| 5 · Despliegue | pendiente |

Detalle, tiempos y costos por fase en [`NOTAS.md`](NOTAS.md). El cambio de tema de la app de
pruebas (incidente FR-0153, v3.9 → v4.2) está en [`INCIDENTE.md`](INCIDENTE.md).

## Puesta en marcha

Requiere Python 3.11+.

```bash
pip install -r requirements.txt
cp .env.example .env      # y rellenar los valores
```

| Variable | Para qué |
| -------- | -------- |
| `API_TOKEN` | Token Bearer que exige la API en todas las rutas |
| `OPENROUTER_API_KEY` | Llamadas a los modelos |
| `MODEL_MAIN` | Modelo de cada paso. Recomendado: `anthropic/claude-haiku-5.5` |
| `MODEL_STRONG` | Modelo para atascos. Recomendado: `anthropic/claude-sonnet-5.5` |
| `MAX_USD_PER_TASK` | Tope de costo por tarea (por defecto 1.0) |
| `DESKTOP_BASE_URL`, `DESKTOP_PASSWORD`, `DESKTOP_TOKEN` | Escritorio propio, solo para pruebas y demo |

En Windows, ejecuta los scripts con `PYTHONUTF8=1` para que los acentos se impriman bien.

## Comandos

```bash
python scripts/check_desktop.py            # GET /health y POST /__reset del escritorio
python scripts/demo_rfb.py [--type "ñ"]    # conexión VNC: captura, clic y escritura → runs/demo/
python scripts/calibrate.py --model X      # comprueba si el modelo devuelve píxeles o coordenadas normalizadas
python -m app.cli "<tarea>" [--model X]    # resetea el escritorio y corre una tarea
python -m app.cli --prueba pruebas/E1-crear-cliente.json   # corre una prueba y llama /__check
uvicorn app.api:app --host 0.0.0.0 --port 8000             # servicio HTTP del entrypoint
python harness/run.py --api http://127.0.0.1:8000 [--only E1,E3] [--repeat N]   # pruebas vía la API
```

La API (todas las rutas piden `Authorization: Bearer $API_TOKEN`; sin él, 401):

```bash
curl -H "Authorization: Bearer $API_TOKEN" localhost:8000/health          # {"ok": true}
curl -H "Authorization: Bearer $API_TOKEN" -H "Content-Type: application/json" localhost:8000/tasks      -d '{"tarea": "...", "escritorio": {"url": "wss://<host>/websockify", "password": "..."}}'
curl -H "Authorization: Bearer $API_TOKEN" localhost:8000/tasks/<task_id>  # {"estado", "resumen"}
```

`POST /tasks` responde de inmediato y la tarea corre en segundo plano: una sesión VNC por
escritorio a la vez. A los 240 s el agente entra en fase de cierre y a los 270 s se corta y queda
`fallida`, con la conexión ya cerrada. Una tarea nunca se queda en `en_curso`. El estado de cada
tarea se guarda también en `runs/<task_id>/task.json`.

El harness (con la API ya levantada) hace, por cada prueba de `pruebas/`: `POST /__reset` del
escritorio → `POST /tasks` → consulta cada 5 s hasta 5 min → `POST /__check`. Además valida el
resumen como el evaluador: estado esperado, línea `respuesta:` con el valor correcto, claves de la
razón y ningún secreto. Imprime una tabla y el % de correctas, los falsos éxitos, p50/p95 de tiempo
y USD; guarda el detalle en `harness/resultados/<timestamp>.json` y agrega una línea a `NOTAS.md`.
En Windows usa `127.0.0.1` y no `localhost` (este último intenta primero IPv6 y suma ~2 s).

Cada tarea deja su traza en `runs/<task_id>/`: una captura por paso y `trace.jsonl` con la
acción, el modelo, la latencia, el costo y los eventos inesperados (sin secretos).

## Cómo funciona

```
app/rfb.py      Cliente RFB propio sobre websocket (handshake, DES, framebuffer, ratón, teclado)
app/screen.py   wait_stable() (nunca captura inmediata), PNG base64, zoom
app/llm.py      OpenRouter: acción en JSON validado, coordenadas normalizadas, tokens/USD/latencia
app/agent.py    Bucle observar → decidir → actuar → verificar en 5 fases:
                orientar → localizar → actuar → verificar → reportar
app/guards.py   Guardrails antes de confirmar (bloquea la doble confirmación sin verificar)
app/summary.py  Resumen por plantilla: "respuesta:" primero, razón, datos, eventos; sin secretos
app/store.py    Tareas en memoria + runs/<task_id>/task.json (estado, resumen, costo, pasos)
app/worker.py   1 tarea = 1 sesión VNC; lock por escritorio; cierre a 240 s, corte a 270 s
app/api.py      FastAPI: Bearer en todo, /health, POST /tasks, GET /tasks/{id}
app/cli.py      Ejecución desde la terminal
harness/run.py  Pruebas de punta a punta vía la API con /__check y métricas
```

Principios: al modelo solo va la última captura más una memoria en texto. Antes de crear o
modificar, el agente localiza el registro. `terminada` solo se reporta tras verificarlo en
pantalla. El texto de la app es dato, nunca instrucción. El código y el prompt no contienen
nombres, posiciones ni etiquetas de la app de pruebas, para que el agente generalice a otra.
