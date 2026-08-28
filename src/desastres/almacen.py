"""Persistencia incremental de eventos en JSON + CSV versionados."""

from __future__ import annotations

import csv
import json
import logging
import re
from collections import Counter
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import medios, noticias
from .modelo import CAMPOS_CSV, Evento, a_iso, codigos_de_pais

log = logging.getLogger(__name__)

NOMBRE_JSON = "eventos.json"
NOMBRE_CSV = "eventos.csv"
NOMBRE_RESUMEN = "resumen.json"
NOMBRE_RECIENTES = "recientes.json"

# Bookkeeping propio del scraper: no forma parte de "el evento cambió".
_CAMPOS_BOOKKEEPING = ("visto_por_primera_vez", "cambiado_por_ultima_vez")


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
        evento = Evento.desde_dict(_migrar(crudo))
        eventos[evento.id] = evento
    return eventos


# Ids de GDACS de la forma gdacs:<TIPO>:<evento>:<episodio>.
_ID_GDACS_CON_EPISODIO = re.compile(r"^(gdacs:[A-Z]+:\d+):\d+$")


def _migrar(crudo: dict) -> dict:
    """Completa los campos que un registro viejo no tiene.

    Los eventos que siguen apareciendo en los feeds se corrigen solos en la
    próxima corrida, porque se vuelven a parsear enteros. Los que ya salieron,
    no: sin esto quedarían incompletos para siempre, y son justo los históricos
    que la app va a mostrar.

    Se puede borrar cuando no quede en el histórico ningún registro anterior a
    la introducción de estos campos.
    """
    migrado = crudo

    # `id_agrupado`: sin él, los eventos de GDACS quedan agrupados por episodio
    # en vez de por fenómeno, y los comentarios que la app les cuelgue se
    # fragmentan para siempre.
    if not migrado.get("id_agrupado"):
        coincidencia = _ID_GDACS_CON_EPISODIO.match(str(migrado.get("id", "")))
        if coincidencia is not None:
            migrado = {**migrado, "id_agrupado": coincidencia.group(1)}

    # `paises`: es el campo por el que filtra la app. Se deriva del texto que
    # ya está guardado, así que no hace falta esperar a que el evento vuelva a
    # aparecer en el feed.
    if not migrado.get("paises") and migrado.get("pais"):
        codigos = codigos_de_pais(migrado["pais"])
        if codigos:
            migrado = {**migrado, "paises": codigos}

    return migrado


def fusionar(
    existentes: dict[str, Evento],
    entrantes: list[Evento],
    ahora: datetime,
) -> tuple[dict[str, Evento], Counter]:
    """Mezcla los eventos recién scrapeados sobre el histórico.

    Preserva `visto_por_primera_vez`: es el dato que dice cuándo apareció un
    evento, no cuándo se lo volvió a ver.

    Un evento revisitado sin cambios se deja **byte a byte como estaba**. Esa es
    la propiedad que hace viable guardar el histórico en git: si se le tocara la
    marca de tiempo en cada corrida, las decenas de miles de filas del archivo
    cambiarían cada hora y cada commit pesaría el archivo entero.
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
                cambiado_por_ultima_vez=marca,
            )
            resumen["nuevos"] += 1
            continue

        candidato = replace(
            entrante,
            visto_por_primera_vez=previo.visto_por_primera_vez or marca,
            cambiado_por_ultima_vez=previo.cambiado_por_ultima_vez,
        )
        if _sin_bookkeeping(candidato) == _sin_bookkeeping(previo):
            resumen["sin_cambios"] += 1
            fusionados[entrante.id] = previo
            continue

        resumen["actualizados"] += 1
        fusionados[entrante.id] = replace(candidato, cambiado_por_ultima_vez=marca)

    return fusionados, resumen


def podar(
    eventos: dict[str, Evento],
    dias_retencion: int,
    ahora: datetime,
    activos: set[str] | None = None,
) -> dict[str, Evento]:
    """Descarta eventos viejos que ya no aparecen en los feeds.

    `activos` son los ids que la corrida actual encontró publicados. Nunca se
    podan, por viejos que sean: GDACS mantiene eventos de larguísima duración
    —una sequía puede llevar un año en curso y seguir republicándose— y podarlos
    por su fecha de inicio los borraría en cada corrida para reinsertarlos en la
    siguiente, dejándolos invisibles pese a estar activos.

    Un evento sin fecha parseable se conserva: es preferible a perderlo.
    """
    if dias_retencion <= 0:
        return dict(eventos)

    protegidos = activos or set()
    corte = ahora - timedelta(days=dias_retencion)
    conservados = {}
    for clave, evento in eventos.items():
        if clave in protegidos:
            conservados[clave] = evento
            continue
        fecha = _parsear_iso(evento.fecha_evento)
        if fecha is None or fecha >= corte:
            conservados[clave] = evento
    return conservados


def ordenar(eventos: dict[str, Evento]) -> list[Evento]:
    """Más recientes primero. El id desempata para que la salida sea estable."""
    return sorted(eventos.values(), key=lambda e: (e.fecha_evento, e.id), reverse=True)


def filtrar_recientes(
    eventos: dict[str, Evento],
    *,
    dias: int,
    magnitud_minima_sismo: float,
    ahora: datetime,
) -> list[Evento]:
    """Selecciona lo que consume el front: ventana corta y sin ruido sísmico.

    El feed de USGS incluye cientos de micro-sismos diarios de California que a
    una app de público general no le aportan nada y le multiplican el tamaño de
    la descarga. El umbral se aplica **solo a sismos con magnitud conocida**:
    un ciclón o una inundación no tienen magnitud comparable y nunca se filtran.
    """
    corte = ahora - timedelta(days=dias) if dias > 0 else None
    seleccionados = []

    for evento in ordenar(eventos):
        fecha = _parsear_iso(evento.fecha_evento)
        if corte is not None and fecha is not None and fecha < corte:
            continue
        if (
            evento.tipo == "sismo"
            and evento.magnitud is not None
            and evento.magnitud < magnitud_minima_sismo
        ):
            continue
        seleccionados.append(evento)

    return seleccionados


def guardar_recientes(directorio: Path, eventos: list[Evento], generado: datetime) -> None:
    """Escribe el feed liviano. Sin `extra`: la app no lo usa y pesa.

    `media` va una sola vez, a nivel documento: son plantillas que el cliente
    completa por su cuenta. Repetirlas en cada uno de los ~1.400 eventos sumaría
    cientos de kilobytes de texto idéntico a una descarga que mucha gente hace
    con datos móviles.
    """
    documento = {
        "version": 2,
        "generado": a_iso(generado),
        "total": len(eventos),
        "media": medios.configuracion(),
        "eventos": [_sin_extra(evento) for evento in eventos],
    }
    _escribir_texto(
        directorio / NOMBRE_RECIENTES,
        json.dumps(documento, ensure_ascii=False, indent=2) + "\n",
    )


def guardar_noticias(directorio: Path, resultado, generado: datetime) -> None:
    """Escribe las noticias en su **propio archivo**, aparte de `recientes.json`.

    Meterlas dentro del feed obligaría a bajar los artículos de los 40 eventos
    enriquecidos a todo el que abra la app, aunque solo vaya a mirar uno. Así, el
    feed sigue costando lo mismo que antes y las noticias se piden cuando alguien
    de verdad las quiere ver.
    """
    _escribir_texto(
        directorio / noticias.NOMBRE_ARCHIVO,
        json.dumps(noticias.documento(resultado, generado), ensure_ascii=False, indent=2) + "\n",
    )


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
            escritor.writerow(_para_csv(evento))


def _sin_extra(evento: Evento) -> dict:
    datos = evento.como_dict()
    datos.pop("extra", None)
    return datos


def _para_csv(evento: Evento) -> dict:
    """Aplana lo que el CSV no sabe representar.

    `paises` es una lista; sin esto el writer la volcaría como `['BO', 'PE']`,
    que ninguna planilla sabe leer.
    """
    datos = _sin_extra(evento)
    datos["paises"] = ";".join(evento.paises)
    return datos


def _escribir_texto(ruta: Path, contenido: str) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(contenido, encoding="utf-8")


def _sin_bookkeeping(evento: Evento) -> dict:
    datos = evento.como_dict()
    for campo in _CAMPOS_BOOKKEEPING:
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
