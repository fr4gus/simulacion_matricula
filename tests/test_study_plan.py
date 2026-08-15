from __future__ import annotations

import pytest

from matricula.domain.models import Course
from matricula.domain.study_plan import (
    COURSES,
    StudyPlanError,
    _validate_no_cycles,
    _validate_unique_codes,
    courses_for_cuatrimestre,
    prerequisites_met,
)


def test_real_plan_has_no_duplicate_codes():
    codes = [c.code for c in COURSES]
    assert len(codes) == len(set(codes))


def test_real_plan_has_no_cycles():
    # No debe lanzar.
    _validate_no_cycles(COURSES)


def test_duplicate_codes_are_rejected():
    courses = (
        Course(code="MA001", name="A", cuatrimestre=1),
        Course(code="MA001", name="B", cuatrimestre=1),
    )
    with pytest.raises(StudyPlanError):
        _validate_unique_codes(courses)


def test_prerequisite_cycle_is_rejected():
    courses = (
        Course(code="AA001", name="A", cuatrimestre=1, prerequisites=("BB001",)),
        Course(code="BB001", name="B", cuatrimestre=1, prerequisites=("AA001",)),
    )
    with pytest.raises(StudyPlanError):
        _validate_no_cycles(courses)


def test_courses_for_cuatrimestre():
    c1 = {c.code for c in courses_for_cuatrimestre(1)}
    assert c1 == {"MA001", "CS002", "ES001"}


def test_prerequisites_met():
    assert prerequisites_met("MA001", passed_courses=set())
    assert not prerequisites_met("CS003", passed_courses={"MA001"})
    assert prerequisites_met("CS003", passed_courses={"MA001", "CS002"})
