"""Pool determinista de 1000 nombres completos, compartido entre estudiantes y profesores.

La fuente es `nombres.md` en la raiz del repo (lista numerada "N. Nombre Apellido"),
descargada de 1000randomnames.com -- ver ese archivo para procedencia y fecha.
Este modulo solo la parsea a una tupla inmutable en el orden en que aparece en
el archivo; no baraja ni aleatoriza nada, para que "el siguiente nombre libre
del pool" sea una nocion 100% determinista (ver
`simulation/naming.py::next_free_names`, que decide cuales indices ya estan en
uso).

`NAME_POOL[i]` es `(nombre, apellidos)` -- el orden esperado por
`Student(apellidos=..., nombre=...)` y por el renglon "Nombre Completo" de
`profesores.md`.

La fuente combina nombres y apellidos al azar, asi que un puñado de nombres
completos se repite (2 pares en las 1000 entradas verificadas). "No repetir"
en este sistema significa no reusar la misma *posicion* del pool dos veces
dentro de una carrera de simulacion (ver `simulation/naming.py`), no que cada
nombre completo generado sea unico -- eso ultimo no lo garantiza la fuente.
"""

from __future__ import annotations

import re
from pathlib import Path

_NOMBRES_MD_PATH = Path(__file__).resolve().parents[3] / "nombres.md"
_LIST_ITEM_RE = re.compile(r"^\d+\.\s+(.+)$")


def _parse_nombres_md(path: Path) -> tuple[tuple[str, str], ...]:
    if not path.exists():
        raise FileNotFoundError(
            f"No se encontro el pool de nombres en {path}. Se espera un "
            "nombres.md en la raiz del repo con una lista numerada de 1000 "
            "nombres completos ('N. Nombre Apellido')."
        )
    names: list[tuple[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = _LIST_ITEM_RE.match(line.strip())
        if match is None:
            continue
        full_name = match.group(1).strip()
        # Convencion de la fuente: el primer token es el nombre de pila, el
        # resto (puede incluir mas de una palabra) es el apellido.
        nombre, _, apellidos = full_name.partition(" ")
        names.append((nombre, apellidos))
    return tuple(names)


NAME_POOL: tuple[tuple[str, str], ...] = _parse_nombres_md(_NOMBRES_MD_PATH)


def full_name(index: int) -> str:
    """Nombre completo ("Nombre Apellidos") del pool en la posicion `index`."""
    nombre, apellidos = NAME_POOL[index]
    return f"{nombre} {apellidos}"
