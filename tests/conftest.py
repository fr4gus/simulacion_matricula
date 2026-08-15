from __future__ import annotations

import random
from pathlib import Path

import pytest


@pytest.fixture
def base_dir(tmp_path: Path) -> Path:
    """Directorio raiz aislado para students/ y periodos_lectivos/ en un test."""
    return tmp_path


@pytest.fixture
def seeded_rng() -> random.Random:
    return random.Random(1234)
