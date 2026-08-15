from __future__ import annotations

from pathlib import Path

from matricula.domain.periods import Period
from matricula.orchestration.runner import run_period


def test_run_period_without_on_event_is_unaffected(base_dir: Path):
    """Omitir on_event debe comportarse exactamente igual que antes de instrumentar."""
    result = run_period(base_dir, Period.parse("2026-01"), seed=0, max_workers=1)
    assert result.summary.students_created == 10


def test_event_sequence_matches_pipeline_order(base_dir: Path):
    events: list[dict] = []
    run_period(base_dir, Period.parse("2026-01"), seed=0, max_workers=1, on_event=events.append)

    types = [e["type"] for e in events]

    # run_started es siempre el primero.
    assert types[0] == "run_started"

    # pool_progress aparece 0+ veces, seguido de exactamente un pool_completed.
    first_pool_completed = types.index("pool_completed")
    assert all(t == "pool_progress" for t in types[1:first_pool_completed])

    # Tras el pool, el resto de fases ocurre en este orden exacto (ignorando
    # los eventos "alerts" intercalados, que son opcionales segun haya o no
    # alertas nuevas en cada fase).
    remaining = [t for t in types[first_pool_completed + 1 :] if t != "alerts"]
    assert remaining == [
        "validation_done",
        "demand_done",
        "grouping_done",
        "scheduling_done",
        "assignment_done",
        "run_completed",
        "cuatrimestre_summary",
    ]

    # cuatrimestre_summary es siempre el ultimo evento (censo global emitido
    # despues del resumen de esta corrida).
    assert types[-1] == "cuatrimestre_summary"


def test_pool_progress_reaches_total_and_counts_are_consistent(base_dir: Path):
    events: list[dict] = []
    run_period(base_dir, Period.parse("2026-01"), seed=0, max_workers=2, on_event=events.append)

    pool_progress_events = [e for e in events if e["type"] == "pool_progress"]
    assert len(pool_progress_events) == 10  # un evento por estudiante
    assert pool_progress_events[-1]["completed"] == 10
    assert all(e["total"] == 10 for e in pool_progress_events)

    pool_completed = next(e for e in events if e["type"] == "pool_completed")
    assert pool_completed["completed"] == 10
    assert pool_completed["errors"] == 0


def test_event_payloads_match_final_summary(base_dir: Path):
    events: list[dict] = []
    result = run_period(
        base_dir, Period.parse("2026-01"), seed=0, max_workers=1, on_event=events.append
    )
    summary = result.summary

    validation_done = next(e for e in events if e["type"] == "validation_done")
    assert validation_done["valid"] == summary.requests_valid
    assert validation_done["rejected"] == summary.requests_rejected

    demand_done = next(e for e in events if e["type"] == "demand_done")
    assert demand_done["opened"] == summary.courses_opened
    assert demand_done["closed"] == summary.courses_closed

    grouping_done = next(e for e in events if e["type"] == "grouping_done")
    assert grouping_done["groups_formed"] == summary.groups_formed

    run_completed = next(e for e in events if e["type"] == "run_completed")
    assert run_completed["summary"]["groups_formed"] == summary.groups_formed
    assert run_completed["summary"]["exit_code"] == summary.exit_code
    assert run_completed["summary"]["total_alerts"] == len(summary.alerts)


def test_cuatrimestre_summary_payload_shape(base_dir: Path):
    from matricula.domain.study_plan import MAX_CUATRIMESTRE

    events: list[dict] = []
    run_period(base_dir, Period.parse("2026-01"), seed=0, max_workers=1, on_event=events.append)

    census = next(e for e in events if e["type"] == "cuatrimestre_summary")
    assert set(census["cuatrimestre_counts"]) == {
        f"cuatrimestre_{n}" for n in range(1, MAX_CUATRIMESTRE + 1)
    }
    total_from_counts = sum(census["cuatrimestre_counts"].values()) + census["graduados"]
    assert total_from_counts == census["total_students"]
    assert census["total_students"] == 10  # bootstrap: solo los 10 estudiantes nuevos


def test_cuatrimestre_summary_counts_all_students_not_just_this_run(base_dir: Path):
    # Corrida 1: crea los primeros 10 estudiantes (cuatrimestre 1).
    run_period(base_dir, Period.parse("2026-01"), seed=0, max_workers=1)

    # Corrida 2: crea 10 estudiantes MAS. El censo de esta segunda corrida
    # debe reflejar los 20 en total, no solo los 10 nuevos de este periodo.
    events: list[dict] = []
    run_period(base_dir, Period.parse("2026-02"), seed=0, max_workers=1, on_event=events.append)

    census = next(e for e in events if e["type"] == "cuatrimestre_summary")
    assert census["total_students"] == 20


def test_alert_events_carry_only_new_alerts_not_accumulated(base_dir: Path):
    events: list[dict] = []
    result = run_period(
        base_dir, Period.parse("2026-01"), seed=0, max_workers=1, on_event=events.append
    )

    alert_events = [e for e in events if e["type"] == "alerts"]
    total_from_events = sum(len(e["alerts"]) for e in alert_events)
    # La suma de todas las alertas "nuevas" repartidas entre eventos debe dar
    # exactamente el total final (nunca duplicadas, nunca repetido el
    # acumulado completo en cada evento).
    assert total_from_events == len(result.summary.alerts)

    for event in alert_events:
        for alert in event["alerts"]:
            assert set(alert.keys()) == {"carnet", "course_code", "reason", "status"}
