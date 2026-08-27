from urllib.parse import parse_qs, urlparse

from desastres import medios


def _parametros(url: str) -> dict:
    return {clave: valor[0] for clave, valor in parse_qs(urlparse(url).query).items()}


def test_el_recuadro_queda_centrado_en_el_evento():
    sur, oeste, norte, este = medios.recuadro(-16.5, -68.15, 6.0)
    assert (sur, norte) == (-19.5, -13.5)
    assert (oeste, este) == (-71.15, -65.15)


def test_cerca_del_polo_el_recuadro_se_corre_pero_no_se_achata():
    """Recortarlo devolvería una imagen deformada; correrlo la deja cuadrada."""
    sur, oeste, norte, este = medios.recuadro(88.0, 10.0, 6.0)
    assert norte == 90.0
    assert round(norte - sur, 4) == 6.0
    assert round(este - oeste, 4) == 6.0


def test_cerca_del_antimeridiano_el_ancho_se_conserva():
    sur, oeste, norte, este = medios.recuadro(-20.0, 179.0, 6.0)
    assert este == 180.0
    assert round(este - oeste, 4) == 6.0
    assert -180.0 <= oeste <= 180.0


def test_un_recuadro_mas_grande_que_el_mundo_se_limita_al_mundo():
    sur, oeste, norte, este = medios.recuadro(0.0, 0.0, 400.0)
    assert (sur, norte) == (-90.0, 90.0)
    assert (oeste, este) == (-180.0, 180.0)


def test_la_url_satelital_pide_el_dia_del_evento_no_el_instante():
    url = medios.url_satelite(-16.5, -68.15, "2026-08-24T05:40:47Z", tipo="sismo")
    assert _parametros(url)["TIME"] == "2026-08-24"


def test_la_url_satelital_usa_el_orden_de_bbox_que_espera_epsg_4326():
    """EPSG:4326 va (sur, oeste, norte, este). Invertirlo devuelve mar vacío."""
    url = medios.url_satelite(-16.5, -68.15, "2026-08-24T05:40:47Z", tipo="sismo")
    sur, oeste, norte, este = (float(x) for x in _parametros(url)["BBOX"].split(","))
    assert sur < norte
    assert oeste < este
    assert sur < -16.5 < norte
    assert oeste < -68.15 < este


def test_un_ciclon_se_encuadra_mas_abierto_que_un_sismo():
    """Un ciclón ocupa medio mar; con el recuadro de un sismo se lo pierde."""
    assert medios.grados_de("ciclon") > medios.grados_de("sismo")


def test_un_tipo_desconocido_cae_en_el_encuadre_por_defecto():
    assert medios.grados_de("meteorito") == medios.GRADOS_POR_DEFECTO


def test_sin_coordenadas_no_hay_foto():
    assert medios.url_satelite(None, -68.15, "2026-08-24T05:40:47Z") is None
    assert medios.url_satelite(-16.5, None, "2026-08-24T05:40:47Z") is None


def test_sin_fecha_no_hay_foto():
    """La capa satelital es diaria: sin día no hay nada que pedir."""
    assert medios.url_satelite(-16.5, -68.15, "") is None


def test_la_busqueda_de_video_escapa_la_consulta():
    url = medios.url_busqueda_videos("Terremoto en Ende, Indonesia")
    assert " " not in url
    assert _parametros(url)["search_query"] == "Terremoto en Ende, Indonesia"


def test_la_busqueda_de_video_sin_texto_queda_vacia():
    assert medios.url_busqueda_videos("") == ""


def test_reconoce_imagenes_aunque_traigan_query():
    assert medios.es_imagen("https://x.org/mapa.png?v=3")
    assert medios.es_imagen("https://x.org/MAPA.JPG")
    assert not medios.es_imagen("https://x.org/report.aspx?eventid=1")
    assert not medios.es_imagen("")


def test_la_configuracion_del_feed_trae_todo_lo_que_el_cliente_completa():
    configuracion = medios.configuracion()
    plantilla = configuracion["satelite"]["plantilla"]
    huecos = ("{capa}", "{fecha}", "{sur}", "{oeste}", "{norte}", "{este}", "{ancho}", "{alto}")
    for hueco in huecos:
        assert hueco in plantilla
    assert "{consulta}" in configuracion["videos"]["plantilla_busqueda"]
    assert configuracion["satelite"]["grados_por_tipo"]["sismo"] > 0


def test_limpiar_saca_las_claves_vacias():
    assert medios.limpiar({"icono": "", "mapa": "x.png", "recursos": []}) == {"mapa": "x.png"}
