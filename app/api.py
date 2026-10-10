"""API FastAPI: auth Bearer, GET /health, POST /tasks (<2 s) y GET /tasks/{task_id}."""
import asyncio
import logging
import os
import secrets
import sys
import time

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

load_dotenv()
logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")

from app import store, worker  # noqa: E402  (después de load_dotenv)


def auth(authorization: str | None = Header(default=None)) -> None:
    token = os.getenv("API_TOKEN", "")
    scheme, _, valor = (authorization or "").partition(" ")
    if not token or scheme.lower() != "bearer" or not secrets.compare_digest(valor.encode(), token.encode()):
        raise HTTPException(401, "token inválido", headers={"WWW-Authenticate": "Bearer"})


app = FastAPI(title="Agente sin API")
_background: set[asyncio.Task] = set()


class Escritorio(BaseModel):
    url: str = Field(min_length=1)
    password: str


class NuevaTarea(BaseModel):
    tarea: str = Field(min_length=1)
    escritorio: Escritorio


@app.get("/health")  # sin auth: el healthcheck de Railway no manda token
async def health():
    return {"ok": True}


@app.post("/tasks", dependencies=[Depends(auth)])
async def crear_tarea(body: NuevaTarea):
    t0 = time.monotonic()
    t = store.crear(body.tarea)
    job = asyncio.create_task(worker.run(t.task_id, body.tarea, body.escritorio.model_dump(), t0))
    _background.add(job)
    job.add_done_callback(_background.discard)
    return {"task_id": t.task_id}


@app.get("/tasks/{task_id}", dependencies=[Depends(auth)])
async def ver_tarea(task_id: str):
    t = store.get(task_id)
    if not t:
        raise HTTPException(404, "tarea no encontrada")
    return {"estado": t.estado, "resumen": t.resumen}
