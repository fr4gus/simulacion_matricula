"""Periodo lectivo: formato YYYY-PP, orden, consecutividad.

No confundir con "cuatrimestre" (posicion en el plan de estudios).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from matricula.config import PERIODS_PER_YEAR

_PERIOD_RE = re.compile(r"^(\d{4})-(0[1-3])$")


class InvalidPeriodFormatError(ValueError):
    """El string de periodo no cumple el formato YYYY-PP (PP en 01..03)."""


@dataclass(frozen=True, order=True)
class Period:
    year: int
    number: int  # 1, 2 o 3

    @classmethod
    def parse(cls, text: str) -> Period:
        match = _PERIOD_RE.match(text)
        if not match:
            raise InvalidPeriodFormatError(
                f"Periodo invalido: {text!r}. Se esperaba el formato YYYY-PP, PP en 01-03."
            )
        year, number = match.groups()
        return cls(year=int(year), number=int(number))

    def __str__(self) -> str:
        return f"{self.year:04d}-{PERIODS_PER_YEAR[self.number - 1]}"

    def next(self) -> Period:
        if self.number == len(PERIODS_PER_YEAR):
            return Period(year=self.year + 1, number=1)
        return Period(year=self.year, number=self.number + 1)


def is_consecutive(previous: Period, candidate: Period) -> bool:
    """True si `candidate` es exactamente el periodo siguiente a `previous`."""
    return candidate == previous.next()
