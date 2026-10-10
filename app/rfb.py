"""Cliente RFB propio sobre websocket: handshake con DES, framebuffer, ratón y teclado."""
import asyncio
import struct
import time

from Crypto.Cipher import DES
from PIL import Image
from websockets.asyncio.client import connect

# Keysyms X11 de uso común.
BACKSPACE = 0xFF08
TAB = 0xFF09
ENTER = 0xFF0D
ESC = 0xFF1B
DELETE = 0xFFFF
HOME = 0xFF50
LEFT = 0xFF51
UP = 0xFF52
RIGHT = 0xFF53
DOWN = 0xFF54
END = 0xFF57
SHIFT_L = 0xFFE1
CTRL_L = 0xFFE3
ALT_L = 0xFFE9

_ENC_RAW = 0
_ENC_DESKTOP_SIZE = -223


class RFBError(Exception):
    """Fallo del protocolo RFB o de la autenticación."""


def keysym_for(ch: str) -> int:
    """Keysym de un carácter: ASCII y Latin-1 directos, el resto como 0x01000000 + codepoint."""
    if ch == "\n":
        return ENTER
    if ch == "\t":
        return TAB
    cp = ord(ch)
    return cp if cp < 256 else 0x01000000 + cp


def ws_url(base: str) -> str:
    """URL del websocket VNC a partir de la URL base del escritorio (https → wss + /websockify)."""
    base = base.rstrip("/")
    for http, ws in (("https://", "wss://"), ("http://", "ws://")):
        if base.startswith(http):
            base = ws + base[len(http):]
    return base if base.endswith("/websockify") else base + "/websockify"


def _vnc_key(password: str) -> bytes:
    """Clave DES de VNC: contraseña a 8 bytes con los bits de cada byte invertidos."""
    raw = password.encode("latin-1", errors="replace")[:8].ljust(8, b"\0")
    return bytes(int(f"{b:08b}"[::-1], 2) for b in raw)


class RFBClient:
    def __init__(self, url: str, password: str):
        self.url = url
        self._password = password
        self._ws = None
        self._buf = bytearray()
        self._reader_task: asyncio.Task | None = None
        self._error: BaseException | None = None
        self._buttons = 0
        self.width = 0
        self.height = 0
        self.name = ""
        self._fb = bytearray()
        self.updates = 0
        self.last_update = 0.0
        self.first_frame = asyncio.Event()

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, *exc):
        await self.close()

    # --- transporte ---

    async def _read_exact(self, n: int) -> bytes:
        while len(self._buf) < n:
            msg = await self._ws.recv()
            self._buf += msg if isinstance(msg, bytes) else msg.encode("latin-1")
        data = bytes(self._buf[:n])
        del self._buf[:n]
        return data

    async def _send(self, data: bytes) -> None:
        if self._error:
            raise RFBError(f"conexión RFB caída: {self._error!r}") from self._error
        await self._ws.send(data)

    async def _read_reason(self) -> str:
        (n,) = struct.unpack(">I", await self._read_exact(4))
        return (await self._read_exact(n)).decode("utf-8", errors="replace")

    # --- handshake ---

    async def connect(self) -> None:
        self._ws = await connect(self.url, subprotocols=["binary"], max_size=None)
        try:
            await self._handshake()
        except BaseException:
            await self._ws.close()
            raise
        self._reader_task = asyncio.create_task(self._reader())

    async def reconnect(self) -> None:
        """Cierra lo que quede de la conexión caída y abre una nueva con el mismo escritorio."""
        try:
            await self.close()
        except Exception:
            pass
        self._buf, self._error, self._buttons = bytearray(), None, 0
        self.first_frame = asyncio.Event()
        await self.connect()

    async def _handshake(self) -> None:
        version = await self._read_exact(12)
        if not version.startswith(b"RFB "):
            raise RFBError(f"versión RFB inválida: {version!r}")
        legacy = version[4:11] == b"003.003"
        await self._ws.send(b"RFB 003.003\n" if legacy else b"RFB 003.008\n")

        if legacy:
            (sec,) = struct.unpack(">I", await self._read_exact(4))
            if sec == 0:
                raise RFBError(f"el servidor rechazó la conexión: {await self._read_reason()}")
        else:
            (count,) = await self._read_exact(1)
            if count == 0:
                raise RFBError(f"el servidor rechazó la conexión: {await self._read_reason()}")
            offered = list(await self._read_exact(count))
            sec = 2 if 2 in offered else 1 if 1 in offered else None
            if sec is None:
                raise RFBError(f"tipos de seguridad no soportados: {offered}")
            await self._ws.send(bytes([sec]))

        if sec == 2:
            challenge = await self._read_exact(16)
            cipher = DES.new(_vnc_key(self._password), DES.MODE_ECB)
            await self._ws.send(cipher.encrypt(challenge))
        elif sec != 1:
            raise RFBError(f"tipo de seguridad no soportado: {sec}")

        # En 3.3 con seguridad None no hay SecurityResult.
        if sec == 2 or not legacy:
            (result,) = struct.unpack(">I", await self._read_exact(4))
            if result != 0:
                reason = "" if legacy else await self._read_reason()
                raise RFBError(f"autenticación VNC fallida: {reason or 'sin razón del servidor'}")

        await self._ws.send(b"\x01")  # ClientInit, shared=1
        w, h = struct.unpack(">HH", await self._read_exact(4))
        await self._read_exact(16)  # pixel format del servidor, se reemplaza abajo
        (name_len,) = struct.unpack(">I", await self._read_exact(4))
        self.name = (await self._read_exact(name_len)).decode("utf-8", errors="replace")
        self._resize(w, h)

        # 32 bpp, depth 24, little-endian, true colour, max 255, shifts R16 G8 B0 → bytes B G R X.
        pixel_format = struct.pack(">BBBBHHHBBB3x", 32, 24, 0, 1, 255, 255, 255, 16, 8, 0)
        await self._ws.send(b"\x00\x00\x00\x00" + pixel_format)
        encodings = [_ENC_RAW, _ENC_DESKTOP_SIZE]
        await self._ws.send(struct.pack(f">BxH{len(encodings)}i", 2, len(encodings), *encodings))
        await self._request_update(incremental=False)

    def _resize(self, w: int, h: int) -> None:
        self.width, self.height = w, h
        self._fb = bytearray(w * h * 4)

    async def _request_update(self, incremental: bool) -> None:
        await self._ws.send(struct.pack(">BBHHHH", 3, int(incremental), 0, 0, self.width, self.height))

    # --- mensajes del servidor ---

    async def _reader(self) -> None:
        try:
            while True:
                (msg_type,) = await self._read_exact(1)
                if msg_type == 0:
                    await self._framebuffer_update()
                elif msg_type == 1:  # SetColourMapEntries
                    _, n = struct.unpack(">xHH", await self._read_exact(5))
                    await self._read_exact(n * 6)
                elif msg_type == 2:  # Bell
                    pass
                elif msg_type == 3:  # ServerCutText
                    (n,) = struct.unpack(">3xI", await self._read_exact(7))
                    await self._read_exact(n)
                else:
                    raise RFBError(f"mensaje RFB desconocido: {msg_type}")
        except asyncio.CancelledError:
            raise
        except BaseException as e:
            self._error = e

    async def _framebuffer_update(self) -> None:
        (n_rects,) = struct.unpack(">xH", await self._read_exact(3))
        full_refresh = False
        for _ in range(n_rects):
            x, y, w, h, enc = struct.unpack(">HHHHi", await self._read_exact(12))
            if enc == _ENC_RAW:
                data = await self._read_exact(w * h * 4)
                stride, row = self.width * 4, w * 4
                for r in range(h):
                    start = (y + r) * stride + x * 4
                    self._fb[start:start + row] = data[r * row:(r + 1) * row]
            elif enc == _ENC_DESKTOP_SIZE:
                self._resize(w, h)
                full_refresh = True
            else:
                raise RFBError(f"encoding no pedido: {enc}")
        self.updates += 1
        self.last_update = time.monotonic()
        self.first_frame.set()
        await self._request_update(incremental=not full_refresh)

    # --- API pública ---

    def screenshot(self) -> Image.Image:
        """Copia del framebuffer actual como imagen RGB."""
        if self._error:
            raise RFBError(f"conexión RFB caída: {self._error!r}") from self._error
        return Image.frombytes("RGB", (self.width, self.height), bytes(self._fb), "raw", "BGRX")

    def _clamp(self, x: int, y: int) -> tuple[int, int]:
        return max(0, min(int(x), self.width - 1)), max(0, min(int(y), self.height - 1))

    async def _pointer(self, x: int, y: int, mask: int) -> None:
        x, y = self._clamp(x, y)
        await self._send(struct.pack(">BBHH", 5, mask, x, y))

    async def move(self, x: int, y: int) -> None:
        await self._pointer(x, y, self._buttons)

    async def click(self, x: int, y: int, button: int = 1, hold_ms: int = 150) -> None:
        bit = 1 << (button - 1)
        await self._pointer(x, y, self._buttons)
        await self._pointer(x, y, self._buttons | bit)
        await asyncio.sleep(hold_ms / 1000)
        await self._pointer(x, y, self._buttons)

    async def double_click(self, x: int, y: int) -> None:
        await self.click(x, y, hold_ms=150)
        await asyncio.sleep(0.08)
        await self.click(x, y, hold_ms=150)

    async def scroll(self, x: int, y: int, dy: int) -> None:
        """dy < 0 sube (botón 4), dy > 0 baja (botón 5); un paso de rueda por unidad."""
        button = 4 if dy < 0 else 5
        for _ in range(abs(dy)):
            await self.click(x, y, button=button, hold_ms=30)
            await asyncio.sleep(0.03)

    async def _key_event(self, keysym: int, down: bool) -> None:
        await self._send(struct.pack(">BBxxI", 4, int(down), keysym))

    async def key(self, *keysyms: int) -> None:
        """Combinación: presiona en orden y suelta en orden inverso (ej. key(CTRL_L, ord('a')))."""
        for k in keysyms:
            await self._key_event(k, True)
            await asyncio.sleep(0.02)
        for k in reversed(keysyms):
            await self._key_event(k, False)
            await asyncio.sleep(0.02)

    async def type_text(self, text: str, delay: float = 0.03) -> None:
        for ch in text:
            k = keysym_for(ch)
            await self._key_event(k, True)
            await self._key_event(k, False)
            await asyncio.sleep(delay)

    async def close(self) -> None:
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
        if self._ws:
            await self._ws.close()
