"""Tests offline: ninguno toca la red (el fetch va mockeado)."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pokeapi import (
    Cache,
    EvolutionChain,
    Page,
    Pokemon,
    PokeApiClient,
    Species,
    normalize,
)
from pokeapi.errors import InvalidKeyError, NotFoundError

POKEMON_JSON = {
    "id": 25,
    "name": "pikachu",
    "height": 4,
    "weight": 60,
    "base_experience": 112,
    "types": [
        {"slot": 2, "type": {"name": "flying", "url": ""}},
        {"slot": 1, "type": {"name": "electric", "url": ""}},
    ],
    "stats": [
        {"base_stat": 35, "stat": {"name": "hp"}},
        {"base_stat": 55, "stat": {"name": "attack"}},
    ],
    "abilities": [
        {"ability": {"name": "static"}, "is_hidden": False, "slot": 1},
        {"ability": {"name": "lightning-rod"}, "is_hidden": True, "slot": 3},
    ],
    "sprites": {
        "front_default": "front.png",
        "other": {"official-artwork": {"front_default": "art.png"}},
    },
    "species": {"name": "pikachu", "url": "https://pokeapi.co/api/v2/pokemon-species/25/"},
    "moves": [{"move": {"name": "thunder-shock"}}],
}

SPECIES_JSON = {
    "id": 25,
    "name": "pikachu",
    "is_legendary": False,
    "is_mythical": False,
    "is_baby": False,
    "color": {"name": "yellow"},
    "generation": {"name": "generation-i"},
    "evolution_chain": {"url": "https://pokeapi.co/api/v2/evolution-chain/10/"},
    "names": [{"language": {"name": "es"}, "name": "Pikachu"}],
    "genera": [
        {"language": {"name": "en"}, "genus": "Mouse Pokémon"},
        {"language": {"name": "es"}, "genus": "Pokémon Ratón"},
    ],
    "flavor_text_entries": [
        {"language": {"name": "en"}, "flavor_text": "It raises\nits tail."},
        {"language": {"name": "es"}, "flavor_text": "Levanta\fsu cola."},
    ],
    "varieties": [{"pokemon": {"name": "pikachu"}}],
}

CHAIN_JSON = {
    "id": 10,
    "chain": {
        "species": {"name": "pichu", "url": "https://pokeapi.co/api/v2/pokemon-species/172/"},
        "evolution_details": [],
        "evolves_to": [
            {
                "species": {"name": "pikachu", "url": ""},
                "evolution_details": [
                    {"trigger": {"name": "level-up"}, "min_happiness": 160}
                ],
                "evolves_to": [
                    {
                        "species": {"name": "raichu", "url": ""},
                        "evolution_details": [
                            {"trigger": {"name": "use-item"}, "item": {"name": "thunder-stone"}}
                        ],
                        "evolves_to": [],
                    }
                ],
            }
        ],
    },
}


class FakeClient(PokeApiClient):
    """Cliente que sirve respuestas fijas en vez de salir a la red."""

    def __init__(self, responses, **kwargs):
        PokeApiClient.__init__(self, cache=Cache(enabled=False), **kwargs)
        self.responses = responses
        self.calls = []

    def _fetch(self, url):
        self.calls.append(url)
        for fragment, payload in self.responses.items():
            if fragment in url:
                return payload
        raise NotFoundError("el recurso", url)


class TestPokemonModel(unittest.TestCase):
    def setUp(self):
        self.pokemon = Pokemon.from_dict(POKEMON_JSON)

    def test_tipos_ordenados_por_slot(self):
        self.assertEqual(self.pokemon.types, ["electric", "flying"])

    def test_unidades_convertidas(self):
        self.assertAlmostEqual(self.pokemon.height_m, 0.4)
        self.assertAlmostEqual(self.pokemon.weight_kg, 6.0)

    def test_stats_y_total(self):
        self.assertEqual(self.pokemon.stats["hp"], 35)
        self.assertEqual(self.pokemon.total_stats, 90)

    def test_habilidad_oculta(self):
        hidden = [a.name for a in self.pokemon.abilities if a.is_hidden]
        self.assertEqual(hidden, ["lightning-rod"])

    def test_sprite_prefiere_artwork(self):
        self.assertEqual(self.pokemon.sprites.best, "art.png")

    def test_id_desde_url_de_especie(self):
        self.assertEqual(self.pokemon.species.id, 25)


class TestSpeciesModel(unittest.TestCase):
    def setUp(self):
        self.species = Species.from_dict(SPECIES_JSON)

    def test_genus_en_idioma(self):
        self.assertEqual(self.species.genus("es"), "Pokémon Ratón")

    def test_genus_cae_a_ingles(self):
        self.assertEqual(self.species.genus("fr"), "Mouse Pokémon")

    def test_flavor_text_limpia_saltos(self):
        self.assertEqual(self.species.flavor_text("es"), "Levanta su cola.")

    def test_id_de_cadena_evolutiva(self):
        self.assertEqual(self.species.evolution_chain_id, 10)


class TestEvolutionChain(unittest.TestCase):
    def setUp(self):
        self.chain = EvolutionChain.from_dict(CHAIN_JSON)

    def test_recorrido_completo(self):
        self.assertEqual(self.chain.species_names, ["pichu", "pikachu", "raichu"])

    def test_profundidad(self):
        depths = [depth for depth, _ in self.chain.chain.walk()]
        self.assertEqual(depths, [0, 1, 2])

    def test_una_sola_linea_evolutiva(self):
        paths = self.chain.paths()
        self.assertEqual(len(paths), 1)
        self.assertEqual([n.species.name for n in paths[0]], ["pichu", "pikachu", "raichu"])

    def test_describe_omite_trigger_redundante(self):
        raichu = [n for _, n in self.chain.chain.walk() if n.species.name == "raichu"][0]
        self.assertEqual(raichu.details[0].describe(), "usar thunder stone")


class TestPage(unittest.TestCase):
    def test_parsea_paginacion(self):
        page = Page.from_dict(
            {
                "count": 1351,
                "next": "https://pokeapi.co/api/v2/pokemon?offset=2&limit=2",
                "previous": None,
                "results": [
                    {"name": "bulbasaur", "url": "https://pokeapi.co/api/v2/pokemon/1/"},
                    {"name": "ivysaur", "url": "https://pokeapi.co/api/v2/pokemon/2/"},
                ],
            }
        )
        self.assertEqual(len(page), 2)
        self.assertTrue(page.has_next)
        self.assertEqual([r.id for r in page], [1, 2])


class TestClient(unittest.TestCase):
    def setUp(self):
        self.client = FakeClient(
            {
                "/pokemon-species/": SPECIES_JSON,
                "/evolution-chain/": CHAIN_JSON,
                "/pokemon/": POKEMON_JSON,
            }
        )

    def test_get_pokemon(self):
        self.assertEqual(self.client.get_pokemon("pikachu").id, 25)

    def test_nombre_normalizado_en_url(self):
        self.client.get_pokemon("  PIKACHU  ")
        self.assertTrue(self.client.calls[0].endswith("/pokemon/pikachu"))

    def test_query_params(self):
        client = FakeClient({"pokemon?": {"count": 0, "results": []}})
        client.get_json("pokemon", limit=5, offset=10)
        self.assertIn("limit=5", client.calls[0])
        self.assertIn("offset=10", client.calls[0])

    def test_params_none_se_omiten(self):
        client = FakeClient({"pokemon": {"count": 0, "results": []}})
        client.get_json("pokemon", limit=5, offset=None)
        self.assertNotIn("offset", client.calls[0])

    def test_no_encontrado_menciona_el_recurso(self):
        client = FakeClient({})
        with self.assertRaises(NotFoundError) as ctx:
            client.get_pokemon("mewtree")
        self.assertIn("mewtree", str(ctx.exception))

    def test_cadena_evolutiva_de_un_pokemon(self):
        chain = self.client.get_evolution_chain_of("pikachu")
        self.assertEqual(chain.species_names, ["pichu", "pikachu", "raichu"])

    def test_rechaza_salirse_del_endpoint(self):
        # Escapar no basta: el servidor decodifica %2F y sirve otro recurso.
        for key in ("../type/1", "a/b", "..%2Ftype%2F1", "https://evil.test/x"):
            with self.assertRaises(InvalidKeyError, msg=key):
                self.client._url("pokemon", key)

    def test_rechaza_caracteres_especiales(self):
        for key in ("<script>", "@#$%", "piña", "a b", "💀", ""):
            with self.assertRaises(InvalidKeyError, msg=key):
                self.client._url("pokemon", key)

    def test_acepta_nombres_reales(self):
        for key in ("mr-mime", "porygon-z", "ho-oh", "nidoran-f", "150", "10034"):
            self.assertTrue(self.client._url("pokemon", key).endswith("/" + key), key)

    def test_no_hay_peticion_si_la_clave_es_invalida(self):
        with self.assertRaises(InvalidKeyError):
            self.client.get_json("pokemon", "../type/1")
        self.assertEqual(self.client.calls, [])

    def test_url_absoluta_se_respeta(self):
        url = self.client._url("https://pokeapi.co/api/v2/pokemon/25/")
        self.assertEqual(url, "https://pokeapi.co/api/v2/pokemon/25/")


def _index(*names):
    """Simula la respuesta del índice completo del endpoint."""
    return {
        "count": len(names),
        "next": None,
        "previous": None,
        "results": [
            {
                "name": name,
                "url": "https://pokeapi.co/api/v2/pokemon/{0}/".format(number),
            }
            for number, name in enumerate(names, start=1)
        ],
    }


INDEX_JSON = _index(
    "bulbasaur",
    "charmander",
    "charmeleon",
    "charizard",
    "pikachu",
    "raichu",
    "mew",
    "mewtwo",
    "mr-mime",
    "charizard-mega-x",
)


class TestNormalize(unittest.TestCase):
    def test_minusculas_y_espacios(self):
        self.assertEqual(normalize("  CHARIzard "), "charizard")

    def test_espacios_a_guiones(self):
        self.assertEqual(normalize("Mr Mime"), "mr-mime")

    def test_numeros(self):
        self.assertEqual(normalize(25), "25")


class TestFind(unittest.TestCase):
    def setUp(self):
        self.client = FakeClient({"pokemon?": INDEX_JSON})

    def test_exacto(self):
        match = self.client.find("charizard")
        self.assertEqual(match.kind, "exact")
        self.assertEqual(match.names, ["charizard"])

    def test_exacto_ignora_mayusculas(self):
        self.assertTrue(self.client.find("CHARIZARD").is_exact)

    def test_prefijo_devuelve_todos(self):
        match = self.client.find("chari")
        self.assertEqual(match.kind, "prefix")
        self.assertEqual(match.names, ["charizard", "charizard-mega-x"])

    def test_prefijo_corto(self):
        match = self.client.find("cha")
        self.assertEqual(match.kind, "prefix")
        self.assertEqual(len(match), 4)

    def test_prefijo_unico(self):
        match = self.client.find("bulba")
        self.assertEqual(match.kind, "prefix")
        self.assertTrue(match.is_unique)

    def test_subcadena_cuando_no_hay_prefijo(self):
        match = self.client.find("chu")
        self.assertEqual(match.kind, "contains")
        self.assertEqual(match.names, ["pikachu", "raichu"])

    def test_parecido_para_erratas(self):
        match = self.client.find("pikchu")
        self.assertEqual(match.kind, "similar")
        self.assertIn("pikachu", match.names)

    def test_sin_coincidencias(self):
        match = self.client.find("zzzzz")
        self.assertEqual(match.kind, "none")
        self.assertFalse(match)

    def test_caracteres_especiales_no_coinciden(self):
        for query in ("@#$%", "<script>", "*", "💀", "%20"):
            self.assertEqual(self.client.find(query).kind, "none", query)

    def test_caracteres_especiales_no_llegan_a_la_red(self):
        # Solo se pide el índice: nada de lo escrito se mete en una URL.
        self.client.find("<script>/../etc")
        self.assertEqual(len(self.client.calls), 1)
        self.assertNotIn("script", self.client.calls[0])

    def test_acentos_caen_en_parecidos(self):
        match = self.client.find("pikachú")
        self.assertEqual(match.kind, "similar")
        self.assertIn("pikachu", match.names)

    def test_cadena_vacia(self):
        for query in ("", "   "):
            match = self.client.find(query)
            self.assertEqual(match.kind, "empty", repr(query))
            self.assertFalse(match)

    def test_cadena_vacia_no_pide_el_indice(self):
        self.client.find("")
        self.assertEqual(self.client.calls, [])

    def test_por_id(self):
        match = self.client.find("4")
        self.assertEqual(match.kind, "exact")
        self.assertEqual(match.names, ["charizard"])

    def test_id_inexistente_es_numero_invalido(self):
        match = self.client.find("9999")
        self.assertEqual(match.kind, "invalid-number")
        self.assertFalse(match)

    def test_cero_es_numero_invalido(self):
        self.assertEqual(self.client.find("0").kind, "invalid-number")

    def test_negativo_es_numero_invalido(self):
        self.assertEqual(self.client.find("-5").kind, "invalid-number")

    def test_numero_invalido_no_sugiere_nombres(self):
        # Un número equivocado no debe caer en la búsqueda por parecido.
        self.assertEqual(self.client.find("9999").names, [])

    def test_nombre_exacto_gana_al_prefijo(self):
        # 'mew' existe y además es prefijo de 'mewtwo': debe ganar el exacto.
        match = self.client.find("mew")
        self.assertEqual(match.kind, "exact")
        self.assertEqual(match.names, ["mew"])

    def test_starts_with_no_cae_a_subcadena(self):
        self.assertEqual(self.client.starts_with("chu"), [])
        self.assertEqual(
            [item.name for item in self.client.starts_with("mew")], ["mew", "mewtwo"]
        )

    def test_espacios_se_convierten_en_guiones(self):
        self.assertTrue(self.client.find("mr mime").is_exact)

    def test_tramos_de_ids(self):
        # El índice de prueba es 1-10 continuo.
        self.assertEqual(self.client.id_ranges(), [(1, 10)])

    def test_tramos_detectan_el_salto_a_las_formas(self):
        client = FakeClient(
            {
                "pokemon?": {
                    "count": 3,
                    "results": [
                        {"name": "a", "url": "https://x/pokemon/1/"},
                        {"name": "b", "url": "https://x/pokemon/2/"},
                        {"name": "c", "url": "https://x/pokemon/10001/"},
                    ],
                }
            }
        )
        self.assertEqual(client.id_ranges(), [(1, 2), (10001, 10001)])

    def test_el_indice_se_pide_una_sola_vez(self):
        directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, directory, True)
        self.client.cache = Cache(directory=directory)
        self.client.find("cha")
        self.client.find("pika")
        self.assertEqual(len(self.client.calls), 1)


def _type(*names):
    """Simula /type/{x}: la lista de Pokémon que tienen ese tipo."""
    return {
        "pokemon": [
            {
                "slot": 1,
                "pokemon": {
                    "name": name,
                    "url": "https://pokeapi.co/api/v2/pokemon/{0}/".format(number),
                },
            }
            for name, number in names
        ]
    }


class TestTypes(unittest.TestCase):
    def setUp(self):
        self.client = FakeClient(
            {
                "type/fire": _type(("charmander", 4), ("charizard", 6), ("moltres", 146)),
                "type/flying": _type(("charizard", 6), ("moltres", 146), ("pidgey", 16)),
                "type/ice": _type(),
                "type?": _index("fire", "flying", "ice", "fighting"),
            }
        )

    def test_pokemon_de_un_tipo(self):
        names = [item.name for item in self.client.pokemon_by_type("fire")]
        self.assertEqual(names, ["charmander", "charizard", "moltres"])

    def test_orden_por_pokedex(self):
        ids = [item.id for item in self.client.pokemon_by_type("flying")]
        self.assertEqual(ids, sorted(ids))

    def test_interseccion_de_tipos(self):
        result = self.client.pokemon_of_types(["fire", "flying"])
        self.assertEqual([item.name for item in result], ["charizard", "moltres"])

    def test_union_de_tipos(self):
        result = self.client.pokemon_of_types(["fire", "flying"], match_all=False)
        self.assertEqual(
            [item.name for item in result],
            ["charmander", "charizard", "pidgey", "moltres"],
        )

    def test_tipo_repetido_no_falsea_la_interseccion(self):
        # 'fire fire' debe dar los de fuego, no una lista vacía.
        result = self.client.pokemon_of_types(["fire", "fire"])
        self.assertEqual(len(result), 3)

    def test_interseccion_vacia(self):
        self.assertEqual(self.client.pokemon_of_types(["fire", "ice"]), [])

    def test_sin_tipos(self):
        self.assertEqual(self.client.pokemon_of_types([]), [])

    def test_nombre_de_tipo_se_normaliza(self):
        self.assertEqual(len(self.client.pokemon_by_type("  FIRE ")), 3)

    def test_tipo_por_prefijo(self):
        match = self.client.find("fi", "type")
        self.assertEqual(match.kind, "prefix")
        self.assertEqual(match.names, ["fire", "fighting"])

    def test_tipo_exacto(self):
        self.assertTrue(self.client.find("fire", "type").is_exact)


class TestWeb(unittest.TestCase):
    """La capa HTTP, sin levantar ningún servidor ni tocar la red."""

    def setUp(self):
        from pokeapi import web

        self.web = web
        self.original = web.client
        web.client = FakeClient(
            {
                "/pokemon-species/": SPECIES_JSON,
                "/evolution-chain/": CHAIN_JSON,
                "type/fire": _type(("charmander", 4), ("charizard", 6)),
                "type?": _index("fire", "flying"),
                "pokemon?": INDEX_JSON,
                "/pokemon/": POKEMON_JSON,
            }
        )
        self.addCleanup(setattr, web, "client", self.original)

    def _get(self, path, **params):
        return self.web.dispatch(path, params)

    def test_indice(self):
        status, payload = self._get("/")
        self.assertEqual(status, 200)
        self.assertIn("endpoints", payload)

    def test_pokemon_exacto(self):
        status, payload = self._get("/pokemon/pikachu")
        self.assertEqual(status, 200)
        self.assertEqual(payload["name"], "pikachu")
        self.assertEqual(payload["types"], ["electric", "flying"])

    def test_pokemon_parcial_devuelve_candidatos(self):
        status, payload = self._get("/pokemon/chari")
        self.assertEqual(status, 200)
        self.assertEqual(payload["kind"], "prefix")
        self.assertEqual(len(payload["matches"]), 2)

    def test_pokemon_inexistente(self):
        status, payload = self._get("/pokemon/zzzzz")
        self.assertEqual(status, 404)
        self.assertIn("error", payload)

    def test_numero_invalido(self):
        status, payload = self._get("/pokemon/9999")
        self.assertEqual(status, 400)
        self.assertIn("valid_ranges", payload)

    def test_tipos_combinados(self):
        status, payload = self._get("/type/fire")
        self.assertEqual(status, 200)
        self.assertEqual(payload["count"], 2)

    def test_tipo_inexistente(self):
        status, payload = self._get("/type/zzz")
        self.assertEqual(status, 404)
        self.assertIn("available", payload)

    def test_ruta_desconocida(self):
        self.assertEqual(self._get("/nope")[0], 404)

    def test_search_sin_query(self):
        self.assertEqual(self._get("/search")[0], 400)

    def test_health(self):
        status, payload = self._get("/health")
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "ok")

    def test_raw_devuelve_el_json_original(self):
        status, payload = self._get("/pokemon/pikachu", raw="1")
        self.assertEqual(status, 200)
        self.assertIn("moves", payload)

    def test_wsgi_responde_json(self):
        captured = {}

        def start_response(status, headers):
            captured["status"] = status
            captured["headers"] = dict(headers)

        body = self.web.app(
            {"REQUEST_METHOD": "GET", "PATH_INFO": "/pokemon/pikachu", "QUERY_STRING": ""},
            start_response,
        )
        self.assertEqual(captured["status"], "200 OK")
        self.assertEqual(
            captured["headers"]["Content-Type"], "application/json; charset=utf-8"
        )
        self.assertEqual(captured["headers"]["Access-Control-Allow-Origin"], "*")
        self.assertEqual(json.loads(b"".join(body))["name"], "pikachu")

    def test_wsgi_rechaza_post(self):
        captured = {}
        self.web.app(
            {"REQUEST_METHOD": "POST", "PATH_INFO": "/pokemon/pikachu", "QUERY_STRING": ""},
            lambda status, headers: captured.setdefault("status", status),
        )
        self.assertEqual(captured["status"], "405 Method Not Allowed")

    def test_wsgi_no_filtra_trazas(self):
        def explota(*args, **kwargs):
            raise RuntimeError("secreto interno")

        self.web.client.find = explota
        captured = {}
        body = self.web.app(
            {"REQUEST_METHOD": "GET", "PATH_INFO": "/pokemon/x", "QUERY_STRING": ""},
            lambda status, headers: captured.setdefault("status", status),
        )
        self.assertEqual(captured["status"], "500 Internal Server Error")
        self.assertNotIn("secreto", b"".join(body).decode("utf-8"))


class TestCache(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp()
        self.cache = Cache(directory=self.directory)

    def tearDown(self):
        shutil.rmtree(self.directory, ignore_errors=True)

    def test_guarda_y_recupera(self):
        self.cache.set("http://x/1", {"id": 1})
        self.assertEqual(self.cache.get("http://x/1"), {"id": 1})
        self.assertEqual(self.cache.hits, 1)

    def test_miss_devuelve_none(self):
        self.assertIsNone(self.cache.get("http://x/nope"))

    def test_ttl_caducado(self):
        self.cache.set("http://x/1", {"id": 1})
        self.cache.ttl = -1
        self.assertIsNone(self.cache.get("http://x/1"))

    def test_deshabilitada_no_escribe(self):
        cache = Cache(directory=self.directory, enabled=False)
        cache.set("http://x/1", {"id": 1})
        self.assertIsNone(cache.get("http://x/1"))

    def test_clear_y_info(self):
        self.cache.set("http://x/1", {"id": 1})
        self.cache.set("http://x/2", {"id": 2})
        self.assertEqual(self.cache.info()["entries"], 2)
        self.assertEqual(self.cache.clear(), 2)
        self.assertEqual(self.cache.info()["entries"], 0)

    def test_el_cliente_evita_la_segunda_peticion(self):
        client = FakeClient({"/pokemon/": POKEMON_JSON})
        client.cache = self.cache
        client.get_pokemon("pikachu")
        client.get_pokemon("pikachu")
        self.assertEqual(len(client.calls), 1)


if __name__ == "__main__":
    unittest.main()
