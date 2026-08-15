from __future__ import annotations

from matricula.domain.models import GroupSchedule, ScheduleBlock
from matricula.domain.periods import Period
from matricula.orchestration.assignment import REASON_INDIVIDUAL_CONFLICT, assign_students


def _schedule(course, group, day, hour, minutes=200):
    return GroupSchedule(
        course_code=course,
        group_number=group,
        teacher=f"Prof {course}-{group}",
        classroom="AULA-100",
        blocks=[ScheduleBlock(day=day, start_hour=hour, duration_minutes=minutes)],
    )


def test_student_assigned_to_non_conflicting_courses():
    schedules = [
        _schedule("MA001", "01", day=0, hour=7),
        _schedule("CS002", "01", day=1, hour=7),
    ]
    carnets_by_group = {
        ("MA001", "01"): ["260001"],
        ("CS002", "01"): ["260001"],
    }
    course_names = {"MA001": "Matematicas I", "CS002": "Intro a Compu"}
    result = assign_students(Period.parse("2026-01"), schedules, carnets_by_group, course_names)
    assert len(result.matricula_by_carnet["260001"]) == 2
    assert result.alerts == []


def test_conflicting_courses_produce_alert_and_only_first_is_assigned():
    # El procesamiento por estudiante recorre sus materias en orden de codigo
    # (determinístico): "CS002" < "MA001", asi que CS002 se asigna primero y
    # MA001 (que choca con el bloque ya ocupado) genera la alerta.
    schedules = [
        _schedule("MA001", "01", day=0, hour=7),
        _schedule("CS002", "01", day=0, hour=7),  # mismo dia/hora -> choque
    ]
    carnets_by_group = {
        ("MA001", "01"): ["260001"],
        ("CS002", "01"): ["260001"],
    }
    course_names = {"MA001": "Matematicas I", "CS002": "Intro a Compu"}
    result = assign_students(Period.parse("2026-01"), schedules, carnets_by_group, course_names)
    assigned_codes = {e.course_code for e in result.matricula_by_carnet["260001"]}
    assert assigned_codes == {"CS002"}
    assert len(result.alerts) == 1
    assert result.alerts[0].reason == REASON_INDIVIDUAL_CONFLICT
    assert result.alerts[0].course_code == "MA001"


def test_group_without_schedule_produces_alert():
    carnets_by_group = {("MA001", "01"): ["260001"]}
    result = assign_students(
        Period.parse("2026-01"), [], carnets_by_group, {"MA001": "Matematicas I"}
    )
    assert result.matricula_by_carnet["260001"] == []
    assert len(result.alerts) == 1
    assert result.alerts[0].status == "Sin asignar"
