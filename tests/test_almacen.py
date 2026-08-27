import csv
import json
from datetime import timedelta

import pytest

from desastres import almacen
from desastres.modelo import Evento, a_iso


def hacer_evento(identificador="usgs:x1", fecha="2026-08-06T00:00:00Z", **extras):
    base = dict(
        id=identificador,
        fuente="usgs",
        tipo="sismo",
        titulo="M 5.0 - algún lugar",
        fecha_evento=fecha,
        url="https://example.org/x1",
    )
    base.update(extras)
    return Evento(**base)


def test_cargar_sin_archivo_devuelve_vacio(tmp_path):
    assert almacen.cargar(tmp_path) == {}


def test_cargar_json_corrupto_falla_con_mensaje_util(tmp_path):
    (tmp_path / almacen.NOMBRE_JSON).write_text("{no es json", encoding="utf-8")
    with pytest.raises(ValueError, match="no es JSON válido"):
        almacen.cargar(tmp_path)


def test_fusionar_marca_los_nuevos(ahora):
    fusionados, cambios = almacen.fusionar({}, [hacer_evento()], ahora)
    assert cambios["nuevos"] == 1
    assert fusionados["usgs:x1"].visto_por_primera_vez == a_iso(ahora)
    assert fusionados["usgs:x1"].cambiado_por_ultima_vez == a_iso(ahora)


def test_fusionar_conserva_la_primera_vez_que_se_vio(ahora):
    previos, _ = almacen.fusionar({}, [hacer_evento()], ahora)
    despues = ahora + timedelta(hours=6)

    fusionados, cambios = almacen.fusionar(previos, [hacer_evento(magnitud=5.6)], despues)

    assert cambios["actualizados"] == 1
    assert fusionados["usgs:x1"].visto_por_primera_vez == a_iso(ahora)
    assert fusionados["usgs:x1"].cambiado_por_ultima_vez == a_iso(despues)
    assert fusionados["usgs:x1"].magnitud == 5.6


def test_revisita_identica_no_cuenta_como_actualizacion(ahora):
    previos, _ = almacen.fusionar({}, [hacer_evento()], ahora)
    _, cambios = almacen.fusionar(previos, [hacer_evento()], ahora + timedelta(hours=1))
    assert cambios["sin_cambios"] == 1
    assert cambios["actualizados"] == 0


def test_revisita_identica_no_toca_la_marca_de_cambio(ahora):
    # Propiedad crítica: si esta marca se moviera en cada corrida, las decenas
    # de miles de filas del histórico cambiarían cada hora y git no podría
    # comprimir nada. El registro tiene que quedar idéntico.
    previos, _ = almacen.fusionar({}, [hacer_evento()], ahora)
    fusionados, _ = almacen.fusionar(previos, [hacer_evento()], ahora + timedelta(hours=5))

    assert fusionados["usgs:x1"].cambiado_por_ultima_vez == a_iso(ahora)
    assert fusionados["usgs:x1"] == previos["usgs:x1"]


def test_el_id_agrupado_cae_por_defecto_en_el_id():
    assert hacer_evento("usgs:x1").id_agrupado == "usgs:x1"


def test_cargar_completa_el_id_agrupado_en_registros_viejos(tmp_path):
    # Registros escritos antes de que el campo existiera: sin backfill, los
    # eventos históricos de GDACS quedarían agrupados por episodio.
    antiguo = {
        "version": 1,
        "eventos": [
            {"id": "gdacs:TC:1001298:39", "fuente": "gdacs", "tipo": "ciclon",
             "titulo": "Ciclón", "fecha_evento": "2026-08-01T00:00:00Z", "url": ""},
            {"id": "gdacs:FL:1102344", "fuente": "gdacs", "tipo": "inundacion",
             "titulo": "Inundación", "fecha_evento": "2026-08-01T00:00:00Z", "url": ""},
            {"id": "usgs:us7000abcd", "fuente": "usgs", "tipo": "sismo",
             "titulo": "Sismo", "fecha_evento": "2026-08-01T00:00:00Z", "url": ""},
        ],
    }
    (tmp_path / almacen.NOMBRE_JSON).write_text(json.dumps(antiguo), encoding="utf-8")

    cargados = almacen.cargar(tmp_path)

    assert cargados["gdacs:TC:1001298:39"].id_agrupado == "gdacs:TC:1001298"
    assert cargados["gdacs:FL:1102344"].id_agrupado == "gdacs:FL:1102344"
    assert cargados["usgs:us7000abcd"].id_agrupado == "usgs:us7000abcd"


def test_el_backfill_respeta_un_id_agrupado_ya_presente(tmp_path):
    documento = {
        "version": 1,
        "eventos": [
            {"id": "gdacs:TC:1:2", "id_agrupado": "explícito", "fuente": "gdacs",
             "tipo": "ciclon", "titulo": "x", "fecha_evento": "2026-08-01T00:00:00Z", "url": ""}
        ],
    }
    (tmp_path / almacen.NOMBRE_JSON).write_text(json.dumps(documento), encoding="utf-8")

    assert almacen.cargar(tmp_path)["gdacs:TC:1:2"].id_agrupado == "explícito"


def test_fusionar_no_muta_el_diccionario_original(ahora):
    existentes = {}
    almacen.fusionar(existentes, [hacer_evento()], ahora)
    assert existentes == {}


def test_podar_descarta_lo_anterior_a_la_ventana(ahora):
    viejo = hacer_evento("usgs:viejo", fecha=a_iso(ahora - timedelta(days=40)))
    nuevo = hacer_evento("usgs:nuevo", fecha=a_iso(ahora - timedelta(days=2)))

    conservados = almacen.podar({viejo.id: viejo, nuevo.id: nuevo}, 30, ahora)

    assert set(conservados) == {"usgs:nuevo"}


def test_podar_con_cero_dias_no_descarta_nada(ahora):
    viejo = hacer_evento("usgs:viejo", fecha=a_iso(ahora - timedelta(days=4000)))
    assert almacen.podar({viejo.id: viejo}, 0, ahora) == {viejo.id: viejo}


def test_podar_conserva_eventos_sin_fecha_parseable(ahora):
    roto = hacer_evento("usgs:roto", fecha="fecha inválida")
    assert set(almacen.podar({roto.id: roto}, 30, ahora)) == {"usgs:roto"}


def test_podar_no_toca_lo_que_sigue_publicado(ahora):
    # Caso real: GDACS mantiene sequías que arrancaron hace casi un año y las
    # sigue republicando. Podarlas por su fecha de inicio las borraría en cada
    # corrida para reinsertarlas en la siguiente, y nunca se verían.
    sequia = hacer_evento(
        "gdacs:DR:9", tipo="sequia", fecha=a_iso(ahora - timedelta(days=350))
    )
    abandonado = hacer_evento("usgs:viejo", fecha=a_iso(ahora - timedelta(days=350)))

    conservados = almacen.podar(
        {sequia.id: sequia, abandonado.id: abandonado}, 180, ahora, activos={"gdacs:DR:9"}
    )

    assert set(conservados) == {"gdacs:DR:9"}


def test_ordena_de_mas_reciente_a_mas_antiguo():
    a = hacer_evento("usgs:a", fecha="2026-08-01T00:00:00Z")
    b = hacer_evento("usgs:b", fecha="2026-08-05T00:00:00Z")
    ordenados = almacen.ordenar({"usgs:a": a, "usgs:b": b})
    assert [evento.id for evento in ordenados] == ["usgs:b", "usgs:a"]


def test_guardar_y_recargar_conserva_los_eventos(tmp_path, ahora):
    eventos = {
        "usgs:x1": hacer_evento(magnitud=5.4, extra={"tsunami": 0}),
        "gdacs:EQ:9:1": hacer_evento("gdacs:EQ:9:1", fuente="gdacs", fecha="2026-08-05T00:00:00Z"),
    }

    almacen.guardar(tmp_path, eventos, {"ultima_ejecucion": a_iso(ahora)})
    recargados = almacen.cargar(tmp_path)

    assert set(recargados) == set(eventos)
    assert recargados["usgs:x1"].magnitud == 5.4
    assert recargados["usgs:x1"].extra == {"tsunami": 0}


def test_el_csv_lleva_encabezado_fijo_y_omite_extra(tmp_path, ahora):
    almacen.guardar(tmp_path, {"usgs:x1": hacer_evento(extra={"a": 1})}, {})

    with (tmp_path / almacen.NOMBRE_CSV).open(encoding="utf-8") as manejador:
        filas = list(csv.DictReader(manejador))

    assert list(filas[0]) == list(almacen.CAMPOS_CSV)
    assert "extra" not in filas[0]
    assert filas[0]["id"] == "usgs:x1"


def test_guardar_es_deterministico(tmp_path, ahora):
    eventos = {"usgs:x1": hacer_evento(), "usgs:x2": hacer_evento("usgs:x2")}

    almacen.guardar(tmp_path, eventos, {"ultima_ejecucion": a_iso(ahora)})
    primero = (tmp_path / almacen.NOMBRE_JSON).read_text(encoding="utf-8")
    invertidos = dict(reversed(list(eventos.items())))
    almacen.guardar(tmp_path, invertidos, {"ultima_ejecucion": a_iso(ahora)})
    segundo = (tmp_path / almacen.NOMBRE_JSON).read_text(encoding="utf-8")

    # Sin esto el cron generaría un commit espurio en cada corrida.
    assert primero == segundo


def test_resumen_se_escribe_como_json(tmp_path, ahora):
    almacen.guardar(tmp_path, {}, {"ultima_ejecucion": a_iso(ahora)})
    resumen = json.loads((tmp_path / almacen.NOMBRE_RESUMEN).read_text(encoding="utf-8"))
    assert resumen["ultima_ejecucion"] == a_iso(ahora)


def test_recientes_respeta_la_ventana_de_dias(ahora):
    dentro = hacer_evento("usgs:dentro", fecha=a_iso(ahora - timedelta(days=2)))
    fuera = hacer_evento("usgs:fuera", fecha=a_iso(ahora - timedelta(days=20)))

    seleccionados = almacen.filtrar_recientes(
        {dentro.id: dentro, fuera.id: fuera}, dias=7, magnitud_minima_sismo=0, ahora=ahora
    )

    assert [evento.id for evento in seleccionados] == ["usgs:dentro"]


def test_recientes_filtra_microsismos(ahora):
    grande = hacer_evento("usgs:grande", magnitud=5.0)
    micro = hacer_evento("usgs:micro", magnitud=1.1)

    seleccionados = almacen.filtrar_recientes(
        {grande.id: grande, micro.id: micro}, dias=7, magnitud_minima_sismo=2.5, ahora=ahora
    )

    assert [evento.id for evento in seleccionados] == ["usgs:grande"]


def test_el_umbral_de_magnitud_no_toca_otros_tipos(ahora):
    # Un ciclón mide 185 km/h y una inundación no mide nada: sus magnitudes no
    # son comparables con la escala sísmica y no deben filtrarse nunca.
    inundacion = hacer_evento("gdacs:FL:1", tipo="inundacion", magnitud=None)
    ciclon = hacer_evento("gdacs:TC:1", tipo="ciclon", magnitud=1.0, unidad_magnitud="km/h")

    seleccionados = almacen.filtrar_recientes(
        {inundacion.id: inundacion, ciclon.id: ciclon},
        dias=7,
        magnitud_minima_sismo=2.5,
        ahora=ahora,
    )

    assert {evento.id for evento in seleccionados} == {"gdacs:FL:1", "gdacs:TC:1"}


def test_recientes_conserva_sismos_sin_magnitud_conocida(ahora):
    sismo = hacer_evento("usgs:sinmag", magnitud=None)
    seleccionados = almacen.filtrar_recientes(
        {sismo.id: sismo}, dias=7, magnitud_minima_sismo=2.5, ahora=ahora
    )
    assert [evento.id for evento in seleccionados] == ["usgs:sinmag"]


def test_el_feed_reciente_omite_extra(tmp_path, ahora):
    evento = hacer_evento(extra={"tsunami": 0})
    almacen.guardar_recientes(tmp_path, [evento], ahora)

    documento = json.loads((tmp_path / almacen.NOMBRE_RECIENTES).read_text(encoding="utf-8"))

    assert documento["generado"] == a_iso(ahora)
    assert documento["total"] == 1
    assert "extra" not in documento["eventos"][0]
    assert documento["eventos"][0]["id"] == "usgs:x1"


def test_el_feed_reciente_publica_las_plantillas_de_media_una_sola_vez(tmp_path, ahora):
    """A nivel documento, no por evento: repetirlas 1.400 veces son cientos de KB."""
    almacen.guardar_recientes(tmp_path, [hacer_evento("a"), hacer_evento("b")], ahora)

    documento = json.loads((tmp_path / almacen.NOMBRE_RECIENTES).read_text(encoding="utf-8"))

    assert "{fecha}" in documento["media"]["satelite"]["plantilla"]
    assert all("media" not in evento or evento["media"] == {} for evento in documento["eventos"])


def test_el_feed_reciente_conserva_las_imagenes_propias_del_evento(tmp_path, ahora):
    """Los mapas de GDACS no se pueden derivar de nada: si no van, se pierden."""
    evento = hacer_evento(media={"mapa": "https://www.gdacs.org/x.png"})
    almacen.guardar_recientes(tmp_path, [evento], ahora)

    documento = json.loads((tmp_path / almacen.NOMBRE_RECIENTES).read_text(encoding="utf-8"))

    assert documento["eventos"][0]["media"] == {"mapa": "https://www.gdacs.org/x.png"}


def test_estadisticas_cuenta_por_tipo_fuente_y_alerta():
    eventos = {
        "a": hacer_evento("a", nivel_alerta="verde"),
        "b": hacer_evento("b", fuente="gdacs", tipo="ciclon", nivel_alerta="roja"),
        "c": hacer_evento("c", fuente="gdacs", tipo="ciclon"),
    }

    stats = almacen.estadisticas(eventos)

    assert stats["total"] == 3
    assert stats["por_tipo"] == {"ciclon": 2, "sismo": 1}
    assert stats["por_fuente"] == {"gdacs": 2, "usgs": 1}
    assert stats["por_nivel_alerta"] == {"roja": 1, "verde": 1}


def test_cargar_completa_los_paises_en_registros_viejos(tmp_path):
    # `paises` es el campo por el que filtra la app. Se deriva del texto ya
    # guardado, así que los históricos no tienen que esperar a reaparecer en
    # el feed — y los que ya salieron nunca reaparecerían.
    antiguo = {
        "version": 1,
        "eventos": [
            {"id": "usgs:a", "fuente": "usgs", "tipo": "sismo", "titulo": "x",
             "fecha_evento": "2026-08-01T00:00:00Z", "url": "", "pais": "Alaska"},
            {"id": "gdacs:DR:1", "fuente": "gdacs", "tipo": "sequia", "titulo": "y",
             "fecha_evento": "2026-08-01T00:00:00Z", "url": "", "pais": "Chile, Peru"},
            {"id": "usgs:b", "fuente": "usgs", "tipo": "sismo", "titulo": "z",
             "fecha_evento": "2026-08-01T00:00:00Z", "url": "", "pais": ""},
        ],
    }
    (tmp_path / almacen.NOMBRE_JSON).write_text(json.dumps(antiguo), encoding="utf-8")

    cargados = almacen.cargar(tmp_path)

    assert cargados["usgs:a"].paises == ["US"]
    assert cargados["gdacs:DR:1"].paises == ["CL", "PE"]
    assert cargados["usgs:b"].paises == []
