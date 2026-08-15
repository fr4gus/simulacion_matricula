"""Custom tools del Agent SDK: una por fase de negocio del PRD.

Cada tool es un wrapper delgado sobre una funcion ya existente de
`orchestration/*` -- no reimplementa ninguna regla del PRD, solo (a) valida
el orden de invocacion vía `gate.PhaseGate`, (b) llama la funcion pura
correspondiente sobre el `PipelineState` compartido, y (c) devuelve un resumen
legible para que el agente LLM decida su siguiente paso / narre resultado.

Los handlers son `async def` porque asi lo exige el decorador `@tool` del SDK,
pero todo el trabajo real es sincrono (la logica de negocio de
`orchestration/*` no es async) -- no hay E/S de red aqui salvo la que ya hace
`ProcessPoolExecutor` (bloqueante, se ejecuta tal cual).
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

from matricula.agent_harness.gate import PhaseGate, PhaseOutOfOrderError
from matricula.agent_harness.state import PipelineState
from matricula.domain.models import Alert, Request, RequestStatus
from matricula.domain.study_plan import COURSES_BY_CODE
from matricula.io.period_md import HorarioRow, PeriodRecord, RosterEntry, write_period
from matricula.io.student_md import write_student
from matricula.io.teacher_md import TeacherRegistry, write_teachers
from matricula.orchestration.alerts import alerts_from_closed_courses, alerts_from_rejected_requests
from matricula.orchestration.assignment import assign_students
from matricula.orchestration.demand import compute_demand
from matricula.orchestration.grouping import form_groups, rank_by_priority
from matricula.orchestration.runner import _emit_cuatrimestre_summary
from matricula.orchestration.scheduling import format_horario, schedule_groups
from matricula.orchestration.validation import validate_requests
from matricula.reporting.summary import RunSummary
from matricula.simulation.worker import WorkerResult, process_student


def _error(message: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": message}], "is_error": True}


def _ok(message: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": message}]}


def _emit_new_alerts(on_event: Callable[[dict], None], new_alerts: list[Alert]) -> None:
    """Emite el evento `alerts` con solo las alertas nuevas de una fase.

    Espejo de `orchestration.runner._emit_new_alerts`, duplicado aqui a
    proposito: el modulo del pipeline default no debe depender de
    `agent_harness` (que a su vez depende del extra opcional `agents`).
    """
    if not new_alerts:
        return
    on_event(
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


def _gate_or_error(gate: PhaseGate, phase: str) -> dict[str, Any] | None:
    """Verifica el orden de fase; retorna un resultado de error de tool si
    falla, o `None` si el llamador puede proceder (y el gate ya avanzo).
    """
    try:
        gate.check_and_advance(phase)
    except PhaseOutOfOrderError as exc:
        return _error(str(exc))
    return None


def build_tools(
    state: PipelineState,
    gate: PhaseGate,
    max_workers: int | None,
    on_event: Callable[[dict], None],
):
    """Construye las tools cerradas sobre `state`/`gate`/`on_event` de esta corrida.

    Cada corrida de `run_period_with_agent` tiene su propio `PipelineState` y
    `PhaseGate` (no hay estado global compartido entre corridas), asi que las
    tools se recrean por corrida en vez de ser funciones top-level fijas.
    """

    @tool(
        "simulate_grades",
        "Fase 1 del PRD: simula notas del periodo anterior para cada estudiante "
        "y construye su solicitud de cursos para el periodo objetivo. Debe ser "
        "la primera tool invocada. No recibe argumentos.",
        {},
    )
    async def simulate_grades_tool(_args: dict[str, Any]) -> dict[str, Any]:
        error = _gate_or_error(gate, "simulate_grades")
        if error is not None:
            return error

        all_students = state.all_students
        workers = max_workers
        on_event(
            {
                "type": "run_started",
                "period": str(state.period),
                "total_students": len(all_students),
            }
        )

        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(
                    process_student, student, state.period, state.prev_period, state.seed
                ): student.carnet
                for student in all_students
            }
            completed = 0
            for future in as_completed(futures):
                carnet = futures[future]
                try:
                    result = future.result()
                except Exception as exc:  # noqa: BLE001 - se convierte en alerta, no tumba el pool
                    result = WorkerResult(carnet=carnet, error=str(exc))
                state.worker_results[carnet] = result
                completed += 1
                on_event(
                    {"type": "pool_progress", "completed": completed, "total": len(all_students)}
                )

        pool_errors = sum(1 for r in state.worker_results.values() if r.error)
        on_event(
            {
                "type": "pool_completed",
                "completed": len(state.worker_results),
                "total": len(all_students),
                "errors": pool_errors,
            }
        )

        for carnet, result in state.worker_results.items():
            student = state.students_by_carnet[carnet]
            if result.error:
                state.alerts.append(
                    Alert(
                        carnet=carnet,
                        course_code="",
                        reason=f"Error interno: {result.error}",
                        status="Error",
                    )
                )
                state.all_requests_by_student[carnet] = []
                continue
            student.grades.extend(result.new_grades)
            state.all_requests_by_student[carnet] = result.requested_course_codes

        return _ok(
            f"Notas simuladas y solicitudes construidas para {len(all_students)} "
            f"estudiantes ({pool_errors} errores de worker)."
        )

    @tool(
        "validate_requests",
        "Fase 2 del PRD: valida cada solicitud contra el plan de estudios y el "
        "expediente del estudiante, separando validas de rechazadas. Requiere "
        "haber invocado simulate_grades antes. No recibe argumentos.",
        {},
    )
    async def validate_requests_tool(_args: dict[str, Any]) -> dict[str, Any]:
        error = _gate_or_error(gate, "validate_requests")
        if error is not None:
            return error

        validation_alerts: list[Alert] = []
        for carnet, codes in sorted(state.all_requests_by_student.items()):
            student = state.students_by_carnet[carnet]
            results = validate_requests(student, codes)
            validation_alerts.extend(alerts_from_rejected_requests(results))
            for r in results:
                if r.status.value == "valida":
                    state.valid_requests_by_course.setdefault(r.course_code, []).append(carnet)
                    state.requests_valid_count += 1
                else:
                    state.requests_rejected_count += 1
        state.alerts.extend(validation_alerts)

        on_event(
            {
                "type": "validation_done",
                "valid": state.requests_valid_count,
                "rejected": state.requests_rejected_count,
            }
        )
        _emit_new_alerts(on_event, validation_alerts)

        return _ok(
            f"Validacion completa: {state.requests_valid_count} validas, "
            f"{state.requests_rejected_count} rechazadas."
        )

    @tool(
        "compute_demand",
        "Fase 3 del PRD: agrega la demanda por materia y cierra las que tienen "
        "menos de 5 solicitudes validas. Requiere haber invocado validate_requests "
        "antes. No recibe argumentos.",
        {},
    )
    async def compute_demand_tool(_args: dict[str, Any]) -> dict[str, Any]:
        error = _gate_or_error(gate, "compute_demand")
        if error is not None:
            return error

        flat_valid_requests = [
            Request(carnet, code, RequestStatus.VALID)
            for code, carnets in state.valid_requests_by_course.items()
            for carnet in carnets
        ]
        state.demand = compute_demand(flat_valid_requests)
        closed_alerts = alerts_from_closed_courses(state.demand.closed_courses)
        state.alerts.extend(closed_alerts)

        on_event(
            {
                "type": "demand_done",
                "opened": len(state.demand.open_courses),
                "closed": len(state.demand.closed_courses),
            }
        )
        _emit_new_alerts(on_event, closed_alerts)

        return _ok(
            f"Demanda calculada: {len(state.demand.open_courses)} materias abiertas, "
            f"{len(state.demand.closed_courses)} cerradas."
        )

    @tool(
        "form_groups",
        "Fase 4 del PRD: forma grupos balanceados (max 10/grupo) para cada "
        "materia abierta, admitiendo por prioridad (promedio historico, luego "
        "carne). Requiere haber invocado compute_demand antes. No recibe argumentos.",
        {},
    )
    async def form_groups_tool(_args: dict[str, Any]) -> dict[str, Any]:
        error = _gate_or_error(gate, "form_groups")
        if error is not None:
            return error
        if state.demand is None:
            return _error("Estado inconsistente: compute_demand no dejo resultado disponible.")

        for course_code, carnets in sorted(state.demand.open_courses.items()):
            candidates = [state.students_by_carnet[c] for c in carnets]
            admitted = [s.carnet for s in rank_by_priority(candidates)]
            groups = form_groups(course_code, admitted)
            state.all_groups.extend(groups)
            for group in groups:
                state.carnets_by_group[(course_code, group.number)] = group.carnets

        on_event({"type": "grouping_done", "groups_formed": len(state.all_groups)})
        return _ok(f"{len(state.all_groups)} grupos formados.")

    @tool(
        "schedule_groups",
        "Fase 5 del PRD: asigna profesor, aula y bloque horario a cada grupo, "
        "sin choques. Genera alerta si un grupo no consigue horario. Requiere "
        "haber invocado form_groups antes. No recibe argumentos.",
        {},
    )
    async def schedule_groups_tool(_args: dict[str, Any]) -> dict[str, Any]:
        error = _gate_or_error(gate, "schedule_groups")
        if error is not None:
            return error

        schedules, schedule_alerts, new_teacher_records, name_cursor = schedule_groups(
            state.all_groups, teacher_start_index=state.name_cursor
        )
        state.schedules = schedules
        state.alerts.extend(schedule_alerts)
        state.new_teacher_records.extend(new_teacher_records)
        state.name_cursor = name_cursor

        on_event(
            {
                "type": "scheduling_done",
                "scheduled": len(schedules),
                "unschedulable": len(schedule_alerts),
            }
        )
        _emit_new_alerts(on_event, schedule_alerts)

        return _ok(
            f"{len(schedules)} grupos con horario asignado, "
            f"{len(schedule_alerts)} sin resolver."
        )

    @tool(
        "assign_students",
        "Fase 6 del PRD: asigna cada estudiante admitido a sus grupos, evitando "
        "conflictos de horario individual. Requiere haber invocado schedule_groups "
        "antes. No recibe argumentos.",
        {},
    )
    async def assign_students_tool(_args: dict[str, Any]) -> dict[str, Any]:
        error = _gate_or_error(gate, "assign_students")
        if error is not None:
            return error

        course_names = {code: c.name for code, c in COURSES_BY_CODE.items()}
        result = assign_students(
            state.period, state.schedules, state.carnets_by_group, course_names
        )
        state.assignment = result
        state.alerts.extend(result.alerts)
        assigned_ok = sum(len(entries) for entries in result.matricula_by_carnet.values())

        for carnet, entries in result.matricula_by_carnet.items():
            state.students_by_carnet[carnet].matricula.extend(entries)

        on_event(
            {
                "type": "assignment_done",
                "assigned_ok": assigned_ok,
                "conflicts": len(result.alerts),
            }
        )
        _emit_new_alerts(on_event, result.alerts)

        return _ok(f"{assigned_ok} matriculas confirmadas, {len(result.alerts)} conflictos.")

    @tool(
        "raise_alerts",
        "Consulta de solo lectura: lista las alertas acumuladas hasta ahora en "
        "la corrida (rechazos, cierres de materia, conflictos de horario) para "
        "que decidas como narrarlas o si ameritan detener la corrida. No avanza "
        "el pipeline y puede invocarse en cualquier momento. No recibe argumentos.",
        {},
    )
    async def raise_alerts_tool(_args: dict[str, Any]) -> dict[str, Any]:
        # Solo lectura: exenta del gate a proposito (ver docstring del modulo y
        # gate.py) -- inspeccionar alertas no es una fase del PRD en si misma.
        if not state.alerts:
            return _ok("No hay alertas registradas por ahora.")
        systemic = sum(1 for a in state.alerts if _is_systemic_hint(a))
        lines = [
            f"- [{a.status}] carne={a.carnet or '-'} materia={a.course_code} motivo={a.reason}"
            for a in state.alerts
        ]
        return _ok(
            f"{len(state.alerts)} alertas acumuladas ({systemic} potencialmente sistemicas):\n"
            + "\n".join(lines)
        )

    @tool(
        "persist_results",
        "Fase 7 (final) del PRD: construye el registro del periodo y persiste "
        "students/*.md y periodos_lectivos/YYYY-PP.md. Requiere haber invocado "
        "assign_students antes. Es la ultima tool del pipeline. No recibe argumentos.",
        {},
    )
    async def persist_results_tool(_args: dict[str, Any]) -> dict[str, Any]:
        error = _gate_or_error(gate, "persist_results")
        if error is not None:
            return error
        if state.assignment is None:
            return _error("Estado inconsistente: assign_students no dejo resultado disponible.")

        course_names = {code: c.name for code, c in COURSES_BY_CODE.items()}
        state.horario_rows = [
            HorarioRow(
                course_code=s.course_code,
                course_name=course_names.get(s.course_code, s.course_code),
                group=s.group_number,
                teacher=s.teacher,
                classroom=s.classroom,
                horario=format_horario(s.blocks),
            )
            for s in sorted(state.schedules, key=lambda s: (s.course_code, s.group_number))
        ]

        for (course_code, group_number), carnets in state.carnets_by_group.items():
            assigned_carnets = [
                c
                for c in carnets
                if any(
                    e.course_code == course_code and e.group == group_number
                    for e in state.assignment.matricula_by_carnet.get(c, [])
                )
            ]
            entries = [
                RosterEntry(
                    state.students_by_carnet[c].carnet,
                    state.students_by_carnet[c].apellidos,
                    state.students_by_carnet[c].nombre,
                )
                for c in assigned_carnets
            ]
            entries.sort(key=lambda e: (e.apellidos, e.nombre))
            state.rosters[f"{course_code}-{group_number}"] = entries

        state.period_record = PeriodRecord(
            period_str=str(state.period),
            horario=state.horario_rows,
            rosters=state.rosters,
            alertas=state.alerts,
        )

        for student in state.all_students:
            write_student(state.base_dir, student)
        write_period(state.base_dir, state.period_record)
        write_teachers(
            state.base_dir,
            TeacherRegistry(
                next_free_index=state.name_cursor,
                records=[*state.existing_teacher_records, *state.new_teacher_records],
            ),
        )
        state.persisted = True

        # Censo global por cuatrimestre, igual que orchestration.runner.run_period:
        # se emite despues de persistir para reflejar el estado recien escrito.
        _emit_cuatrimestre_summary(on_event, state.base_dir)

        state.summary = RunSummary(
            period=str(state.period),
            students_created=len(state.new_student_carnets),
            requests_valid=state.requests_valid_count,
            requests_rejected=state.requests_rejected_count,
            courses_opened=len(state.demand.open_courses) if state.demand else 0,
            courses_closed=len(state.demand.closed_courses) if state.demand else 0,
            groups_formed=len(state.all_groups),
            alerts=state.alerts,
        )

        on_event(
            {
                "type": "run_completed",
                "summary": {
                    "period": state.summary.period,
                    "students_created": state.summary.students_created,
                    "requests_valid": state.summary.requests_valid,
                    "requests_rejected": state.summary.requests_rejected,
                    "courses_opened": state.summary.courses_opened,
                    "courses_closed": state.summary.courses_closed,
                    "groups_formed": state.summary.groups_formed,
                    "total_alerts": len(state.summary.alerts),
                    "exit_code": state.summary.exit_code,
                },
            }
        )

        return _ok(
            f"Periodo {state.period} persistido: {len(state.all_students)} estudiantes, "
            f"{len(state.horario_rows)} grupos con horario, {len(state.alerts)} alertas totales."
        )

    tool_fns = [
        simulate_grades_tool,
        validate_requests_tool,
        compute_demand_tool,
        form_groups_tool,
        schedule_groups_tool,
        assign_students_tool,
        raise_alerts_tool,
        persist_results_tool,
    ]
    server = create_sdk_mcp_server(name="matricula", version="1.0.0", tools=tool_fns)
    allowed_tools = [f"mcp__matricula__{fn.name}" for fn in tool_fns]
    return server, allowed_tools


def _is_systemic_hint(alert: Alert) -> bool:
    # Import perezoso para evitar ciclo con orchestration.alerts en el modulo
    # top-level; misma logica que reporting.summary usa para exit_code.
    from matricula.orchestration.alerts import is_systemic

    return is_systemic(alert)
