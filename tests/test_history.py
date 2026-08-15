from __future__ import annotations

from pathlib import Path

from matricula.domain.models import GradeRecord, Student
from matricula.domain.periods import Period
from matricula.domain.study_plan import COURSES
from matricula.io.history import count_graduated_students, load_all_students, migrate_graduated_students
from matricula.io.paths import graduated_dir, students_dir
from matricula.io.student_md import write_student


def _write(base_dir: Path, student: Student) -> None:
    write_student(base_dir, student)


def _graduated_student(carnet: str) -> Student:
    period = Period.parse("2026-01")
    grades = [
        GradeRecord(period=period, course_code=c.code, course_name=c.name, grade=90)
        for c in COURSES
    ]
    return Student(carnet=carnet, apellidos="Perez", nombre="Ana", grades=grades)


def _active_student(carnet: str) -> Student:
    period = Period.parse("2026-01")
    return Student(
        carnet=carnet,
        apellidos="Gomez",
        nombre="Luis",
        grades=[GradeRecord(period=period, course_code="MA001", course_name="Matematicas I", grade=90)],
    )


def test_migrate_moves_only_students_who_finished_the_whole_plan(base_dir: Path):
    _write(base_dir, _graduated_student("260001"))
    _write(base_dir, _active_student("260002"))

    moved = migrate_graduated_students(base_dir)

    assert moved == 1
    assert not (students_dir(base_dir) / "260001.md").exists()
    assert (students_dir(base_dir) / "260002.md").exists()
    assert (graduated_dir(base_dir) / "260001.md").exists()


def test_migrated_students_are_invisible_to_load_all_students_and_are_not_re_migrated(base_dir: Path):
    _write(base_dir, _graduated_student("260001"))
    _write(base_dir, _active_student("260002"))

    migrate_graduated_students(base_dir)

    students = load_all_students(base_dir)
    assert [s.carnet for s in students] == ["260002"]

    # Correr de nuevo no vuelve a mover nada (ya no esta en students/).
    moved_again = migrate_graduated_students(base_dir)
    assert moved_again == 0
    assert count_graduated_students(base_dir) == 1


def test_count_graduated_students_does_not_require_students_dir(base_dir: Path):
    assert count_graduated_students(base_dir) == 0

    _write(base_dir, _graduated_student("260001"))
    migrate_graduated_students(base_dir)
    assert count_graduated_students(base_dir) == 1


def test_migrate_is_a_noop_when_students_dir_is_missing(base_dir: Path):
    assert migrate_graduated_students(base_dir) == 0
