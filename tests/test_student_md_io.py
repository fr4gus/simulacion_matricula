from __future__ import annotations

from pathlib import Path

from matricula.domain.models import GradeRecord, MatriculaEntry, Student
from matricula.domain.periods import Period
from matricula.io.student_md import parse_student, read_student, render_student, write_student


def test_render_matches_prd_example_shape():
    student = Student(
        carnet="260001",
        apellidos="Perez",
        nombre="Juan",
        matricula=[
            MatriculaEntry(Period.parse("2026-01"), "MA001", "01", "Matematicas I"),
        ],
        grades=[],
    )
    text = render_student(student)
    assert "# Estudiante 260001" in text
    assert "## Matricula" in text
    assert "## Expediente de Notas" in text
    assert "| Periodo Lectivo | Codigo Materia | Grupo | Nombre Materia |" in text
    assert "| 2026-01" in text
    assert "MA001" in text


def test_roundtrip_empty_student(base_dir: Path):
    student = Student(carnet="260001", apellidos="Perez", nombre="Juan")
    write_student(base_dir, student)
    loaded = read_student(base_dir / "students" / "260001.md")
    assert loaded.carnet == "260001"
    assert loaded.apellidos == "Perez"
    assert loaded.nombre == "Juan"
    assert loaded.matricula == []
    assert loaded.grades == []


def test_roundtrip_multi_period_with_retake(base_dir: Path):
    student = Student(
        carnet="260002",
        apellidos="Gomez Solis",
        nombre="Ana Maria",
        matricula=[
            MatriculaEntry(Period.parse("2026-01"), "MA001", "01", "Matematicas I"),
            MatriculaEntry(Period.parse("2026-02"), "MA001", "02", "Matematicas I"),  # retake
        ],
        grades=[
            GradeRecord(Period.parse("2026-01"), "MA001", "Matematicas I", 55),
            GradeRecord(Period.parse("2026-02"), "MA001", "Matematicas I", 88),
        ],
    )
    write_student(base_dir, student)
    loaded = read_student(base_dir / "students" / "260002.md")
    assert len(loaded.matricula) == 2
    assert len(loaded.grades) == 2
    assert loaded.grades[0].grade == 55
    assert not loaded.grades[0].passed
    assert loaded.grades[1].passed


def test_parse_student_directly_from_text():
    text = (
        "# Estudiante 260003\n\n"
        "Nombre: Diaz, Carlos\n\n"
        "## Matricula\n\n"
        "| Periodo Lectivo | Codigo Materia | Grupo | Nombre Materia |\n"
        "| --------------- | -------------- | ----- | -------------- |\n"
        "| 2026-01         | MA001          | 01    | Matematicas I  |\n\n"
        "## Expediente de Notas\n\n"
        "| Periodo Lectivo | Codigo Materia | Nombre Materia | Nota (de 0 a 100) |\n"
        "| --------------- | -------------- | --------------- | ----------------- |\n"
    )
    student = parse_student("260003", text)
    assert student.apellidos == "Diaz"
    assert student.nombre == "Carlos"
    assert len(student.matricula) == 1
    assert student.grades == []
