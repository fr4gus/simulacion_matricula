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
