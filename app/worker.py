"""Ejecuta una tarea en una sesión VNC, con lock por escritorio y reloj de cierre (240 s) y corte (270 s)."""
import asyncio
import logging
import os
import time

from app import store
from app.agent import run_task
from app.llm import Resultado
from app.rfb import RFBClient, ws_url
from app.summary import build_summary, redact

DEADLINE_S = 270
CIERRE_S = 240

log = logging.getLogger("worker")
_locks: dict[str, asyncio.Lock] = {}


async def _operar(task_id: str, tarea: str, url: str, password: str, t0: float, secrets: list[str]):
    """Un escritorio = una sesión a la vez. El VNC se cierra antes de soltar el lock."""
    async with _locks.setdefault(url, asyncio.Lock()):
        client = RFBClient(url, password)
        await client.connect()
        try:
            def on_step(n, a, modelo, usd):
                store.actualizar(task_id, pasos=n)
                log.info(redact(f"tarea {task_id} paso {n} {time.monotonic() - t0:.0f}s USD {usd:.4f} "
                                f"[{modelo}] {a.fase}/{a.accion} · {(a.pensamiento or '')[:100]}", secrets))

            return await run_task(tarea, client, deadline=t0 + DEADLINE_S, cierre=t0 + CIERRE_S,
                                  task_id=task_id, secrets=secrets, on_step=on_step)
        finally:
            await client.close()


async def run(task_id: str, tarea: str, escritorio: dict, t0: float) -> None:
    """Corre la tarea y siempre la deja en terminada o fallida; t0 es el instante de creación."""
    password = escritorio["password"]
    secrets = [password, os.getenv("API_TOKEN", ""), os.getenv("OPENROUTER_API_KEY", "")]
    estado, resumen, campos = "fallida", "", {}
    try:
        res = await asyncio.wait_for(
            _operar(task_id, tarea, ws_url(escritorio["url"]), password, t0, secrets),
            timeout=t0 + DEADLINE_S - time.monotonic())
        estado, resumen = res.estado, res.resumen
        campos = {"costo": round(res.usd, 4), "pasos": res.pasos}
    except TimeoutError:
        resumen = build_summary("fallida", Resultado(razon=f"se agotó el tiempo ({DEADLINE_S} s) antes de terminar"))
    except Exception as e:
        log.exception("tarea %s: error", task_id)
        resumen = build_summary("fallida", Resultado(razon=f"error interno: {type(e).__name__}: {str(e)[:160]}"), secrets=secrets)
    finally:
        store.actualizar(task_id, estado=estado, resumen=redact(resumen or estado, secrets), **campos)
        log.info("tarea %s: %s en %.0f s · pasos %s · USD %s", task_id, estado, time.monotonic() - t0,
                 campos.get("pasos", "-"), campos.get("costo", "-"))
