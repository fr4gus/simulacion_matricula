"""Servidor local minimo (HTTP + Server-Sent Events) para ver una corrida en vivo.

Sirve dos rutas:
  GET /        -> el frontend estatico (static/index.html)
  GET /events  -> stream `text/event-stream` con los eventos emitidos por
                  `run_period(..., on_event=...)`, uno por linea `data: <json>`.

No hay buffer/replay de historial: un cliente que se conecta despues del
inicio de la corrida solo ve eventos desde ese momento en adelante (decision
de diseno confirmada: mantiene el servidor simple, sin estado persistente).

Solo stdlib (http.server, socketserver, queue, threading) - no agrega
dependencias de runtime al proyecto.
"""

from __future__ import annotations

import json
import queue
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

_STATIC_DIR = Path(__file__).parent / "static"
_INDEX_HTML_PATH = _STATIC_DIR / "index.html"


class _Broadcaster:
    """Reparte cada evento emitido a todas las colas de clientes SSE conectados."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._client_queues: list[queue.Queue] = []

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue()
        with self._lock:
            self._client_queues.append(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            if q in self._client_queues:
                self._client_queues.remove(q)

    def publish(self, event: dict) -> None:
        with self._lock:
            targets = list(self._client_queues)
        for q in targets:
            q.put(event)


def _make_handler(broadcaster: _Broadcaster) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:  # noqa: A002 - firma stdlib
            pass  # silencia el log de acceso por defecto; ver server.py docstring

        def do_GET(self) -> None:  # noqa: N802 - nombre requerido por BaseHTTPRequestHandler
            if self.path == "/":
                self._serve_index()
            elif self.path == "/events":
                self._serve_events()
            else:
                self.send_error(404, "No encontrado")

        def _serve_index(self) -> None:
            body = _INDEX_HTML_PATH.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _serve_events(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()

            client_queue = broadcaster.subscribe()
            try:
                while True:
                    event = client_queue.get()  # bloquea hasta el proximo evento
                    payload = f"data: {json.dumps(event)}\n\n".encode()
                    self.wfile.write(payload)
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                broadcaster.unsubscribe(client_queue)

    return Handler


class ServerHandle:
    """Handle devuelto por `start()`: permite emitir eventos y detener el servidor."""

    def __init__(
        self, httpd: ThreadingHTTPServer, broadcaster: _Broadcaster, thread: threading.Thread
    ):
        self._httpd = httpd
        self._broadcaster = broadcaster
        self._thread = thread

    @property
    def port(self) -> int:
        return self._httpd.server_address[1]

    def emit(self, event: dict) -> None:
        self._broadcaster.publish(event)

    def stop(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
        self._thread.join(timeout=5)


def start(port: int = 8765, host: str = "127.0.0.1") -> ServerHandle:
    """Arranca el servidor en un hilo daemon y retorna un handle listo para usar.

    Si el puerto ya esta en uso, `OSError` se propaga de inmediato (fail-fast)
    en vez de colgarse.
    """
    broadcaster = _Broadcaster()
    handler_cls = _make_handler(broadcaster)
    httpd = ThreadingHTTPServer((host, port), handler_cls)

    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    return ServerHandle(httpd, broadcaster, thread)
