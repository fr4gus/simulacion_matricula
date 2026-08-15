"""Punto de entrada del modo `--agents`: corre un agente orquestador real del
Claude Agent SDK sobre el mismo pipeline determinista de `orchestration/`.

`run_period_with_agent` tiene una firma paralela a
`orchestration.runner.run_period` para que `cli.py` pueda elegir entre ambas
con un simple `if args.agents`. La diferencia de fondo: aqui quien decide
*cuando* invocar cada fase es un `ClaudeSDKClient` real (ver `tools.py` para
las 8 tools expuestas), no una secuencia fija de llamadas Python. El orden
correcto del PRD sigue garantizado por `gate.PhaseGate` -- el LLM puede narrar,
reintentar o fallar, pero no puede desviar la corrida del pipeline de 11 pasos.

Si el agente termina su turno sin haber invocado `persist_results` (se cuelga,
se rinde, agota su presupuesto de turnos), este modulo fuerza la persistencia
igual con lo que el `PipelineState` tenga acumulado y agrega un `Alert` de
tipo "Error" documentando la corrida incompleta -- la corrida nunca se cuelga
ni deja el directorio de datos a medio escribir sin alerta.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from pathlib import Path

from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ClaudeSDKClient, TextBlock

from matricula.agent_harness.gate import PhaseGate
from matricula.agent_harness.state import PipelineState
from matricula.agent_harness.tools import build_tools
from matricula.config import NEW_STUDENTS_PER_PERIOD
from matricula.domain.models import Alert, Student
from matricula.domain.periods import Period
from matricula.io.history import latest_period, load_all_students, migrate_graduated_students
from matricula.io.paths import profesores_file
from matricula.io.period_md import PeriodRecord, write_period
from matricula.io.student_md import write_student
from matricula.io.teacher_md import TeacherRegistry, read_teachers, write_teachers
from matricula.orchestration.runner import RunResult, _emit_cuatrimestre_summary, new_carnets
from matricula.reporting.summary import RunSummary
from matricula.simulation.naming import allocate_names

DEFAULT_MODEL = "claude-sonnet-5"
DEFAULT_MODEL_ENV_VAR = "MATRICULA_AGENT_MODEL"

SYSTEM_PROMPT = """\
Eres el orquestador del proceso de matricula universitaria. Tu unico trabajo \
es invocar, EN ESTE ORDEN EXACTO, las siguientes tools -- una vez cada una, \
sin argumentos:

1. simulate_grades
2. validate_requests
3. compute_demand
4. form_groups
5. schedule_groups
6. assign_students
7. persist_results

Puedes invocar `raise_alerts` en cualquier momento (no cuenta como parte de \
la secuencia) para revisar que alertas se han generado hasta el momento y \
narrar en tu respuesta que decisiones de negocio implican (por ejemplo, si \
una materia se cerro por baja demanda, o si un grupo quedo sin horario \
disponible).

El orden de las 7 tools de la secuencia esta forzado por el sistema: si \
invocas una fuera de orden, la tool devolvera un error explicandote cual es \
la siguiente esperada. No intentes rodear esa restriccion ni inventar un \
orden distinto -- simplemente sigue la secuencia indicada.

Cuando termines, resume en texto plano (no markdown extenso) cuantos \
estudiantes, materias y grupos se procesaron, y si quedaron alertas para \
revision humana.
"""


def _default_worker_count() -> int:
    return os.cpu_count() or 1


def run_period_with_agent(
    base_dir: Path,
    period: Period,
    seed: int = 0,
    max_workers: int | None = None,
    on_event: Callable[[dict], None] | None = None,
    model: str | None = None,
) -> RunResult:
    """Corre el pipeline de 11 pasos del PRD para `period`, con un agente real
    del Claude Agent SDK decidiendo cuando invocar cada fase.

    Firma paralela a `orchestration.runner.run_period`: mismos parametros,
    mismo tipo de retorno. La logica de negocio de cada fase no cambia -- ver
    `tools.py`, que delega en las mismas funciones de `orchestration/*` que
    usa el modo default.
    """
    return asyncio.run(
        _run_period_with_agent_async(base_dir, period, seed, max_workers, on_event, model)
    )


async def _run_period_with_agent_async(
    base_dir: Path,
    period: Period,
    seed: int,
    max_workers: int | None,
    on_event: Callable[[dict], None] | None,
    model: str | None,
) -> RunResult:
    emit: Callable[[dict], None] = on_event or (lambda event: None)
    resolved_model = model or os.environ.get(DEFAULT_MODEL_ENV_VAR) or DEFAULT_MODEL

    # --- Pasos 1-3 del PRD: mecanicos, sin decision de negocio -- se hacen
    # igual que en el modo default, antes de arrancar el agente. ---
    # Mover a graduated/ a quien ya haya aprobado todo el plan en un run
    # anterior, igual que orchestration.runner.run_period (ver
    # io/history.py::migrate_graduated_students).
    migrate_graduated_students(base_dir)
    prev_period = latest_period(base_dir)
    students = load_all_students(base_dir)
    students_by_carnet = {s.carnet: s for s in students}

    # Los nombres de estudiantes y de profesores salen del mismo pool
    # compartido (domain.names.NAME_POOL); el cursor persiste en
    # profesores.md, igual que en orchestration.runner.run_period.
    teacher_registry = read_teachers(profesores_file(base_dir))
    name_cursor = teacher_registry.next_free_index

    new_period_carnets = new_carnets(base_dir, period, NEW_STUDENTS_PER_PERIOD)
    student_names = allocate_names(name_cursor, len(new_period_carnets))
    name_cursor = student_names.next_free_index
    new_students = [
        Student(carnet=carnet, apellidos=apellidos, nombre=nombre)
        for carnet, (nombre, apellidos) in zip(
            new_period_carnets, student_names.names, strict=True
        )
    ]
    for s in new_students:
        students_by_carnet[s.carnet] = s

    state = PipelineState(base_dir=base_dir, period=period, seed=seed)
    state.prev_period = prev_period
    state.students_by_carnet = students_by_carnet
    state.new_student_carnets = new_period_carnets
    state.name_cursor = name_cursor
    state.existing_teacher_records = teacher_registry.records

    gate = PhaseGate()
    server, allowed_tools = build_tools(state, gate, max_workers, emit)

    options = ClaudeAgentOptions(
        model=resolved_model,
        system_prompt=SYSTEM_PROMPT,
        mcp_servers={"matricula": server},
        allowed_tools=allowed_tools,
        permission_mode="bypassPermissions",
    )

    async with ClaudeSDKClient(options=options) as client:
        await client.query(
            f"Corre el proceso de matricula para el periodo {period}. "
            f"Hay {len(students_by_carnet)} estudiantes en total "
            f"({len(new_students)} nuevos)."
        )
        async for message in client.receive_response():
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock) and block.text.strip():
                        emit({"type": "agent_message", "text": block.text})

    if not state.persisted:
        # El agente no completo la secuencia (se colgo, se rindio, agoto su
        # presupuesto de turnos). Forzamos persistencia con lo acumulado y
        # dejamos constancia via alerta -- la corrida nunca cuelga ni deja
        # el directorio de datos a medio escribir sin explicacion.
        state.alerts.append(
            Alert(
                carnet="",
                course_code="",
                reason=(
                    f"El agente orquestador no completo el pipeline (ultima fase "
                    f"confirmada: {gate.completed[-1] if gate.completed else 'ninguna'})."
                ),
                status="Error",
            )
        )
        state.period_record = PeriodRecord(
            period_str=str(period),
            horario=state.horario_rows,
            rosters=state.rosters,
            alertas=state.alerts,
        )
        for student in state.all_students:
            write_student(base_dir, student)
        write_period(base_dir, state.period_record)
        write_teachers(
            base_dir,
            TeacherRegistry(
                next_free_index=state.name_cursor,
                records=[*state.existing_teacher_records, *state.new_teacher_records],
            ),
        )

        # Mismo censo que emite persist_results_tool en el camino feliz -- ver
        # tools.py -- para que el force-persist tambien lo reporte.
        _emit_cuatrimestre_summary(emit, base_dir)

        state.summary = RunSummary(
            period=str(period),
            students_created=len(new_students),
            requests_valid=state.requests_valid_count,
            requests_rejected=state.requests_rejected_count,
            courses_opened=len(state.demand.open_courses) if state.demand else 0,
            courses_closed=len(state.demand.closed_courses) if state.demand else 0,
            groups_formed=len(state.all_groups),
            alerts=state.alerts,
        )
        emit(
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

    assert state.summary is not None
    assert state.period_record is not None
    return RunResult(
        summary=state.summary, period_record=state.period_record, students=state.all_students
    )
