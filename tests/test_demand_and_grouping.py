from __future__ import annotations

from matricula.domain.models import Request, RequestStatus, Student
from matricula.orchestration.demand import compute_demand
from matricula.orchestration.grouping import form_groups, rank_by_priority


def _valid(carnet, code):
    return Request(carnet, code, RequestStatus.VALID)


def test_course_closes_below_minimum():
    requests = [_valid(f"26000{i}", "MA001") for i in range(1, 5)]  # 4 solicitudes
    result = compute_demand(requests)
    assert "MA001" not in result.open_courses
    assert result.closed_courses["MA001"] == [f"26000{i}" for i in range(1, 5)]


def test_course_opens_at_exactly_minimum():
    requests = [_valid(f"26000{i}", "MA001") for i in range(1, 6)]  # 5 solicitudes
    result = compute_demand(requests)
    assert result.open_courses["MA001"] == [f"26000{i}" for i in range(1, 6)]


def test_rejected_requests_are_ignored_in_demand():
    requests = [
        _valid("260001", "MA001"),
        Request("260002", "MA001", RequestStatus.REJECTED, "algo"),
    ]
    result = compute_demand(requests)
    assert "MA001" not in result.open_courses  # solo 1 valida, < 5


def test_group_count_ceil_and_capacity():
    carnets = [f"{260000 + i}" for i in range(15)]
    groups = form_groups("MA001", carnets)
    assert len(groups) == 2  # ceil(15/10) = 2
    sizes = sorted(len(g.carnets) for g in groups)
    assert sizes == [7, 8]  # diferencia maxima de 1
    assert sum(len(g.carnets) for g in groups) == 15


def test_single_group_when_at_or_under_capacity():
    carnets = [f"{260000 + i}" for i in range(10)]
    groups = form_groups("MA001", carnets)
    assert len(groups) == 1
    assert len(groups[0].carnets) == 10
    assert groups[0].number == "01"


def test_no_groups_for_empty_admission():
    assert form_groups("MA001", []) == []


def test_priority_ranking_average_desc_then_carnet_asc():
    high = Student(carnet="260002", apellidos="A", nombre="A")
    high.grades = []
    from matricula.domain.models import GradeRecord
    from matricula.domain.periods import Period

    high.grades = [GradeRecord(Period.parse("2026-01"), "MA001", "M1", 90)]

    low = Student(carnet="260001", apellidos="B", nombre="B")
    low.grades = [GradeRecord(Period.parse("2026-01"), "MA001", "M1", 70)]

    tie_a = Student(carnet="260003", apellidos="C", nombre="C")
    tie_a.grades = [GradeRecord(Period.parse("2026-01"), "MA001", "M1", 80)]
    tie_b = Student(carnet="260004", apellidos="D", nombre="D")
    tie_b.grades = [GradeRecord(Period.parse("2026-01"), "MA001", "M1", 80)]

    ranked = rank_by_priority([low, tie_b, high, tie_a])
    assert [s.carnet for s in ranked] == ["260002", "260003", "260004", "260001"]
