"""Imágenes y video para cada evento, sin API keys ni descargas extra.

La foto de cada evento sale de NASA Worldview Snapshots, que sirve el mosaico
satelital diario de MODIS recortado a un recuadro arbitrario. Es un endpoint
público, sin clave, y la URL es determinística: se arma con la fecha y las
coordenadas que el evento ya trae, sin pedirle nada a nadie durante el scrapeo.

Justamente por ser determinística, la URL **no se guarda evento por evento**.
`recientes.json` lleva más de mil eventos; repetirle a cada uno la misma
plantilla de 200 caracteres son cientos de kilobytes que alguien descarga con
datos móviles para leerlos todos iguales. En su lugar el feed publica una sola
plantilla y el cliente la completa. De paso, cambiar de capa satelital o de
proveedor no obliga a publicar una app nueva.

Lo que sí es propio de cada evento —los mapas y los íconos que GDACS adjunta en
su RSS— se guarda en el campo `media` del evento, porque no hay forma de
derivarlo.
"""

from __future__ import annotations

from urllib.parse import quote_plus

# Capa de "color real": el mosaico diario tal como se ve desde el satélite.
# Existe desde 2000 y se actualiza todos los días, así que sirve para cualquier
# fecha que el histórico pueda tener.
CAPA_SATELITE = "MODIS_Terra_CorrectedReflectance_TrueColor"

# Sin capas de referencia (costas, etiquetas) a propósito: sus nombres cambian
# entre versiones de GIBS y un nombre inválido no degrada la imagen, hace fallar
# el pedido entero. El cliente dibuja encima el marcador que necesite.
PLANTILLA_SATELITE = (
    "https://wvs.earthdata.nasa.gov/api/v1/snapshot"
    "?REQUEST=GetSnapshot"
    "&LAYERS={capa}"
    "&CRS=EPSG:4326"
    "&TIME={fecha}"
    "&BBOX={sur},{oeste},{norte},{este}"
    "&FORMAT=image/jpeg"
    "&WIDTH={ancho}"
    "&HEIGHT={alto}"
)

CREDITO_SATELITE = "NASA Worldview (MODIS/Terra)"

# Lado del recuadro, en grados. Un sismo se ve en su valle; un ciclón ocupa
# medio mar y con un recuadro chico se lo pierde de vista. Un grado son ~111 km.
GRADOS_POR_TIPO = {
    "sismo": 6.0,
    "volcan": 5.0,
    "incendio": 4.0,
    "inundacion": 8.0,
    "ciclon": 16.0,
    "sequia": 20.0,
    "otro": 8.0,
}
GRADOS_POR_DEFECTO = 8.0

# Búsqueda de video en YouTube. No hay ninguna fuente pública que publique video
# por evento: lo que existe es la cobertura periodística, y el buscador es la
# forma honesta de llegar a ella. Se marca como búsqueda en la interfaz.
PLANTILLA_BUSQUEDA_VIDEOS = "https://www.youtube.com/results?search_query={consulta}"

# Cuántos días de fotogramas puede pedir el cliente para armar el timelapse.
DIAS_TIMELAPSE = 7

_EXTENSIONES_IMAGEN = (".png", ".jpg", ".jpeg", ".gif", ".webp")


def configuracion() -> dict:
    """Bloque `media` del feed: todo lo que el cliente necesita para armar URLs.

    Va una sola vez en el documento, no una vez por evento.
    """
    return {
        "satelite": {
            "plantilla": PLANTILLA_SATELITE,
            "capa": CAPA_SATELITE,
            "credito": CREDITO_SATELITE,
            "grados_por_tipo": dict(sorted(GRADOS_POR_TIPO.items())),
            "grados_por_defecto": GRADOS_POR_DEFECTO,
            "dias_timelapse": DIAS_TIMELAPSE,
        },
        "videos": {
            "plantilla_busqueda": PLANTILLA_BUSQUEDA_VIDEOS,
            "es_busqueda": True,
        },
    }


def grados_de(tipo: str) -> float:
    return GRADOS_POR_TIPO.get(tipo, GRADOS_POR_DEFECTO)


def recuadro(latitud: float, longitud: float, grados: float) -> tuple[float, float, float, float]:
    """Recuadro (sur, oeste, norte, este) centrado en el punto, si el mundo deja.

    Cerca de los polos o del antimeridiano el recuadro no entra centrado. En vez
    de recortarlo —que devolvería una imagen achatada o, si el ancho da cero, un
    error— se lo **desplaza** hacia adentro conservando el tamaño pedido. La
    imagen sigue siendo cuadrada y el evento sigue estando dentro, aunque no
    justo en el centro.
    """
    mitad = max(grados, 0.01) / 2.0
    sur, norte = _ventana(latitud, mitad, -90.0, 90.0)
    oeste, este = _ventana(longitud, mitad, -180.0, 180.0)
    return (_redondear(sur), _redondear(oeste), _redondear(norte), _redondear(este))


def _ventana(centro: float, mitad: float, minimo: float, maximo: float) -> tuple[float, float]:
    ancho = min(mitad * 2.0, maximo - minimo)
    inicio = centro - ancho / 2.0
    if inicio < minimo:
        inicio = minimo
    elif inicio + ancho > maximo:
        inicio = maximo - ancho
    return inicio, inicio + ancho


def _redondear(valor: float) -> float:
    # Cuatro decimales son ~11 m: de sobra para encuadrar, y evita que la URL
    # arrastre el ruido binario del float.
    return round(valor + 0.0, 4)


def url_satelite(
    latitud: float | None,
    longitud: float | None,
    fecha_iso: str,
    *,
    tipo: str = "otro",
    ancho: int = 1024,
    alto: int = 1024,
) -> str | None:
    """Foto satelital del área el día del evento. `None` si falta la posición."""
    if latitud is None or longitud is None:
        return None
    dia = fecha_solo(fecha_iso)
    if not dia:
        return None
    sur, oeste, norte, este = recuadro(latitud, longitud, grados_de(tipo))
    return PLANTILLA_SATELITE.format(
        capa=CAPA_SATELITE,
        fecha=dia,
        sur=sur,
        oeste=oeste,
        norte=norte,
        este=este,
        ancho=ancho,
        alto=alto,
    )


def fecha_solo(fecha_iso: str) -> str:
    """"2026-08-24T05:40:47Z" → "2026-08-24". La capa satelital es diaria."""
    if not fecha_iso:
        return ""
    return str(fecha_iso)[:10]


def url_busqueda_videos(titulo: str, lugar: str = "") -> str:
    """Búsqueda de video en YouTube para el evento."""
    consulta = " ".join(parte for parte in (titulo, lugar) if parte).strip()
    if not consulta:
        return ""
    return PLANTILLA_BUSQUEDA_VIDEOS.format(consulta=quote_plus(consulta))


def es_imagen(url: str) -> bool:
    """¿La URL apunta a una imagen? Se juzga por la extensión, sin pedirla."""
    if not url:
        return False
    sin_consulta = url.split("?", 1)[0].split("#", 1)[0].lower()
    return sin_consulta.endswith(_EXTENSIONES_IMAGEN)


def limpiar(medios: dict) -> dict:
    """Descarta claves vacías: un `media` a medio llenar solo infla el feed."""
    return {clave: valor for clave, valor in medios.items() if valor}
