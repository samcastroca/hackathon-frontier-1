"""Guardrails que se evalúan antes de acciones que confirman (guardar, eliminar, confirmar, exportar)."""
from dataclasses import dataclass

from app.llm import Accion

MISMO_CONTROL_PX = 25


@dataclass
class Guardia:
    """Recuerda la última confirmación para no repetirla sin verificar (evita duplicados)."""
    ultima: tuple[int, int, int] | None = None  # (paso, x, y)
    verificado_desde: bool = True
    fail_revisado: bool = False

    def revisar(self, a: Accion) -> str | None:
        """Devuelve el motivo de rechazo, o None si la acción puede ejecutarse."""
        if a.accion == "fail" and self.ultima and not self.fail_revisado:
            self.fail_revisado = True
            return (f"fail rechazado una vez: en el paso {self.ultima[0]} TÚ confirmaste un cambio. Si el "
                    "registro que ves ahora tiene los datos de la tarea, es tu propio cambio, no uno "
                    "preexistente: responde done con verificado=true. Si de verdad falló, repite fail.")
        if a.fase == "verificar" and not a.confirma_cambio:
            self.verificado_desde = True
        if not (a.confirma_cambio and a.accion in ("click", "double_click", "key")):
            return None
        if self.ultima and not self.verificado_desde and a.x is not None:
            paso, x, y = self.ultima
            if abs(a.x - x) <= MISMO_CONTROL_PX and abs(a.y - y) <= MISMO_CONTROL_PX:
                return (f"Ya confirmaste en este mismo control en el paso {paso}. Muchas apps guardan "
                        "sin cerrar el formulario: antes de repetir, verifica (aviso de éxito, código "
                        "nuevo o búsqueda del registro). Repetir puede crear un duplicado.")
        return None

    def ejecutada(self, paso: int, a: Accion) -> None:
        if a.confirma_cambio and a.x is not None:
            self.ultima = (paso, a.x, a.y)
            self.verificado_desde = False
