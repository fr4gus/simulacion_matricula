"""Orquestador central: corre el pipeline de 11 pasos del PRD para un periodo dado.

Ver PRD.md, "Proceso de Matricula", y CLAUDE.md para el mapeo detallado.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

from matricula.config import NEW_STUDENTS_PER_PERIOD
from matricula.domain.models import Alert, Request, RequestStatus, Student
from matricula.domain.periods import Period
from matricula.domain.study_plan import COURSES_BY_CODE, MAX_CUATRIMESTRE
from matricula.io.history import latest_period, load_all_students
from matricula.io.period_md import HorarioRow, PeriodRecord, RosterEntry, write_period
from matricula.io.student_md import write_student
from matricula.orchestration.alerts import alerts_from_closed_courses, alerts_from_rejected_requests
from matricula.orchestration.assignment import assign_students
from matricula.orchestration.demand import compute_demand
from matricula.orchestration.grouping import form_groups, rank_by_priority
from matricula.orchestration.scheduling import format_horario, schedule_groups
from matricula.orchestration.validation import validate_requests
from matricula.reporting.summary import RunSummary
from matricula.simulation.requests import next_pending_cuatrimestre
from matricula.simulation.worker import WorkerResult, process_student


@dataclass
class RunResult:
    summary: RunSummary
    period_record: PeriodRecord
    students: list[Student] = field(default_factory=list)


def _new_carnets(base_dir: Path, period: Period, count: int) -> list[str]:
    prefix = f"{period.year % 100:02d}"
    existing = load_all_students(base_dir)
    existing_seq = [int(s.carnet[2:]) for s in existing if s.carnet.startswith(prefix)]
    start = (max(existing_seq) + 1) if existing_seq else 1
    return [f"{prefix}{start + i:04d}" for i in range(count)]


def _default_worker_count() -> int:
    return os.cpu_count() or 1


def _emit_cuatrimestre_summary(emit: Callable[[dict], None], base_dir: Path) -> None:
    """Emite un censo global (todos los estudiantes en disco) por cuatrimestre pendiente.

    Se llama despues de escribir los archivos de este periodo, para que el
    censo refleje el estado recien actualizado. A diferencia del resto de
    eventos, no describe esta corrida sino el estado acumulado de toda la
    carrera hasta ahora.
    """
    census_students = load_all_students(base_dir)
    cuatrimestre_counts = {n: 0 for n in range(1, MAX_CUATRIMESTRE + 1)}
    graduados = 0
    for student in census_students:
        cuatrimestre = next_pending_cuatrimestre(student)
        if cuatrimestre is None:
            graduados += 1
        else:
            cuatrimestre_counts[cuatrimestre] += 1

    emit(
        {
            "type": "cuatrimestre_summary",
            "cuatrimestre_counts": {
                f"cuatrimestre_{n}": count for n, count in cuatrimestre_counts.items()
            },
            "graduados": graduados,
            "total_students": len(census_students),
        }
    )


def _emit_new_alerts(emit: Callable[[dict], None], new_alerts: list[Alert]) -> None:
    """Emite el evento `alerts` con solo las alertas nuevas de una fase (no acumuladas)."""
    if not new_alerts:
        return
    emit(
        {
            "type": "alerts",
            "alerts": [
                {
                    "carnet": a.carnet,
                    "course_code": a.course_code,
                    "reason": a.reason,
                    "status": a.status,
                }
                for a in new_alerts
            ],
        }
    )


def run_period(
    base_dir: Path,
    period: Period,
    seed: int = 0,
    max_workers: int | None = None,
    on_event: Callable[[dict], None] | None = None,
) -> RunResult:
    """Corre el pipeline de 11 pasos del PRD para `period`.

    `on_event`, si se pasa, recibe un dict por cada punto de progreso del
    pipeline (ver src/matricula/viz/ para el consumidor de estos eventos).
    Es puramente observacional: no afecta el resultado ni el orden de
    ejecucion, y por defecto es un no-op, asi que los llamadores existentes
    (tests, CLI sin --visualize) no cambian de comportamiento.
    """
    emit: Callable[[dict], None] = on_event or (lambda event: None)

    prev_period = latest_period(base_dir)

    students = load_all_students(base_dir)
    students_by_carnet = {s.carnet: s for s in students}

    # --- Paso 3: crear estudiantes nuevos de este periodo ---
    new_carnets = _new_carnets(base_dir, period, NEW_STUDENTS_PER_PERIOD)
    new_students = [
        Student(carnet=carnet, apellidos=f"Apellido{carnet}", nombre=f"Nombre{carnet}")
        for carnet in new_carnets
    ]
    for s in new_students:
        students_by_carnet[s.carnet] = s

    # --- Pasos 1-4: despachar al pool (notas del periodo anterior + solicitud nueva) ---
    all_students = list(students_by_carnet.values())
    emit({"type": "run_started", "period": str(period), "total_students": len(all_students)})

    worker_results: dict[str, WorkerResult] = {}
    workers = max_workers if max_workers is not None else _default_worker_count()

    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(process_student, student, period, prev_period, seed): student.carnet
            for student in all_students
        }
        completed = 0
        for future in as_completed(futures):
            carnet = futures[future]
            try:
                result = future.result()
            except Exception as exc:  # noqa: BLE001 - se convierte en alerta, no tumba la corrida
                result = WorkerResult(carnet=carnet, error=str(exc))
            worker_results[carnet] = result
            completed += 1
            emit({"type": "pool_progress", "completed": completed, "total": len(all_students)})

    pool_errors = sum(1 for r in worker_results.values() if r.error)
    emit(
        {
            "type": "pool_completed",
            "completed": len(worker_results),
            "total": len(all_students),
            "errors": pool_errors,
        }
    )

    alerts: list[Alert] = []
    all_requests_by_student: dict[str, list[str]] = {}

    for carnet, result in worker_results.items():
        student = students_by_carnet[carnet]
        if result.error:
            alerts.append(
                Alert(
                    carnet=carnet,
                    course_code="",
                    reason=f"Error interno: {result.error}",
                    status="Error",
                )
            )
            all_requests_by_student[carnet] = []
            continue
        student.grades.extend(result.new_grades)
        all_requests_by_student[carnet] = result.requested_course_codes

    # --- Paso 5: validar cada solicitud ---
    valid_requests_by_course: dict[str, list[str]] = {}
    requests_valid_count = 0
    requests_rejected_count = 0
    validation_alerts: list[Alert] = []
    for carnet, codes in sorted(all_requests_by_student.items()):
        student = students_by_carnet[carnet]
        results = validate_requests(student, codes)
        validation_alerts.extend(alerts_from_rejected_requests(results))
        for r in results:
            if r.status.value == "valida":
                valid_requests_by_course.setdefault(r.course_code, []).append(carnet)
                requests_valid_count += 1
            else:
                requests_rejected_count += 1
    alerts.extend(validation_alerts)
    emit(
        {
            "type": "validation_done",
            "valid": requests_valid_count,
            "rejected": requests_rejected_count,
        }
    )
    _emit_new_alerts(emit, validation_alerts)

    # --- Paso 6: demanda y apertura/cierre ---
    flat_valid_requests = [
        Request(carnet, code, RequestStatus.VALID)
        for code, carnets in valid_requests_by_course.items()
        for carnet in carnets
    ]
    demand = compute_demand(flat_valid_requests)
    closed_alerts = alerts_from_closed_courses(demand.closed_courses)
    alerts.extend(closed_alerts)
    emit(
        {
            "type": "demand_done",
            "opened": len(demand.open_courses),
            "closed": len(demand.closed_courses),
        }
    )
    _emit_new_alerts(emit, closed_alerts)

    # --- Paso 7: formacion de grupos (admision por prioridad, reparto balanceado) ---
    carnets_by_group: dict[tuple[str, str], list[str]] = {}
    all_groups = []
    for course_code, carnets in sorted(demand.open_courses.items()):
        candidates = [students_by_carnet[c] for c in carnets]
        admitted = [s.carnet for s in rank_by_priority(candidates)]
        groups = form_groups(course_code, admitted)
        all_groups.extend(groups)
        for group in groups:
            carnets_by_group[(course_code, group.number)] = group.carnets
    emit({"type": "grouping_done", "groups_formed": len(all_groups)})

    # --- Paso 8: horario ---
    schedules, schedule_alerts = schedule_groups(all_groups)
    alerts.extend(schedule_alerts)
    emit(
        {
            "type": "scheduling_done",
            "scheduled": len(schedules),
            "unschedulable": len(schedule_alerts),
        }
    )
    _emit_new_alerts(emit, schedule_alerts)

    # --- Paso 9: asignacion individual ---
    course_names = {code: c.name for code, c in COURSES_BY_CODE.items()}
    assignment = assign_students(period, schedules, carnets_by_group, course_names)
    alerts.extend(assignment.alerts)
    assigned_ok = sum(len(entries) for entries in assignment.matricula_by_carnet.values())
    emit(
        {
            "type": "assignment_done",
            "assigned_ok": assigned_ok,
            "conflicts": len(assignment.alerts),
        }
    )
    _emit_new_alerts(emit, assignment.alerts)

    for carnet, entries in assignment.matricula_by_carnet.items():
        students_by_carnet[carnet].matricula.extend(entries)

    # --- Paso 11: construir y persistir salidas ---
    horario_rows = [
        HorarioRow(
            course_code=s.course_code,
            course_name=course_names.get(s.course_code, s.course_code),
            group=s.group_number,
            teacher=s.teacher,
            classroom=s.classroom,
            horario=format_horario(s.blocks),
        )
        for s in sorted(schedules, key=lambda s: (s.course_code, s.group_number))
    ]

    rosters: dict[str, list[RosterEntry]] = {}
    for (course_code, group_number), carnets in carnets_by_group.items():
        assigned_carnets = [
            c
            for c in carnets
            if any(
                e.course_code == course_code and e.group == group_number
                for e in assignment.matricula_by_carnet.get(c, [])
            )
        ]
        entries = [
            RosterEntry(
                students_by_carnet[c].carnet,
                students_by_carnet[c].apellidos,
                students_by_carnet[c].nombre,
            )
            for c in assigned_carnets
        ]
        entries.sort(key=lambda e: (e.apellidos, e.nombre))
        rosters[f"{course_code}-{group_number}"] = entries

    period_record = PeriodRecord(
        period_str=str(period),
        horario=horario_rows,
        rosters=rosters,
        alertas=alerts,
    )

    for student in all_students:
        write_student(base_dir, student)
    write_period(base_dir, period_record)

    summary = RunSummary(
        period=str(period),
        students_created=len(new_students),
        requests_valid=requests_valid_count,
        requests_rejected=requests_rejected_count,
        courses_opened=len(demand.open_courses),
        courses_closed=len(demand.closed_courses),
        groups_formed=len(all_groups),
        alerts=alerts,
    )

    emit(
        {
            "type": "run_completed",
            "summary": {
                "period": summary.period,
                "students_created": summary.students_created,
                "requests_valid": summary.requests_valid,
                "requests_rejected": summary.requests_rejected,
                "courses_opened": summary.courses_opened,
                "courses_closed": summary.courses_closed,
                "groups_formed": summary.groups_formed,
                "total_alerts": len(summary.alerts),
                "exit_code": summary.exit_code,
            },
        }
    )

    _emit_cuatrimestre_summary(emit, base_dir)

    return RunResult(summary=summary, period_record=period_record, students=all_students)
