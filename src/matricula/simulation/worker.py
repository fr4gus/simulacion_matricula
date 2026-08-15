"""Unidad de trabajo paralela: un estudiante = una llamada de worker.

`process_student` es una funcion top-level (no un metodo ni un closure) para
que sea picklable y ejecutable dentro de un `ProcessPoolExecutor`. Simula las
notas de la matricula pendiente del periodo anterior y construye, en la misma
llamada, la lista de solicitudes del estudiante para el periodo objetivo.

La semilla de cada estudiante se deriva de `(run_seed, carnet)` en vez de usar
`hash()` de Python, que esta salteado por proceso via `PYTHONHASHSEED` y no
séria estable entre procesos del pool.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field

from matricula.domain.models import GradeRecord, Student
from matricula.domain.periods import Period
from matricula.simulation.grades import simulate_grade
from matricula.simulation.requests import build_request_course_codes


@dataclass(frozen=True)
class WorkerResult:
    carnet: str
    new_grades: list[GradeRecord] = field(default_factory=list)
    requested_course_codes: list[str] = field(default_factory=list)
    error: str | None = None


def _student_rng(run_seed: int, carnet: str) -> random.Random:
    """RNG determinista por estudiante, estable entre procesos del pool.

    No usa `hash()` de Python (salteado por proceso via `PYTHONHASHSEED`);
    en su lugar deriva un entero estable via sha256 de `run_seed` + carnet.
    """
    digest = hashlib.sha256(f"{run_seed}:{carnet}".encode()).digest()
    seed_int = int.from_bytes(digest, "big")
    return random.Random(seed_int)


def process_student(
    student: Student,
    target_period: Period,
    previous_period: Period | None,
    run_seed: int,
) -> WorkerResult:
    """Simula notas pendientes y construye la solicitud del `target_period`.

    `student` es un snapshot inmutable tal como fue leido en el proceso
    principal antes de despachar. Solo se simulan notas para materias cuya
    matricula corresponde exactamente a `previous_period` y que aun no tienen
    una nota registrada para ese periodo (evita re-simular en corridas
    repetidas).
    """
    try:
        rng = _student_rng(run_seed, student.carnet)
        new_grades: list[GradeRecord] = []

        if previous_period is not None:
            already_graded = {(g.period, g.course_code) for g in student.grades}
            pending = [
                entry
                for entry in student.matricula
                if entry.period == previous_period
                and (entry.period, entry.course_code) not in already_graded
            ]
            for entry in pending:
                grade = simulate_grade(rng)
                new_grades.append(
                    GradeRecord(
                        period=entry.period,
                        course_code=entry.course_code,
                        course_name=entry.course_name,
                        grade=grade,
                    )
                )

        # El request-builder trabaja sobre el expediente actualizado con las
        # notas recien simuladas (si las hubo).
        updated_student = Student(
            carnet=student.carnet,
            apellidos=student.apellidos,
            nombre=student.nombre,
            matricula=list(student.matricula),
            grades=[*student.grades, *new_grades],
        )
        requested = build_request_course_codes(updated_student)

        return WorkerResult(
            carnet=student.carnet,
            new_grades=new_grades,
            requested_course_codes=requested,
        )
    except Exception as exc:  # noqa: BLE001 - se convierte en alerta, no debe tumbar el pool
        return WorkerResult(carnet=student.carnet, error=str(exc))
