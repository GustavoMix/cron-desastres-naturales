import pytest

from desastres.fuentes.gdacs import FuenteGDACS


@pytest.fixture
def eventos(gdacs_crudo):
    return FuenteGDACS().parsear(gdacs_crudo)


def test_descarta_items_sin_eventid_ni_fecha(eventos):
    assert [evento.id for evento in eventos] == [
        "gdacs:EQ:1477001:1",
        "gdacs:TC:1000988:14",
        "gdacs:FL:1102344",
    ]


def test_traduce_los_codigos_de_amenaza(eventos):
    assert [evento.tipo for evento in eventos] == ["sismo", "ciclon", "inundacion"]


def test_normaliza_niveles_de_alerta(eventos):
    assert [evento.nivel_alerta for evento in eventos] == ["verde", "naranja", "roja"]


def test_lee_severidad_desde_los_atributos(eventos):
    ciclon = eventos[1]
    assert ciclon.magnitud == 185.0
    assert ciclon.unidad_magnitud == "km/h"
    assert ciclon.extra["severidad_texto"] == "Maximum wind speed 185 km/h"


def test_severidad_sin_valor_numerico_queda_en_none(eventos):
    inundacion = eventos[2]
    assert inundacion.magnitud is None
    assert inundacion.unidad_magnitud == ""


def test_lee_coordenadas_anidadas_y_sueltas(eventos):
    # El primer item usa <geo:Point>; el segundo publica geo:lat/geo:long sueltos.
    assert eventos[0].latitud == pytest.approx(-30.0512)
    assert eventos[0].longitud == pytest.approx(-71.4123)
    assert eventos[1].latitud == pytest.approx(13.4)
    assert eventos[1].longitud == pytest.approx(122.7)


def test_prefiere_fromdate_sobre_pubdate(eventos):
    sismo = eventos[0]
    assert sismo.fecha_evento == "2026-08-06T00:53:20Z"
    assert sismo.fecha_actualizacion == "2026-08-06T01:10:00Z"


def test_cae_en_pubdate_cuando_no_hay_fromdate(eventos):
    assert eventos[2].fecha_evento == "2026-08-04T09:30:00Z"


def test_el_episodio_forma_parte_de_la_clave(eventos):
    # Dos episodios del mismo ciclón son registros distintos, no un pisado.
    assert eventos[1].id.endswith(":14")
    assert eventos[1].extra["episodio"] == "14"


def test_id_agrupado_descarta_el_episodio(eventos):
    # Es la clave a la que la app cuelga los comentarios: si llevara el
    # episodio, un ciclón de cinco días fragmentaría sus comentarios.
    ciclon = eventos[1]
    assert ciclon.id == "gdacs:TC:1000988:14"
    assert ciclon.id_agrupado == "gdacs:TC:1000988"


def test_id_agrupado_sin_episodio_coincide_con_el_id(eventos):
    inundacion = eventos[2]
    assert inundacion.id_agrupado == inundacion.id == "gdacs:FL:1102344"


def test_traduce_el_pais_a_codigo_iso(eventos):
    assert [e.paises for e in eventos] == [["CL"], ["PH"], ["PK"]]


def test_rescata_el_icono_de_alerta_y_el_mapa_adjunto(eventos):
    media = eventos[0].media
    assert media["icono"] == "https://www.gdacs.org/images/gdacs_icons/maps/Green/EQ.png"
    assert media["mapa"] == "https://www.gdacs.org/contentdata/resources/EQ/1477001/mapa_general.png"


def test_junta_los_mapas_sueltos_como_recursos(eventos):
    assert eventos[0].media["recursos"] == [
        {
            "url": "https://www.gdacs.org/contentdata/resources/EQ/1477001/intensidad.png",
            "titulo": "Mapa de intensidad",
        },
    ]


def test_descarta_los_recursos_que_no_son_imagenes(eventos):
    """El informe HTML es un link, no una foto: en una galería no va."""
    urls = [recurso["url"] for recurso in eventos[0].media.get("recursos", [])]
    assert all(not url.endswith(".aspx") for url in urls)
    assert "report.aspx" not in eventos[0].media.get("mapa", "")


def test_un_evento_sin_imagenes_no_arrastra_un_media_vacio(eventos):
    """Un dict de claves vacías por evento son kilobytes de nada en el feed."""
    assert eventos[1].media == {}


def test_conserva_la_poblacion_expuesta_y_el_iso3(eventos):
    sismo = eventos[0]
    assert sismo.extra["poblacion_afectada"] == 128000.0
    assert sismo.extra["poblacion_texto"] == "128 thousand people in 100km"
    assert sismo.extra["iso3"] == "CHL"
