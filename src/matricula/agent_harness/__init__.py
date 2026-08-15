"""Modo `--agents`: envuelve el pipeline determinista de `orchestration/` con un
orquestador real del Claude Agent SDK.

Este paquete NO reimplementa ninguna regla de negocio del PRD. Cada fase sigue
siendo la misma funcion pura de `orchestration/*` que usa el modo default
(`orchestration.runner.run_period`); lo unico que cambia es quien decide
*cuando* invocar cada fase: en el modo default es `run_period` en Python
llano, aqui es un agente LLM que llama esas mismas fases como *tools*, con
`gate.PhaseGate` obligando el mismo orden fijo del PRD por debajo.

Import perezoso: este paquete depende de `claude_agent_sdk` (dependencia
opcional, extra `agents`), asi que el modo default de la CLI no debe pagar ese
import ni requerir la dependencia instalada. `run_period_with_agent` se
resuelve solo cuando efectivamente se accede (via `__getattr__`), en vez de
importarse en la carga de este `__init__` -- eso mantiene importable a
`matricula.agent_harness.gate` (y a cualquier otro submodulo sin dependencia
dura del SDK) incluso sin `claude_agent_sdk` instalado.
"""

from __future__ import annotations

__all__ = ["run_period_with_agent"]


def __getattr__(name: str):
    if name == "run_period_with_agent":
        from matricula.agent_harness.orchestrator import run_period_with_agent

        return run_period_with_agent
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
