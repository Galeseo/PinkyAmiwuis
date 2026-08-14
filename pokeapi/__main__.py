"""Permite ejecutar el cliente con `python -m pokeapi`."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
