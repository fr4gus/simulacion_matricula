"""Parseo y render generico de tablas Markdown estilo pipe (GFM).

Usado como utilidad de bajo nivel compartida por student_md.py y period_md.py,
para que ambos formatos de archivo no dupliquen la logica de tokenizado.
"""

from __future__ import annotations


def _split_row(line: str) -> list[str]:
    """Divide una fila `| a | b | c |` en celdas ['a', 'b', 'c'], recortadas."""
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [cell.strip() for cell in stripped.split("|")]


def _is_separator_row(cells: list[str]) -> bool:
    return all(cell.replace("-", "").replace(":", "") == "" for cell in cells)


def parse_table(lines: list[str]) -> tuple[list[str], list[list[str]]]:
    """Parsea una tabla pipe a partir de sus lineas (encabezado, separador, filas...).

    Retorna (headers, rows). Si no hay filas de datos (solo encabezado +
    separador), `rows` es una lista vacia.
    """
    content_lines = [line for line in lines if line.strip()]
    if len(content_lines) < 2:
        return [], []
    headers = _split_row(content_lines[0])
    separator = _split_row(content_lines[1])
    if not _is_separator_row(separator):
        raise ValueError(f"Fila separadora de tabla invalida: {content_lines[1]!r}")
    rows = [_split_row(line) for line in content_lines[2:]]
    return headers, rows


def render_table(headers: list[str], rows: list[list[str]]) -> str:
    """Renderiza una tabla pipe con columnas alineadas al ancho del contenido."""
    all_rows = [headers, *rows]
    widths = [max(len(row[i]) for row in all_rows) for i in range(len(headers))]
    lines = [_render_row(headers, widths)]
    lines.append(_render_row(["-" * w for w in widths], widths))
    for row in rows:
        lines.append(_render_row(row, widths))
    return "\n".join(lines)


def _render_row(cells: list[str], widths: list[int]) -> str:
    padded = [cell.ljust(width) for cell, width in zip(cells, widths, strict=True)]
    return "| " + " | ".join(padded) + " |"
