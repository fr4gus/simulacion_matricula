from __future__ import annotations

from pathlib import Path

from matricula.domain.models import GradeRecord, Student
from matricula.domain.names import NAME_POOL
from matricula.domain.periods import Period
from matricula.domain.study_plan import COURSES
from matricula.io.history import count_graduated_students, load_all_students
from matricula.io.paths import graduated_dir, profesores_file, students_dir
from matricula.io.student_md import write_student
from matricula.io.teacher_md import read_teachers
from matricula.orchestration.runner import run_period


def test_bootstrap_period_creates_first_ten_students_with_cuatrimestre_1(base_dir: Path):
    result = run_period(base_dir, Period.parse("2026-01"), seed=0, max_workers=1)

    assert result.summary.students_created == 10
    assert result.summary.courses_opened == 3  # MA001, CS002, ES001
    assert result.summary.courses_closed == 0
    assert result.summary.groups_formed == 3  # ceil(10/10) por materia
    assert result.summary.exit_code == 0

    students = load_all_students(base_dir)
    assert len(students) == 10
    carnets = sorted(s.carnet for s in students)
    assert carnets == [f"26000{i}" for i in range(1, 10)] + ["260010"]

    for student in students:
        codes = {e.course_code for e in student.matricula}
        assert codes == {"MA001", "CS002", "ES001"}

    period_record = result.period_record
    assert len(period_record.horario) == 3
    assert set(period_record.rosters) == {"MA001-01", "CS002-01", "ES001-01"}
    for roster in period_record.rosters.values():
        assert len(roster) == 10

    # Los 10 estudiantes nuevos toman los primeros 10 nombres del pool
    # compartido, en orden; los 3 profesores generados (uno por materia)
    # continuan el cursor sin repetir indices.
    for i, student in enumerate(sorted(students, key=lambda s: s.carnet)):
        nombre, apellidos = NAME_POOL[i]
        assert (student.nombre, student.apellidos) == (nombre, apellidos)

    registry = read_teachers(profesores_file(base_dir))
    assert registry.next_free_index == 13  # 10 estudiantes + 3 profesores
    assert len(registry.records) == 3
    used_indices = [r.pool_index for r in registry.records]
    assert used_indices == sorted(set(used_indices))  # sin repetidos
    assert set(used_indices).isdisjoint(range(10))  # no pisan los de estudiantes


def test_continuing_period_simulates_grades_and_respects_prerequisites(base_dir: Path):
    run_period(base_dir, Period.parse("2026-01"), seed=0, max_workers=1)
    result = run_period(base_dir, Period.parse("2026-02"), seed=0, max_workers=1)

    assert result.summary.students_created == 10  # 10 nuevos de este periodo tambien

    students = {s.carnet: s for s in load_all_students(base_dir)}
    assert len(students) == 20

    # Los 10 primeros ya deben tener notas simuladas para 2026-01.
    original_ten = [students[f"26000{i}"] if i < 10 else students["260010"] for i in range(1, 11)]
    for student in original_ten:
        period_2026_01_grades = [g for g in student.grades if str(g.period) == "2026-01"]
        assert len(period_2026_01_grades) == 3

        passed_all = all(g.passed for g in period_2026_01_grades)
        requested_codes = {e.course_code for e in student.matricula if str(e.period) == "2026-02"}
        if passed_all:
            # Avanza a cuatrimestre 2 (si esas materias abrieron; con 10
            # solicitantes siempre abren).
            assert requested_codes <= {"CS003", "MA002", "ES010"}
        else:
            # Al menos una materia de cuatrimestre 1 debe repetirse.
            failed_codes = {g.course_code for g in period_2026_01_grades if not g.passed}
            assert failed_codes <= (
                {e.course_code for e in student.matricula if str(e.period) == "2026-02"}
                | {  # o quedo como alerta si la materia no abrio / hubo conflicto
                    a.course_code for a in result.summary.alerts if a.carnet == student.carnet
                }
            )

    # Los 10 nuevos de este periodo entran a cuatrimestre 1.
    new_ten = [students[f"26001{i}"] for i in range(1, 10)] + [students["260020"]]
    for student in new_ten:
        codes = {e.course_code for e in student.matricula if str(e.period) == "2026-02"}
        assert codes <= {"MA001", "CS002", "ES001"}

    # Grupos y horario se regeneran desde cero cada periodo (2026-01 no debe
    # reaparecer en el archivo de 2026-02).
    for row in result.period_record.horario:
        assert row  # solo confirma que la seccion se genero de nuevo, no vacia si hubo demanda

    # El cursor del pool de nombres continua entre corridas: no se reinicia
    # a 0, y ningun indice de profesor se repite entre 2026-01 y 2026-02.
    registry = read_teachers(profesores_file(base_dir))
    used_indices = [r.pool_index for r in registry.records]
    assert len(used_indices) == len(set(used_indices))
    assert registry.next_free_index > 13  # avanzo mas alla de la corrida anterior


def test_students_who_finished_the_plan_are_migrated_to_graduated_before_the_next_run(
    base_dir: Path,
):
    # Un estudiante que ya aprobo todas las materias del plan, escrito
    # directamente en students/ (simula el resultado de una corrida previa).
    period = Period.parse("2026-01")
    graduate = Student(
        carnet="260099",
        apellidos="Rojas",
        nombre="Marta",
        grades=[
            GradeRecord(period=period, course_code=c.code, course_name=c.name, grade=95)
            for c in COURSES
        ],
    )
    write_student(base_dir, graduate)

    result = run_period(base_dir, period, seed=0, max_workers=1)

    # No se pide nada a nombre del graduado -- build_request_course_codes
    # devuelve [] para el una vez completo el plan -- y su expediente se
    # movio fuera de students/ antes de correr el pipeline de este periodo.
    assert not any(a.carnet == "260099" for a in result.summary.alerts)
    assert not (students_dir(base_dir) / "260099.md").exists()
    assert (graduated_dir(base_dir) / "260099.md").exists()

    students = load_all_students(base_dir)
    assert "260099" not in {s.carnet for s in students}
    assert count_graduated_students(base_dir) == 1

    # Una segunda corrida no vuelve a tocarlo: ya no esta en students/.
    run_period(base_dir, Period.parse("2026-02"), seed=0, max_workers=1)
    assert count_graduated_students(base_dir) == 1
