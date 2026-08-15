from __future__ import annotations

from pathlib import Path

from matricula.cli import main
from matricula.reporting.summary import EXIT_ABORTED, EXIT_CLEAN


def test_invalid_period_format_aborts(base_dir: Path, capsys):
    code = main(["run", "2026-99", "--base-dir", str(base_dir)])
    assert code == EXIT_ABORTED
    captured = capsys.readouterr()
    assert "Error" in captured.err


def test_bootstrap_run_succeeds(base_dir: Path):
    code = main(["run", "2026-01", "--base-dir", str(base_dir), "--seed", "0", "--workers", "1"])
    assert code == EXIT_CLEAN
    assert (base_dir / "students").exists()
    assert (base_dir / "periodos_lectivos" / "2026-01.md").exists()
    assert len(list((base_dir / "students").glob("*.md"))) == 10


def test_non_consecutive_period_aborts(base_dir: Path, capsys):
    main(["run", "2026-01", "--base-dir", str(base_dir), "--seed", "0", "--workers", "1"])
    code = main(["run", "2026-03", "--base-dir", str(base_dir), "--seed", "0", "--workers", "1"])
    assert code == EXIT_ABORTED
    captured = capsys.readouterr()
    assert "no consecutivo" in captured.err


def test_consecutive_period_after_bootstrap_succeeds(base_dir: Path):
    main(["run", "2026-01", "--base-dir", str(base_dir), "--seed", "0", "--workers", "1"])
    code = main(["run", "2026-02", "--base-dir", str(base_dir), "--seed", "0", "--workers", "1"])
    assert code == EXIT_CLEAN
    assert len(list((base_dir / "students").glob("*.md"))) == 20


def test_viz_subcommand_parser_defaults():
    from matricula.cli import DEFAULT_VIZ_PORT, build_parser

    parser = build_parser()
    args = parser.parse_args(["viz"])
    assert args.command == "viz"
    assert args.port == DEFAULT_VIZ_PORT
    assert args.host == "127.0.0.1"


def test_viz_subcommand_custom_port_and_host():
    from matricula.cli import build_parser

    parser = build_parser()
    args = parser.parse_args(["viz", "--port", "9000", "--host", "0.0.0.0"])
    assert args.port == 9000
    assert args.host == "0.0.0.0"


def test_run_without_existing_server_starts_and_stops_its_own(base_dir: Path):
    import socket

    from matricula.cli import main as cli_main

    # Puerto libre garantizado.
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        free_port = probe.getsockname()[1]

    code = cli_main(
        [
            "run",
            "2026-01",
            "--base-dir",
            str(base_dir),
            "--seed",
            "0",
            "--workers",
            "1",
            "--visualize",
            "--viz-port",
            str(free_port),
        ]
    )
    assert code == EXIT_CLEAN
    # El servidor propio debe haberse cerrado al terminar: el puerto vuelve
    # a estar libre.
    with socket.socket() as probe2:
        probe2.bind(("127.0.0.1", free_port))


def test_run_connects_to_already_running_viz_server(base_dir: Path):
    from matricula.cli import main as cli_main
    from matricula.viz.server import start as start_viz_server

    server = start_viz_server(port=0)
    try:
        received_queue = server._broadcaster.subscribe()
        code = cli_main(
            [
                "run",
                "2026-01",
                "--base-dir",
                str(base_dir),
                "--seed",
                "0",
                "--workers",
                "1",
                "--visualize",
                "--viz-port",
                str(server.port),
            ]
        )
        assert code == EXIT_CLEAN
        # Al menos un evento debio llegar via /publish al servidor preexistente.
        first_event = received_queue.get(timeout=2)
        assert first_event["type"] == "run_started"
    finally:
        server.stop()


def test_run_aborts_when_port_occupied_by_unrelated_server(base_dir: Path):
    from http.server import BaseHTTPRequestHandler, HTTPServer

    from matricula.cli import main as cli_main

    class DummyHandler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            self.send_response(404)
            self.end_headers()

        def log_message(self, *args):  # noqa: A002
            pass

    dummy = HTTPServer(("127.0.0.1", 0), DummyHandler)
    import threading

    thread = threading.Thread(target=dummy.serve_forever, daemon=True)
    thread.start()
    try:
        code = cli_main(
            [
                "run",
                "2026-01",
                "--base-dir",
                str(base_dir),
                "--seed",
                "0",
                "--workers",
                "1",
                "--visualize",
                "--viz-port",
                str(dummy.server_address[1]),
            ]
        )
        assert code == EXIT_ABORTED
    finally:
        dummy.shutdown()
        dummy.server_close()
