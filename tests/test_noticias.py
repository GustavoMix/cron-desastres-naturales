from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from desastres import noticias
from desastres.modelo import Evento

FIXTURES = Path(__file__).parent / "fixtures"

BuscadorGDELT = noticias.BuscadorGDELT
BuscadorGoogle = noticias.BuscadorGoogleNoticias


@pytest.fixture
def gdelt_crudo() -> bytes:
    return (FIXTURES / "gdelt_articulos.json").read_bytes()


@pytest.fixture
def google_crudo() -> bytes:
    return (FIXTURES / "google_noticias.xml").read_bytes()


def hacer_evento(**kwargs) -> Evento:
    base = dict(
        id="usgs:x1",
        fuente="usgs",
        tipo="sismo",
        titulo="M 5.4 - 24 km SW of La Paz, Bolivia",
        fecha_evento="2026-08-06T00:53:20Z",
        url="https://example.org",
        lugar="24 km SW of La Paz, Bolivia",
        pais="Bolivia",
        paises=["BO"],
        magnitud=5.4,
    )
    base.update(kwargs)
    return Evento(**base)


AHORA = datetime(2026, 8, 10, 12, 0, 0, tzinfo=timezone.utc)


# ------------------------------------------------------------------ consulta


def test_la_consulta_usa_palabras_que_un_diario_usaria():
    """"M 5.4 - 24 km SW of..." no matchea nada: ningún medio titula así."""
    assert noticias.consulta_de(hacer_evento()) == "terremoto La Paz, Bolivia"


def test_la_consulta_saca_distancia_y_rumbo_del_lugar():
    evento = hacer_evento(lugar="104 km WNW of Houma, Tonga")
    assert noticias.consulta_de(evento) == "terremoto Houma, Tonga"


def test_sin_lugar_la_consulta_cae_en_el_pais():
    evento = hacer_evento(lugar="", pais="Chile")
    assert noticias.consulta_de(evento) == "terremoto Chile"


def test_cada_tipo_tiene_su_palabra():
    assert "ciclón" in noticias.consulta_de(hacer_evento(tipo="ciclon"))
    assert "incendio" in noticias.consulta_de(hacer_evento(tipo="incendio"))


# --------------------------------------------------------------------- GDELT


def test_gdelt_parsea_las_notas_y_descarta_las_rotas(gdelt_crudo):
    encontradas = BuscadorGDELT().parsear(gdelt_crudo, 10)
    assert [n.medio for n in encontradas] == ["eldeber.com.bo", "youtube.com", "reuters.com"]


def test_gdelt_trae_la_foto_de_portada(gdelt_crudo):
    """Es la única de las dos fuentes que da imagen, y una foto real vale mucho."""
    primera = BuscadorGDELT().parsear(gdelt_crudo, 10)[0]
    assert primera.imagen == "https://www.eldeber.com.bo/img/sismo.jpg"


def test_gdelt_traduce_su_formato_de_fecha_a_iso(gdelt_crudo):
    assert BuscadorGDELT().parsear(gdelt_crudo, 10)[0].fecha == "2026-08-06T01:15:00Z"


def test_marca_como_video_las_notas_que_son_video(gdelt_crudo):
    encontradas = BuscadorGDELT().parsear(gdelt_crudo, 10)
    assert [n.es_video for n in encontradas] == [False, True, False]


def test_gdelt_respeta_el_maximo(gdelt_crudo):
    assert len(BuscadorGDELT().parsear(gdelt_crudo, 2)) == 2


def test_una_respuesta_que_no_es_json_es_cero_noticias_no_un_error():
    """Ante una consulta que no le gusta, GDELT contesta 200 con texto plano."""
    assert BuscadorGDELT().parsear(b"Your query was too short.", 5) == []


def test_la_url_de_gdelt_acota_la_ventana_al_evento():
    """Sin ventana, "terremoto Chile" trae notas de todos los sismos de la década."""
    url = BuscadorGDELT().url(hacer_evento(), AHORA, 5)
    parametros = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
    assert parametros["startdatetime"] == "20260805005320"
    assert parametros["enddatetime"] == "20260810120000"


def test_la_ventana_nunca_pide_noticias_del_futuro():
    """El evento es de ayer: pedir hasta 7 días adelante sería pedir mañana."""
    evento = hacer_evento(fecha_evento="2026-08-09T00:00:00Z")
    url = BuscadorGDELT().url(evento, AHORA, 5)
    fin = parse_qs(urlparse(url).query)["enddatetime"][0]
    assert fin == "20260810120000"


# ------------------------------------------------------------ Google Noticias


def test_google_parsea_las_notas_y_descarta_las_rotas(google_crudo):
    encontradas = BuscadorGoogle().parsear(google_crudo, 10)
    assert [n.medio for n in encontradas] == ["Página Siete", "El Deber", "Diario Y"]


def test_google_saca_el_medio_pegado_al_final_del_titulo(google_crudo):
    """Google titula "Nota - Diario X"; con el medio en su campo, repetirlo sobra."""
    primera = BuscadorGoogle().parsear(google_crudo, 10)[0]
    assert primera.titulo == "Sismo de 5.4 sacudió La Paz esta madrugada"
    assert primera.medio == "Página Siete"


def test_google_traduce_rfc822_a_iso(google_crudo):
    assert BuscadorGoogle().parsear(google_crudo, 10)[0].fecha == "2026-08-06T01:15:00Z"


def test_una_fecha_ilegible_no_descarta_la_nota(google_crudo):
    """La nota sigue sirviendo aunque no se sepa exactamente cuándo salió."""
    ultima = BuscadorGoogle().parsear(google_crudo, 10)[-1]
    assert ultima.medio == "Diario Y"
    assert ultima.fecha == ""


def test_una_respuesta_que_no_es_xml_es_cero_noticias():
    assert BuscadorGoogle().parsear(b"<<< roto", 5) == []


def test_la_url_de_google_pide_prensa_en_espaniol_de_la_region():
    url = BuscadorGoogle().url(hacer_evento(), AHORA, 5)
    parametros = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
    assert parametros["hl"] == "es-419"
    assert parametros["gl"] == "BO"
    assert "after:2026-08-05" in parametros["q"]
    assert "before:2026-08-10" in parametros["q"]


# ------------------------------------------------------------------ selección


def test_lo_cercano_gana_sobre_lo_grande():
    """Un sismo moderado acá importa más que uno enorme en el otro hemisferio."""
    cerca = hacer_evento(id="cerca", magnitud=4.0, paises=["BO"])
    lejos = hacer_evento(id="lejos", magnitud=7.5, paises=["JP"])

    elegidos = noticias.elegir_para_noticias(
        [lejos, cerca], maximo=2, paises_prioritarios=("BO",)
    )

    assert [e.id for e in elegidos] == ["cerca", "lejos"]


def test_a_igual_cercania_manda_el_nivel_de_alerta():
    roja = hacer_evento(id="roja", nivel_alerta="roja", magnitud=4.0, paises=["JP"])
    verde = hacer_evento(id="verde", nivel_alerta="verde", magnitud=6.9, paises=["JP"])

    elegidos = noticias.elegir_para_noticias([verde, roja], maximo=2)

    assert [e.id for e in elegidos] == ["roja", "verde"]


def test_a_igual_gravedad_manda_lo_mas_reciente():
    viejo = hacer_evento(id="viejo", fecha_evento="2026-08-01T00:00:00Z", magnitud=5.0)
    nuevo = hacer_evento(id="nuevo", fecha_evento="2026-08-09T00:00:00Z", magnitud=5.0)

    elegidos = noticias.elegir_para_noticias([viejo, nuevo], maximo=2)

    assert [e.id for e in elegidos] == ["nuevo", "viejo"]


def test_no_se_consultan_eventos_sin_donde():
    """Buscar "terremoto" a secas trae noticias de cualquier parte del mundo."""
    sin_lugar = hacer_evento(id="sinlugar", lugar="", pais="", paises=[])
    con_lugar = hacer_evento(id="conlugar")

    elegidos = noticias.elegir_para_noticias([sin_lugar, con_lugar], maximo=10)

    assert [e.id for e in elegidos] == ["conlugar"]


def test_el_maximo_acota_cuantos_se_consultan():
    eventos = [hacer_evento(id=f"e{i}") for i in range(10)]
    assert len(noticias.elegir_para_noticias(eventos, maximo=3)) == 3


def test_maximo_cero_no_elige_ninguno():
    assert noticias.elegir_para_noticias([hacer_evento()], maximo=0) == []


# -------------------------------------------------------------------- fetch


class BuscadorFalso:
    def __init__(self, nombre, resultados=None, explota=False):
        self.nombre = nombre
        self.resultados = resultados or []
        self.explota = explota
        self.consultas = 0

    def url(self, evento, ahora, maximo):
        return f"https://falso/{self.nombre}"

    def parsear(self, crudo, maximo):
        return list(self.resultados)


def _descarga_falsa(buscador):
    def descargar(url, **kwargs):
        buscador.consultas += 1
        if buscador.explota:
            raise RuntimeError("caído")
        return b"{}"

    return descargar


def test_el_segundo_buscador_entra_solo_si_el_primero_no_trajo_nada(monkeypatch):
    vacio = BuscadorFalso("vacio")
    suplente = BuscadorFalso("suplente", [noticias.Noticia("T", "https://a.com", "a")])

    llamadas = []

    def descargar(url, **kwargs):
        llamadas.append(url)
        return b"{}"

    monkeypatch.setattr(noticias, "descargar", descargar)
    encontradas = noticias.buscar_para(
        hacer_evento(), ahora=AHORA, timeout=1, reintentos=1, buscadores=(vacio, suplente)
    )

    assert [n.url for n in encontradas] == ["https://a.com"]
    assert llamadas == ["https://falso/vacio", "https://falso/suplente"]


def test_si_el_primero_trae_resultados_no_se_consulta_el_segundo(monkeypatch):
    primero = BuscadorFalso("primero", [noticias.Noticia("T", "https://a.com", "a")])
    segundo = BuscadorFalso("segundo", [noticias.Noticia("U", "https://b.com", "b")])

    llamadas = []
    monkeypatch.setattr(noticias, "descargar", lambda url, **kw: llamadas.append(url) or b"{}")
    noticias.buscar_para(
        hacer_evento(), ahora=AHORA, timeout=1, reintentos=1, buscadores=(primero, segundo)
    )

    assert llamadas == ["https://falso/primero"]


def test_un_buscador_caido_no_tumba_la_busqueda(monkeypatch):
    suplente = BuscadorFalso("suplente", [noticias.Noticia("T", "https://a.com", "a")])

    def descargar(url, **kwargs):
        if url.endswith("roto"):
            raise RuntimeError("caído")
        return b"{}"

    monkeypatch.setattr(noticias, "descargar", descargar)
    encontradas = noticias.buscar_para(
        hacer_evento(),
        ahora=AHORA,
        timeout=1,
        reintentos=1,
        buscadores=(BuscadorFalso("roto"), suplente),
    )

    assert len(encontradas) == 1


def test_ordena_espaniol_primero_y_despues_con_foto():
    ingles = noticias.Noticia("A", "https://a", "a", idioma="english", imagen="x.jpg")
    espaniol_sin_foto = noticias.Noticia("B", "https://b", "b", idioma="spanish")
    espaniol_con_foto = noticias.Noticia("C", "https://c", "c", idioma="spanish", imagen="y.jpg")

    ordenadas = noticias._ordenar([ingles, espaniol_sin_foto, espaniol_con_foto])

    assert [n.titulo for n in ordenadas] == ["C", "B", "A"]


def test_recolectar_agrupa_por_id_agrupado_no_por_id(monkeypatch):
    """Un ciclón de GDACS se republica por episodios; si no, las notas se parten."""
    evento = hacer_evento(id="gdacs:TC:1:14", id_agrupado="gdacs:TC:1", tipo="ciclon")
    monkeypatch.setattr(
        noticias,
        "buscar_para",
        lambda ev, **kw: [noticias.Noticia("T", "https://a.com", "a")],
    )

    resultado = noticias.recolectar(
        [evento], ahora=AHORA, timeout=1, reintentos=1, maximo_eventos=5, espera=0
    )

    assert list(resultado.por_evento) == ["gdacs:TC:1"]


def test_recolectar_espera_entre_consultas_pero_no_antes_de_la_primera(monkeypatch):
    """Sin pausa, decenas de pedidos seguidos hacen que devuelvan 429."""
    eventos = [hacer_evento(id=f"e{i}") for i in range(3)]
    monkeypatch.setattr(noticias, "buscar_para", lambda ev, **kw: [])
    esperas = []

    noticias.recolectar(
        eventos,
        ahora=AHORA,
        timeout=1,
        reintentos=1,
        maximo_eventos=5,
        espera=1.5,
        dormir=esperas.append,
    )

    assert esperas == [1.5, 1.5]


def test_un_evento_sin_noticias_no_ocupa_lugar_en_el_archivo(monkeypatch):
    monkeypatch.setattr(noticias, "buscar_para", lambda ev, **kw: [])

    resultado = noticias.recolectar(
        [hacer_evento()], ahora=AHORA, timeout=1, reintentos=1, maximo_eventos=5, espera=0
    )

    assert resultado.por_evento == {}
    assert resultado.consultados == 1
    assert resultado.con_noticias == 0


def test_el_documento_sale_ordenado_y_con_metadatos():
    resultado = noticias.ResultadoNoticias(
        por_evento={
            "b": [noticias.Noticia("T", "https://b", "b")],
            "a": [noticias.Noticia("U", "https://a", "a")],
        }
    )

    documento = noticias.documento(resultado, AHORA)

    assert list(documento["noticias"]) == ["a", "b"]
    assert documento["eventos_con_noticias"] == 2
    assert documento["generado"] == "2026-08-10T12:00:00Z"

