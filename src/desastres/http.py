"""Descarga HTTP con reintentos, sobre la stdlib (sin dependencias externas)."""

from __future__ import annotations

import logging
import time
import urllib.error
import urllib.request

log = logging.getLogger(__name__)

USER_AGENT = "cron-desastres-naturales/1.0 (+https://github.com/GustavoMix/cron-desastres-naturales)"

# Códigos que vale la pena reintentar: rate limit y fallas transitorias del servidor.
CODIGOS_REINTENTABLES = frozenset({408, 425, 429, 500, 502, 503, 504})


class ErrorDescarga(RuntimeError):
    """La descarga falló tras agotar los reintentos."""


def descargar(
    url: str,
    *,
    timeout: float = 30.0,
    reintentos: int = 3,
    espera_inicial: float = 2.0,
    dormir=time.sleep,
) -> bytes:
    """Descarga `url` y devuelve el cuerpo crudo.

    Reintenta con backoff exponencial ante errores de red y códigos HTTP
    transitorios. Un 4xx que no sea reintentable falla de inmediato: insistir
    sobre un 404 solo gasta tiempo.
    """
    if reintentos < 1:
        raise ValueError("reintentos debe ser >= 1")

    peticion = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    ultimo_error: Exception | None = None

    for intento in range(1, reintentos + 1):
        try:
            with urllib.request.urlopen(peticion, timeout=timeout) as respuesta:
                return respuesta.read()
        except urllib.error.HTTPError as error:
            ultimo_error = error
            if error.code not in CODIGOS_REINTENTABLES:
                raise ErrorDescarga(f"{url} respondió HTTP {error.code}") from error
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            ultimo_error = error

        if intento < reintentos:
            espera = espera_inicial * (2 ** (intento - 1))
            log.warning(
                "intento %d/%d falló para %s (%s); reintento en %.1fs",
                intento,
                reintentos,
                url,
                ultimo_error,
                espera,
            )
            dormir(espera)

    raise ErrorDescarga(f"{url} falló tras {reintentos} intentos: {ultimo_error}") from ultimo_error
