"""Simulacion de notas: 80% probabilidad de aprobar (PRD.md, Proceso de Matricula, paso 1)."""

from __future__ import annotations

import random

from matricula.config import PASS_GRADE, PASS_PROBABILITY


def simulate_grade(rng: random.Random, pass_probability: float = PASS_PROBABILITY) -> int:
    """Genera una nota (0-100) usando la `rng` dada.

    Si el intento "aprueba" (segun `pass_probability`), la nota se sortea en
    [PASS_GRADE, 100]; si reprueba, se sortea en [0, PASS_GRADE - 1].
    """
    if rng.random() < pass_probability:
        return rng.randint(PASS_GRADE, 100)
    return rng.randint(0, PASS_GRADE - 1)
