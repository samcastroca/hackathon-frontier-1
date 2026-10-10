"""Smoke test contra la API desplegada: auth, latencia de POST /tasks y E1 de punta a punta.

Uso: python scripts/smoke_remote.py https://<dominio>
"""
import json
import os
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.rfb import ws_url  # noqa: E402
from app.summary import redact  # noqa: E402

POLL_S = 5
LIMITE_S = 300


def check(nombre: str, ok: bool, detalle: str = "") -> bool:
    print(f"{'OK   ' if ok else 'FALLA'} {nombre} {detalle}", flush=True)
    return ok


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 1
    api_url = sys.argv[1].rstrip("/")
    load_dotenv(ROOT / ".env")
    token, base = os.getenv("API_TOKEN", ""), os.getenv("DESKTOP_BASE_URL", "").rstrip("/")
    password, desk_token = os.getenv("DESKTOP_PASSWORD", ""), os.getenv("DESKTOP_TOKEN", "")
    secretos = [token, password, desk_token, os.getenv("OPENROUTER_API_KEY", "")]
    prueba = json.loads((ROOT / "pruebas" / "E1-crear-cliente.json").read_text(encoding="utf-8"))
    auth = {"Authorization": f"Bearer {token}"}
    ok = True

    with httpx.Client(base_url=api_url, timeout=30) as api:
        r = api.get("/health")
        ok &= check("GET /health sin token", r.status_code == 200, str(r.status_code))
        r = api.get("/health", headers=auth)
        ok &= check("GET /health con token", r.status_code == 200, str(r.status_code))
        r = api.get("/tasks/x")
        ok &= check("GET /tasks/x sin token → 401", r.status_code == 401, str(r.status_code))

        httpx.post(f"{base}/__reset", headers={"Authorization": f"Bearer {desk_token}"}, timeout=90)
        cuerpo = {"tarea": prueba["instruccion"], "escritorio": {"url": ws_url(base), "password": password}}
        t0 = time.monotonic()
        r = api.post("/tasks", json=cuerpo, headers=auth)
        lat = time.monotonic() - t0
        ok &= check("POST /tasks < 2 s", r.status_code == 200 and lat < 2, f"{r.status_code} · {lat * 1000:.0f} ms")
        if r.status_code != 200:
            return 1
        task_id = r.json()["task_id"]

        estado, resumen = "en_curso", ""
        while estado == "en_curso" and time.monotonic() - t0 < LIMITE_S:
            time.sleep(POLL_S)
            d = api.get(f"/tasks/{task_id}", headers=auth).json()
            estado, resumen = d["estado"], d["resumen"]
            print(f"  {time.monotonic() - t0:5.0f} s  {estado}", flush=True)

    total = time.monotonic() - t0
    print(f"\ntask_id: {task_id}\nestado:  {estado}\nresumen: {redact(resumen, secretos)}\ntiempo:  {total:.0f} s")
    ok &= check("E1 estado esperado", estado == prueba["estado_esperado"], f"({prueba['estado_esperado']})")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
