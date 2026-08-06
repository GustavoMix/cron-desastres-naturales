"""Persistencia incremental de eventos en JSON + CSV versionados."""

from __future__ import annotations

import csv
import json
import logging
from collections import Counter
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .modelo import CAMPOS_CSV, Evento, a_iso

log = logging.getLogger(__name__)

NOMBRE_JSON = "eventos.json"
NOMBRE_CSV = "eventos.csv"
NOMBRE_RESUMEN = "resumen.json"

# Campos de bookkeeping propio: cambian en cada corrida y no deben contar como
# "el evento cambió" al comparar contra lo ya almacenado.
_CAMPOS_VOLATILES = ("visto_por_primera_vez", "visto_por_ultima_vez")


def cargar(directorio: Path) -> dict[str, Evento]:
    """Lee el histórico. Devuelve vacío si todavía no existe."""
    ruta = directorio / NOMBRE_JSON
    if not ruta.exists():
        return {}

    try:
        documento = json.loads(ruta.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"{ruta} no es JSON válido: {error}") from error

    eventos = {}
    for crudo in documento.get("eventos", []):
        evento = Evento.desde_dict(crudo)
        eventos[evento.id] = evento
    return eventos


def fusionar(
    existentes: dict[str, Evento],
    entrantes: list[Evento],
    ahora: datetime,
) -> tuple[dict[str, Evento], Counter]:
    """Mezcla los eventos recién scrapeados sobre el histórico.

    Preserva `visto_por_primera_vez` de los eventos ya conocidos: es el dato que
    permite saber cuándo apareció un evento, no cuándo se lo volvió a ver.
    """
    fusionados = dict(existentes)
    marca = a_iso(ahora)
    resumen: Counter = Counter()

    for entrante in entrantes:
        previo = fusionados.get(entrante.id)
        if previo is None:
            fusionados[entrante.id] = replace(
                entrante,
                visto_por_primera_vez=marca,
                visto_por_ultima_vez=marca,
            )
            resumen["nuevos"] += 1
            continue

        actualizado = replace(
            entrante,
            visto_por_primera_vez=previo.visto_por_primera_vez or marca,
            visto_por_ultima_vez=marca,
        )
        if _sin_volatiles(actualizado) == _sin_volatiles(previo):
            resumen["sin_cambios"] += 1
        else:
            resumen["actualizados"] += 1
        fusionados[entrante.id] = actualizado

    return fusionados, resumen


def podar(eventos: dict[str, Evento], dias_retencion: int, ahora: datetime) -> dict[str, Evento]:
    """Descarta eventos más viejos que la ventana de retención.

    Sin poda el archivo crece sin techo y cada commit del cron se vuelve más
    caro. Un evento sin fecha parseable se conserva: es preferible a perderlo.
    """
    if dias_retencion <= 0:
        return dict(eventos)

    corte = ahora - timedelta(days=dias_retencion)
    conservados = {}
    for clave, evento in eventos.items():
        fecha = _parsear_iso(evento.fecha_evento)
        if fecha is None or fecha >= corte:
            conservados[clave] = evento
    return conservados


def ordenar(eventos: dict[str, Evento]) -> list[Evento]:
    """Más recientes primero. El id desempata para que la salida sea estable."""
    return sorted(eventos.values(), key=lambda e: (e.fecha_evento, e.id), reverse=True)


def guardar(directorio: Path, eventos: dict[str, Evento], resumen: dict) -> None:
    directorio.mkdir(parents=True, exist_ok=True)
    ordenados = ordenar(eventos)
    _guardar_json(directorio / NOMBRE_JSON, ordenados)
    _guardar_csv(directorio / NOMBRE_CSV, ordenados)
    _escribir_texto(
        directorio / NOMBRE_RESUMEN,
        json.dumps(resumen, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def estadisticas(eventos: dict[str, Evento]) -> dict:
    """Conteos por tipo, por fuente y por nivel de alerta para el resumen."""
    por_tipo: Counter = Counter()
    por_fuente: Counter = Counter()
    por_alerta: Counter = Counter()
    for evento in eventos.values():
        por_tipo[evento.tipo] += 1
        por_fuente[evento.fuente] += 1
        if evento.nivel_alerta:
            por_alerta[evento.nivel_alerta] += 1
    return {
        "total": len(eventos),
        "por_tipo": dict(sorted(por_tipo.items())),
        "por_fuente": dict(sorted(por_fuente.items())),
        "por_nivel_alerta": dict(sorted(por_alerta.items())),
    }


def _guardar_json(ruta: Path, eventos: list[Evento]) -> None:
    documento = {
        "version": 1,
        "total": len(eventos),
        "eventos": [evento.como_dict() for evento in eventos],
    }
    _escribir_texto(ruta, json.dumps(documento, ensure_ascii=False, indent=2) + "\n")


def _guardar_csv(ruta: Path, eventos: list[Evento]) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("w", encoding="utf-8", newline="") as manejador:
        escritor = csv.DictWriter(manejador, fieldnames=list(CAMPOS_CSV), extrasaction="ignore")
        escritor.writeheader()
        for evento in eventos:
            fila = evento.como_dict()
            fila.pop("extra", None)
            escritor.writerow(fila)


def _escribir_texto(ruta: Path, contenido: str) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(contenido, encoding="utf-8")


def _sin_volatiles(evento: Evento) -> dict:
    datos = evento.como_dict()
    for campo in _CAMPOS_VOLATILES:
        datos.pop(campo, None)
    return datos


def _parsear_iso(valor: str) -> datetime | None:
    if not valor:
        return None
    try:
        momento = datetime.fromisoformat(valor.replace("Z", "+00:00"))
    except ValueError:
        return None
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    return momento
