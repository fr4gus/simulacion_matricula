from __future__ import annotations

from matricula.domain.names import NAME_POOL, full_name
from matricula.simulation.naming import POOL_SIZE, allocate_names


def test_name_pool_has_1000_entries():
    assert len(NAME_POOL) == 1000
    assert POOL_SIZE == 1000


def test_name_pool_entries_are_nombre_apellidos_pairs():
    for nombre, apellidos in NAME_POOL:
        assert nombre
        assert apellidos


def test_full_name_matches_pool_entry():
    nombre, apellidos = NAME_POOL[0]
    assert full_name(0) == f"{nombre} {apellidos}"


def test_allocate_names_returns_consecutive_pool_entries():
    allocation = allocate_names(0, 3)
    assert allocation.names == [NAME_POOL[0], NAME_POOL[1], NAME_POOL[2]]
    assert allocation.next_free_index == 3


def test_allocate_names_continues_from_arbitrary_start_index():
    allocation = allocate_names(997, 2)
    assert allocation.names == [NAME_POOL[997], NAME_POOL[998]]
    assert allocation.next_free_index == 999


def test_allocate_names_wraps_around_when_pool_exhausted():
    allocation = allocate_names(999, 2)
    assert allocation.names == [NAME_POOL[999], NAME_POOL[0]]
    assert allocation.next_free_index == 1


def test_allocate_names_never_repeats_within_a_run():
    allocation = allocate_names(0, 50)
    # Los indices consumidos son todos distintos (aunque, por la fuente, dos
    # nombres completos puedan coincidir por casualidad -- ver domain/names.py).
    assert len(allocation.names) == 50
