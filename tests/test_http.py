import urllib.error

import pytest

from desastres import http


class RespuestaFalsa:
    def __init__(self, cuerpo):
        self._cuerpo = cuerpo

    def read(self):
        return self._cuerpo

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def encadenar(monkeypatch, resultados):
    """Hace que cada llamada a urlopen consuma el siguiente resultado de la lista."""
    pendientes = list(resultados)
    llamadas = []

    def falso_urlopen(peticion, timeout=None):
        llamadas.append(peticion.full_url)
        siguiente = pendientes.pop(0)
        if isinstance(siguiente, Exception):
            raise siguiente
        return RespuestaFalsa(siguiente)

    monkeypatch.setattr(http.urllib.request, "urlopen", falso_urlopen)
    return llamadas


def test_devuelve_el_cuerpo_al_primer_intento(monkeypatch):
    llamadas = encadenar(monkeypatch, [b"contenido"])
    esperas = []

    assert http.descargar("https://ejemplo.invalid/a", dormir=esperas.append) == b"contenido"
    assert len(llamadas) == 1
    assert esperas == []


def test_reintenta_ante_error_de_red_con_backoff_exponencial(monkeypatch):
    llamadas = encadenar(
        monkeypatch,
        [urllib.error.URLError("caída"), urllib.error.URLError("caída"), b"al fin"],
    )
    esperas = []

    resultado = http.descargar(
        "https://ejemplo.invalid/a", reintentos=3, espera_inicial=2.0, dormir=esperas.append
    )

    assert resultado == b"al fin"
    assert len(llamadas) == 3
    assert esperas == [2.0, 4.0]


def test_reintenta_ante_503(monkeypatch):
    error = urllib.error.HTTPError("https://ejemplo.invalid/a", 503, "no disponible", {}, None)
    encadenar(monkeypatch, [error, b"ok"])

    assert http.descargar("https://ejemplo.invalid/a", dormir=lambda _: None) == b"ok"


def test_no_reintenta_ante_404(monkeypatch):
    error = urllib.error.HTTPError("https://ejemplo.invalid/a", 404, "no está", {}, None)
    llamadas = encadenar(monkeypatch, [error])

    with pytest.raises(http.ErrorDescarga, match="HTTP 404"):
        http.descargar("https://ejemplo.invalid/a", reintentos=3, dormir=lambda _: None)

    assert len(llamadas) == 1


def test_agotar_los_reintentos_levanta_error_descarga(monkeypatch):
    encadenar(monkeypatch, [urllib.error.URLError("caída")] * 2)

    with pytest.raises(http.ErrorDescarga, match="falló tras 2 intentos"):
        http.descargar("https://ejemplo.invalid/a", reintentos=2, dormir=lambda _: None)


def test_manda_user_agent_identificable(monkeypatch):
    capturadas = {}

    def falso_urlopen(peticion, timeout=None):
        capturadas.update(peticion.headers)
        return RespuestaFalsa(b"ok")

    monkeypatch.setattr(http.urllib.request, "urlopen", falso_urlopen)
    http.descargar("https://ejemplo.invalid/a")

    assert "cron-desastres-naturales" in capturadas["User-agent"]
