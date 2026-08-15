"""Resolucion de rutas para students/ y periodos_lectivos/."""

from __future__ import annotations

from pathlib import Path


def students_dir(base_dir: Path) -> Path:
    return base_dir / "students"


def periodos_dir(base_dir: Path) -> Path:
    return base_dir / "periodos_lectivos"


def student_file(base_dir: Path, carnet: str) -> Path:
    return students_dir(base_dir) / f"{carnet}.md"


def period_file(base_dir: Path, period_str: str) -> Path:
    return periodos_dir(base_dir) / f"{period_str}.md"
