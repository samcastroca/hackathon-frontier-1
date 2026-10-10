"""Harness: reset, POST /tasks, poll, /__check, validación local del resumen y métricas."""
import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.rfb import ws_url  # noqa: E402

PRUEBAS = ROOT / "pruebas"
RESULTADOS = Path(__file__).resolve().parent / "resultados"
RUNS = ROOT / "runs"
POLL_S = 5
LIMITE_S = 300
NUM_RE = re.compile(r"-?\d+(?:[.,]\d+)?")


def cargar_pruebas(only: str | None) -> list[dict]:
    pruebas = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(PRUEBAS.glob("*.json"))]
    if only:
        ids = {i.strip().upper() for i in only.split(",")}
        pruebas = [p for p in pruebas if p["id"].upper() in ids]
    return pruebas


def linea_respuesta(resumen: str) -> str | None:
    for linea in resumen.splitlines():
        if linea.strip().lower().startswith("respuesta:"):
            return linea.split(":", 1)[1].strip()
    return None


def validar_local(prueba: dict, estado: str, resumen: str, secretos: list[str]) -> list[str]:
    """Lo que el evaluador mira del estado y el resumen. Devuelve la lista de fallos."""
    fallos = []
    if estado != prueba["estado_esperado"]:
        fallos.append(f"estado {estado} ≠ {prueba['estado_esperado']}")
    resp = linea_respuesta(resumen)
    esperada = prueba.get("respuesta_esperada")
    if esperada is not None:
        if resp is None:
            fallos.append("falta la línea respuesta:")
        elif NUM_RE.fullmatch(esperada.strip()):
            m = NUM_RE.match(resp)
            if not m or m.group(0).replace(",", ".") != esperada.strip().replace(",", "."):
                fallos.append(f"respuesta «{resp}» no empieza por {esperada}")
        elif resp.lower() != esperada.strip().lower():
            fallos.append(f"respuesta «{resp}» ≠ «{esperada}»")
    faltan = [c for c in prueba.get("claves_razon", []) if c not in resumen]
    if faltan:
        fallos.append(f"faltan claves en el resumen: {', '.join(faltan)}")
    es_pregunta = "?" in prueba["instruccion"] or "¿" in prueba["instruccion"]
    if prueba["estado_esperado"] == "fallida" and es_pregunta and resp is not None:
        fallos.append("pregunta sin respuesta posible trae línea respuesta:")
    if any(s and s in resumen for s in secretos):
        fallos.append("el resumen contiene un secreto")
    return fallos


def correr(prueba: dict, api: httpx.Client, desk: httpx.Client, escritorio: dict, secretos: list[str]) -> dict:
    r = desk.post("/__reset")
    r.raise_for_status()
    t0 = time.monotonic()
    r = api.post("/tasks", json={"tarea": prueba["instruccion"], "escritorio": escritorio})
    r.raise_for_status()
    post_s = time.monotonic() - t0
    task_id = r.json()["task_id"]
    print(f"  {prueba['id']}: task_id={task_id} (POST {post_s * 1000:.0f} ms)", flush=True)

    estado, resumen = "en_curso", ""
    while time.monotonic() - t0 < LIMITE_S:
        time.sleep(POLL_S)
        t = api.get(f"/tasks/{task_id}").json()
        estado, resumen = t["estado"], t["resumen"]
        if estado != "en_curso":
            break
    else:
        estado = "timeout"
    segundos = time.monotonic() - t0

    check = desk.post("/__check", json=prueba).json()
    checks = {c["nombre"]: c["ok"] for c in check.get("checks", [])}
    fallos = validar_local(prueba, estado, resumen, secretos)
    correcta = bool(check.get("pass")) and not fallos

    local = RUNS / task_id / "task.json"
    meta = json.loads(local.read_text(encoding="utf-8")) if local.exists() else {}
    return {
        "id": prueba["id"], "task_id": task_id, "correcta": correcta,
        "falso_exito": estado == "terminada" and not correcta,
        "check_pass": bool(check.get("pass")), "checks": checks, "fallos_locales": fallos,
        "estado": estado, "respuesta": linea_respuesta(resumen), "resumen": resumen,
        "segundos": round(segundos, 1), "post_ms": round(post_s * 1000),
        "pasos": meta.get("pasos"), "usd": meta.get("costo"),
    }


def _check(checks: dict, palabra: str) -> str:
    for nombre, ok in checks.items():
        if palabra in nombre:
            return "ok" if ok else "NO"
    return "-"


def percentil(valores: list[float], p: float) -> float:
    v = sorted(valores)
    return v[min(len(v) - 1, round(p * (len(v) - 1)))] if v else 0.0


def imprimir(corridas: list[dict], resumen: dict) -> None:
    cols = ["id", "correcta", "cambios", "fuera", "duplic.", "estado", "respuesta", "s", "pasos", "USD"]
    filas = [[c["id"], "SÍ" if c["correcta"] else "no", _check(c["checks"], "cambios"),
              _check(c["checks"], "fuera"), _check(c["checks"], "duplicados"), c["estado"],
              (c["respuesta"] or "-")[:24], f"{c['segundos']:.0f}", str(c["pasos"] or "-"),
              f"{c['usd']:.4f}" if c["usd"] is not None else "-"] for c in corridas]
    anchos = [max(len(str(x)) for x in col) for col in zip(cols, *filas)]
    for fila in [cols, *filas]:
        print("  ".join(str(x).ljust(a) for x, a in zip(fila, anchos)))
    for c in corridas:
        if c["fallos_locales"]:
            print(f"- {c['id']} ({c['task_id']}): {'; '.join(c['fallos_locales'])}")
    print(f"\nCorrectas {resumen['correctas']}/{resumen['total']} ({resumen['pct']:.0f} %) · "
          f"falsos éxitos {resumen['falsos_exitos']} · p50 {resumen['p50_s']:.0f} s · "
          f"p95 {resumen['p95_s']:.0f} s · USD {resumen['usd_total']:.4f}")


def anotar_notas(resumen: dict, ids: list[str]) -> None:
    notas = ROOT / "NOTAS.md"
    texto = notas.read_text(encoding="utf-8")
    if "## Harness · corridas" not in texto:
        texto = texto.rstrip() + "\n\n## Harness · corridas\n"
    linea = (f"- {datetime.now():%Y-%m-%d %H:%M} · {','.join(ids)} · correctas "
             f"{resumen['correctas']}/{resumen['total']} · falsos éxitos {resumen['falsos_exitos']} · "
             f"p50/p95 {resumen['p50_s']:.0f}/{resumen['p95_s']:.0f} s · USD {resumen['usd_total']:.4f} · "
             f"{os.getenv('MODEL_MAIN', '?')}\n")
    notas.write_text(texto.rstrip("\n") + "\n" + linea, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--api", required=True, help="URL base de nuestra API, ej. http://localhost:8000")
    ap.add_argument("--only", help="ids separados por coma, ej. E1,E3")
    ap.add_argument("--repeat", type=int, default=1)
    args = ap.parse_args()

    load_dotenv(ROOT / ".env")
    env = {n: os.getenv(n, "") for n in ("API_TOKEN", "DESKTOP_BASE_URL", "DESKTOP_PASSWORD", "DESKTOP_TOKEN")}
    faltan = [n for n, v in env.items() if not v]
    if faltan:
        print(f"Faltan variables en .env: {', '.join(faltan)}")
        return 1
    secretos = [env["API_TOKEN"], env["DESKTOP_PASSWORD"], env["DESKTOP_TOKEN"], os.getenv("OPENROUTER_API_KEY", "")]
    escritorio = {"url": ws_url(env["DESKTOP_BASE_URL"]), "password": env["DESKTOP_PASSWORD"]}
    pruebas = cargar_pruebas(args.only)
    if not pruebas:
        print("No hay pruebas que coincidan con --only")
        return 1

    corridas = []
    with httpx.Client(base_url=args.api.rstrip("/"), timeout=30,
                      headers={"Authorization": f"Bearer {env['API_TOKEN']}"}) as api, \
         httpx.Client(base_url=env["DESKTOP_BASE_URL"].rstrip("/"), timeout=60,
                      headers={"Authorization": f"Bearer {env['DESKTOP_TOKEN']}"}) as desk:
        for rep in range(args.repeat):
            for prueba in pruebas:
                corridas.append(correr(prueba, api, desk, escritorio, secretos))

    tiempos = [c["segundos"] for c in corridas]
    correctas = sum(c["correcta"] for c in corridas)
    resumen = {
        "total": len(corridas), "correctas": correctas, "pct": 100 * correctas / len(corridas),
        "falsos_exitos": sum(c["falso_exito"] for c in corridas),
        "p50_s": percentil(tiempos, 0.5), "p95_s": percentil(tiempos, 0.95),
        "usd_total": round(sum(c["usd"] or 0 for c in corridas), 4),
        "model_main": os.getenv("MODEL_MAIN"),
    }
    print()
    imprimir(corridas, resumen)

    RESULTADOS.mkdir(exist_ok=True)
    salida = RESULTADOS / f"{datetime.now():%Y%m%d-%H%M%S}.json"
    salida.write_text(json.dumps({"resumen": resumen, "corridas": corridas}, ensure_ascii=False, indent=2),
                      encoding="utf-8")
    anotar_notas(resumen, [p["id"] for p in pruebas])
    print(f"Resultado en {salida.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
