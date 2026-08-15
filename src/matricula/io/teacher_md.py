"""Reader/writer de profesores.md: registro de nombres de profesor ya usados,
y del cursor del pool compartido de nombres (`domain.names.NAME_POOL`).

Formato:

    # Profesores

    Proximo indice libre del pool: 7

    | Indice Pool | Nombre Completo | Materia-Grupo |
    | ----------- | ---------------- | ------------- |
    | 3           | Colson Bridges    | MA001-01      |

`Indice Pool` es la posicion (0-999) en `domain.names.NAME_POOL` de donde salio
el nombre -- la clave real que evita reusar el mismo indice dos veces (ver
`simulation/naming.py`); `Nombre Completo` se guarda tambien para legibilidad,
sin tener que resolver el indice contra el pool. `Materia-Grupo` documenta a
que grupo quedo asignado ese profesor en la corrida donde se lo genero
(formato `MA001-01`, igual que `Group.group_code`).

"Proximo indice libre del pool" es el cursor global y determinista compartido
con los estudiantes: cada estudiante nuevo Y cada profesor nuevo, en TODA
corrida (`run_period` o `run_period_with_agent`), consume el siguiente indice
en orden 0, 1, 2, ... y lo avanza -- es la unica fuente de verdad sobre
"cuantos nombres del pool ya se repartieron", en vez de intentar derivarlo de
`students/*.md` (que guarda el nombre como texto, sin el indice de origen).

Igual que `student_md.py`/`period_md.py`: `write_teachers` siempre re-renderiza
el archivo completo desde la lista en memoria, nunca parchea texto.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from matricula.domain.models import TeacherRecord
from matricula.io.markdown_tables import parse_table, render_table

HEADERS = ["Indice Pool", "Nombre Completo", "Materia-Grupo"]
_CURSOR_LINE_RE = re.compile(r"^Proximo indice libre del pool:\s*(\d+)\s*$")


@dataclass(frozen=True)
class TeacherRegistry:
    next_free_index: int
    records: list[TeacherRecord]


def parse_teachers(text: str) -> TeacherRegistry:
    lines = text.splitlines()
    next_free_index = 0
    for line in lines:
        match = _CURSOR_LINE_RE.match(line.strip())
        if match is not None:
            next_free_index = int(match.group(1))
            break

    table_start = None
    for i, line in enumerate(lines):
        if line.strip().startswith("|"):
            table_start = i
            break
    rows: list[list[str]] = []
    if table_start is not None:
        _, rows = parse_table(lines[table_start:])

    records = [
        TeacherRecord(pool_index=int(index_str), full_name=name, group_code=group_code)
        for index_str, name, group_code in rows
    ]
    return TeacherRegistry(next_free_index=next_free_index, records=records)


def render_teachers(registry: TeacherRegistry) -> str:
    rows = [[str(r.pool_index), r.full_name, r.group_code] for r in registry.records]
    parts = [
        "# Profesores",
        "",
        f"Proximo indice libre del pool: {registry.next_free_index}",
        "",
        render_table(HEADERS, rows),
        "",
    ]
    return "\n".join(parts)


def read_teachers(path: Path) -> TeacherRegistry:
    if not path.exists():
        return TeacherRegistry(next_free_index=0, records=[])
    return parse_teachers(path.read_text(encoding="utf-8"))


def write_teachers(base_dir: Path, registry: TeacherRegistry) -> Path:
    from matricula.io.paths import profesores_file

    path = profesores_file(base_dir)
    path.write_text(render_teachers(registry), encoding="utf-8")
    return path
