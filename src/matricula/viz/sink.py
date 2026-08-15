"""Destinos posibles para los eventos que emite `run_period(..., on_event=...)`.

`EventSink` es la interfaz comun (solo `.emit(event: dict) -> None`) que
satisface el parametro `on_event` de `run_period` sin importar de donde venga
el servidor que finalmente muestra los eventos:

- `InProcessSink`: el servidor vive en el mismo proceso Python que la corrida
  (comportamiento historico de `matricula run --visualize`, cuando no hay un
  servidor `matricula viz` standalone ya corriendo).
- `HttpSink`: el servidor vive en OTRO proceso (`matricula viz`, ya corriendo
  de antemano); los eventos se empujan via `POST /publish`.
- `DelayingSink`: decorador que envuelve cualquier otro sink y agrega una
  pausa artificial antes de reenviar cada evento, solo para demos (`--demo-delay`).
  No afecta el resultado de la corrida: `run_period` ya termino de computar
  cada fase antes de llamar a `emit(...)`, asi que dormir aqui solo retrasa
  el reloj de pared, nunca el contenido de lo que se escribe a disco.

Solo stdlib - sin dependencias de runtime nuevas.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from typing import Protocol

# Eventos de "tick" frecuente (uno por estudiante procesado por el pool);
# reciben una fraccion del delay para que la barra de progreso avance de
# forma fluida en vez de a saltos largos.
_POOL_TICK_SCALE = 0.3


class EventSink(Protocol):
    def emit(self, event: dict) -> None: ...


class InProcessSink:
    """Reenvia eventos a un `ServerHandle` que vive en este mismo proceso."""

    def __init__(self, server) -> None:  # server: viz.server.ServerHandle
        self._server = server

    def emit(self, event: dict) -> None:
        self._server.emit(event)


class HttpSink:
    """Reenvia eventos a un servidor de matricula-viz corriendo en otro proceso."""

    def __init__(self, base_url: str, timeout: float = 2.0) -> None:
        self._publish_url = base_url.rstrip("/") + "/publish"
        self._timeout = timeout
        self._warned = False

    def emit(self, event: dict) -> None:
        body = json.dumps(event).encode()
        request = urllib.request.Request(
            self._publish_url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout):
                pass
        except (urllib.error.URLError, OSError) as exc:
            # Perder el visualizador nunca debe abortar ni alterar la
            # corrida real (mismo contrato que on_event=None): se avisa una
            # sola vez para no inundar stderr si el servidor cae a mitad de
            # una corrida larga.
            if not self._warned:
                print(
                    f"Aviso: no se pudo enviar eventos al visualizador ({exc}); "
                    "la corrida continua normalmente.",
                    file=sys.stderr,
                )
                self._warned = True


class DelayingSink:
    """Envuelve otro sink agregando una pausa artificial, solo para demos."""

    def __init__(self, inner: EventSink, delay: float) -> None:
        self._inner = inner
        self._delay = delay

    def emit(self, event: dict) -> None:
        scale = _POOL_TICK_SCALE if event.get("type") == "pool_progress" else 1.0
        time.sleep(self._delay * scale)
        self._inner.emit(event)
