import pytest

from desastres.fuentes.usgs import FuenteUSGS


@pytest.fixture
def eventos(usgs_crudo):
    return FuenteUSGS().parsear(usgs_crudo)


def test_descarta_rasgos_sin_id_ni_fecha(eventos):
    # El fixture trae 5 rasgos: uno sin `time` y otro sin `id` deben caer.
    assert [evento.id for evento in eventos] == [
        "usgs:us7000abcd",
        "usgs:us7000volc",
        "usgs:ci40123456",
    ]


def test_mapea_campos_del_sismo(eventos):
    sismo = eventos[0]
    assert sismo.fuente == "usgs"
    assert sismo.tipo == "sismo"
    assert sismo.magnitud == 5.4
    assert sismo.unidad_magnitud == "mww"
    assert sismo.nivel_alerta == "verde"
    assert sismo.lugar == "24 km SW of Coquimbo, Chile"
    assert sismo.pais == "Chile"
    assert sismo.url.endswith("us7000abcd")


def test_invierte_el_orden_de_coordenadas_geojson(eventos):
    # GeoJSON publica [lon, lat, profundidad]; el modelo separa cada eje.
    sismo = eventos[0]
    assert sismo.latitud == pytest.approx(-30.0512)
    assert sismo.longitud == pytest.approx(-71.4123)
    assert sismo.profundidad_km == pytest.approx(42.6)


def test_convierte_epoch_ms_a_iso_utc(eventos):
    assert eventos[0].fecha_evento == "2026-08-06T01:33:20Z"
    assert eventos[0].fecha_actualizacion == "2026-08-06T02:23:20Z"


def test_tolera_campos_nulos(eventos):
    volcan = eventos[1]
    assert volcan.tipo == "volcan"
    assert volcan.magnitud is None
    assert volcan.unidad_magnitud == ""
    assert volcan.nivel_alerta == ""
    assert volcan.fecha_actualizacion == ""
    # Sin tercer valor en `coordinates` no hay profundidad que informar.
    assert volcan.profundidad_km is None


def test_evento_no_tectonico_cae_en_otro(eventos):
    assert eventos[2].tipo == "otro"


def test_feed_vacio_no_rompe():
    assert FuenteUSGS().parsear(b'{"type": "FeatureCollection", "features": []}') == []
