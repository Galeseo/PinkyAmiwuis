"""Capa HTTP sobre el cliente: una app WSGI sin dependencias.

Local:
    python3 -m pokeapi.web            # http://localhost:8000

En producción (Render, Railway, Fly…), con cualquier servidor WSGI:
    gunicorn pokeapi.web:app --bind 0.0.0.0:$PORT
"""

from __future__ import annotations

import json
import os
import urllib.parse
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from .client import PokeApiClient
from .errors import (
    HttpError,
    InvalidKeyError,
    NetworkError,
    NotFoundError,
    PokeApiError,
    RateLimitError,
)
from .models import EvolutionNode, NamedResource, Pokemon, Species

# Un solo cliente para todo el proceso: así la caché en disco se comparte
# entre peticiones en vez de rehacerse en cada una.
client = PokeApiClient()

# Cuánto puede cachear el navegador o el CDN. Los datos de la PokéAPI no
# cambian de un día para otro.
BROWSER_CACHE = "public, max-age=3600"


# ---------------------------------------------------------------------------
# Serialización
# ---------------------------------------------------------------------------


def _resource(item: NamedResource) -> Dict[str, Any]:
    return {"id": item.id, "name": item.name}


def _pokemon(pokemon: Pokemon) -> Dict[str, Any]:
    return {
        "id": pokemon.id,
        "name": pokemon.name,
        "types": pokemon.types,
        "height_m": pokemon.height_m,
        "weight_kg": pokemon.weight_kg,
        "base_experience": pokemon.base_experience,
        "stats": pokemon.stats,
        "total_stats": pokemon.total_stats,
        "abilities": [
            {"name": ability.name, "is_hidden": ability.is_hidden}
            for ability in pokemon.abilities
        ],
        "sprites": {
            "default": pokemon.sprites.front_default,
            "shiny": pokemon.sprites.front_shiny,
            "artwork": pokemon.sprites.official_artwork,
        },
    }


def _species(species: Species, language: str) -> Dict[str, Any]:
    return {
        "id": species.id,
        "name": species.name,
        "display_name": species.display_name(language),
        "genus": species.genus(language),
        "flavor_text": species.flavor_text(language),
        "generation": species.generation,
        "color": species.color,
        "habitat": species.habitat,
        "is_legendary": species.is_legendary,
        "is_mythical": species.is_mythical,
        "is_baby": species.is_baby,
        "capture_rate": species.capture_rate,
        "varieties": species.varieties,
    }


def _evolution(node: EvolutionNode) -> Dict[str, Any]:
    return {
        "name": node.species.name,
        "conditions": [detail.describe() for detail in node.details],
        "evolves_to": [_evolution(child) for child in node.evolves_to],
    }


# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------


def route_index() -> Dict[str, Any]:
    return {
        "service": "pokeapi-py",
        "description": "Proxy cacheado de la PokéAPI con búsqueda por nombre parcial.",
        "endpoints": {
            "GET /pokemon/{nombre|id}": "Ficha. Admite parciales: /pokemon/chari",
            "GET /species/{nombre|id}": "Especie y Pokédex. ?lang=es por defecto",
            "GET /evolution/{nombre|id}": "Cadena evolutiva",
            "GET /type/{tipo}": "Pokémon de un tipo. Varios: /type/fire,flying",
            "GET /types": "Los tipos disponibles",
            "GET /search?q={texto}": "Busca por subcadena",
            "GET /health": "Estado del servicio",
        },
        "notes": {
            "raw": "Añade ?raw=1 para el JSON original de la PokéAPI.",
            "type_mode": "Con varios tipos, ?mode=any devuelve los que tienen alguno.",
        },
    }


def route_pokemon(query: str, params: Dict[str, str]) -> Tuple[int, Dict[str, Any]]:
    match = client.find(query, "pokemon")

    if match.kind == "empty":
        return 400, {"error": "Escribe un nombre o un número."}
    if match.kind == "invalid-number":
        return 400, {
            "error": "Número no válido: {0}".format(match.query),
            "valid_ranges": [list(pair) for pair in client.id_ranges("pokemon")],
        }
    if not match:
        return 404, {"error": "No hay ningún Pokémon que coincida con '{0}'.".format(
            match.query
        )}

    if not match.is_exact and not match.is_unique:
        # Ambigüedad: 200 con los candidatos, que es información útil, no un error.
        return 200, {
            "query": match.query,
            "kind": match.kind,
            "matches": [_resource(item) for item in match.results],
        }

    pokemon = client.get_pokemon(match.results[0].name)
    if params.get("raw"):
        return 200, pokemon.raw
    return 200, _pokemon(pokemon)


def route_species(query: str, params: Dict[str, str]) -> Tuple[int, Dict[str, Any]]:
    match = client.find(query, "pokemon")
    if not match:
        return 404, {"error": "No se encontró '{0}'.".format(match.query)}

    species = client.get_species_of(match.results[0].name)
    if params.get("raw"):
        return 200, species.raw
    return 200, _species(species, params.get("lang", "es"))


def route_evolution(query: str, params: Dict[str, str]) -> Tuple[int, Dict[str, Any]]:
    match = client.find(query, "pokemon")
    if not match:
        return 404, {"error": "No se encontró '{0}'.".format(match.query)}

    chain = client.get_evolution_chain_of(match.results[0].name)
    if params.get("raw"):
        return 200, chain.raw
    return 200, {
        "id": chain.id,
        "species": chain.species_names,
        "chain": _evolution(chain.chain),
    }


def route_type(query: str, params: Dict[str, str]) -> Tuple[int, Dict[str, Any]]:
    requested = [part for part in query.replace("+", ",").split(",") if part.strip()]
    if not requested:
        return 400, {"error": "Indica al menos un tipo, p. ej. /type/fire"}

    names: List[str] = []
    for raw in requested:
        match = client.find(raw, "type")
        if not match:
            return 404, {
                "error": "No existe el tipo '{0}'.".format(raw),
                "available": [item.name for item in client.name_index("type")],
            }
        if not match.is_exact and not match.is_unique:
            return 400, {
                "error": "'{0}' es ambiguo.".format(raw),
                "matches": [item.name for item in match.results],
            }
        names.append(match.results[0].name)

    match_all = params.get("mode", "all") != "any"
    results = client.pokemon_of_types(names, match_all=match_all)
    return 200, {
        "types": names,
        "mode": "all" if match_all else "any",
        "count": len(results),
        "pokemon": [_resource(item) for item in results],
    }


def route_types() -> Tuple[int, Dict[str, Any]]:
    types = client.name_index("type")
    return 200, {"count": len(types), "types": [item.name for item in types]}


def route_search(params: Dict[str, str]) -> Tuple[int, Dict[str, Any]]:
    needle = (params.get("q") or "").strip().lower()
    if not needle:
        return 400, {"error": "Falta el parámetro ?q="}

    endpoint = params.get("endpoint", "pokemon")
    try:
        index = client.name_index(endpoint)
    except PokeApiError:
        return 400, {"error": "Endpoint no válido: '{0}'.".format(endpoint)}

    results = [item for item in index if needle in item.name]
    return 200, {
        "query": needle,
        "count": len(results),
        "results": [_resource(item) for item in results],
    }


def dispatch(path: str, params: Dict[str, str]) -> Tuple[int, Dict[str, Any]]:
    """Devuelve (status, payload) para una ruta ya normalizada."""
    parts = [part for part in path.strip("/").split("/") if part]

    if not parts:
        return 200, route_index()

    head = parts[0]
    rest = "/".join(parts[1:])

    if head == "health":
        return 200, {"status": "ok", "cache": client.cache_info()}
    if head == "types":
        return route_types()
    if head == "search":
        return route_search(params)

    if head in ("pokemon", "species", "evolution", "type"):
        if not rest:
            if head == "type":
                return route_types()
            return 400, {"error": "Falta el nombre, p. ej. /{0}/pikachu".format(head)}
        handler = {
            "pokemon": route_pokemon,
            "species": route_species,
            "evolution": route_evolution,
            "type": route_type,
        }[head]
        return handler(rest, params)

    return 404, {"error": "Ruta desconocida: /{0}".format(path.strip('/'))}


# ---------------------------------------------------------------------------
# WSGI
# ---------------------------------------------------------------------------

STATUS_TEXT = {
    200: "200 OK",
    400: "400 Bad Request",
    404: "404 Not Found",
    405: "405 Method Not Allowed",
    429: "429 Too Many Requests",
    500: "500 Internal Server Error",
    502: "502 Bad Gateway",
    504: "504 Gateway Timeout",
}


def _error_status(exc: PokeApiError) -> Tuple[int, str]:
    """Traduce los errores del cliente al código HTTP que les corresponde."""
    if isinstance(exc, NotFoundError):
        return 404, str(exc)
    if isinstance(exc, InvalidKeyError):
        return 400, str(exc)
    if isinstance(exc, RateLimitError):
        return 429, "La PokéAPI pidió bajar el ritmo. Reinténtalo en unos segundos."
    if isinstance(exc, NetworkError):
        return 504, "No se pudo contactar con la PokéAPI."
    if isinstance(exc, HttpError):
        return 502, "La PokéAPI respondió con un error."
    return 500, str(exc)


def app(environ: Dict[str, Any], start_response: Callable) -> Iterable[bytes]:
    """Aplicación WSGI. Compatible con gunicorn, waitress, wsgiref…"""
    method = environ.get("REQUEST_METHOD", "GET").upper()
    path = environ.get("PATH_INFO", "/")
    raw_query = environ.get("QUERY_STRING", "")
    params = {
        key: values[0]
        for key, values in urllib.parse.parse_qs(raw_query).items()
        if values
    }

    if method == "OPTIONS":
        return _respond(start_response, 200, {})
    if method not in ("GET", "HEAD"):
        return _respond(start_response, 405, {"error": "Solo se admite GET."})

    try:
        status, payload = dispatch(path, params)
    except PokeApiError as exc:
        code, message = _error_status(exc)
        status, payload = code, {"error": message}
    except Exception as exc:  # noqa: BLE001 - nunca devolvemos una traza al cliente
        status, payload = 500, {"error": "Error interno: {0}".format(type(exc).__name__)}

    return _respond(start_response, status, payload, head_only=(method == "HEAD"))


def _respond(
    start_response: Callable,
    status: int,
    payload: Dict[str, Any],
    head_only: bool = False,
) -> Iterable[bytes]:
    body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    headers = [
        ("Content-Type", "application/json; charset=utf-8"),
        ("Content-Length", str(len(body))),
        ("Access-Control-Allow-Origin", "*"),
        ("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS"),
        ("Cache-Control", BROWSER_CACHE if status == 200 else "no-store"),
    ]
    start_response(STATUS_TEXT.get(status, "500 Internal Server Error"), headers)
    return [] if head_only else [body]


def serve(host: str = "0.0.0.0", port: Optional[int] = None) -> None:
    """Servidor con la librería estándar, sin necesidad de gunicorn.

    Multihilo, así que una petición lenta a la PokéAPI no bloquea al resto.
    Sirve para desarrollo y como plan B en producción si gunicorn no está
    disponible: ``python -m pokeapi.web`` respeta la variable PORT.
    """
    from socketserver import ThreadingMixIn
    from wsgiref.simple_server import WSGIServer, make_server

    class ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
        daemon_threads = True

    port = port or int(os.environ.get("PORT", 8000))
    print("Escuchando en http://{0}:{1}".format(host, port))
    make_server(host, port, app, server_class=ThreadingWSGIServer).serve_forever()


if __name__ == "__main__":
    serve()
