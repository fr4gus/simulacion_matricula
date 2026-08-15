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
                      period

  period                Periodo lectivo en formato YYYY-PP (PP: 01-03)
  --seed SEED           Semilla RNG (default: 0) — determina la simulacion de notas;
                         misma semilla = mismo resultado, sin importar --workers.
  --base-dir BASE_DIR   Directorio raiz para students/ y periodos_lectivos/ (default: .)
  --workers WORKERS     Numero de procesos del pool (default: os.cpu_count())
  --visualize           Levanta un servidor local con vista en tiempo real del progreso
  --viz-port VIZ_PORT   Puerto del servidor de visualizacion (default: 8765)
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

Con `--visualize`, el comando levanta un servidor local mientras dura la corrida y muestra su
progreso en el navegador:

```bash
.venv/bin/python -m matricula run 2026-01 --visualize
```

Imprime una URL (por defecto `http://127.0.0.1:8765`) para abrir en el navegador. La página
muestra, en vivo, el avance del pool de estudiantes y de cada fase del pipeline (validación,
demanda, grupos, horario, asignación), además de una tabla de alertas que se va llenando
conforme ocurren. No requiere instalar nada adicional: el servidor usa solo la librería estándar
de Python. Si el navegador se conecta después de que la corrida ya avanzó, solo verá los eventos
a partir de ese momento (no hay reproducción del historial).

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
  viz/                        # visualizador opcional en tiempo real (--visualize)
tests/                   # suite de pytest
PRD.md                   # especificacion del dominio (incluye seccion de aclaraciones)
AGENTS.md                # convenciones de estructura y estilo
CLAUDE.md                # guia de arquitectura para trabajar en este repo con Claude Code
```

Los directorios `students/` y `periodos_lectivos/` son **datos generados**, no versionados: se
crean en el directorio desde el que se ejecuta `matricula run` (o en `--base-dir` si se
especifica).
