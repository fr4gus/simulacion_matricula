from __future__ import annotations

from matricula.domain.models import GradeRecord, Student
from matricula.domain.periods import Period
from matricula.simulation.requests import (
    build_request_course_codes,
    failed_course_codes,
    next_pending_cuatrimestre,
)


def _grade(period_str, code, name, grade):
    return GradeRecord(Period.parse(period_str), code, name, grade)


def test_new_student_requests_cuatrimestre_1():
    student = Student(carnet="260001", apellidos="A", nombre="A")
    assert next_pending_cuatrimestre(student) == 1
    codes = build_request_course_codes(student)
    assert set(codes) == {"MA001", "CS002", "ES001"}


def test_continuing_student_requests_next_pending_cuatrimestre_only():
    student = Student(
        carnet="260002",
        apellidos="B",
        nombre="B",
        grades=[
            _grade("2026-01", "MA001", "Matematicas I", 85),
            _grade("2026-01", "CS002", "Intro a Compu", 90),
            _grade("2026-01", "ES001", "Humanidades", 75),
        ],
    )
    assert next_pending_cuatrimestre(student) == 2
    codes = build_request_course_codes(student)
    assert set(codes) == {"CS003", "MA002", "ES010"}


def test_student_never_skips_ahead_even_if_prereqs_met():
    # Aprobo cuatrimestre 1 y 2 completos "de golpe" (caso hipotetico) pero
    # el sistema solo debe pedir cuatrimestre 3, nunca cuatrimestre 4.
    student = Student(
        carnet="260003",
        apellidos="C",
        nombre="C",
        grades=[
            _grade("2026-01", "MA001", "Matematicas I", 90),
            _grade("2026-01", "CS002", "Intro a Compu", 90),
            _grade("2026-01", "ES001", "Humanidades", 90),
            _grade("2026-02", "CS003", "Programacion I", 90),
            _grade("2026-02", "MA002", "Matematicas II", 90),
            _grade("2026-02", "ES010", "Ingles I", 90),
        ],
    )
    assert next_pending_cuatrimestre(student) == 3
    codes = build_request_course_codes(student)
    assert set(codes) == {"CS004", "MA003", "ES020"}


def test_failed_course_is_retaken_automatically():
    student = Student(
        carnet="260004",
        apellidos="D",
        nombre="D",
        grades=[
            _grade("2026-01", "MA001", "Matematicas I", 55),  # reprobo
            _grade("2026-01", "CS002", "Intro a Compu", 90),
            _grade("2026-01", "ES001", "Humanidades", 80),
        ],
    )
    assert failed_course_codes(student) == ["MA001"]
    codes = build_request_course_codes(student)
    # MA001 se repite; cuatrimestre 1 no esta completo (MA001 sigue pendiente)
    # asi que el "siguiente cuatrimestre pendiente" sigue siendo 1, y las
    # materias ya aprobadas de ese cuatrimestre no se vuelven a pedir.
    assert codes == ["MA001"]


def test_retake_does_not_block_unrelated_courses_of_next_cuatrimestre():
    # Repueba MA001 en el segundo periodo (retake), pero ya aprobo CS002 y
    # ES001 de cuatrimestre 1. ES010 (cuatrimestre 2, sin prerrequisitos) no
    # depende de MA001, pero como el estudiante SIGUE en cuatrimestre 1
    # (MA001 aun no aprobado), el "siguiente cuatrimestre pendiente" es 1,
    # no 2 - por diseno, no se solicita ES010 todavia.
    student = Student(
        carnet="260005",
        apellidos="E",
        nombre="E",
        grades=[
            _grade("2026-01", "MA001", "Matematicas I", 55),
            _grade("2026-01", "CS002", "Intro a Compu", 90),
            _grade("2026-01", "ES001", "Humanidades", 80),
            _grade("2026-02", "MA001", "Matematicas I", 40),  # reprueba retake tambien
        ],
    )
    assert next_pending_cuatrimestre(student) == 1
    codes = build_request_course_codes(student)
    assert codes == ["MA001"]


def test_student_who_finished_everything_requests_nothing():
    grades = []
    for number in range(1, 5):
        from matricula.domain.study_plan import courses_for_cuatrimestre

        for course in courses_for_cuatrimestre(number):
            grades.append(_grade("2026-01", course.code, course.name, 95))
    student = Student(carnet="260006", apellidos="F", nombre="F", grades=grades)
    assert next_pending_cuatrimestre(student) is None
    assert build_request_course_codes(student) == []
