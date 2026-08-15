"""Resolucion de rutas para students/, periodos_lectivos/ y profesores.md."""

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


def profesores_file(base_dir: Path) -> Path:
    """Archivo unico en la raiz de `base_dir` con el registro de profesores usados."""
    return base_dir / "profesores.md"
