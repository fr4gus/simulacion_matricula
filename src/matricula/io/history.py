"""Descubrimiento del historial almacenado: ultimo periodo, todos los expedientes."""

from __future__ import annotations

from pathlib import Path

from matricula.domain.models import Student
from matricula.domain.periods import Period
from matricula.io.paths import graduated_dir, periodos_dir, students_dir
from matricula.io.student_md import read_student
from matricula.simulation.requests import next_pending_cuatrimestre


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


def migrate_graduated_students(base_dir: Path) -> int:
    """Mueve a `graduated/` los expedientes en `students/` que ya aprobaron
    todo el plan de estudios (ver `simulation.requests.next_pending_cuatrimestre`).

    Se llama al inicio de `run_period()`, antes de `load_all_students()`, para
    que un estudiante que se gradua en un periodo siga siendo procesado
    normalmente en ese run, pero deje de ocupar workers y de aparecer en el
    censo por cuatrimestre a partir del run siguiente. `graduated/` es puro
    historico: ningun run futuro vuelve a leerlo.

    Retorna cuantos expedientes se movieron.
    """
    source_dir = students_dir(base_dir)
    if not source_dir.exists():
        return 0
    target_dir = graduated_dir(base_dir)

    moved = 0
    for path in sorted(source_dir.glob("*.md")):
        student = read_student(path)
        if next_pending_cuatrimestre(student) is not None:
            continue
        target_dir.mkdir(parents=True, exist_ok=True)
        path.rename(target_dir / path.name)
        moved += 1
    return moved


def count_graduated_students(base_dir: Path) -> int:
    """Cuenta expedientes en `graduated/` sin leerlos ni meterlos al pipeline.

    Usado solo para reportar el acumulado historico de graduados en el censo
    (ver `orchestration.runner._emit_cuatrimestre_summary`).
    """
    directory = graduated_dir(base_dir)
    if not directory.exists():
        return 0
    return sum(1 for _ in directory.glob("*.md"))
