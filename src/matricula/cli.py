"""CLI: `matricula run <periodo> [...]` y `matricula viz [...]`."""

from __future__ import annotations

import argparse
import signal
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

from matricula.domain.periods import InvalidPeriodFormatError, Period, is_consecutive
from matricula.io.history import latest_period
from matricula.orchestration.runner import run_period
from matricula.reporting.summary import EXIT_ABORTED, EXIT_CLEAN, print_summary

DEFAULT_SEED = 0
DEFAULT_VIZ_PORT = 8765
HEALTH_CHECK_TIMEOUT = 0.5


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="matricula")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Corre el proceso de matricula de un periodo")
    run_parser.add_argument("period", help="Periodo lectivo en formato YYYY-PP (PP: 01-03)")
    run_parser.add_argument(
        "--seed", type=int, default=DEFAULT_SEED, help="Semilla RNG (default: 0)"
    )
    run_parser.add_argument(
        "--base-dir",
        type=Path,
        default=Path("."),
        help="Directorio raiz para students/ y periodos_lectivos/ (default: .)",
    )
    run_parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Numero de procesos del pool (default: os.cpu_count())",
    )
    run_parser.add_argument(
        "--visualize",
        action="store_true",
        help="Muestra el progreso en tiempo real. Se conecta a un servidor "
        "'matricula viz' ya corriendo en --viz-port si existe; si no, "
        "levanta uno propio solo para esta corrida.",
    )
    run_parser.add_argument(
        "--viz-port",
        type=int,
        default=DEFAULT_VIZ_PORT,
        help=f"Puerto del servidor de visualizacion (default: {DEFAULT_VIZ_PORT})",
    )
    run_parser.add_argument(
        "--demo-delay",
        type=float,
        default=0.0,
        help="Retraso artificial en segundos entre eventos del visualizador, "
        "para demos (default: 0, sin retraso; solo tiene efecto junto a "
        "--visualize)",
    )

    viz_parser = subparsers.add_parser(
        "viz", help="Levanta el servidor de visualizacion de forma independiente"
    )
    viz_parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_VIZ_PORT,
        help=f"Puerto donde escuchar (default: {DEFAULT_VIZ_PORT})",
    )
    viz_parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host donde escuchar (default: 127.0.0.1)",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "run":
        return _run(args)
    if args.command == "viz":
        return _viz(args)

    parser.print_help(sys.stderr)
    return EXIT_ABORTED


def _run(args: argparse.Namespace) -> int:
    try:
        period = Period.parse(args.period)
    except InvalidPeriodFormatError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_ABORTED

    base_dir: Path = args.base_dir
    prev = latest_period(base_dir)
    if prev is not None and not is_consecutive(prev, period):
        print(
            f"Error: periodo no consecutivo. Ultimo periodo almacenado: {prev}, "
            f"se esperaba {prev.next()}, se recibio {period}.",
            file=sys.stderr,
        )
        return EXIT_ABORTED

    server = None
    on_event = None
    if args.visualize:
        sink, server, error = _build_sink(args.viz_port)
        if error is not None:
            print(error, file=sys.stderr)
            return EXIT_ABORTED
        if args.demo_delay > 0:
            from matricula.viz.sink import DelayingSink

            sink = DelayingSink(sink, args.demo_delay)
        on_event = sink.emit

    try:
        result = run_period(
            base_dir, period, seed=args.seed, max_workers=args.workers, on_event=on_event
        )
    finally:
        if server is not None:
            server.stop()

    print_summary(result.summary)
    return result.summary.exit_code


def _build_sink(port: int):
    """Decide si conectarse a un servidor `matricula viz` ya corriendo en
    `port`, o levantar uno propio (comportamiento historico), o abortar si el
    puerto esta ocupado por algo que no es un servidor de matricula-viz.

    Retorna (sink, server_or_None, error_message_or_None). `server` solo se
    llena cuando el llamador es dueno del ciclo de vida del servidor (debe
    detenerlo al terminar); si es None, el servidor pertenece a otro proceso
    y no debe tocarse.
    """
    from matricula.viz.server import start as start_viz_server
    from matricula.viz.sink import HttpSink, InProcessSink

    health_url = f"http://127.0.0.1:{port}/health"
    try:
        with urllib.request.urlopen(health_url, timeout=HEALTH_CHECK_TIMEOUT) as response:
            if response.status == 200:
                base_url = f"http://127.0.0.1:{port}"
                return HttpSink(base_url), None, None
            error = (
                f"Error: el puerto {port} esta en uso por otro proceso "
                "(no parece un servidor de matricula viz)."
            )
            return None, None, error
    except urllib.error.HTTPError:
        # El puerto respondio HTTP pero con un codigo de error (ej. 404): hay
        # *algo* escuchando ahi, pero no es nuestro servidor (que siempre
        # responde 200 en /health). No debe tratarse como "puerto libre".
        error = (
            f"Error: el puerto {port} esta en uso por otro proceso "
            "(no parece un servidor de matricula viz)."
        )
        return None, None, error
    except TimeoutError:
        error = (
            f"Error: el puerto {port} esta en uso por otro proceso "
            "(no respondio a tiempo, no parece un servidor de matricula viz)."
        )
        return None, None, error
    except urllib.error.URLError:
        pass  # nadie escucha en el puerto (conexion rechazada): levantamos uno propio

    try:
        server = start_viz_server(port=port)
    except OSError as exc:
        error = f"Error: no se pudo iniciar el visualizador en el puerto {port}: {exc}"
        return None, None, error

    print(f"Visualizador: http://127.0.0.1:{server.port}", file=sys.stderr)
    return InProcessSink(server), server, None


def _viz(args: argparse.Namespace) -> int:
    from matricula.viz.server import start as start_viz_server

    try:
        server = start_viz_server(port=args.port, host=args.host)
    except OSError as exc:
        print(
            f"Error: no se pudo iniciar el visualizador en {args.host}:{args.port}: {exc}",
            file=sys.stderr,
        )
        return EXIT_ABORTED

    print(f"Visualizador escuchando en http://{args.host}:{server.port} (Ctrl+C para detener)")

    stop_requested = threading.Event()

    def _handle_sigint(signum, frame) -> None:  # noqa: ARG001 - firma requerida por signal
        stop_requested.set()

    previous_handler = signal.signal(signal.SIGINT, _handle_sigint)
    try:
        stop_requested.wait()
    except KeyboardInterrupt:
        pass
    finally:
        signal.signal(signal.SIGINT, previous_handler)

    print("Deteniendo visualizador...")
    server.stop()
    return EXIT_CLEAN


if __name__ == "__main__":
    sys.exit(main())
