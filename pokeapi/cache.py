"""Caché local en disco para las respuestas de la PokéAPI.

La PokéAPI es gratuita y pide expresamente que se cacheen las respuestas: los
datos son prácticamente estáticos, así que guardarlos en local evita miles de
peticiones repetidas.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from typing import Any, Dict, Optional

DEFAULT_TTL = 7 * 24 * 60 * 60  # 7 días


def default_cache_dir() -> str:
    """Directorio de caché por plataforma, sobreescribible con POKEAPI_CACHE_DIR."""
    override = os.environ.get("POKEAPI_CACHE_DIR")
    if override:
        return os.path.expanduser(override)
    if sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Caches")
    else:
        base = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    return os.path.join(base, "pokeapi-py")


class Cache:
    """Caché de ficheros JSON con TTL, indexada por URL."""

    def __init__(
        self,
        directory: Optional[str] = None,
        ttl: Optional[float] = DEFAULT_TTL,
        enabled: bool = True,
    ) -> None:
        """``ttl`` en segundos; ``None`` desactiva la caducidad."""
        self.directory = directory or default_cache_dir()
        self.ttl = ttl
        self.enabled = enabled
        self.hits = 0
        self.misses = 0

    # -- rutas -----------------------------------------------------------

    def _path_for(self, url: str) -> str:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]
        return os.path.join(self.directory, digest + ".json")

    # -- lectura / escritura ---------------------------------------------

    def get(self, url: str) -> Optional[Dict[str, Any]]:
        """Devuelve la respuesta cacheada, o None si no hay o ya caducó."""
        if not self.enabled:
            return None
        path = self._path_for(url)
        try:
            with open(path, "r", encoding="utf-8") as handle:
                entry = json.load(handle)
        except (IOError, OSError, ValueError):
            self.misses += 1
            return None

        if self.ttl is not None and time.time() - entry.get("fetched_at", 0) > self.ttl:
            self.misses += 1
            self._unlink(path)
            return None

        self.hits += 1
        return entry.get("data")

    def set(self, url: str, data: Dict[str, Any]) -> None:
        """Guarda una respuesta. Los fallos de escritura no rompen la petición."""
        if not self.enabled:
            return
        path = self._path_for(url)
        entry = {"url": url, "fetched_at": time.time(), "data": data}
        try:
            os.makedirs(self.directory, exist_ok=True)
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as handle:
                json.dump(entry, handle)
            os.replace(tmp, path)
        except (IOError, OSError):
            pass

    # -- mantenimiento ----------------------------------------------------

    def clear(self) -> int:
        """Borra la caché entera. Devuelve cuántas entradas se eliminaron."""
        removed = 0
        for path in self._entries():
            if self._unlink(path):
                removed += 1
        return removed

    def info(self) -> Dict[str, Any]:
        """Estadísticas de la caché: entradas, tamaño y aciertos de esta sesión."""
        entries = self._entries()
        size = 0
        for path in entries:
            try:
                size += os.path.getsize(path)
            except OSError:
                pass
        return {
            "directory": self.directory,
            "entries": len(entries),
            "bytes": size,
            "ttl_seconds": self.ttl,
            "hits": self.hits,
            "misses": self.misses,
        }

    def _entries(self):
        try:
            names = os.listdir(self.directory)
        except OSError:
            return []
        return [
            os.path.join(self.directory, name)
            for name in names
            if name.endswith(".json")
        ]

    @staticmethod
    def _unlink(path: str) -> bool:
        try:
            os.remove(path)
            return True
        except OSError:
            return False
