"""Contrato común de las fuentes."""

from __future__ import annotations

from typing import Protocol

from ..modelo import Evento


class Fuente(Protocol):
    """Una fuente sabe descargar su feed y traducirlo al modelo canónico.

    La separación entre `obtener` (red) y `parsear` (puro) es deliberada: los
    tests ejercitan `parsear` con fixtures y nunca tocan la red.
    """

    nombre: str
    url: str

    def obtener(self, *, timeout: float, reintentos: int) -> bytes:
        ...

    def parsear(self, crudo: bytes) -> list[Evento]:
        ...
