from __future__ import annotations

import time

from matricula.viz.server import start
from matricula.viz.sink import DelayingSink, HttpSink, InProcessSink


def test_in_process_sink_calls_server_emit_directly():
    server = start(port=0)
    try:
        received = []
        queue = server._broadcaster.subscribe()  # acceso directo solo para el test
        sink = InProcessSink(server)
        sink.emit({"type": "run_started", "period": "2026-01"})
        received.append(queue.get(timeout=2))
        assert received == [{"type": "run_started", "period": "2026-01"}]
    finally:
        server.stop()


def test_http_sink_publishes_to_real_server():
    server = start(port=0)
    try:
        queue = server._broadcaster.subscribe()
        sink = HttpSink(f"http://127.0.0.1:{server.port}")
        sink.emit({"type": "pool_progress", "completed": 1, "total": 10})
        event = queue.get(timeout=2)
        assert event == {"type": "pool_progress", "completed": 1, "total": 10}
    finally:
        server.stop()


def test_http_sink_does_not_raise_when_server_unreachable():
    # Puerto sin nada escuchando: emit() no debe lanzar (contrato:
    # perder el visualizador nunca debe afectar la corrida real).
    sink = HttpSink("http://127.0.0.1:1", timeout=0.3)
    sink.emit({"type": "run_started"})  # no debe lanzar


def test_delaying_sink_zero_delay_never_sleeps(monkeypatch):
    calls = []
    monkeypatch.setattr(time, "sleep", lambda s: calls.append(s))

    inner_events = []
    inner = type("Inner", (), {"emit": lambda self, e: inner_events.append(e)})()
    sink = DelayingSink(inner, delay=0.0)
    sink.emit({"type": "run_started"})

    assert calls == [0.0]  # sleep(0) se llama pero no pausa de forma perceptible
    assert inner_events == [{"type": "run_started"}]


def test_delaying_sink_scales_pool_progress_shorter_than_phase_events(monkeypatch):
    calls = []
    monkeypatch.setattr(time, "sleep", lambda s: calls.append(s))

    inner = type("Inner", (), {"emit": lambda self, e: None})()
    sink = DelayingSink(inner, delay=1.0)

    sink.emit({"type": "pool_progress", "completed": 1, "total": 10})
    sink.emit({"type": "validation_done", "valid": 1, "rejected": 0})

    assert calls[0] < calls[1]  # pool_progress duerme menos que un evento de fase
    assert calls[1] == 1.0
