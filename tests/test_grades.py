from __future__ import annotations

import random

from matricula.config import PASS_GRADE
from matricula.simulation.grades import simulate_grade


def test_simulate_grade_is_deterministic_for_fixed_seed():
    rng1 = random.Random(42)
    rng2 = random.Random(42)
    grades1 = [simulate_grade(rng1) for _ in range(50)]
    grades2 = [simulate_grade(rng2) for _ in range(50)]
    assert grades1 == grades2


def test_simulate_grade_respects_pass_boundary():
    rng = random.Random(0)
    for _ in range(500):
        grade = simulate_grade(rng)
        assert 0 <= grade <= 100


def test_simulate_grade_pass_probability_close_to_80_percent():
    rng = random.Random(7)
    grades = [simulate_grade(rng) for _ in range(5000)]
    pass_rate = sum(1 for g in grades if g >= PASS_GRADE) / len(grades)
    assert 0.75 <= pass_rate <= 0.85


def test_simulate_grade_forced_fail_and_pass_via_probability():
    rng = random.Random(1)
    always_fail = simulate_grade(rng, pass_probability=0.0)
    assert always_fail < PASS_GRADE
    always_pass = simulate_grade(rng, pass_probability=1.0)
    assert always_pass >= PASS_GRADE
