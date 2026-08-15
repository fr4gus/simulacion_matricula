"""`PhaseGate`: impone en Python el orden fijo de fases del PRD.

El agente LLM decide *cuando* llamar cada tool, pero no puede alterar la
secuencia real: cada tool wrapper (ver `tools.py`) llama
`gate.check_and_advance(phase)` antes de ejecutar su logica de negocio real.
Si el agente intenta invocar una fase fuera de orden (o una fase ya
completada), la tool devuelve un error explicativo en vez de ejecutar -- el
LLM puede leer el error y reintentar en el orden correcto, pero la corrida
subyacente nunca se desvia del pipeline de 11 pasos del PRD.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Orden fijo de fases (subset de los 11 pasos del PRD que corresponden a
# decisiones de negocio; los pasos puramente de lectura/emision de eventos no
# necesitan gate). `raise_alerts` es de solo lectura y esta exenta del gate
# (ver tools.py): se puede invocar en cualquier momento posterior a que
# existan alertas, sin avanzar ni bloquear la secuencia.
PHASE_ORDER: tuple[str, ...] = (
    "simulate_grades",
    "validate_requests",
    "compute_demand",
    "form_groups",
    "schedule_groups",
    "assign_students",
    "persist_results",
)


class PhaseOutOfOrderError(Exception):
    """El agente intento invocar una fase fuera de la secuencia del PRD."""

    def __init__(self, attempted: str, expected: str | None) -> None:
        self.attempted = attempted
        self.expected = expected
        if expected is None:
            message = (
                f"No se puede ejecutar '{attempted}': el pipeline ya completo todas "
                "las fases."
            )
        else:
            message = (
                f"No se puede ejecutar '{attempted}' todavia: la siguiente fase "
                f"esperada es '{expected}'. Invoca las tools en el orden del PRD."
            )
        super().__init__(message)


@dataclass
class PhaseGate:
    """Rastrea el progreso del pipeline y valida cada intento de avance."""

    _order: tuple[str, ...] = PHASE_ORDER
    _next_index: int = field(default=0, init=False)
    completed: list[str] = field(default_factory=list, init=False)

    @property
    def next_phase(self) -> str | None:
        if self._next_index >= len(self._order):
            return None
        return self._order[self._next_index]

    @property
    def is_complete(self) -> bool:
        return self._next_index >= len(self._order)

    def check_and_advance(self, phase: str) -> None:
        """Valida que `phase` sea la siguiente esperada y avanza el cursor.

        Lanza `PhaseOutOfOrderError` si `phase` no es la fase esperada en
        este momento (incluye el caso de re-invocar una fase ya completada,
        o de saltarse una fase pendiente).
        """
        expected = self.next_phase
        if phase != expected:
            raise PhaseOutOfOrderError(attempted=phase, expected=expected)
        self.completed.append(phase)
        self._next_index += 1
