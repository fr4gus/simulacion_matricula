"""Descubrimiento del historial almacenado: ultimo periodo, todos los expedientes."""

from __future__ import annotations

from pathlib import Path

from matricula.domain.models import Student
from matricula.domain.periods import Period
from matricula.io.paths import periodos_dir, students_dir
from matricula.io.student_md import read_student


def stored_periods(base_dir: Path) -> list[Period]:
    directory = periodos_dir(base_dir)
    if not directory.exists():
        return []
    periods = []
    for path in directory.glob("*.md"):
        try:
            periods.append(Period.parse(path.stem))
        except ValueError:
            continue
    return sorted(periods)


def latest_period(base_dir: Path) -> Period | None:
    periods = stored_periods(base_dir)
    return periods[-1] if periods else None


def load_all_students(base_dir: Path) -> list[Student]:
    directory = students_dir(base_dir)
    if not directory.exists():
        return []
    students = []
    for path in sorted(directory.glob("*.md")):
        students.append(read_student(path))
    return students
