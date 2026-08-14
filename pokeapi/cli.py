"""CLI de la PokéAPI.

    python -m pokeapi pokemon pikachu
    python -m pokeapi evolution eevee
    python -m pokeapi list --limit 10
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, List, Optional, Tuple

from .cache import Cache
from .client import PokeApiClient, normalize
from .errors import PokeApiError
from .models import EvolutionNode, Match, Pokemon, Species

# Cuántos candidatos se listan antes de resumir el resto.
MAX_CANDIDATES = 40

STAT_LABELS = {
    "hp": "PS",
    "attack": "Ataque",
    "defense": "Defensa",
    "special-attack": "At. Esp.",
    "special-defense": "Def. Esp.",
    "speed": "Velocidad",
}


# ---------------------------------------------------------------------------
# Formato
# ---------------------------------------------------------------------------


def _title(text: str) -> str:
    return text.replace("-", " ").title()


def _bar(value: int, maximum: int = 255, width: int = 24) -> str:
    filled = int(round((min(value, maximum) / maximum) * width))
    return "█" * filled + "·" * (width - filled)


def print_pokemon(pokemon: Pokemon, show_moves: bool = False) -> None:
    print("#{0:04d}  {1}".format(pokemon.id, _title(pokemon.name)))
    print("Tipos:      {0}".format(", ".join(_title(t) for t in pokemon.types)))
    print("Altura:     {0:.1f} m".format(pokemon.height_m))
    print("Peso:       {0:.1f} kg".format(pokemon.weight_kg))
    if pokemon.base_experience is not None:
        print("Exp. base:  {0}".format(pokemon.base_experience))

    abilities = ", ".join(
        _title(a.name) + (" (oculta)" if a.is_hidden else "") for a in pokemon.abilities
    )
    if abilities:
        print("Habilidades: {0}".format(abilities))

    print("\nEstadísticas base")
    for key, value in pokemon.stats.items():
        label = STAT_LABELS.get(key, _title(key))
        print("  {0:<10} {1:>3}  {2}".format(label, value, _bar(value)))
    print("  {0:<10} {1:>3}".format("TOTAL", pokemon.total_stats))

    if pokemon.sprites.best:
        print("\nSprite: {0}".format(pokemon.sprites.best))

    if show_moves and pokemon.moves:
        print("\nMovimientos ({0}):".format(len(pokemon.moves)))
        print("  " + ", ".join(_title(m) for m in sorted(pokemon.moves)))


def print_species(species: Species, language: str = "es") -> None:
    print("#{0:04d}  {1}".format(species.id, species.display_name(language)))
    genus = species.genus(language)
    if genus:
        print(genus)

    flags = []
    if species.is_legendary:
        flags.append("legendario")
    if species.is_mythical:
        flags.append("singular")
    if species.is_baby:
        flags.append("bebé")
    if flags:
        print("Categoría:  {0}".format(", ".join(flags)))

    rows = [
        ("Generación", species.generation),
        ("Color", species.color),
        ("Forma", species.shape),
        ("Hábitat", species.habitat),
        ("Captura", species.capture_rate),
        ("Felicidad", species.base_happiness),
        ("Crecimiento", species.growth_rate),
    ]
    print()
    for label, value in rows:
        if value is not None:
            printable = _title(str(value)) if isinstance(value, str) else value
            print("{0:<12} {1}".format(label + ":", printable))

    text = species.flavor_text(language)
    if text:
        print("\n{0}".format(text))

    if len(species.varieties) > 1:
        print("\nVariantes: {0}".format(", ".join(_title(v) for v in species.varieties)))


def print_evolution(node: EvolutionNode) -> None:
    """Dibuja el árbol evolutivo con la condición de cada paso."""
    for depth, current in node.walk():
        prefix = "   " * depth + ("└─ " if depth else "")
        line = prefix + _title(current.species.name)
        if current.details:
            conditions = " / ".join(detail.describe() for detail in current.details)
            line += "  ({0})".format(conditions)
        print(line)


def print_page(page: Any, offset: int) -> None:
    for index, item in enumerate(page.results, start=offset + 1):
        print("{0:>5}. {1:<24} {2}".format(index, _title(item.name), item.url))
    print("\nMostrando {0} de {1}.".format(len(page.results), page.count))


def dump(value: Any) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# Resolución de nombres parciales
# ---------------------------------------------------------------------------


def _prog() -> str:
    """Cómo se invocó el programa, para que los ejemplos sean copiables."""
    if os.path.basename(sys.argv[0] or "") == "__main__.py":
        return "python3 -m pokeapi"
    return "pokeapi"


def print_invalid_number(client: PokeApiClient, match: Match) -> None:
    """Mensaje para un número que no corresponde a ningún Pokémon."""
    print("Número no válido: {0}".format(match.query))

    ranges = client.id_ranges("pokemon")
    if not ranges:
        return

    tramos = ["del {0} al {1}".format(start, end) for start, end in ranges]
    if len(tramos) == 1:
        print("Los números van {0}.".format(tramos[0]))
    else:
        print(
            "Los números van {0} (Pokédex) y {1} (formas alternativas).".format(
                tramos[0], ", ".join(tramos[1:])
            )
        )


def print_resources(items: List[Any], show_ids: bool = True) -> None:
    """Imprime una lista de recursos, con su número de Pokédex si lo tienen."""
    for item in items:
        if show_ids:
            number = "#{0:04d}".format(item.id) if item.id else "     "
            print("  {0}  {1}".format(number, _title(item.name)))
        else:
            print("  {0}".format(_title(item.name)))


def print_candidates(
    match: Match, command: str, noun: str = "Pokémon", show_ids: bool = True
) -> None:
    """Lista los recursos que encajan con lo que se escribió."""
    total = len(match.results)

    if match.kind == "prefix":
        print("'{0}' coincide con {1} {2}:\n".format(match.query, total, noun))
    elif match.kind == "contains":
        print(
            "Ningún nombre empieza por '{0}', pero {1} lo contienen:\n".format(
                match.query, total
            )
        )
    elif match.kind == "similar":
        print("No existe '{0}'. ¿Quisiste decir?\n".format(match.query))
    else:
        print("No hay ningún {0} que coincida con '{1}'.".format(
            "tipo" if noun != "Pokémon" else "Pokémon", match.query
        ))
        return

    print_resources(match.results[:MAX_CANDIDATES], show_ids)

    if total > MAX_CANDIDATES:
        print("  … y {0} más.".format(total - MAX_CANDIDATES))

    example = match.results[0].name
    print("\nAfina la búsqueda:  {0} {1} {2}".format(_prog(), command, example))


def resolve(
    client: PokeApiClient,
    query: str,
    command: str,
    exact: bool,
    as_json: bool,
    type_fallback: bool = False,
) -> Tuple[Optional[str], Optional[str], int]:
    """Convierte lo escrito en un nombre concreto de la API.

    Devuelve ``(nombre, nota, código)``. Si el nombre no se puede resolver a
    uno solo, imprime los candidatos y devuelve ``nombre`` a ``None`` con el
    código de salida que debe usar el comando: 0 si hubo algo que mostrar,
    2 si no coincidió nada.
    """
    if exact:
        return normalize(query), None, 0

    match = client.find(query, "pokemon")

    if match.is_exact:
        # Aunque sea exacto, avisamos si es prefijo de otros: 'mew' existe,
        # pero quien lo escribe quizá buscaba mewtwo.
        name = match.results[0].name
        others = [
            item.name
            for item in client.starts_with(name)
            if item.name != name
        ]
        note = None
        if others:
            shown = ", ".join(_title(other) for other in others[:4])
            if len(others) > 4:
                shown += ", …"
            note = "También empiezan por '{0}': {1}".format(name, shown)
        return name, note, 0

    # Si lo escrito es exactamente un tipo, se busca la lista de ese tipo y no
    # un Pokémon que lo contenga en el nombre. Va después del nombre exacto,
    # así que un Pokémon nunca queda tapado por un tipo homónimo.
    if type_fallback and match.kind != "empty":
        as_type = client.find(query, "type")
        if as_type.is_exact:
            print_type_listing(client, [as_type.results[0].name], as_json=as_json)
            return None, None, 0

    if match.is_unique and match.kind in ("prefix", "contains"):
        name = match.results[0].name
        print("→ {0}\n".format(_title(name)))
        return name, None, 0

    if as_json:
        dump({"query": match.query, "kind": match.kind, "matches": match.names})
    elif match.kind == "empty":
        print("Escribe un nombre o un número, p. ej. 'pikachu', 'chari' o '25'.")
    elif match.kind == "invalid-number":
        print_invalid_number(client, match)
    else:
        print_candidates(match, command)
    return None, None, 0 if match.results else 2


# ---------------------------------------------------------------------------
# Comandos
# ---------------------------------------------------------------------------


def cmd_pokemon(client: PokeApiClient, args: argparse.Namespace) -> int:
    name, note, code = resolve(
        client, args.name, "pokemon", args.exact, args.json, type_fallback=True
    )
    if name is None:
        return code

    pokemon = client.get_pokemon(name)
    if args.json:
        dump(pokemon.raw)
        return 0

    print_pokemon(pokemon, show_moves=args.moves)
    if note:
        print("\n{0}".format(note))
    return 0


def cmd_species(client: PokeApiClient, args: argparse.Namespace) -> int:
    name, note, code = resolve(client, args.name, "species", args.exact, args.json)
    if name is None:
        return code

    species = client.get_species_of(name)
    if args.json:
        dump(species.raw)
        return 0

    print_species(species, language=args.lang)
    if note:
        print("\n{0}".format(note))
    return 0


def cmd_evolution(client: PokeApiClient, args: argparse.Namespace) -> int:
    name, note, code = resolve(client, args.name, "evolution", args.exact, args.json)
    if name is None:
        return code

    chain = client.get_evolution_chain_of(name)
    if args.json:
        dump(chain.raw)
        return 0

    print("Cadena evolutiva #{0}".format(chain.id))
    print_evolution(chain.chain)
    if note:
        print("\n{0}".format(note))
    return 0


def resolve_type(client: PokeApiClient, query: str) -> Optional[str]:
    """Resuelve el nombre de un tipo, admitiendo abreviaturas ('ele' -> electric)."""
    match = client.find(query, "type")

    if match.is_exact:
        return match.results[0].name
    if match.is_unique and match.kind in ("prefix", "contains"):
        return match.results[0].name

    print_candidates(match, "type", noun="tipos", show_ids=False)
    return None


def print_type_listing(
    client: PokeApiClient,
    names: List[str],
    match_all: bool = True,
    as_json: bool = False,
) -> int:
    """Imprime todos los Pokémon de uno o varios tipos."""
    results = client.pokemon_of_types(names, match_all=match_all)

    if as_json:
        dump({
            "types": names,
            "mode": "all" if match_all else "any",
            "count": len(results),
            "pokemon": [item.name for item in results],
        })
        return 0

    separator = " + " if match_all else " o "
    label = "Tipo" if len(names) == 1 else "Tipos"
    print("{0} {1} — {2} Pokémon\n".format(
        label, separator.join(_title(name) for name in names), len(results)
    ))

    if not results:
        print("  Ninguno combina esos tipos.")
        print("\nPrueba con --any para ver los que tienen alguno de ellos.")
        return 0

    print_resources(results)
    return 0


def cmd_type(client: PokeApiClient, args: argparse.Namespace) -> int:
    # Sin argumentos, enseñamos qué tipos hay.
    if not args.types:
        types = client.name_index("type")
        print("Tipos disponibles ({0}):\n".format(len(types)))
        print_resources(types, show_ids=False)
        print("\nEjemplo:  {0} type fire flying".format(_prog()))
        return 0

    names = []
    for raw in args.types:
        name = resolve_type(client, raw)
        if name is None:
            return 2
        names.append(name)

    return print_type_listing(client, names, not args.any, args.json)


def cmd_list(client: PokeApiClient, args: argparse.Namespace) -> int:
    if args.all:
        names = []
        for item in client.iter_resource(args.endpoint, page_size=args.limit):
            names.append(item.name)
            if not args.json:
                print("{0:>5}. {1}".format(len(names), _title(item.name)))
        if args.json:
            dump(names)
        else:
            print("\nTotal: {0}.".format(len(names)))
        return 0

    page = client.list_resource(args.endpoint, limit=args.limit, offset=args.offset)
    if args.json:
        dump({"count": page.count, "results": [r.name for r in page.results]})
    else:
        print_page(page, args.offset)
    return 0


def cmd_search(client: PokeApiClient, args: argparse.Namespace) -> int:
    needle = normalize(args.text)
    matches = [
        item for item in client.name_index(args.endpoint) if needle in item.name
    ]

    if args.json:
        dump([item.name for item in matches])
        return 0

    for item in matches:
        number = "#{0:04d}".format(item.id) if item.id else "     "
        print("  {0}  {1}".format(number, _title(item.name)))
    print("\n{0} coincidencia(s) para '{1}'.".format(len(matches), args.text))
    return 0


def cmd_cache(client: PokeApiClient, args: argparse.Namespace) -> int:
    if args.clear:
        removed = client.clear_cache()
        print("Caché vaciada: {0} entrada(s) eliminada(s).".format(removed))
        return 0
    info = client.cache_info()
    if args.json:
        dump(info)
        return 0
    print("Directorio: {0}".format(info["directory"]))
    print("Entradas:   {0}".format(info["entries"]))
    print("Tamaño:     {0:.1f} KB".format(info["bytes"] / 1024.0))
    ttl = info["ttl_seconds"]
    print("TTL:        {0}".format(
        "sin caducidad" if ttl is None else "{0:.0f} h".format(ttl / 3600.0)
    ))
    return 0


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pokeapi", description="Cliente de línea de comandos para la PokéAPI."
    )
    parser.add_argument("--json", action="store_true", help="Salida en JSON crudo.")
    parser.add_argument(
        "--exact",
        action="store_true",
        help="Usa el nombre tal cual, sin buscar coincidencias parciales.",
    )
    parser.add_argument("--no-cache", action="store_true", help="Ignora la caché local.")
    parser.add_argument(
        "--ttl", type=float, default=None, help="TTL de la caché en horas."
    )
    parser.add_argument(
        "--timeout", type=float, default=10.0, help="Timeout por petición (s)."
    )

    sub = parser.add_subparsers(dest="command")

    p_pokemon = sub.add_parser("pokemon", help="Ficha de un Pokémon.")
    p_pokemon.add_argument("name", help="Nombre o id (p. ej. pikachu o 25).")
    p_pokemon.add_argument("--moves", action="store_true", help="Lista sus movimientos.")
    p_pokemon.set_defaults(func=cmd_pokemon)

    p_species = sub.add_parser("species", help="Datos de especie y Pokédex.")
    p_species.add_argument("name", help="Nombre o id.")
    p_species.add_argument("--lang", default="es", help="Idioma (por defecto: es).")
    p_species.set_defaults(func=cmd_species)

    p_evo = sub.add_parser("evolution", help="Cadena evolutiva.")
    p_evo.add_argument("name", help="Nombre o id.")
    p_evo.set_defaults(func=cmd_evolution)

    p_type = sub.add_parser("type", help="Lista los Pokémon de uno o varios tipos.")
    p_type.add_argument(
        "types",
        nargs="*",
        help="Tipos (fire, water…). Sin argumentos, lista los tipos que hay.",
    )
    p_type.add_argument(
        "--any",
        action="store_true",
        help="Los que tengan ALGUNO de los tipos, en vez de todos.",
    )
    p_type.set_defaults(func=cmd_type)

    p_list = sub.add_parser("list", help="Listado paginado de recursos.")
    p_list.add_argument("--endpoint", default="pokemon", help="pokemon, type, move…")
    p_list.add_argument("--limit", type=int, default=20, help="Tamaño de página.")
    p_list.add_argument("--offset", type=int, default=0, help="Desplazamiento.")
    p_list.add_argument("--all", action="store_true", help="Recorre todas las páginas.")
    p_list.set_defaults(func=cmd_list)

    p_search = sub.add_parser("search", help="Busca por subcadena en los nombres.")
    p_search.add_argument("text", help="Texto a buscar.")
    p_search.add_argument("--endpoint", default="pokemon", help="Recurso a recorrer.")
    p_search.set_defaults(func=cmd_search)

    p_cache = sub.add_parser("cache", help="Estado de la caché local.")
    p_cache.add_argument("--clear", action="store_true", help="Vacía la caché.")
    p_cache.set_defaults(func=cmd_cache)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not getattr(args, "func", None):
        parser.print_help()
        return 1

    cache = Cache(enabled=not args.no_cache)
    if args.ttl is not None:
        cache.ttl = args.ttl * 3600
    client = PokeApiClient(cache=cache, timeout=args.timeout)

    try:
        return args.func(client, args)
    except PokeApiError as exc:
        print("Error: {0}".format(exc), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\nCancelado.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
