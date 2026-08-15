from __future__ import annotations

import pytest

from matricula.domain.periods import InvalidPeriodFormatError, Period, is_consecutive


def test_parse_and_str_roundtrip():
    p = Period.parse("2026-01")
    assert p.year == 2026
    assert p.number == 1
    assert str(p) == "2026-01"


@pytest.mark.parametrize("text", ["2026-00", "2026-04", "26-01", "2026/01", "abcd-01", ""])
def test_parse_rejects_invalid_format(text):
    with pytest.raises(InvalidPeriodFormatError):
        Period.parse(text)


def test_next_rolls_over_year_after_period_03():
    assert Period.parse("2026-03").next() == Period.parse("2027-01")


def test_next_increments_within_year():
    assert Period.parse("2026-01").next() == Period.parse("2026-02")
    assert Period.parse("2026-02").next() == Period.parse("2026-03")


def test_is_consecutive_true_case():
    assert is_consecutive(Period.parse("2026-01"), Period.parse("2026-02"))
    assert is_consecutive(Period.parse("2026-03"), Period.parse("2027-01"))


def test_is_consecutive_false_cases():
    assert not is_consecutive(Period.parse("2026-01"), Period.parse("2026-03"))
    assert not is_consecutive(Period.parse("2026-01"), Period.parse("2026-01"))
    assert not is_consecutive(Period.parse("2026-02"), Period.parse("2026-01"))


def test_period_ordering():
    assert Period.parse("2026-01") < Period.parse("2026-02")
    assert Period.parse("2026-03") < Period.parse("2027-01")
