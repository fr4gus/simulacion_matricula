"""`PipelineState`: acumula, en memoria del lado del harness, los resultados
de cada fase del pipeline mientras el agente LLM las va invocando.

Las tools (`tools.py`) operan sobre claves/IDs (carnets, codigos de materia)
al hablar con el modelo -- el LLM nunca necesita transportar ida y vuelta el
payload completo de `Student`/`Group`/`GroupSchedule`, que puede ser grande y
no hay garantia de que un LLM lo reproduzca fielmente. El estado real vive
aqui, del lado Python, igual que en las variables locales de
`orchestration.runner.run_period`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from matricula.domain.models import Alert, Group, GroupSchedule, Student, TeacherRecord
from matricula.domain.periods import Period
from matricula.io.period_md import HorarioRow, PeriodRecord, RosterEntry
from matricula.orchestration.assignment import AssignmentResult
from matricula.orchestration.demand import DemandResult
from matricula.reporting.summary import RunSummary
from matricula.simulation.worker import WorkerResult


@dataclass
class PipelineState:
    """Espejo, del lado del harness de agentes, de las variables locales que
    `orchestration.runner.run_period` usa para llevar el pipeline paso a paso.
    """

    base_dir: Path
    period: Period
    seed: int

    # Poblado antes de arrancar el agente (paso 1-3 del PRD: no requieren
    # decision alguna, son puramente mecanicos).
    prev_period: Period | None = None
    students_by_carnet: dict[str, Student] = field(default_factory=dict)
    new_student_carnets: list[str] = field(default_factory=list)

    # Cursor del pool compartido de nombres (domain.names.NAME_POOL) y
    # registros ya persistidos en profesores.md, leidos antes de arrancar el
    # agente (igual que en orchestration.runner.run_period). schedule_groups
    # avanza name_cursor y agrega a new_teacher_records; persist_results usa
    # ambos para reescribir profesores.md.
    name_cursor: int = 0
    existing_teacher_records: list[TeacherRecord] = field(default_factory=list)
    new_teacher_records: list[TeacherRecord] = field(default_factory=list)

    # --- simulate_grades ---
    worker_results: dict[str, WorkerResult] = field(default_factory=dict)
    all_requests_by_student: dict[str, list[str]] = field(default_factory=dict)

    # --- validate_requests ---
    valid_requests_by_course: dict[str, list[str]] = field(default_factory=dict)
    requests_valid_count: int = 0
    requests_rejected_count: int = 0

    # --- compute_demand ---
    demand: DemandResult | None = None

    # --- form_groups ---
    all_groups: list[Group] = field(default_factory=list)
    carnets_by_group: dict[tuple[str, str], list[str]] = field(default_factory=dict)

    # --- schedule_groups ---
    schedules: list[GroupSchedule] = field(default_factory=list)

    # --- assign_students ---
    assignment: AssignmentResult | None = None

    # Alertas acumuladas de todas las fases, en el mismo orden que
    # `run_period` las agrega (rechazos de validacion, cierres de materia,
    # horarios sin resolver, conflictos individuales, mas cualquier error de
    # worker o del propio agente).
    alerts: list[Alert] = field(default_factory=list)

    # --- persist_results ---
    horario_rows: list[HorarioRow] = field(default_factory=list)
    rosters: dict[str, list[RosterEntry]] = field(default_factory=dict)
    period_record: PeriodRecord | None = None
    summary: RunSummary | None = None
    persisted: bool = False

    @property
    def all_students(self) -> list[Student]:
        return list(self.students_by_carnet.values())
