from __future__ import annotations

from pathlib import Path

from matricula.domain.models import Alert
from matricula.io.period_md import (
    HorarioRow,
    PeriodRecord,
    RosterEntry,
    read_period,
    write_period,
)


def test_roundtrip_full_period(base_dir: Path):
    record = PeriodRecord(
        period_str="2026-01",
        horario=[
            HorarioRow("MA001", "Matematicas I", "01", "Juan Perez", "AULA-100", "L 07:00-09:20"),
            HorarioRow("CS002", "Intro a Compu", "01", "Ana Solis", "AULA-101", "M 09:00-11:20"),
        ],
        rosters={
            "MA001-01": [
                RosterEntry("250005", "Aguilar Jimenes", "Pedro"),
                RosterEntry("260015", "Benavides Perez", "Juan"),
            ],
            "MA001-02": [RosterEntry("260020", "Campos Solano", "Ana")],
        },
        alertas=[Alert("260031", "CS004", "Prerrequisito no cumplido", "Rechazada")],
    )
    write_period(base_dir, record)
    loaded = read_period(base_dir / "periodos_lectivos" / "2026-01.md")

    assert loaded.period_str == "2026-01"
    assert len(loaded.horario) == 2
    assert loaded.horario[0].course_code == "MA001"
    assert loaded.horario[0].horario == "L 07:00-09:20"

    assert set(loaded.rosters) == {"MA001-01", "MA001-02"}
    assert [e.carnet for e in loaded.rosters["MA001-01"]] == ["250005", "260015"]
    assert [e.carnet for e in loaded.rosters["MA001-02"]] == ["260020"]

    assert len(loaded.alertas) == 1
    assert loaded.alertas[0].carnet == "260031"
    assert loaded.alertas[0].reason == "Prerrequisito no cumplido"


def test_groups_are_not_mixed_across_courses(base_dir: Path):
    record = PeriodRecord(
        period_str="2026-01",
        rosters={
            "MA001-01": [RosterEntry("260001", "A", "A")],
            "CS002-01": [RosterEntry("260002", "B", "B")],
        },
    )
    write_period(base_dir, record)
    loaded = read_period(base_dir / "periodos_lectivos" / "2026-01.md")
    assert loaded.rosters["MA001-01"] != loaded.rosters["CS002-01"]
    assert len(loaded.rosters["MA001-01"]) == 1
    assert len(loaded.rosters["CS002-01"]) == 1


def test_empty_period_roundtrip(base_dir: Path):
    record = PeriodRecord(period_str="2026-01")
    write_period(base_dir, record)
    loaded = read_period(base_dir / "periodos_lectivos" / "2026-01.md")
    assert loaded.horario == []
    assert loaded.rosters == {}
    assert loaded.alertas == []
