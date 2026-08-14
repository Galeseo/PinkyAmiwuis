"""Ejemplo de uso del cliente de la PokéAPI.

    python3 ejemplo.py
"""

from pokeapi import NotFoundError, PokeApiClient

client = PokeApiClient()

# 1. Ficha de un Pokémon
pikachu = client.get_pokemon("pikachu")
print("{0} (#{1}) — tipos: {2}".format(pikachu.name, pikachu.id, ", ".join(pikachu.types)))
print("  {0:.1f} m, {1:.1f} kg, total de stats: {2}".format(
    pikachu.height_m, pikachu.weight_kg, pikachu.total_stats
))
print("  sprite: {0}".format(pikachu.sprites.best))

# 2. Datos de especie (con textos en español)
species = client.get_species_of(pikachu)
print("\n{0} — {1}".format(species.display_name("es"), species.genus("es")))
print("  {0}".format(species.flavor_text("es")))

# 3. Cadena evolutiva
chain = client.get_evolution_chain_of("eevee")
print("\nEvoluciones de Eevee:")
for path in chain.paths():
    conditions = path[-1].details[0].describe() if path[-1].details else "—"
    print("  {0}: {1}".format(path[-1].species.name, conditions))

# 4. Por tipo
fuego = client.pokemon_by_type("fire")
dobles = client.pokemon_of_types(["fire", "flying"])
print("\n{0} Pokémon de fuego; {1} son además voladores: {2}".format(
    len(fuego), len(dobles), ", ".join(item.name for item in dobles[:3])
))

# 5. Listado paginado
page = client.list_pokemon(limit=5, offset=0)
print("\nPrimeros 5 de {0} Pokémon: {1}".format(
    page.count, ", ".join(item.name for item in page)
))

# 6. Recorrer todo el catálogo de forma perezosa (aquí, solo los tipos)
types = [item.name for item in client.iter_resource("type", page_size=50)]
print("\n{0} tipos: {1}".format(len(types), ", ".join(types)))

# 7. Manejo de errores
try:
    client.get_pokemon("mewtree")
except NotFoundError as exc:
    print("\nError controlado: {0}".format(exc))

print("\nCaché: {0} entradas en {1}".format(
    client.cache_info()["entries"], client.cache_info()["directory"]
))
