"""Excepciones del cliente de la PokéAPI."""

from __future__ import annotations

from typing import Optional


class PokeApiError(Exception):
    """Error base de la PokéAPI."""


class NotFoundError(PokeApiError):
    """El recurso pedido no existe (HTTP 404)."""

    def __init__(self, resource: str, key: str) -> None:
        super().__init__("No se encontró {0} '{1}'".format(resource, key))
        self.resource = resource
        self.key = key


class HttpError(PokeApiError):
    """La API respondió con un código de error."""

    def __init__(self, status: int, url: str, body: str = "") -> None:
        super().__init__("HTTP {0} en {1}".format(status, url))
        self.status = status
        self.url = url
        self.body = body


class RateLimitError(HttpError):
    """La API pidió que bajemos el ritmo (HTTP 429)."""

    def __init__(self, url: str, retry_after: Optional[float] = None) -> None:
        HttpError.__init__(self, 429, url)
        self.retry_after = retry_after


class NetworkError(PokeApiError):
    """No se pudo contactar con la API (DNS, timeout, conexión caída)."""


class InvalidKeyError(PokeApiError):
    """La clave no tiene forma de nombre o id de la PokéAPI.

    Se comprueba antes de salir a la red: los nombres de la API solo usan
    minúsculas, dígitos y guiones, así que cualquier otra cosa (una barra, un
    '..', un carácter de control) se rechaza aquí en vez de acabar en una URL.
    """

    def __init__(self, key: str) -> None:
        super().__init__(
            "Clave no válida: {0!r}. Solo se admiten minúsculas, dígitos y "
            "guiones (p. ej. 'mr-mime' o '25').".format(key)
        )
        self.key = key
