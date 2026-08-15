from __future__ import annotations

from matricula.domain.models import MatriculaEntry, Student
from matricula.domain.periods import Period
from matricula.simulation.worker import process_student


def test_new_student_no_grades_simulated_and_requests_cuatrimestre_1():
    student = Student(carnet="260001", apellidos="A", nombre="A")
    result = process_student(
        student,
        target_period=Period.parse("2026-01"),
        previous_period=None,
        run_seed=0,
    )
    assert result.error is None
    assert result.new_grades == []
    assert set(result.requested_course_codes) == {"MA001", "CS002", "ES001"}


def test_continuing_student_grades_simulated_for_pending_matricula():
    student = Student(
        carnet="260002",
        apellidos="B",
        nombre="B",
        matricula=[
            MatriculaEntry(Period.parse("2026-01"), "MA001", "01", "Matematicas I"),
            MatriculaEntry(Period.parse("2026-01"), "CS002", "01", "Intro a Compu"),
            MatriculaEntry(Period.parse("2026-01"), "ES001", "01", "Humanidades"),
        ],
    )
    result = process_student(
        student,
        target_period=Period.parse("2026-02"),
        previous_period=Period.parse("2026-01"),
        run_seed=0,
    )
    assert result.error is None
    assert len(result.new_grades) == 3
    assert {g.course_code for g in result.new_grades} == {"MA001", "CS002", "ES001"}
    # La solicitud del nuevo periodo depende de si aprobo o no cada materia.
    passed = {g.course_code for g in result.new_grades if g.passed}
    if len(passed) == 3:
        assert set(result.requested_course_codes) == {"CS003", "MA002", "ES010"}


def test_already_graded_matricula_is_not_resimulated():
    from matricula.domain.models import GradeRecord

    student = Student(
        carnet="260003",
        apellidos="C",
        nombre="C",
        matricula=[MatriculaEntry(Period.parse("2026-01"), "MA001", "01", "Matematicas I")],
        grades=[GradeRecord(Period.parse("2026-01"), "MA001", "Matematicas I", 85)],
    )
    result = process_student(
        student,
        target_period=Period.parse("2026-02"),
        previous_period=Period.parse("2026-01"),
        run_seed=0,
    )
    assert result.new_grades == []


def test_deterministic_across_calls_with_same_seed():
    student = Student(
        carnet="260004",
        apellidos="D",
        nombre="D",
        matricula=[
            MatriculaEntry(Period.parse("2026-01"), "MA001", "01", "Matematicas I"),
        ],
    )
    r1 = process_student(student, Period.parse("2026-02"), Period.parse("2026-01"), run_seed=99)
    r2 = process_student(student, Period.parse("2026-02"), Period.parse("2026-01"), run_seed=99)
    assert [g.grade for g in r1.new_grades] == [g.grade for g in r2.new_grades]


def test_different_seed_can_change_outcome_but_not_required_to():
    # No afirmamos que SIEMPRE cambie (podria coincidir), solo que la funcion
    # acepta una semilla distinta sin fallar.
    student = Student(
        carnet="260005",
        apellidos="E",
        nombre="E",
        matricula=[MatriculaEntry(Period.parse("2026-01"), "MA001", "01", "Matematicas I")],
    )
    result = process_student(student, Period.parse("2026-02"), Period.parse("2026-01"), run_seed=1)
    assert result.error is None
