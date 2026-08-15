"""Validacion de solicitudes contra el plan de estudios y el expediente del estudiante.

PRD.md, Proceso de Matricula, paso 5: separar solicitudes validas de
rechazadas y crear una alerta por cada rechazo (carne, materia, motivo, estado).
"""

from __future__ import annotations

from matricula.domain.models import Request, RequestStatus, Student
from matricula.domain.study_plan import COURSES_BY_CODE, prerequisites_met

REASON_UNKNOWN_COURSE = "Materia inexistente en el plan de estudios"
REASON_PREREQUISITE_NOT_MET = "Prerrequisito no cumplido"
REASON_ALREADY_PASSED = "Materia ya aprobada"
REASON_DUPLICATE = "Solicitud duplicada"


def validate_requests(student: Student, course_codes: list[str]) -> list[Request]:
    """Valida la lista ordenada de codigos de materia solicitados por `student`.

    No depende de la demanda de otros estudiantes ni de cupos (eso ocurre en
    una fase posterior, `demand.py` / `grouping.py`); esta funcion solo
    verifica reglas propias del estudiante y del plan de estudios.
    """
    passed = student.passed_courses()
    results: list[Request] = []
    seen: set[str] = set()

    for code in course_codes:
        if code in seen:
            results.append(Request(student.carnet, code, RequestStatus.REJECTED, REASON_DUPLICATE))
            continue
        seen.add(code)

        course = COURSES_BY_CODE.get(code)
        if course is None:
            results.append(
                Request(student.carnet, code, RequestStatus.REJECTED, REASON_UNKNOWN_COURSE)
            )
            continue

        latest = student.latest_grade_for(code)
        is_retake = latest is not None and not latest.passed
        if code in passed and not is_retake:
            results.append(
                Request(student.carnet, code, RequestStatus.REJECTED, REASON_ALREADY_PASSED)
            )
            continue

        if not prerequisites_met(code, passed):
            results.append(
                Request(student.carnet, code, RequestStatus.REJECTED, REASON_PREREQUISITE_NOT_MET)
            )
            continue

        results.append(Request(student.carnet, code, RequestStatus.VALID))

    return results
