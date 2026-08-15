"""CLI: `python -m matricula run <periodo> [--seed N] [--base-dir PATH]`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from matricula.domain.periods import InvalidPeriodFormatError, Period, is_consecutive
from matricula.io.history import latest_period
from matricula.orchestration.runner import run_period
from matricula.reporting.summary import EXIT_ABORTED, print_summary

DEFAULT_SEED = 0


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
        help="Levanta un servidor local con vista en tiempo real del progreso",
    )
    run_parser.add_argument(
        "--viz-port",
        type=int,
        default=8765,
        help="Puerto del servidor de visualizacion (default: 8765)",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "run":
        return _run(args)

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
        from matricula.viz.server import start as start_viz_server

        try:
            server = start_viz_server(port=args.viz_port)
        except OSError as exc:
            print(
                f"Error: no se pudo iniciar el visualizador en el puerto {args.viz_port}: {exc}",
                file=sys.stderr,
            )
            return EXIT_ABORTED
        print(f"Visualizador: http://127.0.0.1:{server.port}", file=sys.stderr)
        on_event = server.emit

    try:
        result = run_period(
            base_dir, period, seed=args.seed, max_workers=args.workers, on_event=on_event
        )
    finally:
        if server is not None:
            server.stop()

    print_summary(result.summary)
    return result.summary.exit_code


if __name__ == "__main__":
    sys.exit(main())
