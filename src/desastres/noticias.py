"""Qué dijeron los medios sobre cada evento.

Las tres fuentes de eventos (USGS, GDACS, EONET) informan el fenómeno físico:
dónde tembló, con qué magnitud, a qué hora. Ninguna cuenta *qué pasó* —si hubo
heridos, si se cayó un puente, cómo se vio desde la calle—, y eso es justo lo
que una persona quiere leer y ver después de un terremoto. Para eso hay que ir
a los medios.

Se consultan dos buscadores de noticias, en orden, y ninguno pide API key:

1. **GDELT** monitorea la prensa mundial y devuelve JSON con `socialimage`: la
   foto de portada del artículo. Es la única de las dos que da imagen, y una
   foto del derrumbe real vale más que cualquier vista satelital.
2. **Google Noticias (RSS)** entra si GDELT no encontró nada. Con `hl=es-419` y
   `gl=BO` prioriza prensa en español y de la región, que es la que le sirve a
   quien usa la app.

**No se buscan noticias para todos los eventos.** El feed lleva ~1.400 y hacer
una consulta por cada uno serían 1.400 pedidos por corrida contra servicios
ajenos y gratuitos, para enriquecer en su enorme mayoría microsismos de los que
ningún medio escribió nunca. Se eligen los que importan (ver
`elegir_para_noticias`) y el resto queda sin noticias, que es la respuesta
correcta: no las hay.

Sobre el audio: no existe ninguna fuente pública que publique audio por evento.
Lo que sí aparece son notas de medios que embeben video, y esas se marcan con
`es_video` para que la app las pueda mostrar aparte.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus, urlparse
from xml.etree import ElementTree

from .http import descargar
from .modelo import Evento, a_iso

log = logging.getLogger(__name__)

NOMBRE_ARCHIVO = "noticias.json"

# Cómo se dice cada tipo en la prensa. El vocabulario interno no sirve para
# buscar: ningún diario titula "evento de tipo sismo".
ETIQUETAS_TIPO = {
    "sismo": "terremoto",
    "ciclon": "ciclón huracán",
    "inundacion": "inundación",
    "volcan": "volcán erupción",
    "incendio": "incendio forestal",
    "sequia": "sequía",
    "derrumbe": "derrumbe deslizamiento",
    "otro": "",
}

# Ventana de búsqueda alrededor del evento. Sin ella, buscar "terremoto Chile"
# devuelve notas de todos los terremotos de Chile de la última década, y la app
# mostraría como noticia de hoy algo de 2015.
DIAS_ANTES = 1
DIAS_DESPUES = 7

# Cuántas notas se guardan por evento. Más de esto es scroll que nadie hace, y
# peso en un archivo que se baja con datos móviles.
MAXIMO_POR_EVENTO = 6

# Pausa entre consultas. GDELT y Google Noticias son gratuitos y sin key; hacer
# decenas de pedidos seguidos es la forma de que empiecen a devolver 429.
ESPERA_ENTRE_CONSULTAS = 1.0

# Dominios cuyas "noticias" son en realidad video.
DOMINIOS_VIDEO = ("youtube.com", "youtu.be", "vimeo.com", "dailymotion.com", "rumble.com")


@dataclass
class Noticia:
    titulo: str
    url: str
    medio: str
    fecha: str = ""
    imagen: str = ""
    idioma: str = ""
    es_video: bool = False
    # De qué buscador salió. Sirve para diagnosticar cuando uno se degrada.
    buscador: str = ""

    def como_dict(self) -> dict:
        return asdict(self)


@dataclass
class ResultadoNoticias:
    """Lo encontrado, más el estado de cada buscador para el resumen."""

    por_evento: dict[str, list[Noticia]] = field(default_factory=dict)
    consultados: int = 0
    con_noticias: int = 0
    errores: int = 0


def consulta_de(evento: Evento) -> str:
    """Las palabras con las que un diario habría titulado esto.

    Se usa `lugar` y no el título de la fuente: el título de USGS es
    "M 4.5 - 104 km WNW of Houma, Tonga", y buscar eso literal no devuelve nada
    porque ningún medio escribe así.
    """
    partes = [ETIQUETAS_TIPO.get(evento.tipo, "")]
    lugar = _lugar_buscable(evento.lugar) or evento.pais
    if lugar:
        partes.append(lugar)
    elif evento.pais:
        partes.append(evento.pais)
    return " ".join(parte for parte in partes if parte).strip()


def _lugar_buscable(lugar: str) -> str:
    """"104 km WNW of Houma, Tonga" → "Houma, Tonga".

    La distancia y el rumbo son ruido para un buscador de texto: ningún medio
    los menciona, y dejarlos hace que la consulta no matchee nada.
    """
    if not lugar:
        return ""
    limpio = lugar.strip()
    if " of " in limpio:
        limpio = limpio.split(" of ", 1)[1]
    return limpio.strip()


def _ventana(evento: Evento, ahora: datetime) -> tuple[datetime, datetime]:
    inicio = _parsear(evento.fecha_evento) or ahora
    desde = inicio - timedelta(days=DIAS_ANTES)
    # El final se recorta a "ahora": pedirle a un buscador noticias del futuro
    # es, en el mejor caso, una consulta desperdiciada.
    hasta = min(inicio + timedelta(days=DIAS_DESPUES), ahora)
    if hasta <= desde:
        hasta = desde + timedelta(days=1)
    return desde, hasta


def _parsear(iso: str) -> datetime | None:
    if not iso:
        return None
    try:
        momento = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    return momento if momento.tzinfo else momento.replace(tzinfo=timezone.utc)


def es_video(url: str) -> bool:
    dominio = urlparse(url).netloc.lower()
    return any(dominio == d or dominio.endswith("." + d) for d in DOMINIOS_VIDEO)


# --------------------------------------------------------------------- GDELT


class BuscadorGDELT:
    """API de documentos de GDELT. JSON, sin key, y con foto de portada."""

    nombre = "gdelt"
    BASE = "https://api.gdeltproject.org/api/v2/doc/doc"

    def url(self, evento: Evento, ahora: datetime, maximo: int) -> str:
        desde, hasta = _ventana(evento, ahora)
        return (
            f"{self.BASE}?query={quote_plus(consulta_de(evento))}"
            f"&mode=ArtList&format=json&sort=DateDesc"
            f"&maxrecords={maximo}"
            f"&startdatetime={desde.strftime('%Y%m%d%H%M%S')}"
            f"&enddatetime={hasta.strftime('%Y%m%d%H%M%S')}"
        )

    def parsear(self, crudo: bytes, maximo: int) -> list[Noticia]:
        # Ante una consulta que no le gusta, GDELT no responde un error HTTP:
        # devuelve 200 con un texto plano explicando el problema. Eso revienta
        # el parseo de JSON, y es un resultado vacío, no una falla del scraper.
        try:
            documento = json.loads(crudo)
        except (json.JSONDecodeError, UnicodeDecodeError):
            log.debug("GDELT respondió algo que no es JSON; se toma como sin resultados")
            return []

        noticias = []
        for entrada in (documento.get("articles") or [])[:maximo]:
            if not isinstance(entrada, dict):
                continue
            url = str(entrada.get("url") or "").strip()
            titulo = str(entrada.get("title") or "").strip()
            if not url or not titulo:
                continue
            noticias.append(
                Noticia(
                    titulo=titulo,
                    url=url,
                    medio=str(entrada.get("domain") or "").strip(),
                    fecha=_fecha_gdelt(entrada.get("seendate")),
                    imagen=str(entrada.get("socialimage") or "").strip(),
                    idioma=str(entrada.get("language") or "").strip().lower(),
                    es_video=es_video(url),
                    buscador=self.nombre,
                )
            )
        return noticias


def _fecha_gdelt(valor: object) -> str:
    """GDELT publica "20260824T053000Z", que no es ISO 8601 del todo."""
    texto = str(valor or "").strip()
    if not texto:
        return ""
    try:
        return a_iso(datetime.strptime(texto, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc))
    except ValueError:
        log.debug("fecha GDELT no parseable: %r", texto)
        return ""


# ------------------------------------------------------------ Google Noticias


class BuscadorGoogleNoticias:
    """RSS de Google Noticias, en español y con sesgo regional."""

    nombre = "google"
    BASE = "https://news.google.com/rss/search"

    def url(self, evento: Evento, ahora: datetime, maximo: int) -> str:
        desde, hasta = _ventana(evento, ahora)
        consulta = (
            f"{consulta_de(evento)} "
            f"after:{desde.strftime('%Y-%m-%d')} before:{hasta.strftime('%Y-%m-%d')}"
        )
        # hl/gl/ceid en es-419 y BO: la prensa que le sirve a quien usa la app
        # es la que escribe en su idioma, no la agencia en inglés.
        return f"{self.BASE}?q={quote_plus(consulta)}&hl=es-419&gl=BO&ceid=BO:es-419"

    def parsear(self, crudo: bytes, maximo: int) -> list[Noticia]:
        try:
            raiz = ElementTree.fromstring(crudo)
        except ElementTree.ParseError:
            log.debug("Google Noticias respondió algo que no es XML")
            return []

        noticias = []
        for item in raiz.iter("item"):
            if len(noticias) >= maximo:
                break
            url = _texto(item, "link")
            titulo = _texto(item, "title")
            if not url or not titulo:
                continue
            medio = _texto(item, "source")
            noticias.append(
                Noticia(
                    # Google le pega " - Diario X" al título. Con el medio ya en
                    # su propio campo, repetirlo solo gasta ancho de pantalla.
                    titulo=_sin_sufijo_de_medio(titulo, medio),
                    url=url,
                    medio=medio,
                    fecha=_fecha_rfc822(_texto(item, "pubDate")),
                    idioma="spanish",
                    es_video=es_video(url),
                    buscador=self.nombre,
                )
            )
        return noticias


def _texto(elemento: ElementTree.Element, etiqueta: str) -> str:
    hijo = elemento.find(etiqueta)
    if hijo is None or hijo.text is None:
        return ""
    return hijo.text.strip()


def _sin_sufijo_de_medio(titulo: str, medio: str) -> str:
    if medio and titulo.endswith(f" - {medio}"):
        return titulo[: -len(f" - {medio}")].strip()
    return titulo


def _fecha_rfc822(valor: str) -> str:
    if not valor:
        return ""
    try:
        return a_iso(parsedate_to_datetime(valor))
    except (TypeError, ValueError):
        log.debug("fecha RSS no parseable: %r", valor)
        return ""


BUSCADORES = (BuscadorGDELT(), BuscadorGoogleNoticias())


# ------------------------------------------------------------------ selección


def elegir_para_noticias(
    eventos: list[Evento],
    *,
    maximo: int,
    paises_prioritarios: tuple[str, ...] = (),
) -> list[Evento]:
    """Los eventos que valen una consulta a los medios.

    Se prioriza lo cercano sobre lo grande: un sismo moderado en Bolivia le
    importa más a quien usa esta app que uno enorme en el Pacífico. Después,
    gravedad, y a igual gravedad, lo más reciente.
    """
    prioritarios = {codigo.upper() for codigo in paises_prioritarios}

    def orden(evento: Evento) -> tuple:
        cerca = 0 if prioritarios & {p.upper() for p in evento.paises} else 1
        return (cerca, -_peso(evento), _negativo(evento.fecha_evento))

    # Un evento sin lugar ni país no se puede buscar: la consulta quedaría en
    # "terremoto" a secas y traería noticias de cualquier parte del mundo.
    buscables = [
        evento
        for evento in eventos
        if consulta_de(evento).strip() and _tiene_donde(evento)
    ]
    return sorted(buscables, key=orden)[: max(maximo, 0)]


def _tiene_donde(evento: Evento) -> bool:
    return bool(_lugar_buscable(evento.lugar) or evento.pais)


def _peso(evento: Evento) -> float:
    """Qué tan noticiable es. La alerta manda; la magnitud sísmica desempata."""
    pesos = {"roja": 400.0, "naranja": 300.0, "amarilla": 200.0, "verde": 100.0}
    peso = pesos.get(evento.nivel_alerta, 0.0)
    if evento.tipo == "sismo" and evento.magnitud is not None:
        peso += evento.magnitud * 10
    return peso


def _negativo(fecha: str) -> str:
    """Truco para ordenar fechas ISO descendente dentro de una tupla ascendente."""
    # Invertir cada carácter no es posible con texto, así que se ordena por el
    # complemento numérico de los dígitos, que para ISO 8601 alcanza.
    return "".join(chr(0x10FFFD - ord(c)) if c.isdigit() else c for c in fecha)


# -------------------------------------------------------------------- fetch


def buscar_para(
    evento: Evento,
    *,
    ahora: datetime,
    timeout: float,
    reintentos: int,
    maximo: int = MAXIMO_POR_EVENTO,
    buscadores=BUSCADORES,
) -> list[Noticia]:
    """Noticias de un evento. El segundo buscador entra solo si el primero falla."""
    for buscador in buscadores:
        try:
            crudo = descargar(
                buscador.url(evento, ahora, maximo), timeout=timeout, reintentos=reintentos
            )
            encontradas = buscador.parsear(crudo, maximo)
        except Exception as error:  # noqa: BLE001 - un buscador caído no tumba la corrida
            log.warning("buscador %s falló para %s: %s", buscador.nombre, evento.id, error)
            continue
        if encontradas:
            return _ordenar(encontradas)
    return []


def _ordenar(noticias: list[Noticia]) -> list[Noticia]:
    """Español primero, después con foto, después lo más reciente."""
    return sorted(
        noticias,
        key=lambda n: (
            0 if n.idioma.startswith("spanish") or n.idioma.startswith("es") else 1,
            0 if n.imagen else 1,
            _negativo(n.fecha),
        ),
    )


def recolectar(
    eventos: list[Evento],
    *,
    ahora: datetime,
    timeout: float,
    reintentos: int,
    maximo_eventos: int,
    paises_prioritarios: tuple[str, ...] = (),
    maximo_por_evento: int = MAXIMO_POR_EVENTO,
    espera: float = ESPERA_ENTRE_CONSULTAS,
    dormir=time.sleep,
    buscadores=BUSCADORES,
) -> ResultadoNoticias:
    """Busca noticias para los eventos elegidos y las agrupa por `id_agrupado`.

    La clave es `id_agrupado` y no `id` a propósito: GDACS republica un ciclón
    por episodios, y colgar las noticias del episodio las fragmentaría entre
    veinte registros del mismo fenómeno.
    """
    elegidos = elegir_para_noticias(
        eventos, maximo=maximo_eventos, paises_prioritarios=paises_prioritarios
    )
    resultado = ResultadoNoticias()

    for indice, evento in enumerate(elegidos):
        if indice > 0 and espera > 0:
            dormir(espera)
        resultado.consultados += 1
        encontradas = buscar_para(
            evento,
            ahora=ahora,
            timeout=timeout,
            reintentos=reintentos,
            maximo=maximo_por_evento,
            buscadores=buscadores,
        )
        if not encontradas:
            continue
        resultado.con_noticias += 1
        resultado.por_evento[evento.id_agrupado] = encontradas

    return resultado


def documento(resultado: ResultadoNoticias, generado: datetime) -> dict:
    return {
        "version": 1,
        "generado": a_iso(generado),
        "eventos_con_noticias": len(resultado.por_evento),
        "noticias": {
            clave: [noticia.como_dict() for noticia in noticias]
            for clave, noticias in sorted(resultado.por_evento.items())
        },
    }
