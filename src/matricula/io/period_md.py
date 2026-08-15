"""Reader/writer de periodos_lectivos/YYYY-PP.md.

Formato (ver PRD.md, seccion "Resultado de la matricula"):

    # Periodo Lectivo YYYY-PP

    ## Horario

    | Codigo Materia | Nombre Curso  | Grupo | Profesor   | Aula     | Horario |
    | -------------- | ------------- | ----- | ---------- | -------- | ------- |
    | MA001          | Matematicas I | 01    | Juan Perez | AULA-101 | ...     |

    ## Listas de Estudiantes por Materia y Grupo

    ### MA001 - Grupo 01

    | Carné  | Apellidos       | Nombre |
    | ------ | --------------- | ------ |
    | 250005 | Aguilar Jimenes | Pedro  |

    ## Alertas para Revision Humana

    | Carné  | Codigo Materia | Motivo | Estado |
    | ------ | -------------- | ------ | ------ |
    | 260031 | CS004          | ...    | ...    |
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from matricula.domain.models import Alert

HORARIO_HEADERS = ["Codigo Materia", "Nombre Curso", "Grupo", "Profesor", "Aula", "Horario"]
ROSTER_HEADERS = ["Carné", "Apellidos", "Nombre"]
ALERTAS_HEADERS = ["Carné", "Codigo Materia", "Motivo", "Estado"]


@dataclass(frozen=True)
class HorarioRow:
    course_code: str
    course_name: str
    group: str
    teacher: str
    classroom: str
    horario: str


@dataclass(frozen=True)
class RosterEntry:
    carnet: str
    apellidos: str
    nombre: str


@dataclass
class PeriodRecord:
    period_str: str
    horario: list[HorarioRow] = field(default_factory=list)
    rosters: dict[str, list[RosterEntry]] = field(default_factory=dict)  # "MA001-01" -> entries
    alertas: list[Alert] = field(default_factory=list)


def parse_period(period_str: str, text: str) -> PeriodRecord:
    from matricula.io.markdown_tables import parse_table

    lines = text.splitlines()
    top_sections = _split_h2_sections(lines)

    horario: list[HorarioRow] = []
    if "Horario" in top_sections:
        _, rows = parse_table(top_sections["Horario"])
        for row in rows:
            code, name, group, teacher, classroom, schedule = row
            horario.append(HorarioRow(code, name, group, teacher, classroom, schedule))

    rosters: dict[str, list[RosterEntry]] = {}
    if "Listas de Estudiantes por Materia y Grupo" in top_sections:
        for group_code, group_lines in _split_h3_sections(
            top_sections["Listas de Estudiantes por Materia y Grupo"]
        ).items():
            _, rows = parse_table(group_lines)
            rosters[group_code] = [RosterEntry(carnet, ap, nom) for carnet, ap, nom in rows]

    alertas: list[Alert] = []
    if "Alertas para Revision Humana" in top_sections:
        _, rows = parse_table(top_sections["Alertas para Revision Humana"])
        for carnet, code, motivo, estado in rows:
            alertas.append(Alert(carnet=carnet, course_code=code, reason=motivo, status=estado))

    return PeriodRecord(period_str=period_str, horario=horario, rosters=rosters, alertas=alertas)


def _split_h2_sections(lines: list[str]) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in lines:
        if line.startswith("## "):
            current = line.removeprefix("## ").strip()
            sections[current] = []
        elif line.startswith("# "):
            continue
        elif current is not None:
            sections[current].append(line)
    return sections


def _split_h3_sections(lines: list[str]) -> dict[str, list[str]]:
    """Divide por encabezados `### {Materia} - Grupo {NN}` -> clave "MATERIA-NN"."""
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in lines:
        if line.startswith("### "):
            title = line.removeprefix("### ").strip()
            course_code, _, group_part = title.partition(" - Grupo ")
            current = f"{course_code.strip()}-{group_part.strip()}"
            sections[current] = []
        elif current is not None:
            sections[current].append(line)
    return sections


def render_period(record: PeriodRecord) -> str:
    from matricula.io.markdown_tables import render_table

    parts = [f"# Periodo Lectivo {record.period_str}", ""]

    parts.append("## Horario")
    parts.append("")
    horario_rows = [
        [h.course_code, h.course_name, h.group, h.teacher, h.classroom, h.horario]
        for h in record.horario
    ]
    parts.append(render_table(HORARIO_HEADERS, horario_rows))
    parts.append("")

    parts.append("## Listas de Estudiantes por Materia y Grupo")
    parts.append("")
    for group_code in sorted(record.rosters):
        course_code, _, group_number = group_code.rpartition("-")
        parts.append(f"### {course_code} - Grupo {group_number}")
        parts.append("")
        roster_rows = [[e.carnet, e.apellidos, e.nombre] for e in record.rosters[group_code]]
        parts.append(render_table(ROSTER_HEADERS, roster_rows))
        parts.append("")

    parts.append("## Alertas para Revision Humana")
    parts.append("")
    alertas_rows = [[a.carnet, a.course_code, a.reason, a.status] for a in record.alertas]
    parts.append(render_table(ALERTAS_HEADERS, alertas_rows))
    parts.append("")

    return "\n".join(parts)


def read_period(path: Path) -> PeriodRecord:
    return parse_period(path.stem, path.read_text(encoding="utf-8"))


def write_period(base_dir: Path, record: PeriodRecord) -> Path:
    from matricula.io.paths import period_file, periodos_dir

    periodos_dir(base_dir).mkdir(parents=True, exist_ok=True)
    path = period_file(base_dir, record.period_str)
    path.write_text(render_period(record), encoding="utf-8")
    return path
