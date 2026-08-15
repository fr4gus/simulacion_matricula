from __future__ import annotations

import pytest

from matricula.agent_harness.gate import PHASE_ORDER, PhaseGate, PhaseOutOfOrderError


def test_gate_starts_with_first_phase_expected():
    gate = PhaseGate()
    assert gate.next_phase == PHASE_ORDER[0]
    assert not gate.is_complete
    assert gate.completed == []


def test_gate_advances_through_full_sequence_in_order():
    gate = PhaseGate()
    for phase in PHASE_ORDER:
        gate.check_and_advance(phase)
    assert gate.is_complete
    assert gate.next_phase is None
    assert gate.completed == list(PHASE_ORDER)


def test_gate_rejects_phase_invoked_out_of_order():
    gate = PhaseGate()
    with pytest.raises(PhaseOutOfOrderError):
        gate.check_and_advance(PHASE_ORDER[1])
    # El intento fallido no debe avanzar el cursor.
    assert gate.next_phase == PHASE_ORDER[0]
    assert gate.completed == []


def test_gate_rejects_repeating_an_already_completed_phase():
    gate = PhaseGate()
    gate.check_and_advance(PHASE_ORDER[0])
    with pytest.raises(PhaseOutOfOrderError):
        gate.check_and_advance(PHASE_ORDER[0])
    assert gate.completed == [PHASE_ORDER[0]]


def test_gate_rejects_any_phase_after_pipeline_complete():
    gate = PhaseGate()
    for phase in PHASE_ORDER:
        gate.check_and_advance(phase)
    with pytest.raises(PhaseOutOfOrderError) as exc_info:
        gate.check_and_advance(PHASE_ORDER[-1])
    assert exc_info.value.expected is None


def test_out_of_order_error_message_names_expected_phase():
    gate = PhaseGate()
    with pytest.raises(PhaseOutOfOrderError) as exc_info:
        gate.check_and_advance("compute_demand")
    assert exc_info.value.attempted == "compute_demand"
    assert exc_info.value.expected == PHASE_ORDER[0]
    assert PHASE_ORDER[0] in str(exc_info.value)
