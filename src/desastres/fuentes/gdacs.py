"""GDACS (Global Disaster Alert and Coordination System): feed multi-amenaza.

RSS público, sin API key: https://www.gdacs.org/xml/rss.xml
Cubre sismos, ciclones, inundaciones, volcanes, sequías e incendios forestales.
"""

from __future__ import annotations

import logging
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

from ..http import descargar
from ..medios import es_imagen, limpiar
from ..modelo import (
    TIPO_CICLON,
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
    normalizar_alerta,
)

log = logging.getLogger(__name__)

URL_POR_DEFECTO = "https://www.gdacs.org/xml/rss.xml"

NS = {
    "gdacs": "http://www.gdacs.org",
    "geo": "http://www.w3.org/2003/01/geo/wgs84_pos#",
    "dc": "http://purl.org/dc/elements/1.1/",
}

TIPOS_GDACS = {
    "EQ": TIPO_SISMO,
    "TC": TIPO_CICLON,
    "FL": TIPO_INUNDACION,
    "VO": TIPO_VOLCAN,
    "DR": TIPO_SEQUIA,
    "WF": TIPO_INCENDIO,
}


class FuenteGDACS:
    nombre = "gdacs"

    def __init__(self, url: str = URL_POR_DEFECTO):
        self.url = url

    def obtener(self, *, timeout: float, reintentos: int) -> bytes:
        return descargar(self.url, timeout=timeout, reintentos=reintentos)

    def parsear(self, crudo: bytes) -> list[Evento]:
        raiz = ElementTree.fromstring(crudo)
        eventos = []
        for elemento in raiz.iter("item"):
            evento = self._convertir(elemento)
            if evento is not None:
                eventos.append(evento)
        return eventos

    def _convertir(self, item: ElementTree.Element) -> Evento | None:
        codigo_tipo = (_texto(item, "gdacs:eventtype") or "").upper()
        id_evento = _texto(item, "gdacs:eventid")
        if not id_evento:
            log.warning("item GDACS sin eventid; se omite")
            return None

        # Un mismo evento (p. ej. un ciclón) se republica por episodios. El
        # episodio forma parte de `id` para no pisar el estado anterior, pero
        # `id_agrupado` lo omite: es el fenómeno del mundo real, y es la clave
        # a la que la app tiene que colgar los comentarios.
        id_episodio = _texto(item, "gdacs:episodeid")
        id_agrupado = f"gdacs:{codigo_tipo or 'NA'}:{id_evento}"
        clave = f"{id_agrupado}:{id_episodio}" if id_episodio else id_agrupado

        fecha_evento = _fecha(_texto(item, "gdacs:fromdate")) or _fecha(_texto(item, "pubDate"))
        if not fecha_evento:
            log.warning("item GDACS %s sin fecha utilizable; se omite", id_evento)
            return None

        pais = (_texto(item, "gdacs:country") or "").strip()
        severidad = item.find("gdacs:severity", NS)
        latitud, longitud = _coordenadas(item)
        poblacion = item.find("gdacs:population", NS)

        return Evento(
            id=clave,
            id_agrupado=id_agrupado,
            fuente=self.nombre,
            tipo=TIPOS_GDACS.get(codigo_tipo, TIPO_OTRO),
            titulo=(_texto(item, "title") or "").strip(),
            fecha_evento=fecha_evento,
            fecha_actualizacion=_fecha(_texto(item, "pubDate")),
            url=(_texto(item, "link") or "").strip(),
            lugar=(_texto(item, "gdacs:country") or "").strip(),
            pais=pais,
            paises=codigos_de_pais(pais),
            magnitud=a_float(severidad.get("value")) if severidad is not None else None,
            unidad_magnitud=(severidad.get("unit") or "") if severidad is not None else "",
            nivel_alerta=normalizar_alerta(_texto(item, "gdacs:alertlevel")),
            latitud=latitud,
            longitud=longitud,
            media=_medios(item),
            extra={
                "codigo_tipo": codigo_tipo,
                "episodio": id_episodio,
                "puntaje_alerta": a_float(_texto(item, "gdacs:alertscore")),
                "severidad_texto": (severidad.text or "").strip() if severidad is not None else "",
                "hasta": _fecha(_texto(item, "gdacs:todate")),
                "iso3": (_texto(item, "gdacs:iso3") or "").strip(),
                "poblacion_afectada": (
                    a_float(poblacion.get("value")) if poblacion is not None else None
                ),
                "poblacion_texto": (poblacion.text or "").strip() if poblacion is not None else "",
                "descripcion": (_texto(item, "description") or "").strip(),
            },
        )


# Cuántas imágenes sueltas se conservan por evento. GDACS puede adjuntar una
# docena de mapas casi iguales; más de cuatro no le aportan nada a nadie y sí le
# suman peso al feed.
MAXIMO_RECURSOS = 4


def _medios(item: ElementTree.Element) -> dict:
    """Rescata las imágenes que GDACS adjunta: ícono de alerta y mapas.

    El RSS de GDACS cambió de forma varias veces —los mapas estuvieron en
    `enclosure`, en `gdacs:resources` y en elementos sueltos— así que en vez de
    apostar a un camino fijo se recorre el item entero juntando cualquier URL
    que termine en extensión de imagen. Si un día GDACS mueve las imágenes de
    lugar otra vez, esto las sigue encontrando; si las saca, el evento se queda
    sin `media` y el cliente cae en la foto satelital, que no depende de GDACS.
    """
    icono = ""
    candidatos: list[tuple[str, str]] = []

    for elemento in item.iter():
        etiqueta = elemento.tag.rsplit("}", 1)[-1].lower()
        url = (elemento.get("url") or "").strip()
        if not url and etiqueta.endswith("icon"):
            url = (elemento.text or "").strip()
        if not es_imagen(url):
            continue

        if etiqueta.endswith("icon"):
            icono = icono or url
            continue

        titulo = (elemento.get("title") or elemento.get("description") or "").strip()
        candidatos.append((url, titulo))

    vistos = {icono}
    mapa = ""
    recursos = []
    for url, titulo in candidatos:
        if url in vistos:
            continue
        vistos.add(url)
        if not mapa:
            mapa = url
            continue
        if len(recursos) < MAXIMO_RECURSOS:
            recursos.append({"url": url, "titulo": titulo} if titulo else {"url": url})

    return limpiar({"icono": icono, "mapa": mapa, "recursos": recursos})


def _texto(elemento: ElementTree.Element, ruta: str) -> str:
    hijo = elemento.find(ruta, NS)
    if hijo is None or hijo.text is None:
        return ""
    return hijo.text.strip()


def _coordenadas(item: ElementTree.Element) -> tuple[float | None, float | None]:
    """Lee lat/long, que GDACS publica anidadas en `geo:Point` o sueltas."""
    punto = item.find("geo:Point", NS)
    contenedor = punto if punto is not None else item
    return a_float(_texto(contenedor, "geo:lat")), a_float(_texto(contenedor, "geo:long"))


def _fecha(valor: str) -> str:
    """Convierte una fecha RFC 822 ("Thu, 06 Aug 2026 01:23:00 GMT") a ISO UTC."""
    if not valor:
        return ""
    try:
        return a_iso(parsedate_to_datetime(valor))
    except (TypeError, ValueError):
        log.warning("fecha GDACS no parseable: %r", valor)
        return ""
