"""NASA EONET v3: eventos naturales en curso, vistos desde satélite.

API pública, sin API key: https://eonet.gsfc.nasa.gov/api/v3/events

Aporta lo que a las otras dos fuentes les falta. USGS son solo sismos; GDACS
publica lo que cruza su umbral humanitario, que deja afuera casi todos los
incendios y erupciones. EONET cataloga justo esos: incendios forestales,
volcanes en erupción, tormentas severas y hielo marino, que además son los
eventos que mejor se ven en la foto satelital.

EONET no informa país ni nivel de alerta —solo categoría, posición y fecha—, así
que estos eventos quedan sin `paises` y no matchean los filtros por país. Es
correcto: inventarles un país por proximidad sería peor que no tenerlo.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

from ..http import descargar
from ..modelo import (
    TIPO_CICLON,
    TIPO_DERRUMBE,
    TIPO_INCENDIO,
    TIPO_INUNDACION,
    TIPO_OTRO,
    TIPO_SEQUIA,
    TIPO_SISMO,
    TIPO_VOLCAN,
    Evento,
    a_float,
    a_iso,
    codigos_de_pais,
)

log = logging.getLogger(__name__)

# `status=all` incluye los cerrados: un incendio que se apagó ayer sigue siendo
# noticia hoy, y el histórico lo quiere. La ventana de 60 días cubre de sobra el
# intervalo entre corridas del cron semanal.
URL_POR_DEFECTO = "https://eonet.gsfc.nasa.gov/api/v3/events?status=all&days=60&limit=500"

TIPOS_EONET = {
    "wildfires": TIPO_INCENDIO,
    "volcanoes": TIPO_VOLCAN,
    "severestorms": TIPO_CICLON,
    "floods": TIPO_INUNDACION,
    "drought": TIPO_SEQUIA,
    "landslides": TIPO_DERRUMBE,
    "earthquakes": TIPO_SISMO,
}

# Categorías que EONET publica y que no son un desastre que la app deba mostrar
# como alerta ("waterColor" es floración de algas; "snow", nevadas estacionales).
# Caen en "otro" por el diccionario de arriba, no hace falta listarlas.


class FuenteEONET:
    nombre = "eonet"

    def __init__(self, url: str = URL_POR_DEFECTO):
        self.url = url

    def obtener(self, *, timeout: float, reintentos: int) -> bytes:
        return descargar(self.url, timeout=timeout, reintentos=reintentos)

    def parsear(self, crudo: bytes) -> list[Evento]:
        documento = json.loads(crudo)
        eventos = []
        for entrada in documento.get("events") or []:
            evento = self._convertir(entrada)
            if evento is not None:
                eventos.append(evento)
        return eventos

    def _convertir(self, entrada: dict) -> Evento | None:
        if not isinstance(entrada, dict):
            return None

        identificador = entrada.get("id")
        if not identificador:
            log.warning("evento EONET sin id; se omite")
            return None

        # `geometry` es la traza del evento en el tiempo: un incendio aparece
        # una vez por día mientras arde. La primera posición es dónde empezó
        # —que es lo que la gente busca— y la última, cuándo se lo vio por
        # última vez.
        geometrias = [g for g in (entrada.get("geometry") or []) if isinstance(g, dict)]
        if not geometrias:
            log.warning("evento EONET %s sin geometría; se omite", identificador)
            return None

        primera, ultima = geometrias[0], geometrias[-1]
        fecha_evento = _fecha(primera.get("date"))
        if not fecha_evento:
            log.warning("evento EONET %s sin fecha utilizable; se omite", identificador)
            return None

        latitud, longitud = _punto(primera)
        categoria = _categoria(entrada)
        titulo = str(entrada.get("title") or "").strip() or f"Evento {identificador}"
        lugar = _lugar_desde_titulo(titulo)

        # La magnitud puede venir en cualquier geometría; la última es la que
        # refleja el tamaño actual del incendio o la tormenta.
        magnitud = a_float(ultima.get("magnitudeValue")) or a_float(primera.get("magnitudeValue"))
        unidad = str(ultima.get("magnitudeUnit") or primera.get("magnitudeUnit") or "")

        return Evento(
            id=f"eonet:{identificador}",
            fuente=self.nombre,
            tipo=TIPOS_EONET.get(categoria, TIPO_OTRO),
            titulo=titulo,
            fecha_evento=fecha_evento,
            fecha_actualizacion=_fecha(ultima.get("date")),
            url=_url_publica(entrada),
            lugar=lugar,
            pais=lugar,
            paises=codigos_de_pais(lugar),
            magnitud=magnitud,
            unidad_magnitud=unidad,
            # EONET no clasifica gravedad. Dejarlo vacío hace que la app la
            # deduzca de la magnitud, que es más honesto que inventar un nivel.
            nivel_alerta="",
            latitud=latitud,
            longitud=longitud,
            extra={
                "categoria": categoria,
                "cerrado": _fecha(entrada.get("closed")),
                "posiciones": len(geometrias),
                "descripcion": str(entrada.get("description") or "").strip(),
            },
        )


def _categoria(entrada: dict) -> str:
    for categoria in entrada.get("categories") or []:
        if isinstance(categoria, dict) and categoria.get("id"):
            return str(categoria["id"]).strip().lower()
    return ""


def _punto(geometria: dict) -> tuple[float | None, float | None]:
    """Devuelve (lat, lon). EONET publica GeoJSON: las coordenadas van [lon, lat].

    Un polígono (los incendios grandes vienen así) se reduce a su primer vértice:
    para encuadrar una foto satelital alcanza, y evita depender de que el anillo
    esté bien formado.
    """
    coordenadas = geometria.get("coordinates")
    while isinstance(coordenadas, list) and coordenadas and isinstance(coordenadas[0], list):
        coordenadas = coordenadas[0]
    if not isinstance(coordenadas, list) or len(coordenadas) < 2:
        return None, None
    return a_float(coordenadas[1]), a_float(coordenadas[0])


def _url_publica(entrada: dict) -> str:
    """La página que puede abrir una persona, no el JSON de la API.

    `link` apunta al endpoint de la API, que en un navegador es un muro de
    JSON. Las fuentes originales (InciWeb, Smithsonian) sí son páginas legibles.
    """
    for fuente in entrada.get("sources") or []:
        if isinstance(fuente, dict) and str(fuente.get("url") or "").startswith("http"):
            return str(fuente["url"]).strip()
    identificador = str(entrada.get("id") or "").strip()
    if identificador:
        return f"https://eonet.gsfc.nasa.gov/api/v3/events/{identificador}"
    return str(entrada.get("link") or "").strip()


def _lugar_desde_titulo(titulo: str) -> str:
    """"Wildfire - Butte County, California" → "Butte County, California"."""
    if " - " in titulo:
        return titulo.split(" - ", 1)[1].strip()
    return ""


def _fecha(valor: object) -> str:
    """EONET publica ISO 8601 ya en UTC; se normaliza al mismo formato que el resto."""
    if not valor:
        return ""
    texto = str(valor).strip()
    try:
        momento = datetime.fromisoformat(texto.replace("Z", "+00:00"))
    except ValueError:
        log.warning("fecha EONET no parseable: %r", texto)
        return ""
    return a_iso(momento)
