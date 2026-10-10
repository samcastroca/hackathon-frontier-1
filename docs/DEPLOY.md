# Despliegue (Railway)

URL pública: **https://hackathon-frontier-1-production.up.railway.app**
(proyecto `charismatic-strength`, servicio `hackathon-frontier-1`, entorno `production`).

> **ADVERTENCIA — congelar a las 19:45.** No hacer push a `main` después de esa hora. Cada push
> redespliega el servicio, y las tareas viven en memoria: un redespliegue borra las tareas en curso
> y el evaluador recibe 404 al consultarlas.

## Cómo está armado

- `Dockerfile`: `python:3.11-slim`, instala `requirements.txt`, copia `app/` y arranca
  `uvicorn app.api:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1`. Un solo worker porque el
  store de tareas está en memoria.
- `railway.json` (config as code): builder `DOCKERFILE`, healthcheck en `/health` (60 s),
  1 réplica, reinicio `ON_FAILURE` (10 reintentos) y `sleepApplication: false`.
  El CLI avisa que config as code queda obsoleto en favor de `.railway/railway.ts`, pero los
  archivos siguen funcionando hasta 2026-12-01.
- `/health` responde 200 sin token (el healthcheck de Railway no manda header); el resto exige
  `Authorization: Bearer $API_TOKEN`.

## Reproducir

1. En Railway: New Project → Deploy from GitHub repo → este repo.
2. Variables del servicio (dashboard → Variables): `API_TOKEN`, `OPENROUTER_API_KEY`,
   `MODEL_MAIN`, `MODEL_STRONG`, `MAX_USD_PER_TASK`. Pegar sin espacios ni saltos de línea.
   Las variables `DESKTOP_*` no hacen falta en producción: el escritorio llega en cada `POST /tasks`.
3. Enlazar localmente: `railway link` (elegir proyecto, entorno y servicio).
4. `git push origin main` → Railway construye y despliega solo.
5. Dominio: `railway domain` (o Settings → Networking → Generate Domain).
6. Verificar: `python scripts/smoke_remote.py https://<dominio>` y luego
   `python harness/run.py --api https://<dominio>`.

## Seguir el despliegue y ver logs

```bash
railway status                 # proyecto/servicio enlazado
railway deployment list        # deployments y su estado (BUILDING, DEPLOYING, SUCCESS, FAILED)
railway logs --build           # logs del build
railway logs -d -n 100         # logs del deployment (una línea por paso de cada tarea)
railway logs --http            # logs HTTP (peticiones del evaluador)
railway deployment redeploy    # redesplegar sin push
```

Cada paso sale como
`tarea <id> paso N <s>s USD <x> [modelo] fase/acción · pensamiento corto`, y al final
`tarea <id>: <estado> en <s> s · pasos N · USD x`. Los logs pasan por la redacción de secretos.
Con el harness remoto la columna USD sale «-» (las trazas `runs/` quedan en el contenedor): el
costo se lee en estos logs.

## Plan B: túnel desde el portátil

Si Railway falla, levantar la API en local y exponerla con Cloudflare:

```bash
uvicorn app.api:app --host 0.0.0.0 --port 8000 --workers 1
cloudflared tunnel --url http://localhost:8000   # imprime una URL https://<algo>.trycloudflare.com
```

`cloudflared` no viene instalado: `winget install --id Cloudflare.cloudflared`. El portátil debe
quedar encendido, sin suspender, hasta que termine la evaluación.
