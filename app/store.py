"""Task store: estado, resumen, traza y costo de cada tarea, en memoria y en JSON bajo runs/."""
import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

RUNS = Path(__file__).resolve().parent.parent / "runs"


@dataclass
class Tarea:
    task_id: str
    tarea: str
    estado: str = "en_curso"
    resumen: str = ""
    creada: float = field(default_factory=time.time)
    costo: float = 0.0
    pasos: int = 0


TASKS: dict[str, Tarea] = {}


def _persistir(t: Tarea) -> None:
    out = RUNS / t.task_id
    out.mkdir(parents=True, exist_ok=True)
    (out / "task.json").write_text(json.dumps(asdict(t), ensure_ascii=False, indent=2), encoding="utf-8")


def crear(tarea: str) -> Tarea:
    t = Tarea(task_id=uuid.uuid4().hex[:12], tarea=tarea)
    TASKS[t.task_id] = t
    _persistir(t)
    return t


def get(task_id: str) -> Tarea | None:
    return TASKS.get(task_id)


def actualizar(task_id: str, **campos) -> None:
    t = TASKS[task_id]
    for k, v in campos.items():
        setattr(t, k, v)
    _persistir(t)
