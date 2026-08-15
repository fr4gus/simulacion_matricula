"""Reader/writer de students/DDDDDD.md.

Formato (ver PRD.md, seccion "Expedientes de Estudiantes"):

    # Estudiante DDDDDD

    ## Matricula

    | Periodo Lectivo | Codigo Materia | Grupo | Nombre Materia |
    | --------------- | -------------- | ----- | -------------- |
    | 2026-01         | MA001          | 01    | Matematicas I  |

    ## Expediente de Notas

    | Periodo Lectivo | Codigo Materia | Nombre Materia | Nota (de 0 a 100) |
    | --------------- | -------------- | -------------- | ----------------- |
    | 2026-01         | MA001          | Matematicas I  | 85                |

El carne se toma del nombre de archivo, no del cuerpo. `write_student` siempre
re-renderiza el archivo completo desde el `Student` en memoria.
"""

from __future__ import annotations

from pathlib import Path

from matricula.domain.models import GradeRecord, MatriculaEntry, Student
from matricula.domain.periods import Period
from matricula.io.markdown_tables import parse_table, render_table

MATRICULA_HEADERS = ["Periodo Lectivo", "Codigo Materia", "Grupo", "Nombre Materia"]
EXPEDIENTE_HEADERS = ["Periodo Lectivo", "Codigo Materia", "Nombre Materia", "Nota (de 0 a 100)"]


def _new_student(carnet: str, apellidos: str = "", nombre: str = "") -> Student:
    return Student(carnet=carnet, apellidos=apellidos, nombre=nombre)


def parse_student(carnet: str, text: str) -> Student:
    """Parsea el contenido de un students/DDDDDD.md ya existente."""
    lines = text.splitlines()
    sections = _split_sections(lines)

    matricula: list[MatriculaEntry] = []
    if "Matricula" in sections:
        _, rows = parse_table(sections["Matricula"])
        for row in rows:
            period_str, code, group, name = row
            matricula.append(
                MatriculaEntry(
                    period=Period.parse(period_str),
                    course_code=code,
                    group=group,
                    course_name=name,
                )
            )

    grades: list[GradeRecord] = []
    if "Expediente de Notas" in sections:
        _, rows = parse_table(sections["Expediente de Notas"])
        for row in rows:
            period_str, code, name, grade_str = row
            grades.append(
                GradeRecord(
                    period=Period.parse(period_str),
                    course_code=code,
                    course_name=name,
                    grade=int(grade_str),
                )
            )

    apellidos, nombre = _parse_identity(sections.get("_header", []))
    return Student(
        carnet=carnet, apellidos=apellidos, nombre=nombre, matricula=matricula, grades=grades
    )


def _parse_identity(header_lines: list[str]) -> tuple[str, str]:
    """El nombre completo se guarda en una linea `Nombre: Apellidos, Nombre` bajo el titulo."""
    for line in header_lines:
        if line.startswith("Nombre:"):
            value = line.removeprefix("Nombre:").strip()
            if "," in value:
                apellidos, nombre = value.split(",", 1)
                return apellidos.strip(), nombre.strip()
            return value, ""
    return "", ""


def _split_sections(lines: list[str]) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {"_header": []}
    current = "_header"
    for line in lines:
        if line.startswith("## "):
            current = line.removeprefix("## ").strip()
            sections[current] = []
        elif line.startswith("# "):
            continue
        else:
            sections[current].append(line)
    return sections


def render_student(student: Student) -> str:
    matricula_rows = [
        [str(entry.period), entry.course_code, entry.group, entry.course_name]
        for entry in student.matricula
    ]
    grade_rows = [
        [str(record.period), record.course_code, record.course_name, str(record.grade)]
        for record in student.grades
    ]

    parts = [f"# Estudiante {student.carnet}", ""]
    if student.apellidos or student.nombre:
        parts.append(f"Nombre: {student.apellidos}, {student.nombre}")
        parts.append("")
    parts.append("## Matricula")
    parts.append("")
    parts.append(render_table(MATRICULA_HEADERS, matricula_rows))
    parts.append("")
    parts.append("## Expediente de Notas")
    parts.append("")
    parts.append(render_table(EXPEDIENTE_HEADERS, grade_rows))
    parts.append("")
    return "\n".join(parts)


def read_student(path: Path) -> Student:
    carnet = path.stem
    return parse_student(carnet, path.read_text(encoding="utf-8"))


def write_student(base_dir: Path, student: Student) -> Path:
    from matricula.io.paths import student_file, students_dir

    students_dir(base_dir).mkdir(parents=True, exist_ok=True)
    path = student_file(base_dir, student.carnet)
    path.write_text(render_student(student), encoding="utf-8")
    return path
