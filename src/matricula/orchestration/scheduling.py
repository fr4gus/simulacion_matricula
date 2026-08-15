"""Asignacion de profesor, aula y bloques de horario para cada grupo.

PRD.md, supuestos + Proceso de Matricula paso 8, y seccion "Aclaraciones" #4:
- Horario: Lunes-Viernes, 07:00-17:00.
- Cada materia dura 200 min/semana: un bloque continuo de 200 min, o dos
  bloques de 100 min en dias distintos (sin regla de no-adyacencia).
- Los bloques (continuos o divididos) empiezan en horas alineadas a
  {07,09,11,13,15}.
- Un profesor no puede impartir dos grupos al mismo tiempo. Un aula no puede
  alojar dos grupos al mismo tiempo. Maximo 100 aulas (AULA-100..AULA-199).
- Si un grupo no consigue combinacion sin conflictos, se genera una alerta y
  el resto de la corrida continua (Aclaraciones #3).

Esta fase es completamente determinista (sin RNG): procesa los grupos en un
orden fijo (codigo de materia, luego numero de grupo) y prueba las
combinaciones candidatas en un orden fijo tambien, de modo que el resultado
no depende de nada mas que la entrada.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations

from matricula.config import (
    BLOCK_START_HOURS,
    CLASSROOM_NUMBER_START,
    COURSE_WEEKLY_MINUTES,
    DAY_CODES,
    MAX_CLASSROOMS,
    SCHOOL_DAYS,
    SCHOOL_END_HOUR,
    SPLIT_BLOCK_MINUTES,
)
from matricula.domain.models import Alert, Group, GroupSchedule, ScheduleBlock, TeacherRecord
from matricula.simulation.naming import POOL_SIZE, allocate_names

REASON_UNSCHEDULABLE = "No fue posible asignar horario/aula/profesor sin conflictos"


def classroom_codes() -> list[str]:
    return [f"AULA-{CLASSROOM_NUMBER_START + i}" for i in range(MAX_CLASSROOMS)]


def _candidate_block_sets() -> list[list[ScheduleBlock]]:
    """Genera, en orden fijo, todas las combinaciones candidatas de bloques.

    Primero se intentan bloques continuos de 200 min (uno por dia), luego
    combinaciones de dos bloques de 100 min en dos dias distintos.
    """
    candidates: list[list[ScheduleBlock]] = []

    continuous_starts = [
        h for h in BLOCK_START_HOURS if h + COURSE_WEEKLY_MINUTES / 60 <= SCHOOL_END_HOUR
    ]
    for day in SCHOOL_DAYS:
        for hour in continuous_starts:
            candidates.append(
                [ScheduleBlock(day=day, start_hour=hour, duration_minutes=COURSE_WEEKLY_MINUTES)]
            )

    split_starts = [h for h in BLOCK_START_HOURS if h + SPLIT_BLOCK_MINUTES / 60 <= SCHOOL_END_HOUR]
    for day_a, day_b in combinations(SCHOOL_DAYS, 2):
        for hour_a in split_starts:
            for hour_b in split_starts:
                candidates.append(
                    [
                        ScheduleBlock(
                            day=day_a, start_hour=hour_a, duration_minutes=SPLIT_BLOCK_MINUTES
                        ),
                        ScheduleBlock(
                            day=day_b, start_hour=hour_b, duration_minutes=SPLIT_BLOCK_MINUTES
                        ),
                    ]
                )

    return candidates


_CANDIDATE_BLOCK_SETS = _candidate_block_sets()


def _block_end_hour(block: ScheduleBlock) -> float:
    return block.start_hour + block.duration_minutes / 60


def overlaps(a: ScheduleBlock, b: ScheduleBlock) -> bool:
    if a.day != b.day:
        return False
    return a.start_hour < _block_end_hour(b) and b.start_hour < _block_end_hour(a)


def blocks_conflict(blocks_a: list[ScheduleBlock], blocks_b: list[ScheduleBlock]) -> bool:
    return any(overlaps(a, b) for a in blocks_a for b in blocks_b)


def format_horario(blocks: list[ScheduleBlock]) -> str:
    parts = []
    for block in blocks:
        start = block.start_hour
        end = _block_end_hour(block)
        end_hour = int(end)
        end_minute = int(round((end % 1) * 60))
        parts.append(f"{DAY_CODES[block.day]} {start:02.0f}:00-{end_hour:02d}:{end_minute:02d}")
    return " / ".join(parts)


@dataclass
class TeacherPool:
    """Asigna nombres de profesor nuevos desde el pool compartido de nombres
    (`domain.names`), uno por grupo adicional; nunca reusa el mismo indice del
    pool dentro de la misma corrida.

    `start_index` es el cursor con el que arranca esta corrida (leido de
    `profesores.md`, ver `io/teacher_md.py`); `next_free_index`, tras agotar
    la instancia, es el cursor a persistir para la proxima corrida.
    """

    start_index: int
    records: list[TeacherRecord] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._next_index = self.start_index

    def new_teacher_for(self, group_code: str) -> str:
        allocation = allocate_names(self._next_index, 1)
        nombre, apellidos = allocation.names[0]
        full_name = f"{nombre} {apellidos}"
        record = TeacherRecord(
            pool_index=self._next_index % POOL_SIZE, full_name=full_name, group_code=group_code
        )
        self.records.append(record)
        self._next_index = allocation.next_free_index
        return full_name

    @property
    def next_free_index(self) -> int:
        return self._next_index


def schedule_groups(
    groups: list[Group], teacher_start_index: int = 0
) -> tuple[list[GroupSchedule], list[Alert], list[TeacherRecord], int]:
    """Asigna profesor, aula y horario a cada grupo, en orden materia+grupo.

    Retorna `(schedules, alerts, teacher_records, next_free_teacher_index)`:
    `teacher_records` son los profesores nuevos generados en esta llamada
    (para persistir en `profesores.md`) y `next_free_teacher_index` es el
    cursor del pool de nombres a guardar para la proxima corrida.

    Cada grupo recibe un profesor nuevo (nunca compartido entre grupos, ni
    siquiera de la misma materia), tomado del pool compartido de nombres. El
    aula y el bloque horario se buscan entre las combinaciones candidatas, en
    orden fijo, evitando choques con aulas/profesores ya usados por grupos
    previamente asignados en esta misma corrida.

    Ademas de las restricciones duras (profesor y aula nunca se comparten en
    el mismo bloque), se prefiere activamente un horario que no choque con
    ningun bloque ya asignado a *cualquier* otro grupo de esta corrida. Un
    estudiante tipico solicita varias materias del mismo cuatrimestre, y si
    todas cayeran en el mismo bloque (p.ej. porque el primer candidato libre
    de aula/profesor es siempre el mismo), la fase de asignacion individual
    (assignment.py) generaria conflictos evitables. Esta preferencia es un
    "mejor esfuerzo" de diversificacion, no una regla dura del PRD: si no
    hay ningun candidato libre de choques globales, se recurre al primer
    candidato que solo respete profesor/aula.
    """
    ordered = sorted(groups, key=lambda g: (g.course_code, g.number))
    teachers = TeacherPool(start_index=teacher_start_index)
    rooms = classroom_codes()

    schedules: list[GroupSchedule] = []
    alerts: list[Alert] = []

    # Ocupacion por aula: mapea aula -> lista de bloques usados.
    classroom_busy: dict[str, list[ScheduleBlock]] = {room: [] for room in rooms}
    # Ocupacion global (todos los grupos ya asignados), usada solo como
    # preferencia blanda para diversificar horarios entre materias distintas.
    globally_busy: list[ScheduleBlock] = []

    for group in ordered:
        teacher = teachers.new_teacher_for(group.group_code)
        teacher_busy: list[ScheduleBlock] = []  # profesor es nuevo, nunca tiene ocupacion previa

        assigned: GroupSchedule | None = None
        fallback: GroupSchedule | None = None
        for blocks in _CANDIDATE_BLOCK_SETS:
            if blocks_conflict(blocks, teacher_busy):
                continue
            for room in rooms:
                if blocks_conflict(blocks, classroom_busy[room]):
                    continue
                candidate = GroupSchedule(
                    course_code=group.course_code,
                    group_number=group.number,
                    teacher=teacher,
                    classroom=room,
                    blocks=blocks,
                )
                if fallback is None:
                    fallback = candidate
                if not blocks_conflict(blocks, globally_busy):
                    assigned = candidate
                    break
            if assigned is not None:
                break

        chosen = assigned or fallback
        if chosen is None:
            alerts.append(
                Alert(
                    carnet="",
                    course_code=f"{group.course_code}-{group.number}",
                    reason=REASON_UNSCHEDULABLE,
                    status="Sin horario",
                )
            )
            continue

        classroom_busy[chosen.classroom].extend(chosen.blocks)
        globally_busy.extend(chosen.blocks)
        schedules.append(chosen)

    return schedules, alerts, teachers.records, teachers.next_free_index
