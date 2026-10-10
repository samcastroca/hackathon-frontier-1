"""Calibra coordenadas de un modelo: pide la posición de un texto visible, hace clic y guarda la captura."""
import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.cli import desktop_env, reset_desktop  # noqa: E402
from app.llm import LLM, parse_json  # noqa: E402
from app.rfb import RFBClient, ws_url  # noqa: E402
from app.screen import to_png_b64, wait_stable  # noqa: E402

PROMPT = ("La imagen es una captura de pantalla de {w}x{h} píxeles. Devuelve solo JSON "
          '{{"x": <número>, "y": <número>}} con el centro del texto "{target}". '
          "Usa las coordenadas que usarías para hacer clic ahí.")


async def run(model: str, target: str, expected: tuple[int, int]) -> None:
    base, password, token = desktop_env()
    await reset_desktop(base, token)
    client = RFBClient(ws_url(base), password)
    await client.connect()
    llm = LLM()
    try:
        img = await wait_stable(client)
        w, h = img.size
        raw = await llm.chat(model, [{"role": "user", "content": [
            {"type": "text", "text": PROMPT.format(w=w, h=h, target=target)},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{to_png_b64(img)}"}}]}],
            max_tokens=100)
        p = parse_json(raw)
        x, y = float(p["x"]), float(p["y"])
        ex, ey = expected
        modes = {"pixels": (x, y), "norm1000": (x * w / 1000, y * h / 1000), "norm1": (x * w, y * h)}
        mode = min(modes, key=lambda m: abs(modes[m][0] - ex) + abs(modes[m][1] - ey))
        px, py = (round(v) for v in modes[mode])
        call = llm.calls[-1]
        print(f"{model}: crudo=({x:g}, {y:g}) → modo {mode} → ({px}, {py}); esperado {expected}; "
              f"error {abs(px - ex) + abs(py - ey)} px; {call.latencia:.2f} s; USD {call.usd:.5f}")
        await client.click(px, py)
        out = ROOT / "runs" / "calibracion"
        out.mkdir(parents=True, exist_ok=True)
        (await wait_stable(client)).save(out / f"{model.replace('/', '_')}.png")
    finally:
        await llm.close()
        await client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--target", default="Ayuda", help="texto visible en la captura")
    parser.add_argument("--expected", default="384,48", help="posición real en píxeles x,y")
    args = parser.parse_args()
    asyncio.run(run(args.model, args.target, tuple(int(v) for v in args.expected.split(","))))


if __name__ == "__main__":
    main()
