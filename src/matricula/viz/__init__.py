"""Visualizador opcional en tiempo real para `matricula run --visualize`.

Este paquete es puramente observacional y esta desacoplado de
`orchestration/`: `runner.py` no importa nada de aqui, solo acepta un
callback `on_event` generico. Solo se activa si el usuario pasa
`--visualize` en la CLI.
"""
