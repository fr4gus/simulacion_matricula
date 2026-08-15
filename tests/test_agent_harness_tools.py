"""Tests de `agent_harness.tools`: cada tool debe delegar en la funcion pura
de `orchestration/*` correspondiente, sin reimplementar logica de negocio.

`claude_agent_sdk` no es una dependencia base del proyecto (extra opcional
"agents"), asi que estos tests instalan un stub minimo del paquete en
`sys.modules` antes de importar `agent_harness.tools` -- el stub imita la
forma real de `@tool` (devuelve un objeto tipo `SdkMcpTool` con `.name` y
`.handler`, no la funcion decorada) y de `create_sdk_mcp_server`, lo
suficiente para invocar cada handler como funcion async sin levantar
ninguna sesion real del SDK.
"""

from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path

import pytest


def _install_fake_claude_agent_sdk() -> None:
    if "claude_agent_sdk" in sys.modules:
        return
    fake = types.ModuleType("claude_agent_sdk")

    class _FakeSdkMcpTool:
        """Imita la forma real de `SdkMcpTool`: un objeto con `.name` y
        `.handler`, no la funcion decorada -- ver claude_agent_sdk.tool."""

        def __init__(self, name, description, input_schema, handler, annotations=None):
            self.name = name
            self.description = description
            self.input_schema = input_schema
            self.handler = handler
            self.annotations = annotations

    def tool(name, description, input_schema, annotations=None):
        def decorator(fn):
            return _FakeSdkMcpTool(name, description, input_schema, fn, annotations)

        return decorator

    def create_sdk_mcp_server(name, version="1.0.0", tools=None):
        return {"name": name, "version": version, "tools": list(tools or [])}

    fake.tool = tool
    fake.create_sdk_mcp_server = create_sdk_mcp_server
    sys.modules["claude_agent_sdk"] = fake


_install_fake_claude_agent_sdk()

from matricula.agent_harness.gate import PhaseGate  # noqa: E402
from matricula.agent_harness.state import PipelineState  # noqa: E402
from matricula.agent_harness.tools import build_tools  # noqa: E402
from matricula.domain.models import Student  # noqa: E402
from matricula.domain.periods import Period  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def state(tmp_path: Path) -> PipelineState:
    period = Period.parse("2026-01")
    s = PipelineState(base_dir=tmp_path, period=period, seed=0)
    s.prev_period = None
    s.students_by_carnet = {
        "260001": Student(carnet="260001", apellidos="Aguilar", nombre="Pedro"),
    }
    s.new_student_carnets = ["260001"]
    return s


@pytest.fixture
def tools_by_name(state: PipelineState):
    gate = PhaseGate()
    events: list[dict] = []
    _server, _allowed = build_tools(state, gate, max_workers=1, on_event=events.append)
    # server["tools"] son objetos _FakeSdkMcpTool (name + handler), no las
    # funciones decoradas -- imita la forma real de SdkMcpTool del SDK.
    return gate, events, _server


def test_simulate_grades_tool_delegates_to_worker_pool(state, tools_by_name):
    gate, events, server = tools_by_name
    fn = next(t for t in server["tools"] if t.name == "simulate_grades")

    result = _run(fn.handler({}))

    assert result.get("is_error") is not True
    assert gate.completed == ["simulate_grades"]
    assert "260001" in state.all_requests_by_student
    assert any(e["type"] == "run_started" for e in events)
    assert any(e["type"] == "pool_completed" for e in events)


def test_validate_requests_tool_out_of_order_returns_gate_error(state, tools_by_name):
    _gate, _events, server = tools_by_name
    fn = next(t for t in server["tools"] if t.name == "validate_requests")

    result = _run(fn.handler({}))

    assert result.get("is_error") is True
    assert "simulate_grades" in result["content"][0]["text"]


def test_validate_requests_tool_delegates_to_validation_module(state, tools_by_name):
    gate, _events, server = tools_by_name
    simulate = next(t for t in server["tools"] if t.name == "simulate_grades")
    validate = next(t for t in server["tools"] if t.name == "validate_requests")

    _run(simulate.handler({}))
    result = _run(validate.handler({}))

    assert result.get("is_error") is not True
    assert gate.completed == ["simulate_grades", "validate_requests"]
    # MA001 es materia de cuatrimestre 1, sin prerequisitos: debe validarse.
    assert state.requests_valid_count + state.requests_rejected_count > 0


def test_persist_results_tool_requires_full_sequence_first(state, tools_by_name):
    _gate, _events, server = tools_by_name
    fn = next(t for t in server["tools"] if t.name == "persist_results")

    result = _run(fn.handler({}))

    assert result.get("is_error") is True
    assert state.persisted is False


def test_raise_alerts_tool_is_read_only_and_does_not_touch_gate(state, tools_by_name):
    gate, _events, server = tools_by_name
    from matricula.domain.models import Alert

    state.alerts.append(
        Alert(carnet="260001", course_code="MA001", reason="test", status="Rechazada")
    )
    fn = next(t for t in server["tools"] if t.name == "raise_alerts")

    result = _run(fn.handler({}))

    assert result.get("is_error") is not True
    assert "260001" in result["content"][0]["text"]
    assert gate.completed == []  # no avanza el pipeline
    assert gate.next_phase == "simulate_grades"


def test_full_sequence_runs_all_phases_and_persists(state, tools_by_name):
    gate, _events, server = tools_by_name
    handlers = {t.name: t for t in server["tools"]}

    for phase in (
        "simulate_grades",
        "validate_requests",
        "compute_demand",
        "form_groups",
        "schedule_groups",
        "assign_students",
        "persist_results",
    ):
        result = _run(handlers[phase].handler({}))
        assert result.get("is_error") is not True, f"{phase} fallo: {result}"

    assert gate.is_complete
    assert state.persisted is True
    assert state.summary is not None
    assert (state.base_dir / "students" / "260001.md").exists()
    assert (state.base_dir / "periodos_lectivos" / "2026-01.md").exists()
