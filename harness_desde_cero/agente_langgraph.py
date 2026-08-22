"""
mini-agente con LANGGRAPH: el MISMO harness que agente.py, reescrito con StateGraph.

Compara este archivo con agente.py linea por linea. La logica es identica -
loop, tools, condicion de parada, guardrails - pero en vez de escribir el
`for` a mano, se lo DECLARAS al grafo como nodos y edges (conexiones).

    agente.py (crudo)              agente_langgraph.py (StateGraph)
    --------------------------      --------------------------
    lista `mensajes`          ->    State (MessagesState)
    llamar al modelo (paso A) ->    nodo "llamar_modelo"
    ejecutar tools (paso D)   ->    nodo "ejecutar_tools"
    condicion de parada (C)   ->    edge condicional
    el `for` que repite       ->    el edge que vuelve de tools a modelo

Uso:
    export ANTHROPIC_API_KEY="tu-key"
    python agente_langgraph.py "listame los archivos de esta carpeta"
"""

import os
import sys

from langchain_core.tools import tool
from langchain_anthropic import ChatAnthropic
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode, tools_condition

# ---------------------------------------------------------------------------
# 0. CONFIGURACION (identica a agente.py)
# ---------------------------------------------------------------------------
MODEL = "claude-sonnet-4-6"
WORKDIR = os.path.abspath(".")  # GUARDRAIL: las tools no pueden salir de esta carpeta


# ---------------------------------------------------------------------------
# 1. LAS HERRAMIENTAS
# ---------------------------------------------------------------------------
# En agente.py, una tool era: (a) un esquema JSON + (b) una funcion Python,
# conectados a mano en el diccionario EJECUTORES.
#
# Con LangGraph (via langchain_core), el decorador @tool hace las dos cosas
# a la vez: LEE la firma de la funcion y el docstring, y genera el esquema
# que el modelo necesita automaticamente. Sigue siendo tu codigo el que
# se ejecuta - el decorador solo te ahorra escribir el JSON a mano.

def _ruta_segura(path: str) -> str:
    """GUARDRAIL: identico al de agente.py - no se puede salir de WORKDIR."""
    destino = os.path.abspath(os.path.join(WORKDIR, path))
    if not destino.startswith(WORKDIR):
        raise ValueError(f"Acceso denegado fuera del directorio de trabajo: {path}")
    return destino


@tool
def leer_archivo(path: str) -> str:
    """Lee y devuelve el contenido de texto de un archivo dado su path relativo."""
    destino = _ruta_segura(path)
    with open(destino, "r", encoding="utf-8") as f:
        return f.read()


@tool
def listar_directorio(path: str) -> str:
    """Lista los archivos y carpetas dentro de un directorio dado su path relativo."""
    destino = _ruta_segura(path)
    entradas = os.listdir(destino)
    return "\n".join(sorted(entradas)) if entradas else "(directorio vacio)"


TOOLS = [leer_archivo, listar_directorio]

# El modelo, con las tools "atadas" (bind_tools reemplaza el parametro
# `tools=TOOLS` que le pasabamos a client.messages.create en agente.py).
modelo = ChatAnthropic(model=MODEL).bind_tools(TOOLS)


# ---------------------------------------------------------------------------
# 2. LOS NODOS (las piezas que en agente.py eran pasos dentro del `for`)
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = (
    "Sos un asistente que ayuda a explorar un proyecto de codigo. "
    "Usa las herramientas disponibles cuando necesites informacion. "
    "Cuando tengas la respuesta final, respondela en texto sin pedir mas tools."
)


def llamar_modelo(state: MessagesState):
    """NODO equivalente al paso (A) de agente.py: le pasamos el historial
    completo al modelo y devolvemos su respuesta. LangGraph se encarga de
    ANEXAR este resultado al `state["messages"]" automaticamente (es el
    equivalente a nuestro `mensajes.append(...)` manual)."""
    mensajes = [{"role": "system", "content": SYSTEM_PROMPT}] + state["messages"]
    respuesta = modelo.invoke(mensajes)
    return {"messages": [respuesta]}


# El nodo que EJECUTA las tools ya viene hecho: ToolNode. Es el equivalente
# exacto de nuestra funcion `ejecutar_tool` + el paso (D) del loop -
# revisa el ultimo mensaje, ejecuta cada tool_call, y arma los tool_result.
ejecutar_tools = ToolNode(TOOLS)


# ---------------------------------------------------------------------------
# 3. EL GRAFO (el equivalente declarativo del `for` en agente.py)
# ---------------------------------------------------------------------------
grafo = StateGraph(MessagesState)

grafo.add_node("llamar_modelo", llamar_modelo)
grafo.add_node("ejecutar_tools", ejecutar_tools)

grafo.add_edge(START, "llamar_modelo")

# CONDICION DE PARADA: equivalente al `if respuesta.stop_reason != "tool_use"`
# de agente.py. `tools_condition` es una funcion que ya viene con LangGraph:
# mira el ultimo mensaje y decide a donde ir.
grafo.add_conditional_edges(
    "llamar_modelo",
    tools_condition,          # revisa: ¿el modelo pidio una tool?
    {
        "tools": "ejecutar_tools",  # si, pidio tool -> ir a ejecutarla
        END: END,                    # no, ya termino -> parar
    },
)

# Despues de ejecutar las tools, siempre volvemos al modelo.
# Esto ES el `for` que repite en agente.py - aqui es un edge fijo.
grafo.add_edge("ejecutar_tools", "llamar_modelo")

agente = grafo.compile()

# Nota: agente.py tenia un GUARDRAIL explicito `MAX_TURNS = 10` escrito a
# mano en el `for`. En LangGraph el equivalente es pasar
# `{"recursion_limit": 10}` como config al invocar el grafo (mas abajo) -
# el guardrail sigue existiendo, solo que se lo pasas al framework
# en vez de escribir el contador vos mismo.


# ---------------------------------------------------------------------------
# 4. PUNTO DE ENTRADA
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("Falta la variable de entorno ANTHROPIC_API_KEY.")

    tarea = " ".join(sys.argv[1:]) or "Listame los archivos de la carpeta actual."

    resultado = agente.invoke(
        {"messages": [{"role": "user", "content": tarea}]},
        config={"recursion_limit": 10},  # GUARDRAIL: equivalente a MAX_TURNS
    )

    print("\n=== Respuesta final ===")
    print(resultado["messages"][-1].content)
