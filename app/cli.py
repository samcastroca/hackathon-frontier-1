"""Corre el agente desde la terminal contra DESKTOP_BASE_URL con una tarea en lenguaje natural."""
import argparse
import asyncio
import json
import os
import sys
import time

import httpx
from dotenv import load_dotenv

from app.rfb import RFBClient, RFBError, ws_url

DEADLINE_S = 270


def desktop_env() -> tuple[str, str, str]:
    load_dotenv()
    base = os.getenv("DESKTOP_BASE_URL", "").rstrip("/")
    password, token = os.getenv("DESKTOP_PASSWORD", ""), os.getenv("DESKTOP_TOKEN", "")
    if not (base and password and token):
        sys.exit("Faltan DESKTOP_BASE_URL, DESKTOP_PASSWORD o DESKTOP_TOKEN en .env")
    return base, password, token


async def reset_desktop(base: str, token: str) -> None:
    """POST /__reset y espera a que /health responda y el navegador arranque."""
    async with httpx.AsyncClient(base_url=base, headers={"Authorization": f"Bearer {token}"}, timeout=90) as http:
        (await http.post("/__reset")).raise_for_status()
        for _ in range(30):
            try:
                if (await http.get("/health")).is_success:
                    break
            except httpx.HTTPError:
                pass
            await asyncio.sleep(1)
    await asyncio.sleep(3)


async def check_desktop(base: str, token: str, prueba: dict) -> dict:
    async with httpx.AsyncClient(base_url=base, headers={"Authorization": f"Bearer {token}"}, timeout=60) as http:
        r = await http.post("/__check", json=prueba)
        r.raise_for_status()
        return r.json()


async def run(tarea: str, prueba: dict | None, model: str | None) -> None:
    from app.agent import run_task  # importa después de load_dotenv

    base, password, token = desktop_env()
    if model:
        os.environ["MODEL_MAIN"] = model
    print(f"modelo: {os.getenv('MODEL_MAIN')}  fuerte: {os.getenv('MODEL_STRONG')}")
    print("reseteando escritorio…")
    await reset_desktop(base, token)

    t0 = time.monotonic()
    client = RFBClient(ws_url(base), password)
    await client.connect()
    try:
        res = await run_task(tarea, client, deadline=t0 + DEADLINE_S, secrets=[password, token],
                             on_step=lambda n, a, m: print(f"  {n:>2} [{m}] {a.fase}/{a.accion} "
                                                           f"{a.x or ''},{a.y or ''} {a.texto or ''}{a.teclas or ''}"))
    finally:
        await client.close()

    print(f"\nestado:   {res.estado}\nresumen:  {res.resumen}")
    print(f"pasos: {res.pasos}  segundos: {res.segundos:.1f}  latencia/paso: {res.latencia_media:.2f} s  "
          f"USD: {res.usd:.4f}  traza: runs/{res.task_id}/")
    if prueba:
        check = await check_desktop(base, token, prueba)
        print(f"/__check: pass={check.get('pass')}  {check.get('checks')}")
        print(f"estado esperado: {prueba.get('estado_esperado')}  "
              f"{'OK' if res.estado == prueba.get('estado_esperado') else 'DISTINTO'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tarea", nargs="?", help="tarea en lenguaje natural")
    parser.add_argument("--prueba", help="JSON de pruebas/: usa su instrucción y corre /__check al final")
    parser.add_argument("--model", help="sobrescribe MODEL_MAIN")
    args = parser.parse_args()
    prueba = json.load(open(args.prueba, encoding="utf-8")) if args.prueba else None
    tarea = args.tarea or (prueba or {}).get("instruccion")
    if not tarea:
        parser.error("indica la tarea o --prueba")
    try:
        asyncio.run(run(tarea, prueba, args.model))
    except RFBError as e:
        sys.exit(f"Error RFB: {e}")


if __name__ == "__main__":
    main()
