"""Dataclasses del dominio: cursos, estudiantes, solicitudes, grupos, horario, alertas."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from matricula.domain.periods import Period


@dataclass(frozen=True)
class Course:
    code: str  # p.ej. "MA001"
    name: str  # p.ej. "Matematicas I"
    cuatrimestre: int  # posicion en el plan de estudios (1..N)
    prerequisites: tuple[str, ...] = ()  # codigos de materia


@dataclass(frozen=True)
class GradeRecord:
    """Una fila del "Expediente de Notas" de un estudiante."""

    period: Period
    course_code: str
    course_name: str
    grade: int  # 0..100

    @property
    def passed(self) -> bool:
        from matricula.config import PASS_GRADE

        return self.grade >= PASS_GRADE


@dataclass(frozen=True)
class MatriculaEntry:
    """Una fila de la seccion "Matricula" de un estudiante: a que grupo fue asignado."""

    period: Period
    course_code: str
    group: str  # "01", "02", ...
    course_name: str


@dataclass
class Student:
    carnet: str  # "DDDDDD"
    apellidos: str
    nombre: str
    matricula: list[MatriculaEntry] = field(default_factory=list)
    grades: list[GradeRecord] = field(default_factory=list)

    def historical_average(self) -> float:
        if not self.grades:
            return 0.0
        return sum(g.grade for g in self.grades) / len(self.grades)

    def passed_courses(self) -> set[str]:
        """Codigos de materia con al menos una nota >= PASS_GRADE."""
        return {g.course_code for g in self.grades if g.passed}

    def latest_grade_for(self, course_code: str) -> GradeRecord | None:
        matches = [g for g in self.grades if g.course_code == course_code]
        if not matches:
            return None
        return max(matches, key=lambda g: (g.period.year, g.period.number))


class RequestStatus(Enum):
    VALID = "valida"
    REJECTED = "rechazada"


@dataclass(frozen=True)
class Request:
    carnet: str
    course_code: str
    status: RequestStatus
    reason: str | None = None  # solo cuando status == REJECTED


@dataclass
class Group:
    course_code: str
    number: str  # "01", "02", ...
    carnets: list[str] = field(default_factory=list)

    @property
    def group_code(self) -> str:
        return f"{self.course_code}-{self.number}"


@dataclass(frozen=True)
class ScheduleBlock:
    day: int  # 0=Lunes .. 4=Viernes
    start_hour: int  # hora de inicio, en BLOCK_START_HOURS
    duration_minutes: int  # 100 o 200


@dataclass
class GroupSchedule:
    course_code: str
    group_number: str
    teacher: str
    classroom: str
    blocks: list[ScheduleBlock] = field(default_factory=list)


@dataclass(frozen=True)
class Alert:
    carnet: str
    course_code: str
    reason: str
    status: str
