"""Helpers de construccion/agregacion de alertas para el reporte final."""

from __future__ import annotations

from matricula.domain.models import Alert, Request, RequestStatus


def alerts_from_rejected_requests(requests: list[Request]) -> list[Alert]:
    return [
        Alert(carnet=r.carnet, course_code=r.course_code, reason=r.reason or "", status="Rechazada")
        for r in requests
        if r.status == RequestStatus.REJECTED
    ]


def alerts_from_closed_courses(closed_courses: dict[str, list[str]]) -> list[Alert]:
    from matricula.orchestration.demand import REASON_COURSE_CLOSED

    return [
        Alert(
            carnet=carnet, course_code=course_code, reason=REASON_COURSE_CLOSED, status="Rechazada"
        )
        for course_code, carnets in closed_courses.items()
        for carnet in carnets
    ]


# Alertas consideradas "sistemicas" (afectan el exit code) vs. "rutinarias"
# (rechazos esperados del negocio, no afectan el exit code). Ver
# reporting/summary.py para el uso de esta clasificacion.
SYSTEMIC_REASON_MARKERS = (
    "No fue posible asignar horario",
    "Conflicto de horario con otra materia",
    "Grupo sin horario asignado",
)


def is_systemic(alert: Alert) -> bool:
    return any(marker in alert.reason for marker in SYSTEMIC_REASON_MARKERS)
