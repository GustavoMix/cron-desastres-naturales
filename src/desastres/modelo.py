"""Modelo canónico de evento, común a todas las fuentes."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone

# Tipos de amenaza normalizados. Cada fuente traduce su vocabulario a estos.
TIPO_SISMO = "sismo"
TIPO_CICLON = "ciclon"
TIPO_INUNDACION = "inundacion"
TIPO_VOLCAN = "volcan"
TIPO_INCENDIO = "incendio"
TIPO_SEQUIA = "sequia"
TIPO_OTRO = "otro"

TIPOS = (
    TIPO_SISMO,
    TIPO_CICLON,
    TIPO_INUNDACION,
    TIPO_VOLCAN,
    TIPO_INCENDIO,
    TIPO_SEQUIA,
    TIPO_OTRO,
)

# Niveles de alerta normalizados, de menor a mayor.
ALERTAS = ("verde", "amarilla", "naranja", "roja")


@dataclass
class Evento:
    """Un evento de desastre natural, ya normalizado.

    `id` incluye el prefijo de la fuente (`usgs:...`, `gdacs:...`) para que dos
    fuentes nunca colisionen aunque reutilicen el mismo identificador interno.
    """

    id: str
    fuente: str
    tipo: str
    titulo: str
    fecha_evento: str
    url: str
    lugar: str = ""
    pais: str = ""
    magnitud: float | None = None
    unidad_magnitud: str = ""
    nivel_alerta: str = ""
    latitud: float | None = None
    longitud: float | None = None
    profundidad_km: float | None = None
    fecha_actualizacion: str = ""
    visto_por_primera_vez: str = ""
    visto_por_ultima_vez: str = ""
    # Campos crudos que no encajan en el modelo pero conviene no perder.
    extra: dict = field(default_factory=dict)

    def como_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def desde_dict(cls, datos: dict) -> Evento:
        conocidos = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in datos.items() if k in conocidos})


# Orden fijo de columnas del CSV. `extra` se omite: es anidado y varía por fuente.
CAMPOS_CSV = tuple(f.name for f in fields(Evento) if f.name != "extra")


def ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


def a_iso(momento: datetime | None) -> str:
    """Serializa a ISO 8601 en UTC con sufijo `Z`, siempre al segundo."""
    if momento is None:
        return ""
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    en_utc = momento.astimezone(timezone.utc).replace(microsecond=0)
    return en_utc.isoformat().replace("+00:00", "Z")


def desde_epoch_ms(ms: object) -> str:
    """Convierte un epoch en milisegundos (formato USGS) a ISO 8601 UTC."""
    if ms is None:
        return ""
    try:
        segundos = float(ms) / 1000.0
    except (TypeError, ValueError):
        return ""
    if math.isnan(segundos) or math.isinf(segundos):
        return ""
    try:
        return a_iso(datetime.fromtimestamp(segundos, tz=timezone.utc))
    except (OverflowError, OSError, ValueError):
        return ""


def a_float(valor: object) -> float | None:
    """Castea a float tolerando `None`, cadenas vacías y basura."""
    if valor is None or valor == "":
        return None
    try:
        resultado = float(valor)
    except (TypeError, ValueError):
        return None
    if math.isnan(resultado) or math.isinf(resultado):
        return None
    return resultado


def normalizar_alerta(valor: object) -> str:
    """Traduce el nivel de alerta de cualquier fuente al vocabulario común."""
    if not valor:
        return ""
    equivalencias = {
        "green": "verde",
        "verde": "verde",
        "yellow": "amarilla",
        "amarilla": "amarilla",
        "amarillo": "amarilla",
        "orange": "naranja",
        "naranja": "naranja",
        "red": "roja",
        "roja": "roja",
        "rojo": "roja",
    }
    return equivalencias.get(str(valor).strip().lower(), "")
