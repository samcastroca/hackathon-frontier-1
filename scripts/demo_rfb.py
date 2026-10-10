"""Prueba de conexión al escritorio: captura, clic en el centro y escritura opcional."""
import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

from app.rfb import CTRL_L, RFBClient, RFBError, ws_url  # noqa: E402
from app.screen import wait_stable  # noqa: E402

OUT = ROOT / "runs" / "demo"


async def run(text: str | None) -> None:
    load_dotenv(ROOT / ".env")
    base, password = os.getenv("DESKTOP_BASE_URL", ""), os.getenv("DESKTOP_PASSWORD", "")
    if not base or not password:
        sys.exit("Faltan DESKTOP_BASE_URL o DESKTOP_PASSWORD en .env")
    OUT.mkdir(parents=True, exist_ok=True)

    t = time.perf_counter()

    def step(name: str) -> None:
        nonlocal t
        now = time.perf_counter()
        print(f"{name:<28} {now - t:6.2f} s")
        t = now

    client = RFBClient(ws_url(base), password)
    await client.connect()
    step("conectar + handshake")
    try:
        print(f"escritorio: {client.name!r}  resolución: {client.width}x{client.height}")
        await asyncio.wait_for(client.first_frame.wait(), timeout=10)
        step("primer frame")
        (await wait_stable(client)).save(OUT / "0.png")
        step("0.png (estable)")

        await client.click(client.width // 2, client.height // 2)
        step("clic en el centro")
        (await wait_stable(client)).save(OUT / "1.png")
        step("1.png (estable)")

        if text is not None:
            await client.key(CTRL_L, ord("a"))
            await client.type_text(text)
            step("Ctrl+A + escribir")
            (await wait_stable(client)).save(OUT / "2.png")
            step("2.png (estable)")
        print(f"updates recibidos: {client.updates}  capturas en {OUT.relative_to(ROOT)}")
    finally:
        await client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--type", dest="text", help="texto a escribir en el campo con foco")
    args = parser.parse_args()
    try:
        asyncio.run(run(args.text))
    except RFBError as e:
        sys.exit(f"Error RFB: {e}")


if __name__ == "__main__":
    main()
