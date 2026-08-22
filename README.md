# Sistema multiagéntico de simulación de matrícula

Simulación, período por período, del proceso de matrícula universitaria descrito en
[`PRD.md`](PRD.md): generación de notas, solicitudes de estudiantes, validación contra el plan
de estudios, apertura de cursos, formación de grupos, generación de horario y asignación de
estudiantes a sus grupos.

Es un sistema **multiagéntico sin LLM**: un orquestador central despacha un pool de procesos
(uno por estudiante, vía `ProcessPoolExecutor`) que simulan notas y arman solicitudes en
paralelo real; luego el orquestador corre las fases secuenciales (validación, demanda, grupos,
horario, asignación) que requieren estado compartido. Ver [`CLAUDE.md`](CLAUDE.md) para el mapa
completo de módulos y las decisiones de diseño.

## Requisitos

- **Python 3.11 o superior** (probado con 3.12). Sin más requisitos de sistema — no hay base de
  datos, no hay servicios externos, no hay dependencias nativas que compilar.
- **Sin dependencias de runtime**: el paquete usa únicamente la librería estándar de Python
  (`argparse`, `dataclasses`, `concurrent.futures`, `random`, `http.server`, etc.). No hace
  falta instalar nada de PyPI para ejecutar `matricula run`.
- Para desarrollo (tests y lint) se necesitan `pytest` y `ruff`, instalables como dependencias
  opcionales (ver abajo).
- No requiere Docker, ni red, ni credenciales. Todo corre localmente sobre el sistema de
  archivos.

## Instalación

```bash
git clone <este-repo>
cd simulacion_matricula
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"   # instala el paquete + pytest/ruff para desarrollo
```

Para instalar solo lo necesario para correr el sistema (sin herramientas de desarrollo):

```bash
.venv/bin/pip install -e .
```

En otra máquina, estos son los únicos pasos: clonar, crear el entorno virtual, instalar. No hay
configuración adicional, variables de entorno, ni archivos de secretos.

El modo skills (ver más abajo) no necesita ninguna instalación adicional: no usa el paquete
Python, sino un agente de Claude Code/Codex leyendo los skills de `.claude/skills/`.

## Uso

El comando principal corre el proceso de matrícula de **un período a la vez**:

```bash
.venv/bin/python -m matricula run <PERIODO> [opciones]
```

`<PERIODO>` tiene el formato `YYYY-PP` (por ejemplo `2026-01`), donde `PP` es `01`, `02` o `03`.

### Primera corrida (bootstrap)

Si no existe historial previo en el directorio de trabajo, la primera corrida inicializa la
simulación: crea los primeros 10 estudiantes y matricula las materias de cuatrimestre 1.

```bash
.venv/bin/python -m matricula run 2026-01
```

Esto crea, en el directorio actual:

- `students/DDDDDD.md` — un archivo por estudiante, con su matrícula y expediente de notas.
- `periodos_lectivos/2026-01.md` — el horario del período, las listas de estudiantes por
  materia/grupo, y las alertas para revisión humana.
- `profesores.md` — un único archivo (no por período) con el registro de profesores generados
  hasta ahora y el cursor del pool de nombres compartido (ver abajo).

Los nombres de estudiantes y profesores salen de un pool compartido de 1000 nombres reales
(`nombres.md`, en la raíz del repo, no del directorio de trabajo) — cada nombre nuevo, sea de
estudiante o de profesor, consume la siguiente posición libre del pool y nunca repite una ya
usada dentro de la simulación; `profesores.md` es lo que hace ese seguimiento posible entre
corridas.

### Corridas siguientes (consecutivas)

Cada corrida posterior debe ser el período inmediato siguiente al último almacenado. El sistema
valida esto automáticamente y rechaza períodos fuera de secuencia:

```bash
.venv/bin/python -m matricula run 2026-02   # continúa desde 2026-01
.venv/bin/python -m matricula run 2026-03   # continúa desde 2026-02
.venv/bin/python -m matricula run 2027-01   # el ciclo de periodos reinicia despues de "03"
```

Cada corrida simula las notas de la matrícula del período anterior (80% de probabilidad de
aprobar), construye las solicitudes del nuevo período (siguiente cuatrimestre pendiente, más
repetición automática de materias reprobadas), y repite todo el pipeline.

### Opciones de la CLI

```
usage: matricula run [-h] [--seed SEED] [--base-dir BASE_DIR]
                      [--workers WORKERS] [--visualize] [--viz-port VIZ_PORT]
                      [--demo-delay DEMO_DELAY]
                      period

  period                 Periodo lectivo en formato YYYY-PP (PP: 01-03)
  --seed SEED            Semilla RNG (default: 0) — determina la simulacion de notas;
                          misma semilla = mismo resultado, sin importar --workers.
  --base-dir BASE_DIR    Directorio raiz para students/ y periodos_lectivos/ (default: .)
  --workers WORKERS      Numero de procesos del pool (default: os.cpu_count())
  --visualize            Muestra el progreso en tiempo real. Se conecta a un servidor
                          'matricula viz' ya corriendo en --viz-port si existe; si no,
                          levanta uno propio solo para esta corrida.
  --viz-port VIZ_PORT    Puerto del servidor de visualizacion (default: 8765)
  --demo-delay SEGUNDOS  Retraso artificial entre eventos del visualizador, para demos
                          (default: 0, sin retraso). Solo tiene efecto junto a --visualize.
```

Ejemplo con un directorio de trabajo explícito (útil para no mezclar corridas con el repo):

```bash
.venv/bin/python -m matricula run 2026-01 --base-dir /ruta/a/mi/simulacion --seed 42
```

### Códigos de salida

- `0` — corrida limpia, sin alertas sistémicas (los rechazos rutinarios, como una materia
  cerrada por baja demanda o un prerrequisito no cumplido, son parte normal del proceso y no
  cuentan).
- `1` — la corrida terminó pero generó alertas sistémicas (un grupo sin horario asignable, o un
  estudiante con un conflicto de horario sin resolver). Revisar la tabla de alertas en
  `periodos_lectivos/<periodo>.md`.
- `2` — la corrida se abortó antes de ejecutar el pipeline (formato de período inválido, período
  no consecutivo respecto al historial almacenado, o archivos existentes ilegibles).

### Visualizador en tiempo real (opcional)

Con `--visualize`, el comando muestra el progreso de la corrida en un navegador mientras esta se
ejecuta:

```bash
.venv/bin/python -m matricula run 2026-01 --visualize
```

Imprime una URL (por defecto `http://127.0.0.1:8765`) para abrir en el navegador. La página
muestra, en vivo:

- El avance del pool de estudiantes y de cada fase del pipeline (validación, demanda, grupos,
  horario, asignación).
- Una tabla de alertas que se va llenando conforme ocurren.
- Un **censo de cuatrimestres**: cuántos estudiantes hay en cada cuatrimestre del plan y cuántos
  ya se graduaron (aprobaron todas las materias). Este censo es global — cuenta todos los
  estudiantes en `students/`, no solo los de la corrida actual.

No requiere instalar nada adicional: el servidor usa solo la librería estándar de Python.

#### Servidor de visualización independiente

Si vas a hacer varias corridas seguidas, es mejor levantar el visualizador aparte, una sola vez,
y dejarlo corriendo:

```bash
.venv/bin/python -m matricula viz --port 8765   # queda corriendo hasta Ctrl+C
```

Con el servidor ya corriendo, cada `matricula run --visualize` (mismo `--viz-port`) se conecta a
él automáticamente en vez de levantar uno nuevo — así puedes correr varios períodos seguidos
mientras miras la misma pestaña del navegador. Cada corrida nueva resetea la página (limpia las
tarjetas de fase y la tabla de alertas) antes de mostrar su propio progreso. Si no hay ningún
servidor escuchando en el puerto, `matricula run --visualize` levanta uno propio para esa corrida
y lo cierra al terminar (comportamiento por defecto, sin cambios). Si el puerto está ocupado por
otro proceso que no es un servidor de matrícula, la corrida se aborta con un mensaje claro
(`exit code 2`).

Si el navegador se conecta después de que una corrida ya avanzó, solo verá los eventos a partir
de ese momento (no hay reproducción del historial de esa corrida).

#### Retraso artificial para demos (`--demo-delay`)

Una corrida real (10-40 estudiantes) completa el pipeline en milisegundos — muy rápido para ver
las transiciones de fase a simple vista. `--demo-delay SEGUNDOS` agrega una pausa artificial
antes de reenviar cada evento al visualizador, sin afectar el resultado de la corrida (los
archivos se calculan y escriben exactamente igual; solo cambia cuándo se notifica al navegador):

```bash
.venv/bin/python -m matricula run 2026-01 --visualize --demo-delay 1
```

### Modo skills (orquestación por agente, opcional)

Por defecto, `matricula run` corre el pipeline de 11 pasos del PRD con un orquestador Python
secuencial 100% determinista (mismo `--seed` ⇒ mismo resultado, byte a byte, sin importar
`--workers`). Existe además un segundo camino, **independiente de la CLI y sin nada de Python de
negocio**: los skills de `.claude/skills/`, donde un agente de Claude Code (o Codex) corre el
pipeline completo con su propio razonamiento, leyendo y escribiendo directamente
`students/*.md`, `periodos_lectivos/*.md` y `profesores.md`.

Son tres skills, de los cuales solo el primero se invoca a mano:

- **`matricula`** — el orquestador y único punto de entrada. Corre inline los pasos globales y
  baratos del PRD (0, 2, 3, 10, 11: migrar graduados, verificar consecutividad, generar
  carnets/nombres, consolidar alertas, persistir archivos) y delega el resto vía la herramienta
  `Task`.
- **`matricula-estudiante`** — un `Task` por estudiante, en lotes de hasta 5 en paralelo. Cubre
  los pasos 1 y 4 (simular notas del período anterior, construir la lista de solicitudes) para un
  solo estudiante. Es el análogo, en este modo, del worker que el modo default corre en el
  `ProcessPoolExecutor`.
- **`matricula-horario`** — un único `Task` por corrida, sin paralelismo. Cubre los pasos 5 a 9
  (validación, demanda, grupos, horario, asignación individual) en una sola pasada secuencial,
  por la misma razón por la que `orchestration/*` es single-process en el modo default: cada fase
  necesita la salida completa de la anterior y todas mutan estado global compartido.

Invocación (dentro de una sesión de Claude Code):

```
/matricula 2026-02
/matricula 2026-02 n_estudiantes=20 base_dir=data/escenario-a
```

`base_dir` es `data/` por defecto (directorio generado y gitignoreado). Un `escenario.md`
opcional en la raíz de `base_dir` permite variar constantes del PRD (`max_aulas`,
`capacidad_aula`, `cupo_grupo`, `minimo_apertura`, `probabilidad_aprobacion`, `nota_minima`,
`estudiantes_nuevos_por_periodo`) para forzar escenarios de estrés.

Combina con el visualizador igual que el modo default, con una diferencia: el skill nunca levanta
el servidor, así que hay que tener `matricula viz` ya corriendo. Publica el mismo vocabulario de
eventos que `runner.py` más cuatro propios (`subagent_started`/`subagent_completed`,
`phase_started`/`phase_completed`) para mostrar los subagentes en progreso.

Este modo **no es determinista** (un LLM decide el cálculo y el ritmo de la narración) — el
mismo trade-off que tenía el antiguo modo `--agents` basado en el Claude Agent SDK, que fue
eliminado por completo y reemplazado por estos skills.

## Desarrollo

```bash
.venv/bin/python -m pytest                          # suite completa
.venv/bin/python -m pytest tests/test_scheduling.py  # un archivo puntual
.venv/bin/ruff check src tests                        # lint
.venv/bin/ruff format src tests                       # formateo
```

Ver [`AGENTS.md`](AGENTS.md) para convenciones de estilo y estructura, y
[`CLAUDE.md`](CLAUDE.md) para el mapa de módulos y las decisiones de diseño (frontera de
concurrencia, determinismo, formatos de archivo).

## Estructura del repositorio

```
src/matricula/          # codigo fuente del paquete
  domain/                # modelos puros, plan de estudios, periodos
  io/                     # lectura/escritura de students/*.md y periodos_lectivos/*.md
  simulation/              # simulacion de notas + construccion de solicitudes (worker paralelo)
  orchestration/            # fases secuenciales del pipeline + el runner central
  reporting/                 # resumen de la corrida y decision de exit code
  viz/                        # visualizador opcional en tiempo real (--visualize / matricula viz)
.claude/skills/          # modo skills: orquestador matricula + subagentes estudiante/horario
tests/                   # suite de pytest
PRD.md                   # especificacion del dominio (incluye seccion de aclaraciones)
AGENTS.md                # convenciones de estructura y estilo
CLAUDE.md                # guia de arquitectura para trabajar en este repo con Claude Code
```

Los directorios `students/` y `periodos_lectivos/` son **datos generados**, no versionados: se
crean en el directorio desde el que se ejecuta `matricula run` (o en `--base-dir` si se
especifica).
