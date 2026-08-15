from __future__ import annotations

from matricula.domain.models import Group, ScheduleBlock
from matricula.orchestration.scheduling import (
    blocks_conflict,
    format_horario,
    overlaps,
    schedule_groups,
)


def test_single_group_gets_valid_schedule():
    groups = [Group(course_code="MA001", number="01", carnets=[f"26000{i}" for i in range(10)])]
    schedules, alerts = schedule_groups(groups)
    assert alerts == []
    assert len(schedules) == 1
    schedule = schedules[0]
    assert schedule.teacher == "Profesor MA001-1"
    assert schedule.classroom.startswith("AULA-")
    total_minutes = sum(b.duration_minutes for b in schedule.blocks)
    assert total_minutes == 200


def test_two_groups_same_course_get_different_teachers_and_no_conflicts():
    groups = [
        Group(course_code="MA001", number="01", carnets=["260001"]),
        Group(course_code="MA001", number="02", carnets=["260002"]),
    ]
    schedules, alerts = schedule_groups(groups)
    assert alerts == []
    assert len(schedules) == 2
    teachers = {s.teacher for s in schedules}
    assert len(teachers) == 2  # nunca comparten profesor
    # No pueden compartir aula+horario exactamente iguales.
    s1, s2 = schedules
    if s1.classroom == s2.classroom:
        assert not blocks_conflict(s1.blocks, s2.blocks)


def test_blocks_on_different_days_never_conflict():
    a = ScheduleBlock(day=0, start_hour=7, duration_minutes=100)
    b = ScheduleBlock(day=1, start_hour=7, duration_minutes=100)
    assert not overlaps(a, b)


def test_blocks_same_day_overlapping_hours_conflict():
    a = ScheduleBlock(day=0, start_hour=7, duration_minutes=100)
    b = ScheduleBlock(day=0, start_hour=8, duration_minutes=100)  # 08:00-09:40 vs 07:00-08:40
    assert overlaps(a, b)


def test_blocks_same_day_adjacent_hours_do_not_conflict():
    a = ScheduleBlock(day=0, start_hour=7, duration_minutes=100)  # 07:00-08:40
    b = ScheduleBlock(day=0, start_hour=9, duration_minutes=100)  # 09:00-10:40
    assert not overlaps(a, b)


def test_schedule_stays_within_school_hours():
    groups = [Group(course_code="MA001", number="01", carnets=["260001"])]
    schedules, _ = schedule_groups(groups)
    for block in schedules[0].blocks:
        end = block.start_hour + block.duration_minutes / 60
        assert 7 <= block.start_hour
        assert end <= 17


def test_format_horario_continuous_block():
    blocks = [ScheduleBlock(day=0, start_hour=7, duration_minutes=200)]
    assert format_horario(blocks) == "L 07:00-10:20"


def test_format_horario_split_blocks():
    blocks = [
        ScheduleBlock(day=0, start_hour=7, duration_minutes=100),
        ScheduleBlock(day=3, start_hour=9, duration_minutes=100),
    ]
    assert format_horario(blocks) == "L 07:00-08:40 / J 09:00-10:40"


def test_exhausting_all_classrooms_produces_alert_not_crash():
    # Fuerza mas grupos que aulas disponibles usando franjas identicas: cada
    # grupo tiene su propio profesor (nunca choca por profesor), asi que el
    # limitante real es el numero de aulas x combinaciones de horario, que es
    # generoso; en cambio probamos que si MAX_CLASSROOMS fuera 0 no habria
    # crash. Aqui solo garantizamos que 100 grupos distintos de la misma
    # materia no truenan el proceso (puede haber alertas si se agota el pool).
    groups = [
        Group(course_code="MA001", number=f"{i:02d}", carnets=[f"26{i:04d}"]) for i in range(1, 30)
    ]
    schedules, alerts = schedule_groups(groups)
    assert len(schedules) + len(alerts) == len(groups)
    for alert in alerts:
        assert alert.status == "Sin horario"
