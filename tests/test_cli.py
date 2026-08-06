import argparse
import json

import pytest

from desastres import almacen, cli
from desastres.http import ErrorDescarga


class FuenteFalsa:
    """Fuente de mentira: devuelve un payload fijo o revienta, sin tocar la red."""

    def __init__(self, nombre, crudo=None, eventos=None, error=None):
        self.nombre = nombre
        self.url = f"https://ejemplo.invalid/{nombre}"
        self._crudo = crudo or b"{}"
        self._eventos = eventos or []
        self._error = error

    def obtener(self, *, timeout, reintentos):
        if self._error is not None:
            raise self._error
        return self._crudo

    def parsear(self, crudo):
        return self._eventos


def argumentos(salida, **extras):
    base = dict(
        fuentes="usgs",
        salida=salida,
        retencion_dias=400,
        timeout=5.0,
        reintentos=1,
        dry_run=False,
        verbose=False,
    )
    base.update(extras)
    return argparse.Namespace(**base)


def test_resolver_fuentes_por_defecto_incluye_todas():
    fuentes = cli.resolver_fuentes("usgs,gdacs")
    assert [fuente.nombre for fuente in fuentes] == ["usgs", "gdacs"]


def test_resolver_fuentes_deduplica_y_respeta_el_orden():
    fuentes = cli.resolver_fuentes("gdacs, usgs ,gdacs")
    assert [fuente.nombre for fuente in fuentes] == ["gdacs", "usgs"]


def test_resolver_fuente_desconocida_explica_las_validas():
    with pytest.raises(ValueError, match="fuente\\(s\\) desconocida\\(s\\): noaa"):
        cli.resolver_fuentes("noaa")


def test_resolver_sin_fuentes_falla():
    with pytest.raises(ValueError, match="al menos una fuente"):
        cli.resolver_fuentes("  ,  ")


def test_recolectar_sigue_con_las_demas_si_una_falla(usgs_crudo):
    from desastres.fuentes.usgs import FuenteUSGS

    buena = FuenteUSGS()
    buena.obtener = lambda **_: usgs_crudo
    rota = FuenteFalsa("gdacs", error=ErrorDescarga("502 del servidor"))

    eventos, estado = cli.recolectar([rota, buena], timeout=1, reintentos=1)

    assert len(eventos) == 3
    assert estado["gdacs"] == {"ok": False, "eventos": 0, "error": "502 del servidor"}
    assert estado["usgs"]["ok"] is True


def test_ejecucion_completa_escribe_json_csv_y_resumen(tmp_path, monkeypatch, usgs_crudo):
    from desastres.fuentes.usgs import FuenteUSGS

    fuente = FuenteUSGS()
    fuente.obtener = lambda **_: usgs_crudo
    monkeypatch.setattr(cli, "resolver_fuentes", lambda _: [fuente])

    codigo = cli.ejecutar(argumentos(tmp_path))

    assert codigo == cli.EXITO
    assert (tmp_path / almacen.NOMBRE_JSON).exists()
    assert (tmp_path / almacen.NOMBRE_CSV).exists()
    resumen = json.loads((tmp_path / almacen.NOMBRE_RESUMEN).read_text(encoding="utf-8"))
    assert resumen["cambios"]["nuevos"] == 3
    assert resumen["historico"]["total"] == 3


def test_segunda_corrida_no_duplica_eventos(tmp_path, monkeypatch, usgs_crudo):
    from desastres.fuentes.usgs import FuenteUSGS

    fuente = FuenteUSGS()
    fuente.obtener = lambda **_: usgs_crudo
    monkeypatch.setattr(cli, "resolver_fuentes", lambda _: [fuente])

    cli.ejecutar(argumentos(tmp_path))
    cli.ejecutar(argumentos(tmp_path))

    resumen = json.loads((tmp_path / almacen.NOMBRE_RESUMEN).read_text(encoding="utf-8"))
    assert resumen["cambios"] == {
        "nuevos": 0,
        "actualizados": 0,
        "sin_cambios": 3,
        "podados": 0,
    }
    assert resumen["historico"]["total"] == 3


def test_fallo_total_deja_el_historico_intacto(tmp_path, monkeypatch):
    rota = FuenteFalsa("usgs", error=ErrorDescarga("timeout"))
    monkeypatch.setattr(cli, "resolver_fuentes", lambda _: [rota])

    codigo = cli.ejecutar(argumentos(tmp_path))

    assert codigo == cli.FALLO_TOTAL
    assert not (tmp_path / almacen.NOMBRE_JSON).exists()


def test_fallo_parcial_guarda_y_avisa(tmp_path, monkeypatch, usgs_crudo):
    from desastres.fuentes.usgs import FuenteUSGS

    buena = FuenteUSGS()
    buena.obtener = lambda **_: usgs_crudo
    rota = FuenteFalsa("gdacs", error=ErrorDescarga("503"))
    monkeypatch.setattr(cli, "resolver_fuentes", lambda _: [buena, rota])

    codigo = cli.ejecutar(argumentos(tmp_path))

    assert codigo == cli.FALLO_PARCIAL
    resumen = json.loads((tmp_path / almacen.NOMBRE_RESUMEN).read_text(encoding="utf-8"))
    assert resumen["fuentes"]["gdacs"]["ok"] is False
    assert resumen["historico"]["total"] == 3


def test_dry_run_no_escribe_nada(tmp_path, monkeypatch, usgs_crudo):
    from desastres.fuentes.usgs import FuenteUSGS

    fuente = FuenteUSGS()
    fuente.obtener = lambda **_: usgs_crudo
    monkeypatch.setattr(cli, "resolver_fuentes", lambda _: [fuente])

    codigo = cli.ejecutar(argumentos(tmp_path, dry_run=True))

    assert codigo == cli.EXITO
    assert list(tmp_path.iterdir()) == []


def test_main_con_fuente_invalida_devuelve_fallo_total(tmp_path):
    assert cli.main(["--fuentes", "inexistente", "--salida", str(tmp_path)]) == cli.FALLO_TOTAL
