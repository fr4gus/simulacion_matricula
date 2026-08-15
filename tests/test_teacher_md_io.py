from __future__ import annotations

from pathlib import Path

from matricula.domain.models import TeacherRecord
from matricula.io.paths import profesores_file
from matricula.io.teacher_md import (
    TeacherRegistry,
    read_teachers,
    render_teachers,
    write_teachers,
)


def test_roundtrip_teacher_registry(base_dir: Path):
    registry = TeacherRegistry(
        next_free_index=13,
        records=[
            TeacherRecord(pool_index=10, full_name="Braelynn Callahan", group_code="CS002-01"),
            TeacherRecord(pool_index=11, full_name="Quinton Ryan", group_code="ES001-01"),
            TeacherRecord(pool_index=12, full_name="Morgan Phillips", group_code="MA001-01"),
        ],
    )

    write_teachers(base_dir, registry)
    loaded = read_teachers(profesores_file(base_dir))

    assert loaded == registry


def test_read_teachers_missing_file_returns_empty_registry(base_dir: Path):
    loaded = read_teachers(profesores_file(base_dir))
    assert loaded == TeacherRegistry(next_free_index=0, records=[])


def test_render_teachers_includes_cursor_line():
    registry = TeacherRegistry(next_free_index=7, records=[])
    text = render_teachers(registry)
    assert "Proximo indice libre del pool: 7" in text
    assert "# Profesores" in text
