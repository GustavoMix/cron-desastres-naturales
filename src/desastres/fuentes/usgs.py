"""USGS Earthquake Hazards Program: sismos de los últimos 7 días.

Feed GeoJSON público, sin API key:
https://earthquake.usgs.gov/earthquakes/feed/v1.0/geojson.php
"""

from __future__ import annotations

import json
import logging

from ..http import descargar
from ..modelo import (
    TIPO_OTRO,
    TIPO_SISMO,
    TIPO_VOLCAN,
    Evento,
    a_float,
    codigos_de_pais,
    desde_epoch_ms,
    normalizar_alerta,
)

log = logging.getLogger(__name__)

# Feed de 7 días, no el de 24 h. La ventana del feed tiene que cubrir el
# intervalo entre corridas o se pierden eventos: con el cron semanal, el feed
# diario dejaría afuera 6 de cada 7 días de sismos. El de 7 días además da
# margen para que una corrida fallida no cause un agujero permanente.
URL_POR_DEFECTO = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_week.geojson"

# `properties.type` del feed. Todo lo que no sea tectónico cae en "otro"
# (quarry blast, explosion, ice quake, mine collapse, sonic boom...).
TIPOS_USGS = {
    "earthquake": TIPO_SISMO,
    "volcanic eruption": TIPO_VOLCAN,
}


class FuenteUSGS:
    nombre = "usgs"

    def __init__(self, url: str = URL_POR_DEFECTO):
        self.url = url

    def obtener(self, *, timeout: float, reintentos: int) -> bytes:
        return descargar(self.url, timeout=timeout, reintentos=reintentos)

    def parsear(self, crudo: bytes) -> list[Evento]:
        documento = json.loads(crudo)
        rasgos = documento.get("features") or []
        eventos = []
        for rasgo in rasgos:
            evento = self._convertir(rasgo)
            if evento is not None:
                eventos.append(evento)
        return eventos

    def _convertir(self, rasgo: dict) -> Evento | None:
        if not isinstance(rasgo, dict):
            return None

        identificador = rasgo.get("id")
        propiedades = rasgo.get("properties") or {}
        if not identificador or not isinstance(propiedades, dict):
            log.warning("rasgo USGS sin id o sin properties; se omite")
            return None

        fecha_evento = desde_epoch_ms(propiedades.get("time"))
        if not fecha_evento:
            log.warning("rasgo USGS %s sin marca de tiempo válida; se omite", identificador)
            return None

        # geometry.coordinates es [lon, lat, profundidad_km] — nótese el orden.
        geometria = rasgo.get("geometry") or {}
        coordenadas = geometria.get("coordinates") or []
        longitud = a_float(coordenadas[0]) if len(coordenadas) > 0 else None
        latitud = a_float(coordenadas[1]) if len(coordenadas) > 1 else None
        profundidad = a_float(coordenadas[2]) if len(coordenadas) > 2 else None

        lugar = str(propiedades.get("place") or "")
        region = _region_desde_lugar(lugar)
        titulo = str(propiedades.get("title") or lugar or f"Sismo {identificador}")

        return Evento(
            id=f"usgs:{identificador}",
            fuente=self.nombre,
            tipo=TIPOS_USGS.get(str(propiedades.get("type") or "").lower(), TIPO_OTRO),
            titulo=titulo,
            fecha_evento=fecha_evento,
            fecha_actualizacion=desde_epoch_ms(propiedades.get("updated")),
            url=str(propiedades.get("url") or ""),
            lugar=lugar,
            pais=region,
            paises=codigos_de_pais(region),
            magnitud=a_float(propiedades.get("mag")),
            unidad_magnitud=str(propiedades.get("magType") or ""),
            nivel_alerta=normalizar_alerta(propiedades.get("alert")),
            latitud=latitud,
            longitud=longitud,
            profundidad_km=profundidad,
            extra={
                "tsunami": propiedades.get("tsunami"),
                "significancia": propiedades.get("sig"),
                "estado_revision": propiedades.get("status"),
                "red": propiedades.get("net"),
            },
        )


def _region_desde_lugar(lugar: str) -> str:
    """Extrae la región del campo `place` ("10 km SW of Ciudad, Chile").

    El feed no trae país estructurado; lo que sigue a la última coma es la mejor
    aproximación disponible, y para sismos en EE. UU. es un estado ("Alaska",
    "CA"). Por eso el resultado se traduce después a códigos ISO: filtrar por
    este texto pondría cada estado como si fuera un país aparte.
    """
    if "," not in lugar:
        return ""
    return lugar.rsplit(",", 1)[1].strip()
