"""Plan de estudios fijo (PRD.md, seccion "El Plan de Estudios").

Se valida al importar: codigos de materia unicos y ausencia de dependencias
circulares entre requisitos. Si el plan se edita y se rompe alguna de estas
invariantes, el import falla de inmediato (fail-fast) en vez de dejar que el
error aparezca mas adelante en la simulacion.
"""

from __future__ import annotations

from matricula.domain.models import Course

COURSES: tuple[Course, ...] = (
    # Cuatrimestre 1
    Course(code="MA001", name="Matematicas I", cuatrimestre=1, prerequisites=()),
    Course(code="CS002", name="Intro a Compu", cuatrimestre=1, prerequisites=()),
    Course(code="ES001", name="Humanidades", cuatrimestre=1, prerequisites=()),
    # Cuatrimestre 2
    Course(code="CS003", name="Programacion I", cuatrimestre=2, prerequisites=("MA001", "CS002")),
    Course(code="MA002", name="Matematicas II", cuatrimestre=2, prerequisites=("MA001",)),
    Course(code="ES010", name="Ingles I", cuatrimestre=2, prerequisites=()),
    # Cuatrimestre 3
    Course(code="CS004", name="Programacion II", cuatrimestre=3, prerequisites=("CS003",)),
    Course(code="MA003", name="Matematicas III", cuatrimestre=3, prerequisites=("MA002",)),
    Course(code="ES020", name="Ingles II", cuatrimestre=3, prerequisites=("ES010",)),
    # Cuatrimestre 4
    Course(code="CS005", name="Algoritmos", cuatrimestre=4, prerequisites=("CS004",)),
    Course(code="MA004", name="Matematicas IV", cuatrimestre=4, prerequisites=("MA003",)),
    Course(code="CS020", name="Redes", cuatrimestre=4, prerequisites=()),
)


class StudyPlanError(ValueError):
    """El plan de estudios viola una invariante (codigos duplicados o ciclo)."""


def _validate_unique_codes(courses: tuple[Course, ...]) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for course in courses:
        if course.code in seen:
            duplicates.add(course.code)
        seen.add(course.code)
    if duplicates:
        raise StudyPlanError(f"Codigos de materia duplicados en el plan: {sorted(duplicates)}")


def _validate_known_prerequisites(courses: tuple[Course, ...]) -> None:
    codes = {c.code for c in courses}
    for course in courses:
        unknown = [p for p in course.prerequisites if p not in codes]
        if unknown:
            raise StudyPlanError(
                f"{course.code} tiene prerrequisitos inexistentes en el plan: {unknown}"
            )


def _validate_no_cycles(courses: tuple[Course, ...]) -> None:
    by_code = {c.code: c for c in courses}
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {c.code: WHITE for c in courses}

    def visit(code: str, path: list[str]) -> None:
        color[code] = GRAY
        for prereq in by_code[code].prerequisites:
            if color[prereq] == GRAY:
                cycle = " -> ".join([*path, prereq])
                raise StudyPlanError(f"Dependencia circular de prerrequisitos detectada: {cycle}")
            if color[prereq] == WHITE:
                visit(prereq, [*path, prereq])
        color[code] = BLACK

    for course in courses:
        if color[course.code] == WHITE:
            visit(course.code, [course.code])


def _validate(courses: tuple[Course, ...]) -> None:
    _validate_unique_codes(courses)
    _validate_known_prerequisites(courses)
    _validate_no_cycles(courses)


_validate(COURSES)

COURSES_BY_CODE: dict[str, Course] = {c.code: c for c in COURSES}
CUATRIMESTRES: dict[int, tuple[Course, ...]] = {}
for _course in COURSES:
    CUATRIMESTRES.setdefault(_course.cuatrimestre, ())
    CUATRIMESTRES[_course.cuatrimestre] = (*CUATRIMESTRES[_course.cuatrimestre], _course)
del _course

MAX_CUATRIMESTRE = max(CUATRIMESTRES)


def courses_for_cuatrimestre(number: int) -> tuple[Course, ...]:
    return CUATRIMESTRES.get(number, ())


def prerequisites_met(course_code: str, passed_courses: set[str]) -> bool:
    course = COURSES_BY_CODE[course_code]
    return all(prereq in passed_courses for prereq in course.prerequisites)
