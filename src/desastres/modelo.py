"""Modelo canónico de evento, común a todas las fuentes."""

from __future__ import annotations

import logging
import math
import re
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone

from .paises import CODIGOS_POR_NOMBRE, CODIGOS_VALIDOS

log = logging.getLogger(__name__)

# Tipos de amenaza normalizados. Cada fuente traduce su vocabulario a estos.
TIPO_SISMO = "sismo"
TIPO_CICLON = "ciclon"
TIPO_INUNDACION = "inundacion"
TIPO_VOLCAN = "volcan"
TIPO_INCENDIO = "incendio"
TIPO_SEQUIA = "sequia"
TIPO_DERRUMBE = "derrumbe"
TIPO_OTRO = "otro"

TIPOS = (
    TIPO_SISMO,
    TIPO_CICLON,
    TIPO_INUNDACION,
    TIPO_VOLCAN,
    TIPO_INCENDIO,
    TIPO_SEQUIA,
    TIPO_DERRUMBE,
    TIPO_OTRO,
)

# Niveles de alerta normalizados, de menor a mayor.
ALERTAS = ("verde", "amarilla", "naranja", "roja")


@dataclass
class Evento:
    """Un evento de desastre natural, ya normalizado.

    `id` incluye el prefijo de la fuente (`usgs:...`, `gdacs:...`) para que dos
    fuentes nunca colisionen aunque reutilicen el mismo identificador interno.

    `id_agrupado` identifica el fenómeno del mundo real, sin el episodio que
    GDACS le agrega a cada republicación. Es la clave a la que hay que colgar
    los comentarios de la app: si no, un ciclón de cinco días desparrama sus
    comentarios entre veinte "eventos" distintos.
    """

    id: str
    fuente: str
    tipo: str
    titulo: str
    fecha_evento: str
    url: str
    id_agrupado: str = ""
    lugar: str = ""
    # Texto tal como lo informa la fuente. Sirve para mostrar, no para filtrar:
    # USGS pone estados de EE. UU. ("Alaska", "CA") donde debería ir el país.
    pais: str = ""
    # Códigos ISO-3166 alfa-2. **Este es el campo para filtrar**; es lista
    # porque un ciclón o una sequía pueden abarcar varios países.
    paises: list[str] = field(default_factory=list)
    magnitud: float | None = None
    unidad_magnitud: str = ""
    nivel_alerta: str = ""
    latitud: float | None = None
    longitud: float | None = None
    profundidad_km: float | None = None
    fecha_actualizacion: str = ""
    visto_por_primera_vez: str = ""
    # Momento en que este registro cambió por última vez, NO la última vez que
    # se lo vio en el feed: si se lo revisita idéntico, el valor no se toca.
    # Tocarlo en cada corrida haría que las decenas de miles de filas del
    # histórico cambiaran cada hora, y git no podría comprimir nada.
    cambiado_por_ultima_vez: str = ""
    # Imágenes propias del evento que publica la fuente (mapas y logos de
    # GDACS). Solo lo que no se puede derivar: la foto satelital la arma el
    # cliente con la plantilla del feed, así no se repite mil veces.
    media: dict = field(default_factory=dict)
    # Campos crudos que no encajan en el modelo pero conviene no perder.
    extra: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id_agrupado:
            self.id_agrupado = self.id

    def como_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def desde_dict(cls, datos: dict) -> Evento:
        conocidos = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in datos.items() if k in conocidos})


# Orden fijo de columnas del CSV. `extra` y `media` se omiten: son anidados y
# varían por fuente, y una planilla no sabe qué hacer con un dict.
CAMPOS_ANIDADOS = ("extra", "media")
CAMPOS_CSV = tuple(f.name for f in fields(Evento) if f.name not in CAMPOS_ANIDADOS)


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


def codigos_de_pais(texto: object) -> list[str]:
    """Traduce el país que informa una fuente a códigos ISO-3166 alfa-2.

    Devuelve una lista porque GDACS publica eventos multipaís en un solo campo
    ("Australia, Indonesia, Cambodia, Laos"), y un ciclón o una sequía
    efectivamente abarcan varios países.

    Intenta primero con la cadena entera —así "The Democratic Republic of
    Congo" no se parte en pedazos— y recién después separa por comas.
    """
    if not texto:
        return []

    crudo = str(texto).strip()
    directo = _resolver(crudo)
    if directo:
        return [directo]

    codigos: list[str] = []
    for parte in crudo.split(","):
        if not parte.strip():
            continue
        codigo = _resolver(parte)
        if codigo is None:
            log.debug("país no reconocido: %r (de %r)", parte.strip(), crudo)
            continue
        if codigo not in codigos:
            codigos.append(codigo)

    return codigos


def _resolver(nombre: str) -> str | None:
    """Resuelve un nombre suelto a alfa-2, con dos reglas de rescate."""
    limpio = nombre.strip()
    if not limpio:
        return None

    codigo = CODIGOS_POR_NOMBRE.get(limpio.lower())
    if codigo:
        return codigo

    # USGS etiqueta zonas sísmicas como "New Zealand region" o "Chile region".
    sin_sufijo = re.sub(r"\s+region$", "", limpio, flags=re.IGNORECASE)
    if sin_sufijo != limpio:
        codigo = CODIGOS_POR_NOMBRE.get(sin_sufijo.lower())
        if codigo:
            return codigo

    # Algunas fuentes ya publican el alfa-2 ("Baja California, MX"). Se prueba
    # último para que los estados de EE. UU. ganen: "CA" es California, no
    # Canadá, porque USGS a Canadá lo escribe con el nombre completo.
    if len(limpio) == 2 and limpio.upper() in CODIGOS_VALIDOS:
        return limpio.upper()

    return None


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
