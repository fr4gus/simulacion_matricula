"""
mini-agente: un harness agentico DESDE CERO con la API de Anthropic.

No usa el Claude Agent SDK. Solo la libreria base `anthropic` (el cliente HTTP)
y un loop escrito a mano. El objetivo es que VEAS cada pieza del harness:

    1. Las HERRAMIENTAS  -> que puede hacer el agente (aqui: leer archivos, listar carpetas)
    2. El LOOP           -> llamar al modelo, ejecutar tools, devolver resultados, repetir
    3. La CONDICION DE PARADA -> cuando el modelo deja de pedir tools, terminamos
    4. Los GUARDRAILS    -> limites (max de vueltas, y que las tools no salgan de una carpeta)

Uso:
    export ANTHROPIC_API_KEY="tu-key"
    python agente.py "listame los archivos de esta carpeta y luego leeme agente.py"
"""

import os
import sys
import json
import anthropic

# ---------------------------------------------------------------------------
# 0. CONFIGURACION
# ---------------------------------------------------------------------------
# El cliente lee la key de la variable de entorno ANTHROPIC_API_KEY por defecto.
client = anthropic.Anthropic()

MODEL = "claude-sonnet-4-6"   # barato y rapido para practicar. Sube a "claude-opus-4-8" para tareas serias.
MAX_TURNS = 10                # GUARDRAIL: nunca mas de 10 vueltas al loop (evita loops infinitos)
WORKDIR = os.path.abspath(".")  # GUARDRAIL: las tools no pueden salir de esta carpeta


# ---------------------------------------------------------------------------
# 1. LAS HERRAMIENTAS
# ---------------------------------------------------------------------------
# Cada herramienta son DOS cosas:
#   (a) un ESQUEMA que le describe la tool al modelo (nombre, para que sirve, que parametros toma)
#   (b) una FUNCION de Python que realmente la ejecuta
#
# El modelo nunca ejecuta codigo: solo PIDE que ejecutes una tool con ciertos argumentos.
# Ejecutarla es trabajo TUYO (del harness). Esa es la idea central.

TOOLS = [
    {
        "name": "leer_archivo",
        "description": "Lee y devuelve el contenido de texto de un archivo dado su path relativo.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path relativo del archivo a leer, p.ej. 'agente.py'",
                }
            },
            "required": ["path"],
        },
    },
    {
        "name": "listar_directorio",
        "description": "Lista los archivos y carpetas dentro de un directorio dado su path relativo.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path relativo del directorio. Usa '.' para la carpeta actual.",
                }
            },
            "required": ["path"],
        },
    },
]


def _ruta_segura(path: str) -> str:
    """GUARDRAIL: resuelve el path y verifica que no se salga de WORKDIR."""
    destino = os.path.abspath(os.path.join(WORKDIR, path))
    if not destino.startswith(WORKDIR):
        raise ValueError(f"Acceso denegado fuera del directorio de trabajo: {path}")
    return destino


def leer_archivo(path: str) -> str:
    destino = _ruta_segura(path)
    with open(destino, "r", encoding="utf-8") as f:
        return f.read()


def listar_directorio(path: str) -> str:
    destino = _ruta_segura(path)
    entradas = os.listdir(destino)
    return "\n".join(sorted(entradas)) if entradas else "(directorio vacio)"


# Un diccionario que mapea el NOMBRE de la tool a la FUNCION que la ejecuta.
# Cuando el modelo pida "leer_archivo", buscamos aqui como ejecutarla.
EJECUTORES = {
    "leer_archivo": leer_archivo,
    "listar_directorio": listar_directorio,
}


def ejecutar_tool(nombre: str, argumentos: dict) -> str:
    """Ejecuta una tool por nombre y devuelve su resultado como texto.
    Si algo falla, devolvemos el error como texto (el modelo lo lee y reacciona)."""
    try:
        funcion = EJECUTORES[nombre]
        return funcion(**argumentos)
    except Exception as e:
        return f"ERROR ejecutando {nombre}: {e}"


# ---------------------------------------------------------------------------
# 2. EL LOOP AGENTICO (el corazon del harness)
# ---------------------------------------------------------------------------
def correr_agente(tarea: str):
    # La "memoria" de la conversacion. Empieza con el mensaje del usuario.
    # Este historial se manda COMPLETO en cada llamada (el modelo no recuerda solo).
    mensajes = [{"role": "user", "content": tarea}]

    for turno in range(1, MAX_TURNS + 1):
        print(f"\n--- Turno {turno} ---")

        # (A) LLAMAR AL MODELO, pasandole el historial y las tools disponibles.
        respuesta = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=(
                "Sos un asistente que ayuda a explorar un proyecto de codigo. "
                "Usa las herramientas disponibles cuando necesites informacion. "
                "Cuando tengas la respuesta final, respondela en texto sin pedir mas tools."
            ),
            tools=TOOLS,
            messages=mensajes,
        )

        # Guardamos la respuesta del modelo en el historial (tal cual viene).
        mensajes.append({"role": "assistant", "content": respuesta.content})

        # (B) REVISAR: el modelo puede devolver texto, pedidos de tool, o ambos.
        # Imprimimos el texto que haya dicho.
        for bloque in respuesta.content:
            if bloque.type == "text":
                print("Claude:", bloque.text)

        # (C) CONDICION DE PARADA:
        # stop_reason == "tool_use" significa "quiero que ejecutes una o mas tools".
        # Cualquier otra cosa (normalmente "end_turn") significa que ya termino.
        if respuesta.stop_reason != "tool_use":
            print("\n=== Agente termino ===")
            return

        # (D) EJECUTAR cada tool que el modelo pidio, y juntar los resultados.
        resultados = []
        for bloque in respuesta.content:
            if bloque.type == "tool_use":
                print(f"  -> Claude pide: {bloque.name}({json.dumps(bloque.input)})")
                salida = ejecutar_tool(bloque.name, bloque.input)
                print(f"     resultado: {salida[:80]}{'...' if len(salida) > 80 else ''}")
                # Cada resultado se etiqueta con el tool_use_id que el modelo genero,
                # para que sepa a cual de sus pedidos corresponde.
                resultados.append({
                    "type": "tool_result",
                    "tool_use_id": bloque.id,
                    "content": salida,
                })

        # (E) DEVOLVER los resultados al modelo como un mensaje de rol "user".
        # Luego el loop vuelve a (A) y el modelo decide el siguiente paso.
        mensajes.append({"role": "user", "content": resultados})

    print("\n=== Se alcanzo el maximo de turnos (guardrail) ===")


# ---------------------------------------------------------------------------
# 3. PUNTO DE ENTRADA
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("Falta la variable de entorno ANTHROPIC_API_KEY.")
    tarea = " ".join(sys.argv[1:]) or "Listame los archivos de la carpeta actual."
    correr_agente(tarea)