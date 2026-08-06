"""Genera `src/desastres/paises.py` a partir de pycountry.

La tabla se vendoriza para que el scraper siga sin dependencias de runtime:
pycountry solo hace falta acá, y solo cuando haya que regenerarla.

    python herramientas/generar_paises.py

Regenerá cuando cambie la lista ISO-3166 o cuando aparezca un nombre que las
fuentes usan y la tabla no reconoce (los avisos del log del scraper los
delatan: "país no reconocido").
"""

from __future__ import annotations

from pathlib import Path

import pycountry

DESTINO = Path(__file__).resolve().parents[1] / "src" / "desastres" / "paises.py"

# Nombres que USGS y GDACS usan y que no coinciden con el nombre ISO oficial.
# Salen de mirar los datos reales; ampliá cuando el scraper avise que no
# reconoció alguno.
ALIAS = {
    "russia": "RU",
    "russian federation": "RU",
    "south korea": "KR",
    "north korea": "KP",
    "iran": "IR",
    "syria": "SY",
    "vietnam": "VN",
    "laos": "LA",
    "taiwan": "TW",
    "bolivia": "BO",
    "venezuela": "VE",
    "tanzania": "TZ",
    "moldova": "MD",
    "brunei": "BN",
    "cape verde": "CV",
    "ivory coast": "CI",
    "cote d'ivoire": "CI",
    "democratic republic of congo": "CD",
    "the democratic republic of congo": "CD",
    "dr congo": "CD",
    "republic of congo": "CG",
    "congo": "CG",
    "czech republic": "CZ",
    "swaziland": "SZ",
    "burma": "MM",
    "macedonia": "MK",
    "palestine": "PS",
    "vatican city": "VA",
    "east timor": "TL",
    "united states of america": "US",
    "usa": "US",
    "u.s.a.": "US",
    "united kingdom of great britain and northern ireland": "GB",
    "uk": "GB",
    "turkey": "TR",
    "türkiye": "TR",
    "the netherlands": "NL",
    "the gambia": "GM",
    "the bahamas": "BS",
    "the philippines": "PH",
    "u.s. virgin islands": "VI",
    "us virgin islands": "VI",
    "british virgin islands": "VG",
}

# Estados y territorios de EE. UU. Los feeds de USGS ponen esto en el campo
# `place` en lugar del país, y sin traducirlos cada estado aparecería como un
# "país" propio: en una muestra real, 110 eventos quedaban bajo "CA".
ESTADOS_EEUU = """
alabama al alaska ak arizona az arkansas ar california ca colorado co
connecticut ct delaware de florida fl georgia ga hawaii hi idaho id illinois il
indiana in iowa ia kansas ks kentucky ky louisiana la maine me maryland md
massachusetts ma michigan mi minnesota mn mississippi ms missouri mo montana mt
nebraska ne nevada nv "new hampshire" nh "new jersey" nj "new mexico" nm
"new york" ny "north carolina" nc "north dakota" nd ohio oh oklahoma ok oregon
or pennsylvania pa "rhode island" ri "south carolina" sc "south dakota" sd
tennessee tn texas tx utah ut vermont vt virginia va washington wa
"west virginia" wv wisconsin wi wyoming wy "district of columbia" dc
"""


def nombres_de(pais) -> set[str]:
    """Todas las formas en que una fuente puede nombrar a este país."""
    candidatos = {pais.name}
    for atributo in ("official_name", "common_name"):
        valor = getattr(pais, atributo, None)
        if valor:
            candidatos.add(valor)
    # "Bolivia, Plurinational State of" → "Bolivia"
    candidatos |= {nombre.split(",")[0].strip() for nombre in list(candidatos)}
    return {nombre.lower() for nombre in candidatos if nombre}


def construir_tabla() -> dict[str, str]:
    tabla: dict[str, str] = {}

    for pais in pycountry.countries:
        for nombre in nombres_de(pais):
            # El primero gana: evita que un nombre corto compartido se lo lleve
            # un país menos probable.
            tabla.setdefault(nombre, pais.alpha_2)

    # Los alias pisan a la tabla ISO: son los nombres que las fuentes usan de
    # verdad, y valen más que el nombre oficial.
    tabla.update(ALIAS)

    for token in ESTADOS_EEUU.split():
        tabla[token.strip('"').lower()] = "US"
    for compuesto in ("new hampshire", "new jersey", "new mexico", "new york",
                      "north carolina", "north dakota", "rhode island",
                      "south carolina", "south dakota", "west virginia",
                      "district of columbia"):
        tabla[compuesto] = "US"

    return tabla


def main() -> None:
    tabla = construir_tabla()
    lineas = [f'    {nombre!r}: {codigo!r},' for nombre, codigo in sorted(tabla.items())]

    validos = sorted({pais.alpha_2 for pais in pycountry.countries})

    DESTINO.write_text(
        '"""Nombre de país → código ISO-3166 alfa-2.\n'
        "\n"
        "GENERADO POR herramientas/generar_paises.py — no editar a mano.\n"
        "Para agregar un alias, tocá ALIAS en ese script y regeneralo.\n"
        '"""\n'
        "\n"
        "CODIGOS_POR_NOMBRE = {\n" + "\n".join(lineas) + "\n}\n"
        "\n# Alfa-2 válidos, para aceptar códigos que una fuente ya publica así.\n"
        "CODIGOS_VALIDOS = frozenset({\n"
        + "\n".join(f"    {codigo!r}," for codigo in validos)
        + "\n})\n",
        encoding="utf-8",
    )
    print(f"{DESTINO}: {len(tabla)} nombres")


if __name__ == "__main__":
    main()
