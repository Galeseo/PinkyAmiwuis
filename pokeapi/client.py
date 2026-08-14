"""Cliente HTTP de la PokéAPI (https://pokeapi.co/docs/v2).

Sin dependencias externas: solo la librería estándar. Incluye caché en disco,
reintentos con espera exponencial y respeto de la cabecera ``Retry-After``.
"""

from __future__ import annotations

import difflib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Iterator, List, Optional, Tuple, Union

from .cache import Cache
from .errors import (
    HttpError,
    InvalidKeyError,
    NetworkError,
    NotFoundError,
    RateLimitError,
)
from .models import EvolutionChain, Match, NamedResource, Page, Pokemon, Species

BASE_URL = "https://pokeapi.co/api/v2"
USER_AGENT = "pokeapi-py/1.0 (+https://github.com/)"

# La API acepta un limit muy alto, así que el índice completo cabe en una
# sola petición (que además se cachea).
INDEX_LIMIT = 100000

# Todos los nombres de la API se escriben así (comprobado sobre pokemon,
# species, move, item, type y ability). Cualquier otra cosa se rechaza antes
# de construir la URL.
KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")

Key = Union[str, int]


def normalize(query: Union[str, int]) -> str:
    """Pasa lo que escribe el usuario al formato de la API: 'Mr Mime' -> 'mr-mime'."""
    text = str(query).strip().lower()
    return "-".join(text.split())


def is_number(text: str) -> bool:
    """¿Lo escrito es un número de Pokédex? Acepta el signo para cazar '-5'."""
    return text.lstrip("+-").isdigit()


class PokeApiClient:
    """Punto de entrada para consultar la PokéAPI.

    >>> client = PokeApiClient()
    >>> pikachu = client.get_pokemon("pikachu")
    >>> pikachu.types
    ['electric']
    """

    def __init__(
        self,
        base_url: str = BASE_URL,
        cache: Optional[Cache] = None,
        use_cache: bool = True,
        timeout: float = 10.0,
        max_retries: int = 3,
        backoff: float = 0.5,
        user_agent: str = USER_AGENT,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.cache = cache if cache is not None else Cache(enabled=use_cache)
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff = backoff
        self.user_agent = user_agent

    # -- capa HTTP --------------------------------------------------------

    def _url(self, endpoint: str, key: Optional[Key] = None) -> str:
        if endpoint.startswith("http://") or endpoint.startswith("https://"):
            return endpoint
        path = endpoint.strip("/")
        if key is not None:
            clean = str(key).strip().lower()
            # Escapar no basta: el servidor decodifica %2F, así que una clave
            # como '../type/1' acabaría sirviendo otro recurso. Se valida.
            if not KEY_PATTERN.match(clean):
                raise InvalidKeyError(str(key))
            path = "{0}/{1}".format(path, urllib.parse.quote(clean, safe=""))
        return "{0}/{1}".format(self.base_url, path)

    def get_json(self, endpoint: str, key: Optional[Key] = None, **params: Any) -> Dict[str, Any]:
        """GET crudo contra la API, pasando por la caché."""
        url = self._url(endpoint, key)
        if params:
            query = {k: v for k, v in params.items() if v is not None}
            if query:
                url = "{0}?{1}".format(url, urllib.parse.urlencode(query))

        cached = self.cache.get(url)
        if cached is not None:
            return cached

        data = self._fetch(url)
        self.cache.set(url, data)
        return data

    def _fetch(self, url: str) -> Dict[str, Any]:
        request = urllib.request.Request(
            url,
            headers={"User-Agent": self.user_agent, "Accept": "application/json"},
        )
        last_error: Optional[Exception] = None

        for attempt in range(self.max_retries + 1):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    payload = response.read().decode("utf-8")
                return json.loads(payload)

            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    raise NotFoundError("el recurso", url) from exc
                if exc.code == 429:
                    retry_after = _retry_after(exc)
                    last_error = RateLimitError(url, retry_after)
                    if attempt == self.max_retries:
                        raise last_error from exc
                    time.sleep(retry_after or self._delay(attempt))
                    continue
                if 500 <= exc.code < 600:
                    body = _safe_body(exc)
                    last_error = HttpError(exc.code, url, body)
                    if attempt == self.max_retries:
                        raise last_error from exc
                    time.sleep(self._delay(attempt))
                    continue
                raise HttpError(exc.code, url, _safe_body(exc)) from exc

            except urllib.error.URLError as exc:
                last_error = NetworkError("No se pudo conectar con {0}: {1}".format(url, exc.reason))
                if attempt == self.max_retries:
                    raise last_error from exc
                time.sleep(self._delay(attempt))

            except ValueError as exc:  # JSON inválido
                raise HttpError(200, url, "Respuesta no es JSON válido") from exc

        raise last_error or NetworkError("Fallo desconocido en {0}".format(url))

    def _delay(self, attempt: int) -> float:
        return self.backoff * (2 ** attempt)

    # -- Pokémon ----------------------------------------------------------

    def get_pokemon(self, key: Key) -> Pokemon:
        """Un Pokémon por nombre o id."""
        try:
            return Pokemon.from_dict(self.get_json("pokemon", key))
        except NotFoundError:
            raise NotFoundError("el Pokémon", str(key))

    def list_pokemon(self, limit: int = 20, offset: int = 0) -> Page:
        """Una página del listado de Pokémon."""
        return Page.from_dict(self.get_json("pokemon", limit=limit, offset=offset))

    def iter_pokemon(self, page_size: int = 100, start: int = 0) -> Iterator[Any]:
        """Recorre *todos* los Pokémon paginando de forma perezosa."""
        return self.iter_resource("pokemon", page_size=page_size, start=start)

    # -- Especies ---------------------------------------------------------

    def get_species(self, key: Key) -> Species:
        """Una especie por nombre o id.

        Ojo: las formas regionales (``raichu-alola``) son Pokémon pero no
        especies; para esos casos usa :meth:`get_species_of`.
        """
        try:
            return Species.from_dict(self.get_json("pokemon-species", key))
        except NotFoundError:
            raise NotFoundError("la especie", str(key))

    def get_species_of(self, pokemon: Union[Pokemon, Key]) -> Species:
        """La especie de un Pokémon, resolviendo bien las formas alternativas."""
        if not isinstance(pokemon, Pokemon):
            pokemon = self.get_pokemon(pokemon)
        if pokemon.species is None:
            raise NotFoundError("la especie de", pokemon.name)
        return Species.from_dict(self.get_json(pokemon.species.url))

    def list_species(self, limit: int = 20, offset: int = 0) -> Page:
        return Page.from_dict(self.get_json("pokemon-species", limit=limit, offset=offset))

    # -- Evoluciones ------------------------------------------------------

    def get_evolution_chain(self, key: Key) -> EvolutionChain:
        """Una cadena evolutiva por id o por URL completa."""
        return EvolutionChain.from_dict(self.get_json("evolution-chain", key))

    def get_evolution_chain_of(self, pokemon: Union[Pokemon, Key]) -> EvolutionChain:
        """La cadena evolutiva a la que pertenece un Pokémon."""
        species = self.get_species_of(pokemon)
        if not species.evolution_chain_url:
            raise NotFoundError("la cadena evolutiva de", species.name)
        return EvolutionChain.from_dict(self.get_json(species.evolution_chain_url))

    # -- Tipos ------------------------------------------------------------

    def pokemon_by_type(self, key: Key) -> List[NamedResource]:
        """Todos los Pokémon de un tipo, en orden de Pokédex."""
        data = self.get_json("type", normalize(key))
        found = [
            NamedResource.from_dict(entry["pokemon"])
            for entry in data.get("pokemon", [])
            if entry.get("pokemon")
        ]
        return sorted(found, key=lambda item: item.id or 0)

    def pokemon_of_types(
        self, keys: List[Key], match_all: bool = True
    ) -> List[NamedResource]:
        """Pokémon que combinan varios tipos.

        Con ``match_all`` (por defecto) devuelve los que tienen *todos* los
        tipos — fire + flying da Charizard, Moltres…; con ``match_all=False``
        devuelve los que tienen *alguno*.
        """
        if not keys:
            return []

        counts: Dict[str, int] = {}
        found: Dict[str, NamedResource] = {}
        for key in dict.fromkeys(normalize(k) for k in keys):  # sin repetidos
            for item in self.pokemon_by_type(key):
                counts[item.name] = counts.get(item.name, 0) + 1
                found[item.name] = item

        needed = len(set(normalize(key) for key in keys)) if match_all else 1
        matches = [found[name] for name, hits in counts.items() if hits >= needed]
        return sorted(matches, key=lambda item: item.id or 0)

    # -- Genéricos --------------------------------------------------------

    def get_resource(self, endpoint: str, key: Key) -> Dict[str, Any]:
        """Cualquier otro endpoint (``type``, ``ability``, ``move``, ``item``…)."""
        return self.get_json(endpoint, key)

    def list_resource(self, endpoint: str, limit: int = 20, offset: int = 0) -> Page:
        return Page.from_dict(self.get_json(endpoint, limit=limit, offset=offset))

    def iter_resource(
        self, endpoint: str, page_size: int = 100, start: int = 0
    ) -> Iterator[Any]:
        """Itera un endpoint paginado hasta agotarlo."""
        offset = start
        while True:
            page = self.list_resource(endpoint, limit=page_size, offset=offset)
            if not page.results:
                return
            for item in page.results:
                yield item
            if not page.has_next:
                return
            offset += len(page.results)

    # -- Búsqueda por nombre parcial --------------------------------------

    def name_index(self, endpoint: str = "pokemon") -> List[NamedResource]:
        """Todos los nombres de un endpoint, en orden de Pokédex.

        Es una única petición (y queda cacheada), así que resolver nombres
        parciales no cuesta una llamada por intento.
        """
        return self.list_resource(endpoint, limit=INDEX_LIMIT, offset=0).results

    def find(
        self, query: Key, endpoint: str = "pokemon", fuzzy: bool = True
    ) -> Match:
        """Resuelve un nombre parcial: exacto, luego prefijo, subcadena y parecido.

        >>> client.find("chari").names
        ['charizard', 'charizard-mega-x', 'charizard-mega-y', 'charizard-gmax']
        """
        text = normalize(query)
        if not text:
            return Match(text, "empty", [])

        index = self.name_index(endpoint)

        if is_number(text):
            target = int(text)
            hits = [item for item in index if item.id == target]
            # Un número que no existe es un caso distinto de un nombre que no
            # existe: no tiene sentido sugerir nombres parecidos.
            return Match(text, "exact" if hits else "invalid-number", hits)

        for item in index:
            if item.name == text:
                return Match(text, "exact", [item])

        prefix = [item for item in index if item.name.startswith(text)]
        if prefix:
            return Match(text, "prefix", prefix)

        contains = [item for item in index if text in item.name]
        if contains:
            return Match(text, "contains", contains)

        if fuzzy:
            by_name = {item.name: item for item in index}
            close = difflib.get_close_matches(text, list(by_name), n=5, cutoff=0.6)
            if close:
                return Match(text, "similar", [by_name[name] for name in close])

        return Match(text, "none", [])

    def id_ranges(self, endpoint: str = "pokemon") -> List[Tuple[int, int]]:
        """Tramos de números que existen de verdad.

        La numeración no es continua: la Pokédex llega a 1025 y las formas
        alternativas saltan a 10001, así que devolvemos los tramos por
        separado, p. ej. ``[(1, 1025), (10001, 10277)]``.
        """
        ids = sorted(item.id for item in self.name_index(endpoint) if item.id)
        if not ids:
            return []

        ranges: List[Tuple[int, int]] = []
        start = previous = ids[0]
        for current in ids[1:]:
            if current > previous + 1:
                ranges.append((start, previous))
                start = current
            previous = current
        ranges.append((start, previous))
        return ranges

    def starts_with(self, prefix: Key, endpoint: str = "pokemon") -> List[NamedResource]:
        """Solo las coincidencias por prefijo, sin las vueltas atrás de find()."""
        text = normalize(prefix)
        return [item for item in self.name_index(endpoint) if item.name.startswith(text)]

    # -- Caché ------------------------------------------------------------

    def clear_cache(self) -> int:
        return self.cache.clear()

    def cache_info(self) -> Dict[str, Any]:
        return self.cache.info()


def _retry_after(exc: urllib.error.HTTPError) -> Optional[float]:
    value = exc.headers.get("Retry-After") if exc.headers else None
    try:
        return float(value) if value else None
    except (TypeError, ValueError):
        return None


def _safe_body(exc: urllib.error.HTTPError, limit: int = 500) -> str:
    try:
        return exc.read().decode("utf-8", "replace")[:limit]
    except Exception:
        return ""
