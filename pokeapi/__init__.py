"""Cliente de la PokéAPI sin dependencias externas.

    from pokeapi import PokeApiClient

    client = PokeApiClient()
    pikachu = client.get_pokemon("pikachu")
    print(pikachu.types, pikachu.stats)
"""

from .cache import Cache, default_cache_dir
from .client import BASE_URL, PokeApiClient, normalize
from .errors import (
    HttpError,
    InvalidKeyError,
    NetworkError,
    NotFoundError,
    PokeApiError,
    RateLimitError,
)
from .models import (
    Ability,
    EvolutionChain,
    EvolutionDetail,
    EvolutionNode,
    Match,
    NamedResource,
    Page,
    Pokemon,
    Species,
    Sprites,
)

__version__ = "1.0.0"

__all__ = [
    "BASE_URL",
    "Ability",
    "Cache",
    "EvolutionChain",
    "EvolutionDetail",
    "EvolutionNode",
    "HttpError",
    "InvalidKeyError",
    "Match",
    "NamedResource",
    "NetworkError",
    "NotFoundError",
    "Page",
    "PokeApiClient",
    "PokeApiError",
    "Pokemon",
    "RateLimitError",
    "Species",
    "Sprites",
    "default_cache_dir",
    "normalize",
    "__version__",
]
