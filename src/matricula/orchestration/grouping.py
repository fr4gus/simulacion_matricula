"""Formacion de grupos para una materia abierta.

PRD.md, Proceso de Matricula, paso 7 + seccion "Aclaraciones" #3:
- ceil(total/10) grupos, maximo 10 por grupo, diferencia maxima de 1
  estudiante entre grupos.
- La prioridad (promedio historico desc, luego carne asc) solo decide QUIEN
  obtiene cupo cuando la demanda total de la materia excede la capacidad
  total (10 * numero_maximo_de_grupos no aplica: en este sistema no hay techo
  de grupos, asi que en la practica todos los solicitantes validos entran, y
  la prioridad determina el orden de admision solo si en el futuro se
  introdujera un limite). El reparto a un grupo especifico es balanceado,
  sin usar el ranking de prioridad para decidir la posicion.
"""

from __future__ import annotations

import math

from matricula.config import GROUP_CAPACITY
from matricula.domain.models import Group, Student


def priority_key(student: Student) -> tuple[float, int]:
    """Orden de prioridad: promedio historico descendente, carne ascendente."""
    return (-student.historical_average(), int(student.carnet))


def rank_by_priority(students: list[Student]) -> list[Student]:
    return sorted(students, key=priority_key)


def form_groups(course_code: str, admitted_carnets: list[str]) -> list[Group]:
    """Crea ceil(n/10) grupos balanceados (diferencia maxima de 1 estudiante).

    `admitted_carnets` ya viene en el orden final de admision (irrelevante
    para el reparto a grupos especificos, que es libre/balanceado); se asume
    que todos los carnets en la lista fueron admitidos.
    """
    total = len(admitted_carnets)
    if total == 0:
        return []

    group_count = math.ceil(total / GROUP_CAPACITY)
    groups = [Group(course_code=course_code, number=f"{i + 1:02d}") for i in range(group_count)]

    # Reparto balanceado tipo round-robin: garantiza diferencia maxima de 1.
    for index, carnet in enumerate(admitted_carnets):
        groups[index % group_count].carnets.append(carnet)

    return groups
