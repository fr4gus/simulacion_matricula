"""Resumen humano de la corrida + decision de exit code.

Exit codes (ver plan): 0 = limpio, 1 = alertas sistemicas, 2 = abortado antes
de correr (se decide en cli.py, no aqui).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field

from matricula.domain.models import Alert
from matricula.orchestration.alerts import is_systemic

EXIT_CLEAN = 0
EXIT_SYSTEMIC_ALERTS = 1
EXIT_ABORTED = 2


@dataclass
class RunSummary:
    period: str
    students_created: int = 0
    requests_valid: int = 0
    requests_rejected: int = 0
    courses_opened: int = 0
    courses_closed: int = 0
    groups_formed: int = 0
    alerts: list[Alert] = field(default_factory=list)

    @property
    def systemic_alerts(self) -> list[Alert]:
        return [a for a in self.alerts if is_systemic(a)]

    @property
    def exit_code(self) -> int:
        return EXIT_SYSTEMIC_ALERTS if self.systemic_alerts else EXIT_CLEAN


def print_summary(summary: RunSummary, out=None) -> None:
    out = out or sys.stdout
    lines = [
        f"Periodo {summary.period}: corrida completada",
        f"  Estudiantes nuevos creados: {summary.students_created}",
        f"  Solicitudes validas: {summary.requests_valid}",
        f"  Solicitudes rechazadas: {summary.requests_rejected}",
        f"  Materias abiertas: {summary.courses_opened}",
        f"  Materias cerradas (demanda insuficiente): {summary.courses_closed}",
        f"  Grupos formados: {summary.groups_formed}",
        f"  Alertas totales: {len(summary.alerts)} ({len(summary.systemic_alerts)} sistemicas)",
    ]
    if summary.alerts:
        lines.append("  Detalle de alertas:")
        for alert in summary.alerts:
            lines.append(
                f"    - [{alert.status}] carne={alert.carnet or '-'} "
                f"materia={alert.course_code} motivo={alert.reason}"
            )
    print("\n".join(lines), file=out)
