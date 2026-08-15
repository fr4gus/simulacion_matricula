"""Asignacion de cada estudiante admitido a sus grupos, sin conflictos de horario individual.

PRD.md, Proceso de Matricula, paso 9: si una solicitud valida no puede
asignarse sin conflicto con el resto del horario individual del estudiante,
se genera una alerta para revision humana; la corrida continua.
"""

from __future__ import annotations

from dataclasses import dataclass

from matricula.domain.models import Alert, GroupSchedule, MatriculaEntry
from matricula.domain.periods import Period
from matricula.orchestration.scheduling import blocks_conflict

REASON_INDIVIDUAL_CONFLICT = "Conflicto de horario con otra materia asignada al estudiante"


@dataclass
class AssignmentResult:
    matricula_by_carnet: dict[str, list[MatriculaEntry]]
    alerts: list[Alert]


def assign_students(
    period: Period,
    schedules: list[GroupSchedule],
    carnets_by_group: dict[tuple[str, str], list[str]],  # (course_code, group_number) -> carnets
    course_names: dict[str, str],
) -> AssignmentResult:
    """Asigna cada estudiante a los grupos donde quedo admitido, en orden de carne.

    Se procesa estudiante por estudiante para poder detectar conflictos en su
    horario individual acumulado; el orden de procesamiento entre estudiantes
    no afecta el resultado porque cada estudiante solo compite consigo mismo
    (los cupos de grupo ya fueron decididos en la fase de agrupamiento).
    """
    schedule_by_key = {(s.course_code, s.group_number): s for s in schedules}

    # Invertir carnets_by_group -> por estudiante, la lista de (course_code, group_number).
    groups_by_student: dict[str, list[tuple[str, str]]] = {}
    for (course_code, group_number), carnets in carnets_by_group.items():
        for carnet in carnets:
            groups_by_student.setdefault(carnet, []).append((course_code, group_number))

    matricula_by_carnet: dict[str, list[MatriculaEntry]] = {}
    alerts: list[Alert] = []

    for carnet in sorted(groups_by_student):
        student_blocks: list = []
        entries: list[MatriculaEntry] = []
        # Orden deterministico: por codigo de materia.
        for course_code, group_number in sorted(groups_by_student[carnet]):
            key = (course_code, group_number)
            schedule = schedule_by_key.get(key)
            if schedule is None:
                # El grupo no tiene horario (alerta ya generada en scheduling.py).
                alerts.append(
                    Alert(
                        carnet=carnet,
                        course_code=course_code,
                        reason="Grupo sin horario asignado",
                        status="Sin asignar",
                    )
                )
                continue
            if blocks_conflict(schedule.blocks, student_blocks):
                alerts.append(
                    Alert(
                        carnet=carnet,
                        course_code=course_code,
                        reason=REASON_INDIVIDUAL_CONFLICT,
                        status="Sin asignar",
                    )
                )
                continue
            student_blocks.extend(schedule.blocks)
            entries.append(
                MatriculaEntry(
                    period=period,
                    course_code=course_code,
                    group=group_number,
                    course_name=course_names.get(course_code, course_code),
                )
            )

        matricula_by_carnet[carnet] = entries

    return AssignmentResult(matricula_by_carnet=matricula_by_carnet, alerts=alerts)
