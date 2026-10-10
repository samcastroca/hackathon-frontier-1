"""Captura de pantalla: wait_stable(), PNG/base64 y zoom para leer regiones."""
import asyncio
import base64
import hashlib
import io

from PIL import Image

from app.rfb import RFBClient


async def wait_stable(
    client: RFBClient, interval: float = 0.25, max_wait: float = 1.5, min_wait: float = 0.4
) -> Image.Image:
    """Espera min_wait y captura hasta que dos frames seguidos sean iguales o se agote max_wait."""
    await asyncio.sleep(min_wait)
    img = client.screenshot()
    digest = hashlib.blake2b(img.tobytes()).digest()
    waited = 0.0
    while waited < max_wait:
        await asyncio.sleep(interval)
        waited += interval
        img = client.screenshot()
        new = hashlib.blake2b(img.tobytes()).digest()
        if new == digest:
            break
        digest = new
    return img


def to_png_b64(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def zoom(img: Image.Image, x: int, y: int, w: int, h: int, factor: int = 2) -> Image.Image:
    """Recorte ampliado de una región para leer texto pequeño."""
    crop = img.crop((x, y, x + w, y + h))
    return crop.resize((w * factor, h * factor), Image.Resampling.LANCZOS)
