"""Reparto determinista de nombres del pool compartido (`domain.names.NAME_POOL`)
entre estudiantes nuevos y profesores nuevos.

El pool tiene 1000 entradas; `next_free_index` (persistido en `profesores.md`,
ver `io/teacher_md.py`) es el cursor global: cada nombre repartido, sin
importar si termina en un estudiante o en un profesor, consume el siguiente
indice en orden 0, 1, 2, ... Esto es lo que garantiza "no repetir nombres"
entre estudiantes y profesores a traves de corridas -- ambos roles comparten
el mismo cursor, nunca cursores separados.

Si el pool se agota (mas de 1000 nombres repartidos en la vida de la
simulacion), se reinicia por el principio (modulo 1000) en vez de fallar: en
una simulacion de 50+ estudiantes mas profesores nuevos por materia/grupo, es
plausible acercarse al limite, y preferimos reciclar nombres antes que
abortar una corrida por quedarnos sin pool.
"""

from __future__ import annotations

from dataclasses import dataclass

from matricula.domain.names import NAME_POOL

POOL_SIZE = len(NAME_POOL)


@dataclass(frozen=True)
class NameAllocation:
    """Resultado de repartir `count` nombres a partir de `next_free_index`."""

    names: list[tuple[str, str]]  # [(nombre, apellidos), ...], en orden de reparto
    next_free_index: int  # cursor actualizado, a persistir para la proxima corrida


def allocate_names(start_index: int, count: int) -> NameAllocation:
    """Reparte `count` nombres del pool a partir de `start_index`, en orden fijo.

    Recicla el pool (modulo `POOL_SIZE`) si `start_index + count` lo excede,
    en vez de fallar -- ver docstring del modulo.
    """
    names = [NAME_POOL[(start_index + i) % POOL_SIZE] for i in range(count)]
    return NameAllocation(names=names, next_free_index=(start_index + count) % POOL_SIZE)
