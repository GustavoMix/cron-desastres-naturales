import pytest

from desastres.fuentes.eonet import FuenteEONET


@pytest.fixture
def eventos(eonet_crudo):
    return FuenteEONET().parsear(eonet_crudo)


def test_descarta_eventos_sin_id_sin_geometria_ni_fecha_legible(eventos):
    assert [evento.id for evento in eventos] == [
        "eonet:EONET_6201",
        "eonet:EONET_6202",
        "eonet:EONET_6203",
    ]


def test_traduce_las_categorias_a_los_tipos_del_modelo(eventos):
    assert [evento.tipo for evento in eventos] == ["incendio", "volcan", "otro"]


def test_la_fecha_del_evento_es_la_primera_posicion_no_la_ultima(eventos):
    """Un incendio se republica cada día que arde; interesa cuándo empezó."""
    incendio = eventos[0]
    assert incendio.fecha_evento == "2026-08-03T00:00:00Z"
    assert incendio.fecha_actualizacion == "2026-08-05T00:00:00Z"


def test_las_coordenadas_geojson_llegan_invertidas_y_se_enderezan(eventos):
    incendio = eventos[0]
    assert incendio.latitud == 39.75
    assert incendio.longitud == -121.6


def test_un_poligono_se_reduce_a_su_primer_vertice(eventos):
    volcan = eventos[1]
    assert volcan.latitud == -2.0
    assert volcan.longitud == -78.34


def test_la_magnitud_es_la_ultima_medida_no_la_primera(eventos):
    """El incendio empezó con 1.200 acres y va por 8.400: vale el número de hoy."""
    incendio = eventos[0]
    assert incendio.magnitud == 8400.0
    assert incendio.unidad_magnitud == "acres"


def test_prefiere_la_pagina_de_la_fuente_original_al_json_de_la_api(eventos):
    assert eventos[0].url == "https://inciweb.nwcg.gov/incident/9999/"


def test_sin_fuente_original_cae_en_la_pagina_del_evento(eventos):
    assert eventos[1].url == "https://eonet.gsfc.nasa.gov/api/v3/events/EONET_6202"


def test_saca_el_lugar_del_titulo_y_lo_resuelve_a_pais(eventos):
    volcan = eventos[1]
    assert volcan.lugar == "Sangay, Ecuador"
    assert volcan.paises == ["EC"]


def test_un_titulo_sin_guion_no_inventa_lugar(eventos):
    iceberg = eventos[2]
    assert iceberg.lugar == ""
    assert iceberg.paises == []


def test_no_inventa_nivel_de_alerta(eventos):
    """EONET no clasifica gravedad; la app la deduce de la magnitud."""
    assert all(evento.nivel_alerta == "" for evento in eventos)


def test_conserva_si_el_evento_ya_esta_cerrado(eventos):
    assert eventos[1].extra["cerrado"] == "2026-08-04T00:00:00Z"
    assert eventos[0].extra["cerrado"] == ""


def test_un_documento_vacio_no_revienta():
    assert FuenteEONET().parsear(b'{"events": []}') == []
