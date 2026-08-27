"""Punto de entrada del scraper: orquesta fuentes, fusión y persistencia."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from . import almacen
from .fuentes.base import Fuente
from .fuentes.eonet import FuenteEONET
from .fuentes.gdacs import FuenteGDACS
from .fuentes.usgs import FuenteUSGS
from .modelo import Evento, a_iso, ahora_utc

log = logging.getLogger("desastres")

# Códigos de salida: el workflow los distingue para no confundir una caída
# total (nada que guardar) con una parcial (una fuente respondió).
EXITO = 0
FALLO_TOTAL = 1
FALLO_PARCIAL = 2

FUENTES_DISPONIBLES = {
    FuenteUSGS.nombre: FuenteUSGS,
    FuenteGDACS.nombre: FuenteGDACS,
    FuenteEONET.nombre: FuenteEONET,
}

DIAS_RETENCION_POR_DEFECTO = 180
# Ventana y umbral del feed que consume el front. USGS publica cientos de
# micro-sismos diarios que a una app de público general solo le inflan la
# descarga; 2.5 es el umbral habitual de "sismo que la gente llega a sentir".
# Con el cron semanal, una ventana de 7 días dejaría al front sin nada nuevo que
# mostrar durante casi toda la semana. 14 le da contexto entre corridas.
DIAS_RECIENTES_POR_DEFECTO = 14
MAGNITUD_MINIMA_RECIENTES = 2.5


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="desastres",
        description=(
            "Scrapea alertas de desastres naturales (USGS, GDACS) "
            "y las versiona en JSON/CSV."
        ),
    )
    parser.add_argument(
        "--fuentes",
        default=",".join(FUENTES_DISPONIBLES),
        help="Fuentes a consultar, separadas por coma (por defecto: todas).",
    )
    parser.add_argument(
        "--salida",
        type=Path,
        default=Path("datos"),
        help="Directorio donde se escriben eventos.json, eventos.csv y resumen.json.",
    )
    parser.add_argument(
        "--retencion-dias",
        type=int,
        default=DIAS_RETENCION_POR_DEFECTO,
        help="Descarta eventos más viejos que N días. 0 desactiva la poda.",
    )
    parser.add_argument(
        "--dias-recientes",
        type=int,
        default=DIAS_RECIENTES_POR_DEFECTO,
        help="Ventana del feed liviano recientes.json que consume el front.",
    )
    parser.add_argument(
        "--recientes-magnitud-minima",
        type=float,
        default=MAGNITUD_MINIMA_RECIENTES,
        help=(
            "Excluye de recientes.json los sismos por debajo de esta magnitud. "
            "No afecta al histórico ni a otros tipos de evento. 0 no filtra."
        ),
    )
    parser.add_argument("--timeout", type=float, default=30.0, help="Timeout HTTP en segundos.")
    parser.add_argument("--reintentos", type=int, default=3, help="Intentos por fuente.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Consulta y reporta, pero no escribe nada en disco.",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Logging en nivel DEBUG.")
    return parser


def resolver_fuentes(especificacion: str) -> list[Fuente]:
    nombres = [nombre.strip().lower() for nombre in especificacion.split(",") if nombre.strip()]
    if not nombres:
        raise ValueError("hay que indicar al menos una fuente")

    desconocidas = [nombre for nombre in nombres if nombre not in FUENTES_DISPONIBLES]
    if desconocidas:
        raise ValueError(
            f"fuente(s) desconocida(s): {', '.join(desconocidas)}. "
            f"Disponibles: {', '.join(FUENTES_DISPONIBLES)}"
        )

    # dict.fromkeys deduplica conservando el orden pedido.
    return [FUENTES_DISPONIBLES[nombre]() for nombre in dict.fromkeys(nombres)]


def recolectar(
    fuentes: list[Fuente], *, timeout: float, reintentos: int
) -> tuple[list[Evento], dict]:
    """Consulta cada fuente. Una fuente caída no cancela a las demás."""
    eventos: list[Evento] = []
    estado: dict = {}

    for fuente in fuentes:
        try:
            crudo = fuente.obtener(timeout=timeout, reintentos=reintentos)
            obtenidos = fuente.parsear(crudo)
        except Exception as error:  # noqa: BLE001 - una fuente rota no debe tumbar la corrida
            log.error("fuente %s falló: %s", fuente.nombre, error)
            estado[fuente.nombre] = {"ok": False, "eventos": 0, "error": str(error)}
            continue

        log.info("fuente %s: %d eventos", fuente.nombre, len(obtenidos))
        estado[fuente.nombre] = {"ok": True, "eventos": len(obtenidos), "error": None}
        eventos.extend(obtenidos)

    return eventos, estado


def ejecutar(argumentos: argparse.Namespace) -> int:
    fuentes = resolver_fuentes(argumentos.fuentes)
    inicio = ahora_utc()

    entrantes, estado_fuentes = recolectar(
        fuentes, timeout=argumentos.timeout, reintentos=argumentos.reintentos
    )
    fallidas = [nombre for nombre, detalle in estado_fuentes.items() if not detalle["ok"]]

    if len(fallidas) == len(fuentes):
        log.error("todas las fuentes fallaron; no se modifica el histórico")
        return FALLO_TOTAL

    existentes = almacen.cargar(argumentos.salida)
    fusionados, cambios = almacen.fusionar(existentes, entrantes, inicio)
    antes_de_podar = len(fusionados)
    fusionados = almacen.podar(
        fusionados,
        argumentos.retencion_dias,
        inicio,
        activos={evento.id for evento in entrantes},
    )

    recientes = almacen.filtrar_recientes(
        fusionados,
        dias=argumentos.dias_recientes,
        magnitud_minima_sismo=argumentos.recientes_magnitud_minima,
        ahora=inicio,
    )

    resumen = {
        "ultima_ejecucion": a_iso(inicio),
        "fuentes": estado_fuentes,
        "cambios": {
            "nuevos": cambios["nuevos"],
            "actualizados": cambios["actualizados"],
            "sin_cambios": cambios["sin_cambios"],
            "podados": antes_de_podar - len(fusionados),
        },
        "retencion_dias": argumentos.retencion_dias,
        "recientes": {
            "dias": argumentos.dias_recientes,
            "magnitud_minima_sismo": argumentos.recientes_magnitud_minima,
            "total": len(recientes),
        },
        "historico": almacen.estadisticas(fusionados),
    }

    if argumentos.dry_run:
        log.info("dry-run: no se escribe nada en %s", argumentos.salida)
    else:
        almacen.guardar(argumentos.salida, fusionados, resumen)
        almacen.guardar_recientes(argumentos.salida, recientes, inicio)
        log.info(
            "escritos %d eventos (%d en el feed reciente) en %s",
            len(fusionados),
            len(recientes),
            argumentos.salida,
        )

    print(json.dumps(resumen, ensure_ascii=False, indent=2, sort_keys=True))
    return FALLO_PARCIAL if fallidas else EXITO


def main(argv: list[str] | None = None) -> int:
    argumentos = construir_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if argumentos.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    try:
        return ejecutar(argumentos)
    except ValueError as error:
        log.error("%s", error)
        return FALLO_TOTAL


if __name__ == "__main__":
    raise SystemExit(main())
