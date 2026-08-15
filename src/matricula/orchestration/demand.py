"""Agregacion de demanda por materia y regla de apertura/cierre.

PRD.md, Proceso de Matricula, paso 6: una materia abre solo con al menos
MIN_VALID_REQUESTS_TO_OPEN solicitudes validas; si no llega, se cierra y esas
solicitudes quedan rechazadas para el siguiente periodo.
"""

from __future__ import annotations

from dataclasses import dataclass

from matricula.config import MIN_VALID_REQUESTS_TO_OPEN
from matricula.domain.models import Request, RequestStatus

REASON_COURSE_CLOSED = "Materia cerrada: menos de 5 solicitudes validas"


@dataclass
class DemandResult:
    open_courses: dict[str, list[str]]  # course_code -> [carnet, ...] (solicitudes validas)
    closed_courses: dict[str, list[str]]  # course_code -> [carnet, ...] (rechazadas por cierre)


def compute_demand(valid_requests: list[Request]) -> DemandResult:
    by_course: dict[str, list[str]] = {}
    for request in valid_requests:
        if request.status != RequestStatus.VALID:
            continue
        by_course.setdefault(request.course_code, []).append(request.carnet)

    open_courses: dict[str, list[str]] = {}
    closed_courses: dict[str, list[str]] = {}
    for course_code, carnets in by_course.items():
        if len(carnets) >= MIN_VALID_REQUESTS_TO_OPEN:
            open_courses[course_code] = carnets
        else:
            closed_courses[course_code] = carnets

    return DemandResult(open_courses=open_courses, closed_courses=closed_courses)
