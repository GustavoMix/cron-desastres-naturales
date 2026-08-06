import pytest

from desastres.modelo import codigos_de_pais


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("Chile", ["CL"]),
        ("Bolivia", ["BO"]),
        ("chile", ["CL"]),
        ("  Japan  ", ["JP"]),
    ],
)
def test_traduce_nombres_simples(texto, esperado):
    assert codigos_de_pais(texto) == esperado


@pytest.mark.parametrize(
    ("estado", "esperado"),
    [("Alaska", ["US"]), ("CA", ["US"]), ("Texas", ["US"]), ("New Mexico", ["US"])],
)
def test_los_estados_de_eeuu_resuelven_al_pais(estado, esperado):
    # Sin esto, filtrar por país pondría cada estado como si fuera uno aparte:
    # en una muestra real, 110 eventos quedaban bajo "CA" y 63 bajo "Alaska".
    assert codigos_de_pais(estado) == esperado


def test_traduce_nombres_que_no_son_el_iso_oficial():
    assert codigos_de_pais("Russian Federation") == ["RU"]
    assert codigos_de_pais("The Democratic Republic of Congo") == ["CD"]


def test_separa_los_eventos_multipais_de_gdacs():
    # GDACS mete varios países en un solo campo para ciclones y sequías.
    assert codigos_de_pais("Australia, Indonesia, Cambodia") == ["AU", "ID", "KH"]


def test_prefiere_la_cadena_entera_antes_que_partirla():
    # "The Democratic Republic of Congo" tiene comas en otros contextos; si se
    # partiera primero, ningún pedazo resolvería.
    assert codigos_de_pais("Bolivia, Plurinational State of") == ["BO"]


def test_ignora_los_pedazos_que_no_reconoce():
    assert codigos_de_pais("Chile, Vulcanistán") == ["CL"]


def test_deduplica_conservando_el_orden():
    assert codigos_de_pais("Chile, Peru, Chile") == ["CL", "PE"]


@pytest.mark.parametrize("vacio", ["", "   ", None, ",,,"])
def test_devuelve_lista_vacia_sin_datos(vacio):
    assert codigos_de_pais(vacio) == []


def test_region_desconocida_no_rompe():
    assert codigos_de_pais("south of the Kermadec Islands") == []


def test_resuelve_zonas_sismicas_con_sufijo_region():
    # USGS etiqueta así varias zonas: "New Zealand region".
    assert codigos_de_pais("New Zealand region") == ["NZ"]


def test_acepta_un_alfa2_que_la_fuente_ya_publica():
    # USGS escribe "Baja California, MX".
    assert codigos_de_pais("MX") == ["MX"]


def test_ca_es_california_no_canada():
    # USGS escribe Canadá con el nombre completo, así que el código de dos
    # letras siempre es el estado. Los estados ganan sobre el alfa-2 ISO.
    assert codigos_de_pais("CA") == ["US"]
    assert codigos_de_pais("Canada") == ["CA"]


def test_resuelve_territorios_de_eeuu_como_pais_propio():
    # Tienen código ISO propio: no son "US".
    assert codigos_de_pais("U.S. Virgin Islands") == ["VI"]
