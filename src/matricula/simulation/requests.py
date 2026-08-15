"""Construccion de la lista de solicitudes de un estudiante para un periodo dado.

Reglas (PRD.md + seccion "Aclaraciones"):
- Estudiante nuevo: solicita las materias de cuatrimestre 1.
- Estudiante continuante: solicita las materias de su siguiente cuatrimestre
  pendiente (nunca se adelanta), mas la repeticion automatica de cualquier
  materia reprobada (nota mas reciente < PASS_GRADE), sin limite de repeticiones.
- Una materia aprobada (>= PASS_GRADE en su intento mas reciente) no se vuelve
  a solicitar salvo que sea, en el futuro, prerrequisito de otra (eso ya lo
  refleja `passed_courses()`).
"""

from __future__ import annotations

from matricula.config import PASS_GRADE
from matricula.domain.models import Student
from matricula.domain.study_plan import (
    MAX_CUATRIMESTRE,
    courses_for_cuatrimestre,
)


def next_pending_cuatrimestre(student: Student) -> int | None:
    """El primer cuatrimestre (1..MAX) que el estudiante no ha aprobado por completo.

    Retorna None si ya aprobo todas las materias del plan.
    """
    passed = student.passed_courses()
    for number in range(1, MAX_CUATRIMESTRE + 1):
        courses = courses_for_cuatrimestre(number)
        if not all(c.code in passed for c in courses):
            return number
    return None


def failed_course_codes(student: Student) -> list[str]:
    """Codigos de materia cuyo intento mas reciente reprobo (nota < PASS_GRADE)."""
    latest_by_course: dict[str, int] = {}
    order: list[str] = []
    for record in student.grades:
        if record.course_code not in latest_by_course:
            order.append(record.course_code)
        # Los registros se asumen en orden cronologico de insercion; el ultimo
        # valor para un codigo es el intento mas reciente.
        latest_by_course[record.course_code] = record.grade
    return [code for code in order if latest_by_course[code] < PASS_GRADE]


def build_request_course_codes(student: Student) -> list[str]:
    """Codigos de materia que el estudiante solicita este periodo, en orden.

    Retakes primero, luego las materias nuevas del siguiente cuatrimestre
    pendiente (que aun no haya aprobado).
    """
    passed = student.passed_courses()
    retakes = [code for code in failed_course_codes(student) if code not in passed]

    cuatrimestre = next_pending_cuatrimestre(student)
    new_courses: list[str] = []
    if cuatrimestre is not None:
        new_courses = [
            c.code for c in courses_for_cuatrimestre(cuatrimestre) if c.code not in passed
        ]

    # Evitar duplicados si una materia aparece en ambas listas (no deberia,
    # pero se preserva el orden: retakes primero).
    seen: set[str] = set()
    ordered: list[str] = []
    for code in [*retakes, *new_courses]:
        if code not in seen:
            seen.add(code)
            ordered.append(code)
    return ordered
