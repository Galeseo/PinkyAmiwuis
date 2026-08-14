# PinkyAmiwuis
WiuWiuWiu

Cliente de la [PokéAPI](https://pokeapi.co/docs/v2) en Python, **sin dependencias
externas** (solo librería estándar), con caché local en disco, reintentos
automáticos y CLI.

## Uso rápido

```bash
python3 -m pokeapi pokemon pikachu
python3 -m pokeapi evolution eevee
python3 -m pokeapi species charizard --lang es
python3 -m pokeapi type fire flying
python3 -m pokeapi list --limit 10
python3 -m pokeapi search char
python3 -m pokeapi cache
```

### No hace falta escribir el nombre entero

`pokemon`, `species` y `evolution` aceptan nombres parciales. Si lo escrito
encaja con varios Pokémon, se listan para que elijas:

```console
$ python3 -m pokeapi pokemon CHARI
'chari' coincide con 4 Pokémon:

  #0006  Charizard
  #10034  Charizard Mega X
  #10035  Charizard Mega Y
  #10196  Charizard Gmax

Afina la búsqueda:  python3 -m pokeapi pokemon charizard
```

El orden de resolución es: nombre exacto → prefijo → subcadena → parecido.

| Escribes | Qué pasa |
| --- | --- |
| `charizard` | Coincidencia exacta, muestra la ficha |
| `chari` | 4 candidatos, los lista |
| `bulba` | Un solo candidato, lo abre directamente |
| `chu` | Ningún nombre empieza así, busca dentro: pikachu, raichu… |
| `pikchu` | Errata: sugiere pikachu, pichu, raichu |
| `6` | Por número de Pokédex → Charizard |
| `9999` | `Número no válido: 9999` y los tramos que sí existen |
| `Mr Mime` | Los espacios se convierten en guiones |

### Por número

```console
$ python3 -m pokeapi pokemon 150
#0150  Mewtwo

$ python3 -m pokeapi pokemon 9999
Número no válido: 9999
Los números van del 1 al 1025 (Pokédex) y del 10001 al 10326 (formas alternativas).
```

La numeración de la API no es continua —la Pokédex acaba en 1025 y las formas
alternativas (megaevoluciones, Gmax…) empiezan en 10001—, así que los tramos se
calculan del índice real en vez de darlos por supuestos.

Los nombres se resuelven contra un índice completo que se pide **una sola vez**
y queda cacheado, así que no cuesta una petición por intento. Con `--exact`
se salta la resolución y se usa el nombre tal cual.

Instalación opcional (deja el comando `pokeapi` en el PATH):

```bash
pip install -e .
```

## Uso como librería

```python
from pokeapi import PokeApiClient

client = PokeApiClient()

pikachu = client.get_pokemon("pikachu")
print(pikachu.types)        # ['electric']
print(pikachu.stats)        # {'hp': 35, 'attack': 55, ...}
print(pikachu.height_m)     # 0.4
print(pikachu.sprites.best) # URL del artwork oficial

# Especie: textos de Pokédex traducidos
species = client.get_species_of(pikachu)
print(species.genus("es"))        # 'Pokémon Ratón'
print(species.flavor_text("es"))  # descripción de la Pokédex

# Cadena evolutiva (soporta ramificaciones como Eevee)
chain = client.get_evolution_chain_of("eevee")
for path in chain.paths():
    print(path[-1].species.name, path[-1].details[0].describe())

# Listados paginados, o recorrido perezoso del catálogo entero
page = client.list_pokemon(limit=20, offset=0)
for item in client.iter_pokemon():
    ...

# Búsqueda por nombre parcial
match = client.find("chari")
match.kind        # 'exact' | 'prefix' | 'contains' | 'similar' | 'none'
match.names       # ['charizard', 'charizard-mega-x', ...]
match.is_unique   # True si solo hay un candidato

client.starts_with("mew")   # solo prefijo, sin vueltas atrás
client.name_index()         # los 1351 nombres, en una petición cacheada

# Por tipo
client.pokemon_by_type("fire")                      # los 109 de fuego
client.pokemon_of_types(["fire", "flying"])         # los que tienen ambos
client.pokemon_of_types(["fire", "flying"], False)  # los que tienen alguno

# Cualquier otro endpoint
tipo = client.get_resource("type", "electric")
```

Hay un recorrido completo en [ejemplo.py](ejemplo.py).

## Qué incluye

| Módulo | Contenido |
| --- | --- |
| [client.py](pokeapi/client.py) | `PokeApiClient`: HTTP, reintentos con espera exponencial, `Retry-After`, paginación |
| [models.py](pokeapi/models.py) | `Pokemon`, `Species`, `EvolutionChain`, `Page`… tipados, con el JSON original en `.raw` |
| [cache.py](pokeapi/cache.py) | Caché de ficheros JSON con TTL (7 días por defecto) |
| [errors.py](pokeapi/errors.py) | `NotFoundError`, `RateLimitError`, `HttpError`, `NetworkError`, `InvalidKeyError` |
| [cli.py](pokeapi/cli.py) | Comandos `pokemon`, `species`, `evolution`, `type`, `list`, `search`, `cache` |

### Por tipo

```console
$ python3 -m pokeapi type fire flying
Tipos Fire + Flying — 8 Pokémon

  #0006  Charizard
  #0146  Moltres
  #0250  Ho Oh
  #0662  Fletchinder
  #0663  Talonflame
  #0741  Oricorio Baile
  #10035  Charizard Mega Y
  #10196  Charizard Gmax
```

Con varios tipos devuelve los que los tienen **todos**; con `--any`, los que
tienen **alguno**. Los nombres de tipo también admiten abreviaturas (`ele` →
electric) y `type` sin argumentos lista los 21 tipos que hay.

Escribir un tipo en el comando `pokemon` hace lo mismo, porque casi siempre es
lo que se busca:

```console
$ python3 -m pokeapi pokemon fire
Tipo Fire — 109 Pokémon
...
```

Un nombre exacto de Pokémon siempre gana, así que esto nunca tapa una ficha.

### Caracteres especiales

Lo que se escribe se compara contra el índice local, así que nunca acaba dentro
de una URL: `@#$%` o `<script>` simplemente no coinciden con nada. Los acentos
caen en la búsqueda por parecido (`pikachú` → sugiere Pikachu).

Con `--exact` sí se salta el índice, así que ahí la clave se valida contra
`^[a-z0-9][a-z0-9-]*$` (el juego de caracteres real de la API) y se lanza
`InvalidKeyError` antes de salir a la red. No basta con escapar: el servidor
decodifica `%2F`, y una clave como `../type/1` acabaría devolviendo otro
recurso.

### Caché

La PokéAPI es gratuita y pide expresamente que se cacheen las respuestas. Por
defecto se guardan en `~/Library/Caches/pokeapi-py` (macOS) o
`~/.cache/pokeapi-py`, configurable con la variable `POKEAPI_CACHE_DIR`.

```bash
python3 -m pokeapi cache            # estado
python3 -m pokeapi cache --clear    # vaciar
python3 -m pokeapi pokemon ditto --no-cache
```

```python
from pokeapi import Cache, PokeApiClient

client = PokeApiClient(cache=Cache(ttl=None))       # sin caducidad
client = PokeApiClient(use_cache=False)             # siempre a la red
```

## API web

Además del CLI hay una app WSGI ([web.py](pokeapi/web.py)) que expone el cliente
por HTTP. También sin dependencias:

```bash
python3 -m pokeapi.web        # http://localhost:8000
```

| Ruta | Qué devuelve |
| --- | --- |
| `GET /` | Índice de endpoints |
| `GET /pokemon/{nombre\|id}` | Ficha. Admite parciales: `/pokemon/chari` devuelve los candidatos |
| `GET /species/{nombre\|id}` | Especie y Pokédex (`?lang=es`) |
| `GET /evolution/{nombre\|id}` | Cadena evolutiva |
| `GET /type/{tipo}` | Pokémon del tipo. Varios: `/type/fire,flying` (`?mode=any` para la unión) |
| `GET /types` | Los 21 tipos |
| `GET /search?q={texto}` | Búsqueda por subcadena |
| `GET /health` | Estado y estadísticas de caché |

Añade `?raw=1` a cualquiera para recibir el JSON original de la PokéAPI.
Los códigos de estado son 400 (número o petición inválidos), 404 (no existe),
429 (la PokéAPI pidió bajar el ritmo), 502/504 (la PokéAPI falló o no responde).
Manda CORS abierto, así que se puede llamar desde el navegador.

## Desplegar en Render

Ya están [requirements.txt](requirements.txt) (solo gunicorn, como servidor) y
[render.yaml](render.yaml).

1. Sube el repo a GitHub.
2. En Render: **New → Blueprint**, elige el repo. Detecta `render.yaml` y crea
   el servicio con todo configurado.

Si prefieres hacerlo a mano (**New → Web Service**):

| Campo | Valor |
| --- | --- |
| Runtime | Python 3 |
| Build command | `pip install -r requirements.txt` |
| Start command | `gunicorn pokeapi.web:app --bind 0.0.0.0:$PORT` |
| Health check path | `/health` |

Variables de entorno recomendadas: `PYTHON_VERSION=3.11.9` y
`POKEAPI_CACHE_DIR=/tmp/pokeapi-cache` (el disco de Render es efímero; `/tmp`
es el sitio escribible, y la caché sobrevive mientras la instancia siga viva).

En el plan gratuito la instancia se duerme tras 15 minutos sin tráfico, así que
la primera petición después de dormir tarda bastante.

## Tests

Los tests no tocan la red (las respuestas van mockeadas):

```bash
python3 -m unittest discover -s tests
```
# PinkyAmiwuis
