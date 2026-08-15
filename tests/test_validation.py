from __future__ import annotations

from matricula.domain.models import GradeRecord, Student
from matricula.domain.models import RequestStatus as Status
from matricula.domain.periods import Period
from matricula.orchestration.validation import (
    REASON_ALREADY_PASSED,
    REASON_DUPLICATE,
    REASON_PREREQUISITE_NOT_MET,
    REASON_UNKNOWN_COURSE,
    validate_requests,
)


def test_valid_request_new_student():
    student = Student(carnet="260001", apellidos="A", nombre="A")
    results = validate_requests(student, ["MA001"])
    assert results[0].status == Status.VALID


def test_rejected_prerequisite_not_met():
    student = Student(carnet="260002", apellidos="B", nombre="B")
    results = validate_requests(student, ["CS003"])
    assert results[0].status == Status.REJECTED
    assert results[0].reason == REASON_PREREQUISITE_NOT_MET


def test_rejected_already_passed_and_not_retake():
    student = Student(
        carnet="260003",
        apellidos="C",
        nombre="C",
        grades=[GradeRecord(Period.parse("2026-01"), "MA001", "Matematicas I", 90)],
    )
    results = validate_requests(student, ["MA001"])
    assert results[0].status == Status.REJECTED
    assert results[0].reason == REASON_ALREADY_PASSED


def test_valid_retake_after_failing():
    student = Student(
        carnet="260004",
        apellidos="D",
        nombre="D",
        grades=[GradeRecord(Period.parse("2026-01"), "MA001", "Matematicas I", 40)],
    )
    results = validate_requests(student, ["MA001"])
    assert results[0].status == Status.VALID


def test_rejected_duplicate_request():
    student = Student(carnet="260005", apellidos="E", nombre="E")
    results = validate_requests(student, ["MA001", "MA001"])
    assert results[0].status == Status.VALID
    assert results[1].status == Status.REJECTED
    assert results[1].reason == REASON_DUPLICATE


def test_rejected_unknown_course_code():
    student = Student(carnet="260006", apellidos="F", nombre="F")
    results = validate_requests(student, ["ZZ999"])
    assert results[0].status == Status.REJECTED
    assert results[0].reason == REASON_UNKNOWN_COURSE


def test_prerequisites_met_allows_request():
    student = Student(
        carnet="260007",
        apellidos="G",
        nombre="G",
        grades=[
            GradeRecord(Period.parse("2026-01"), "MA001", "Matematicas I", 90),
            GradeRecord(Period.parse("2026-01"), "CS002", "Intro a Compu", 90),
        ],
    )
    results = validate_requests(student, ["CS003"])
    assert results[0].status == Status.VALID
