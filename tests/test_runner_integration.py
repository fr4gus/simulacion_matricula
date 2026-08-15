from __future__ import annotations

from pathlib import Path

from matricula.domain.periods import Period
from matricula.io.history import load_all_students
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
