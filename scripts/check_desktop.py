"""Comprueba el escritorio de pruebas: GET /health y POST /__reset, sin imprimir secretos."""
import os
import sys

import httpx
from dotenv import load_dotenv


def main() -> int:
    load_dotenv()
    base = os.getenv("DESKTOP_BASE_URL", "").rstrip("/")
    token = os.getenv("DESKTOP_TOKEN", "")
    missing = [n for n, v in (("DESKTOP_BASE_URL", base), ("DESKTOP_TOKEN", token)) if not v]
    if missing:
        print(f"Faltan variables en .env: {', '.join(missing)}")
        return 1

    ok = True
    with httpx.Client(base_url=base, headers={"Authorization": f"Bearer {token}"}, timeout=60) as client:
        for method, path in (("GET", "/health"), ("POST", "/__reset")):
            try:
                r = client.request(method, path)
            except httpx.HTTPError as e:
                print(f"{method} {path} -> error de red ({type(e).__name__})")
                ok = False
                continue
            print(f"{method} {path} -> {r.status_code} {r.text[:200]}")
            ok = ok and r.is_success
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
