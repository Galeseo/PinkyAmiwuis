"""Modelos tipados sobre las respuestas JSON de la PokéAPI.

Cada modelo guarda el JSON original en ``raw`` por si hace falta un campo que
no esté mapeado.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional, Tuple


def _id_from_url(url: str) -> Optional[int]:
    """Extrae el id numérico del final de una URL de la PokéAPI."""
    parts = [part for part in (url or "").split("/") if part]
    if parts and parts[-1].isdigit():
        return int(parts[-1])
    return None


def _name(node: Optional[Dict[str, Any]]) -> Optional[str]:
    return node.get("name") if isinstance(node, dict) else None


# ---------------------------------------------------------------------------
# Recursos y paginación
# ---------------------------------------------------------------------------


@dataclass
class NamedResource:
    """Referencia ``{name, url}`` que devuelve la API en los listados."""

    name: str
    url: str

    @property
    def id(self) -> Optional[int]:
        return _id_from_url(self.url)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NamedResource":
        return cls(name=data.get("name", ""), url=data.get("url", ""))


@dataclass
class Match:
    """Resultado de resolver un nombre parcial contra el índice de la API.

    ``kind`` indica cómo se llegó a las coincidencias:

    ``exact``           el nombre (o el id) existe tal cual
    ``prefix``          empieza por lo escrito — "chari" -> charizard, charizard-mega-x
    ``contains``        lo escrito aparece dentro del nombre — "chu" -> pikachu
    ``similar``         nombres parecidos, para erratas — "pikchu" -> pikachu
    ``invalid-number``  un número que no corresponde a ningún Pokémon
    ``empty``           no se escribió nada
    ``none``            sin coincidencias
    """

    query: str
    kind: str
    results: List["NamedResource"] = field(default_factory=list)

    @property
    def is_exact(self) -> bool:
        return self.kind == "exact"

    @property
    def is_unique(self) -> bool:
        return len(self.results) == 1

    @property
    def names(self) -> List[str]:
        return [item.name for item in self.results]

    def __bool__(self) -> bool:
        return bool(self.results)

    def __len__(self) -> int:
        return len(self.results)


@dataclass
class Page:
    """Una página de un listado paginado."""

    count: int
    next: Optional[str]
    previous: Optional[str]
    results: List[NamedResource]

    @property
    def has_next(self) -> bool:
        return bool(self.next)

    def __iter__(self) -> Iterator[NamedResource]:
        return iter(self.results)

    def __len__(self) -> int:
        return len(self.results)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Page":
        return cls(
            count=data.get("count", 0),
            next=data.get("next"),
            previous=data.get("previous"),
            results=[NamedResource.from_dict(item) for item in data.get("results", [])],
        )


# ---------------------------------------------------------------------------
# Pokémon
# ---------------------------------------------------------------------------


@dataclass
class Ability:
    name: str
    is_hidden: bool
    slot: int


@dataclass
class Sprites:
    front_default: Optional[str] = None
    front_shiny: Optional[str] = None
    back_default: Optional[str] = None
    official_artwork: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Sprites":
        other = data.get("other") or {}
        artwork = other.get("official-artwork") or {}
        return cls(
            front_default=data.get("front_default"),
            front_shiny=data.get("front_shiny"),
            back_default=data.get("back_default"),
            official_artwork=artwork.get("front_default"),
        )

    @property
    def best(self) -> Optional[str]:
        """La imagen de mayor calidad disponible."""
        return self.official_artwork or self.front_default


@dataclass
class Pokemon:
    id: int
    name: str
    height: int  # decímetros
    weight: int  # hectogramos
    base_experience: Optional[int]
    types: List[str]
    stats: Dict[str, int]
    abilities: List[Ability]
    sprites: Sprites
    species: Optional[NamedResource]
    moves: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def height_m(self) -> float:
        return self.height / 10.0

    @property
    def weight_kg(self) -> float:
        return self.weight / 10.0

    @property
    def total_stats(self) -> int:
        return sum(self.stats.values())

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Pokemon":
        types = [
            _name(entry.get("type")) or ""
            for entry in sorted(
                data.get("types", []), key=lambda item: item.get("slot", 0)
            )
        ]
        stats = {}
        for entry in data.get("stats", []):
            key = _name(entry.get("stat"))
            if key:
                stats[key] = entry.get("base_stat", 0)
        abilities = [
            Ability(
                name=_name(entry.get("ability")) or "",
                is_hidden=bool(entry.get("is_hidden")),
                slot=entry.get("slot", 0),
            )
            for entry in data.get("abilities", [])
        ]
        species = data.get("species")
        return cls(
            id=data.get("id", 0),
            name=data.get("name", ""),
            height=data.get("height", 0),
            weight=data.get("weight", 0),
            base_experience=data.get("base_experience"),
            types=[t for t in types if t],
            stats=stats,
            abilities=abilities,
            sprites=Sprites.from_dict(data.get("sprites") or {}),
            species=NamedResource.from_dict(species) if species else None,
            moves=[
                _name(entry.get("move")) or "" for entry in data.get("moves", [])
            ],
            raw=data,
        )


# ---------------------------------------------------------------------------
# Especie
# ---------------------------------------------------------------------------


@dataclass
class Species:
    id: int
    name: str
    order: Optional[int]
    is_legendary: bool
    is_mythical: bool
    is_baby: bool
    color: Optional[str]
    shape: Optional[str]
    habitat: Optional[str]
    generation: Optional[str]
    capture_rate: Optional[int]
    base_happiness: Optional[int]
    growth_rate: Optional[str]
    evolution_chain_url: Optional[str]
    varieties: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def evolution_chain_id(self) -> Optional[int]:
        return _id_from_url(self.evolution_chain_url or "")

    def display_name(self, language: str = "es") -> str:
        """Nombre traducido, con vuelta al nombre interno si no existe."""
        for entry in self.raw.get("names", []):
            if _name(entry.get("language")) == language:
                return entry.get("name", self.name)
        return self.name

    def genus(self, language: str = "es") -> Optional[str]:
        """Categoría ('Pokémon Ratón'), en el idioma pedido."""
        fallback = None
        for entry in self.raw.get("genera", []):
            lang = _name(entry.get("language"))
            if lang == language:
                return entry.get("genus")
            if lang == "en" and fallback is None:
                fallback = entry.get("genus")
        return fallback

    def flavor_text(self, language: str = "es") -> Optional[str]:
        """Descripción de la Pokédex, limpiando los saltos de línea del original."""
        fallback = None
        for entry in self.raw.get("flavor_text_entries", []):
            lang = _name(entry.get("language"))
            text = (entry.get("flavor_text") or "").replace("\n", " ")
            text = text.replace("\f", " ").replace("­ ", "").strip()
            if not text:
                continue
            if lang == language:
                return text
            if lang == "en" and fallback is None:
                fallback = text
        return fallback

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Species":
        chain = data.get("evolution_chain") or {}
        return cls(
            id=data.get("id", 0),
            name=data.get("name", ""),
            order=data.get("order"),
            is_legendary=bool(data.get("is_legendary")),
            is_mythical=bool(data.get("is_mythical")),
            is_baby=bool(data.get("is_baby")),
            color=_name(data.get("color")),
            shape=_name(data.get("shape")),
            habitat=_name(data.get("habitat")),
            generation=_name(data.get("generation")),
            capture_rate=data.get("capture_rate"),
            base_happiness=data.get("base_happiness"),
            growth_rate=_name(data.get("growth_rate")),
            evolution_chain_url=chain.get("url"),
            varieties=[
                _name(entry.get("pokemon")) or ""
                for entry in data.get("varieties", [])
            ],
            raw=data,
        )


# ---------------------------------------------------------------------------
# Cadena evolutiva
# ---------------------------------------------------------------------------


@dataclass
class EvolutionDetail:
    """Cómo se desencadena una evolución concreta."""

    trigger: Optional[str]
    min_level: Optional[int]
    item: Optional[str]
    held_item: Optional[str]
    time_of_day: Optional[str]
    min_happiness: Optional[int]
    min_affection: Optional[int]
    location: Optional[str]
    known_move: Optional[str]
    known_move_type: Optional[str]
    gender: Optional[int]
    needs_overworld_rain: bool = False
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvolutionDetail":
        return cls(
            trigger=_name(data.get("trigger")),
            min_level=data.get("min_level"),
            item=_name(data.get("item")),
            held_item=_name(data.get("held_item")),
            time_of_day=data.get("time_of_day") or None,
            min_happiness=data.get("min_happiness"),
            min_affection=data.get("min_affection"),
            location=_name(data.get("location")),
            known_move=_name(data.get("known_move")),
            known_move_type=_name(data.get("known_move_type")),
            gender=data.get("gender"),
            needs_overworld_rain=bool(data.get("needs_overworld_rain")),
            raw=data,
        )

    def describe(self) -> str:
        """Resume la condición en una frase legible."""
        parts: List[str] = []
        if self.min_level:
            parts.append("nivel {0}".format(self.min_level))
        if self.item:
            parts.append("usar {0}".format(self.item.replace("-", " ")))
        if self.held_item:
            parts.append("llevando {0}".format(self.held_item.replace("-", " ")))
        if self.min_happiness:
            parts.append("felicidad {0}+".format(self.min_happiness))
        if self.min_affection:
            parts.append("afecto {0}+".format(self.min_affection))
        if self.known_move:
            parts.append("sabiendo {0}".format(self.known_move.replace("-", " ")))
        if self.known_move_type:
            parts.append("con un movimiento de tipo {0}".format(self.known_move_type))
        if self.location:
            parts.append("en {0}".format(self.location.replace("-", " ")))
        if self.time_of_day:
            parts.append("de {0}".format(self.time_of_day))
        if self.needs_overworld_rain:
            parts.append("bajo la lluvia")
        if self.gender is not None:
            parts.append("solo {0}".format("hembra" if self.gender == 1 else "macho"))
        # El trigger solo se muestra si aporta algo: "use-item" ya está implícito
        # cuando hemos nombrado el objeto, y "level-up" es el caso por defecto.
        redundant = self.trigger == "level-up" or (self.trigger == "use-item" and self.item)
        if self.trigger and not redundant:
            parts.append(self.trigger.replace("-", " "))
        return ", ".join(parts) if parts else (self.trigger or "desconocido")


@dataclass
class EvolutionNode:
    """Un eslabón del árbol evolutivo (puede ramificarse, p. ej. Eevee)."""

    species: NamedResource
    details: List[EvolutionDetail]
    evolves_to: List["EvolutionNode"]
    is_baby: bool = False

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvolutionNode":
        return cls(
            species=NamedResource.from_dict(data.get("species") or {}),
            details=[
                EvolutionDetail.from_dict(item)
                for item in data.get("evolution_details", [])
            ],
            evolves_to=[cls.from_dict(item) for item in data.get("evolves_to", [])],
            is_baby=bool(data.get("is_baby")),
        )

    def walk(self, depth: int = 0) -> Iterator[Tuple[int, "EvolutionNode"]]:
        """Recorre el árbol en profundidad, devolviendo (nivel, nodo)."""
        yield depth, self
        for child in self.evolves_to:
            for item in child.walk(depth + 1):
                yield item

    def paths(self) -> List[List["EvolutionNode"]]:
        """Todas las líneas evolutivas completas desde este nodo hasta las hojas."""
        if not self.evolves_to:
            return [[self]]
        result: List[List["EvolutionNode"]] = []
        for child in self.evolves_to:
            for path in child.paths():
                result.append([self] + path)
        return result


@dataclass
class EvolutionChain:
    id: int
    chain: EvolutionNode
    baby_trigger_item: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvolutionChain":
        return cls(
            id=data.get("id", 0),
            chain=EvolutionNode.from_dict(data.get("chain") or {}),
            baby_trigger_item=_name(data.get("baby_trigger_item")),
            raw=data,
        )

    @property
    def species_names(self) -> List[str]:
        return [node.species.name for _, node in self.chain.walk()]

    def paths(self) -> List[List[EvolutionNode]]:
        return self.chain.paths()
