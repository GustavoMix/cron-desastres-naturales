import json
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


def test_gdelt_descarta_links_de_redes_sociales():
    """"Qué dijeron los medios" es prensa, no un post de Facebook."""
    crudo = json.dumps(
        {
            "articles": [
                {
                    "url": "https://www.facebook.com/BomberosBolivia/posts/123",
                    "title": "Un post cualquiera",
                    "domain": "facebook.com",
                },
                {
                    "url": "https://www.bbc.com/mundo/sismo",
                    "title": "Terremoto sacude La Paz",
                    "domain": "bbc.com",
                },
            ]
        }
    ).encode()

    encontradas = BuscadorGDELT().parsear(crudo, 10)

    assert [n.medio for n in encontradas] == ["bbc.com"]


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


def test_google_descarta_por_el_dominio_real_no_por_el_redirect():
    """El <link> de Google Noticias siempre es news.google.com; el medio real
    (y si es red social) sale del atributo `url` de <source>."""
    crudo = b"""<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0"><channel>
      <item>
        <title>Un post cualquiera - Facebook</title>
        <link>https://news.google.com/rss/articles/FBREDIRECT</link>
        <pubDate>Thu, 06 Aug 2026 01:15:00 GMT</pubDate>
        <source url="https://www.facebook.com/BomberosBolivia">Facebook</source>
      </item>
      <item>
        <title>Terremoto sacude La Paz - BBC News Mundo</title>
        <link>https://news.google.com/rss/articles/BBCREDIRECT</link>
        <pubDate>Thu, 06 Aug 2026 01:15:00 GMT</pubDate>
        <source url="https://www.bbc.com/mundo">BBC News Mundo</source>
      </item>
    </channel></rss>"""

    encontradas = BuscadorGoogle().parsear(crudo, 10)

    assert [n.medio for n in encontradas] == ["BBC News Mundo"]


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


# ------------------------------------------------------------- og:image


def test_leer_og_parsea_ambos_ordenes_de_atributos(monkeypatch):
    directo = b'<meta property="og:image" content="https://medio.com/a.jpg">'
    invertido = b'<meta content="https://medio.com/b.jpg" property="og:image">'

    monkeypatch.setattr(noticias, "descargar", lambda url, **kw: directo)
    assert noticias._leer_og("https://medio.com/nota", timeout=1).imagen == "https://medio.com/a.jpg"

    monkeypatch.setattr(noticias, "descargar", lambda url, **kw: invertido)
    assert noticias._leer_og("https://medio.com/nota", timeout=1).imagen == "https://medio.com/b.jpg"


def test_leer_og_se_queda_con_la_primera_imagen(monkeypatch):
    """La de arriba es la principal; las de abajo suelen ser el logo o publicidad."""
    html = (
        b'<meta property="og:image" content="https://medio.com/nota.jpg">'
        b'<meta property="og:image" content="https://medio.com/logo.png">'
    )
    monkeypatch.setattr(noticias, "descargar", lambda url, **kw: html)

    assert noticias._leer_og("https://medio.com/n", timeout=1).imagen == "https://medio.com/nota.jpg"


def test_leer_og_sin_etiqueta_es_cadena_vacia(monkeypatch):
    monkeypatch.setattr(noticias, "descargar", lambda url, **kw: b"<html>sin nada</html>")
    datos = noticias._leer_og("https://medio.com/nota", timeout=1)
    assert datos.imagen == ""
    assert datos.es_video is False


def test_leer_og_si_la_descarga_falla_no_revienta(monkeypatch):
    def descargar_roto(url, **kwargs):
        raise RuntimeError("caído")

    monkeypatch.setattr(noticias, "descargar", descargar_roto)
    assert noticias._leer_og("https://medio.com/nota", timeout=1) == noticias.DatosDePagina()


def test_leer_og_detecta_video_de_un_canal_de_tv(monkeypatch):
    """El canal publica el video en su propio sitio: por dominio no se detectaba."""
    html = (
        b'<meta property="og:type" content="video.other">'
        b'<meta property="og:image" content="https://tv.bo/portada.jpg">'
    )
    monkeypatch.setattr(noticias, "descargar", lambda url, **kw: html)

    datos = noticias._leer_og("https://tv.bo/nota", timeout=1)

    assert datos.es_video is True
    assert datos.imagen == "https://tv.bo/portada.jpg"


def test_leer_og_detecta_video_por_la_etiqueta_og_video(monkeypatch):
    html = b'<meta property="og:video:url" content="https://tv.bo/v.mp4">'
    monkeypatch.setattr(noticias, "descargar", lambda url, **kw: html)

    assert noticias._leer_og("https://tv.bo/nota", timeout=1).es_video is True


def test_leer_og_no_marca_video_una_nota_de_texto(monkeypatch):
    html = b'<meta property="og:type" content="article">'
    monkeypatch.setattr(noticias, "descargar", lambda url, **kw: html)

    assert noticias._leer_og("https://medio.com/nota", timeout=1).es_video is False


def test_enriquecer_completa_la_foto_de_una_nota_sin_imagen(monkeypatch):
    sin_foto = noticias.Noticia("T", "https://medio.com/nota", "medio")
    monkeypatch.setattr(
        noticias,
        "_leer_og",
        lambda url, **kw: noticias.DatosDePagina(imagen="https://medio.com/foto.jpg"),
    )

    resultado = noticias._enriquecer_desde_la_pagina([sin_foto], timeout=1)

    assert resultado[0].imagen == "https://medio.com/foto.jpg"


def test_enriquecer_no_pide_la_pagina_de_una_nota_que_ya_tiene_foto(monkeypatch):
    con_foto = noticias.Noticia("T", "https://medio.com/nota", "medio", imagen="ya-tenia.jpg")
    llamadas = []
    monkeypatch.setattr(
        noticias,
        "_leer_og",
        lambda url, **kw: llamadas.append(url) or noticias.DatosDePagina(imagen="otra.jpg"),
    )

    resultado = noticias._enriquecer_desde_la_pagina([con_foto], timeout=1)

    assert resultado[0].imagen == "ya-tenia.jpg"
    assert llamadas == []


def test_enriquecer_corta_al_llegar_al_tope_de_paginas(monkeypatch):
    """Cada página es un pedido de red: no se piden las 6 notas de un evento."""
    notas = [noticias.Noticia(f"T{i}", f"https://m{i}.com", "m") for i in range(5)]
    llamadas = []
    monkeypatch.setattr(
        noticias,
        "_leer_og",
        lambda url, **kw: llamadas.append(url) or noticias.DatosDePagina(imagen="foto.jpg"),
    )

    noticias._enriquecer_desde_la_pagina(notas, timeout=1, maximo_paginas=2)

    assert llamadas == ["https://m0.com", "https://m1.com"]


def test_enriquecer_marca_el_video_que_descubrio_la_pagina(monkeypatch):
    nota = noticias.Noticia("T", "https://tv.bo/nota", "tv")
    monkeypatch.setattr(
        noticias,
        "_leer_og",
        lambda url, **kw: noticias.DatosDePagina(imagen="p.jpg", es_video=True),
    )

    resultado = noticias._enriquecer_desde_la_pagina([nota], timeout=1)

    assert resultado[0].es_video is True


def test_enriquecer_no_desmarca_un_video_ya_detectado_por_dominio(monkeypatch):
    nota = noticias.Noticia("T", "https://youtube.com/watch?v=1", "yt", es_video=True)
    monkeypatch.setattr(noticias, "_leer_og", lambda url, **kw: noticias.DatosDePagina())

    resultado = noticias._enriquecer_desde_la_pagina([nota], timeout=1)

    assert resultado[0].es_video is True


def test_enriquecer_se_frena_cuando_no_queda_presupuesto(monkeypatch):
    """Pedir fotos no puede robarle el tiempo a los eventos sin consultar."""
    notas = [noticias.Noticia("T", "https://a.com", "a")]
    llamadas = []
    monkeypatch.setattr(
        noticias,
        "_leer_og",
        lambda url, **kw: llamadas.append(url) or noticias.DatosDePagina(),
    )

    noticias._enriquecer_desde_la_pagina(notas, timeout=1, queda_tiempo=lambda: False)

    assert llamadas == []


def test_enriquecer_sin_resultado_deja_la_nota_igual(monkeypatch):
    sin_foto = noticias.Noticia("T", "https://medio.com/nota", "medio")
    monkeypatch.setattr(noticias, "_leer_og", lambda url, **kw: noticias.DatosDePagina())

    resultado = noticias._enriquecer_desde_la_pagina([sin_foto], timeout=1)

    assert resultado[0].imagen == ""


def test_recolectar_completa_la_foto_de_respaldo(monkeypatch):
    monkeypatch.setattr(
        noticias, "buscar_para", lambda ev, **kw: [noticias.Noticia("T", "https://a.com", "a")]
    )
    monkeypatch.setattr(
        noticias,
        "_leer_og",
        lambda url, **kw: noticias.DatosDePagina(imagen="https://a.com/foto.jpg"),
    )

    resultado = noticias.recolectar(
        [hacer_evento()], ahora=AHORA, timeout=1, reintentos=1, maximo_eventos=5, espera=0
    )

    notas = next(iter(resultado.por_evento.values()))
    assert notas[0].imagen == "https://a.com/foto.jpg"


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


def test_recolectar_corta_al_agotar_el_presupuesto(monkeypatch):
    """Un buscador caído no debe poder comerse el timeout del job entero."""
    eventos = [hacer_evento(id=f"e{i}") for i in range(5)]
    monkeypatch.setattr(noticias, "buscar_para", lambda ev, **kw: [])
    # reloj(): una lectura al arrancar y una por evento evaluado. Se agota
    # justo antes del tercer evento.
    lecturas = iter([0, 0, 50, 110])

    resultado = noticias.recolectar(
        eventos,
        ahora=AHORA,
        timeout=1,
        reintentos=1,
        maximo_eventos=5,
        espera=0,
        presupuesto=100,
        reloj=lambda: next(lecturas),
    )

    assert resultado.consultados == 2


def test_recolectar_sin_presupuesto_no_corta(monkeypatch):
    eventos = [hacer_evento(id=f"e{i}") for i in range(3)]
    monkeypatch.setattr(noticias, "buscar_para", lambda ev, **kw: [])

    resultado = noticias.recolectar(
        eventos, ahora=AHORA, timeout=1, reintentos=1, maximo_eventos=5, espera=0, presupuesto=None
    )

    assert resultado.consultados == 3


def test_un_evento_sin_noticias_no_ocupa_lugar_en_el_archivo(monkeypatch):
    monkeypatch.setattr(noticias, "buscar_para", lambda ev, **kw: [])

    resultado = noticias.recolectar(
        [hacer_evento()], ahora=AHORA, timeout=1, reintentos=1, maximo_eventos=5, espera=0
    )

    assert resultado.por_evento == {}
    assert resultado.consultados == 1
    assert resultado.con_noticias == 0


def test_el_documento_respeta_el_orden_de_relevancia_no_alfabetico():
    """`por_evento` ya viene ordenado por elegir_para_noticias (relevancia);
    reordenar acá por clave tiraría esa prioridad a la basura."""
    resultado = noticias.ResultadoNoticias(
        por_evento={
            "b": [noticias.Noticia("T", "https://b", "b")],
            "a": [noticias.Noticia("U", "https://a", "a")],
        }
    )

    documento = noticias.documento(resultado, AHORA)

    assert list(documento["noticias"]) == ["b", "a"]
    assert documento["eventos_con_noticias"] == 2
    assert documento["generado"] == "2026-08-10T12:00:00Z"

