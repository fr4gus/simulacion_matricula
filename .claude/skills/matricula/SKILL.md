---
name: matricula
description: Ejecuta un periodo completo del proceso de matricula universitaria (PRD.md) orquestando subagentes especializados via Task -- despacha lotes de hasta 5 subagentes matricula-estudiante en paralelo para simular notas y construir solicitudes, y delega la fase secuencial de validacion/demanda/grupos/horario/asignacion a un unico subagente matricula-horario. El propio agente no calcula reglas de negocio de estudiante directamente: coordina, resuelve escenario.md, publica eventos al visualizador y persiste resultados. Usar cuando el usuario pida correr/simular un periodo lectivo, avanzar la matricula, o invoque "/matricula <periodo> [n-estudiantes] [overrides]".
---

# matricula

Este skill orquesta el pipeline de 11 pasos del proceso de matrícula descrito en `PRD.md`
delegando el cálculo pesado a subagentes especializados vía el `Task` tool, en vez de
hacerlo todo en tu propio contexto. **No uses Bash para invocar `python -m matricula`, ni
importes o ejecutes nada de `src/matricula/orchestration/`, `src/matricula/io/`,
`src/matricula/simulation/`.** Ese es el modo "default" del proyecto (sin LLM) y debe
seguir siendo la referencia determinista e independiente. Este skill es un camino paralelo
puramente en lenguaje natural — vos y tus subagentes leen/calculan/escriben siguiendo
reglas explícitas, nunca código Python de negocio.

`PRD.md` (incluida su sección "Aclaraciones") es la fuente normativa de las reglas de
negocio — si algo acá difiere, `PRD.md` gana.

## Tu rol: coordinador, no calculador

Vos ejecutás directamente los pasos 0, 2, 3, 10 y 11 (operaciones de estado global barato:
migración de graduados, verificación de consecutividad, generación de carnets/nombres,
consolidación de alertas, persistencia de archivos). El cálculo de negocio por estudiante
(pasos 1+4) y el pipeline de horario (pasos 5-9) los delegás a subagentes vía `Task`:

- **`matricula-estudiante`** — un subagente por estudiante, hasta 5 en vuelo a la vez.
  Simula notas del período anterior + construye la solicitud de este período.
- **`matricula-horario`** — un único subagente, invocado una sola vez con la solicitud
  consolidada de todos los estudiantes. Corre validación → demanda → grupos → horario →
  asignación en una sola pasada secuencial (esas fases comparten estado global —cupos,
  aulas, profesores, horario acumulado— que no se presta a paralelismo ni a más de un
  subagente; ver `CLAUDE.md`, sección "Multi-agent skill topology").

## 1. Argumentos de invocación

- `periodo` (requerido): `YYYY-PP`, `PP` en `{01, 02, 03}`.
- `n_estudiantes` (opcional, default `10`): cantidad de estudiantes nuevos a crear en esta
  corrida.
- `base_dir` (opcional, default `data/` en la raíz del repo): directorio donde viven y se
  escriben `students/`, `periodos_lectivos/`, `profesores.md`, `escenario.md`,
  `graduated/`. Ver sección 1.1.
- Overrides de escenario opcionales, formato `clave=valor`: `max_aulas=`, `capacidad_aula=`,
  `cupo_grupo=`, `minimo_apertura=`, `probabilidad_aprobacion=`, `nota_minima=`.
- `viz_port` (opcional, default `8765`): puerto del visualizador standalone.

Ejemplo: `/matricula 2026-01 10` · `/matricula 2026-03 10 max_aulas=2` ·
`/matricula 2026-01 10 base_dir=/otro/lugar`

### 1.1 Directorio de datos (`base_dir`)

Por defecto es `data/` en la raíz de este repo (**no** el cwd ni la raíz del repo
directamente) — un directorio generado, deliberadamente separado del código fuente y
listado en `.gitignore` para que ninguna corrida termine commiteada por accidente. Si
`data/` no existe todavía, creála (junto con `data/students/`, `data/periodos_lectivos/`)
en la primera corrida — es la corrida inicializadora, tratala igual que cualquier otra
primera corrida (Paso 2).

Si el usuario pasa `base_dir=<ruta>` explícitamente en la invocación, usá esa ruta en su
lugar (absoluta o relativa a la raíz del repo) — típicamente para tener varios escenarios
de prueba en paralelo (p.ej. `base_dir=data/escenario-aulas-reducidas`) sin que se pisen
entre sí. `nombres.md` (el pool de nombres compartido) sigue siendo el único de la raíz del
repo — no vive dentro de `base_dir`, es un dato de referencia fijo del proyecto, no un
artefacto generado por corrida.

Todas las rutas de `students/*.md`, `periodos_lectivos/*.md`, `profesores.md`,
`escenario.md` y `graduated/*.md` mencionadas en el resto de este documento son relativas a
`base_dir`, no a la raíz del repo.

## 2. Escenario: `escenario.md`

Archivo opcional en la raíz de datos (`base_dir`, junto a `students/`, `periodos_lectivos/`,
`profesores.md`). Formato:

```markdown
# Escenario de Simulacion

Ultima actualizacion: 2026-08-15 (periodo 2026-01)

| Parametro | Valor | Default PRD |
| --- | --- | --- |
| max_aulas | 100 | 100 |
| capacidad_aula | 20 | 20 |
| cupo_grupo | 10 | 10 |
| minimo_apertura | 5 | 5 |
| probabilidad_aprobacion | 0.80 | 0.80 |
| nota_minima | 70 | 70 |
| estudiantes_nuevos_por_periodo | 10 | 10 |
```

Defaults PRD (usar si no hay archivo ni override):

| Parametro | Default |
| --- | --- |
| `max_aulas` | 100 |
| `capacidad_aula` | 20 |
| `cupo_grupo` | 10 |
| `minimo_apertura` | 5 |
| `probabilidad_aprobacion` | 0.80 |
| `nota_minima` | 70 |
| `estudiantes_nuevos_por_periodo` | 10 |

**Precedencia por parámetro** (de mayor a menor prioridad): override de invocación >
`escenario.md` > default PRD.

Reglas: si no existe, no lo crees automáticamente. Los overrides de invocación son
puntuales (no se persisten salvo pedido explícito). **Resolvé todos los valores efectivos
acá, antes de despachar ningún subagente** — tanto `matricula-estudiante` como
`matricula-horario` reciben estos valores ya resueltos en su prompt, nunca leen
`escenario.md` por su cuenta (evita lecturas concurrentes inconsistentes de un archivo que
podría no existir). Reportá al usuario y en `run_started` (sección 3) qué valores se
desvían del default y de dónde salió cada desviación.

## 3. Protocolo de emisión de eventos al visualizador

El humano ya debe haber corrido `python -m matricula viz` de antemano. Vos **no levantás el
servidor** — solo publicás si detectás que está corriendo. Los subagentes **nunca** publican
eventos directamente (no conocen `viz_port` ni el protocolo HTTP) — siempre sos vos quien
publica, después de recibir y parsear cada resultado.

Al arrancar:
```bash
curl -s -o /dev/null -w "%{http_code}" --max-time 1 http://localhost:<viz_port>/health
```
Si no responde `200`, avisá una vez y seguí sin publicar más eventos — nunca bloquees ni
abortes por esto.

Si responde `200`, publicá vía:
```bash
curl -s -X POST http://localhost:<viz_port>/publish -H "Content-Type: application/json" -d '<json>'
```

En este orden:

- `run_started` — `{"type": "run_started", "period": "2026-01", "total_students": 20}`.
- Por cada `Task` de `matricula-estudiante` que despaches (ver sección 4):
  - Justo antes: `{"type": "subagent_started", "role": "estudiante", "id": "260007", "batch_index": 2, "batch_size": 5}`.
  - Justo después de parsear su resultado: `{"type": "subagent_completed", "role": "estudiante", "id": "260007", "status": "ok", "batch_index": 2}`
    (`status`: `"ok"` o `"error"` si devolvió `error != null` o no fue parseable).
  - Inmediatamente después: `{"type": "pool_progress", "completed": N, "total": M}` (cadencia
    igual a la del modo Python — un tick por estudiante procesado).
- `pool_completed` — `{"type": "pool_completed", "completed": M, "total": M, "errors": N}`
  (`errors` = subagentes que devolvieron `status: "error"`).
- Antes de despachar `matricula-horario`: `{"type": "phase_started", "phase": "horario_y_asignacion"}`.
- Al recibir su resultado, en orden: `validation_done`, `alerts` (si las hay),
  `demand_done`, `alerts`, `grouping_done`, `scheduling_done`, `alerts`,
  `assignment_done`, `alerts` — mismos payloads que el modo Python:
  - `{"type": "validation_done", "valid": N, "rejected": N}`
  - `{"type": "demand_done", "opened": N, "closed": N}`
  - `{"type": "grouping_done", "groups_formed": N}`
  - `{"type": "scheduling_done", "scheduled": N, "unschedulable": N}`
  - `{"type": "assignment_done", "assigned_ok": N, "conflicts": N}`
  - `{"type": "alerts", "alerts": [{"carnet": "...", "course_code": "...", "reason": "...", "status": "..."}]}`
    (solo las alertas nuevas de cada fase, no acumuladas)
  - `{"type": "phase_completed", "phase": "horario_y_asignacion"}`
- `run_completed`:
  ```json
  {"type": "run_completed", "summary": {
    "period": "2026-01", "students_created": 10, "requests_valid": N,
    "requests_rejected": N, "courses_opened": N, "courses_closed": N,
    "groups_formed": N, "total_alerts": N, "exit_code": 0
  }}
  ```
  `exit_code`: `0` si no hay alertas sistémicas (ver sección 7), `1` si las hay.
- `cuatrimestre_summary` — censo global tras persistir:
  ```json
  {"type": "cuatrimestre_summary", "cuatrimestre_counts": {
    "cuatrimestre_1": N, "cuatrimestre_2": N, "cuatrimestre_3": N, "cuatrimestre_4": N},
    "graduados": N, "total_students": N}
  ```

## 4. Algoritmo paso a paso

Resolvé primero `base_dir` como se describe en la sección 1.1 (`data/` por defecto, o el
valor explícito de la invocación). Todas las rutas de abajo son relativas a `base_dir`,
salvo `nombres.md` que siempre está en la raíz del repo.

### Paso 0 — Migrar graduados
Para cada `students/DDDDDD.md`, calculá el "siguiente cuatrimestre pendiente" (mismo
criterio que el Paso B de `matricula-estudiante`: primer cuatrimestre 1→4 donde no todas
sus materias tienen nota ≥ `nota_minima` en el intento más reciente). Si ya aprobó los 4
cuatrimestres, movés el archivo **sin modificar su contenido** a `graduated/DDDDDD.md`
(creá `graduated/` si no existe). Hacé esto **antes** de cargar el censo activo.

### Paso 2 — Verificar consecutividad
Listá `periodos_lectivos/*.md` existentes, tomá el de período más reciente. Si existe y
`periodo` no es exactamente su siguiente consecutivo, **detené la ejecución sin escribir
nada** y reportá el error. Si no existe ningún período previo, esta es la corrida
inicializadora.

### Paso 3 — Crear estudiantes nuevos
Prefijo de carnet = últimos 2 dígitos del año de `periodo`. Buscá, entre todos los
`students/*.md` existentes (activos y en `graduated/`), el máximo secuencial ya usado con
ese prefijo; si no hay ninguno, empezá en `0001`. Creá `n_estudiantes` carnets consecutivos
de 6 dígitos.

Nombres: abrí `profesores.md` (dentro de `base_dir`), leé "Proximo indice libre del pool:
N". Abrí `nombres.md` (raíz del repo, 1000 líneas "Nombre Apellido"). Para cada estudiante
nuevo `i` (0-indexado),
el nombre es la línea en la posición `(N + i) mod 1000`. El cursor avanza a `N +
n_estudiantes` — ese valor es el `teacher_start_index` que le vas a pasar a
`matricula-horario` en el Paso 8 (mismo pool compartido, un solo cursor).

### Pasos 1+4 — Despacho de subagentes `matricula-estudiante`

Armá la lista completa de estudiantes activos de esta corrida (los nuevos del Paso 3 +
todos los continuantes cargados de `students/*.md`, ya sin los migrados en el Paso 0).
Determiná el período anterior (o `null` si es la corrida inicializadora).

Dividí la lista en lotes de tamaño máximo 5. Por cada lote, en un único turno/mensaje:
1. Para cada estudiante del lote, publicá `subagent_started` (ver sección 3).
2. Invocá el `Task` tool una vez por estudiante del lote — **todas las invocaciones del
   lote en el mismo mensaje**, no una por una con turnos intermedios — apuntando al skill
   `matricula-estudiante`, con el prompt conteniendo: `carnet`, snapshot de su Matricula +
   Expediente de Notas actuales, `periodo`, `periodo_anterior`, `probabilidad_aprobacion` y
   `nota_minima` efectivos, y el plan de estudios.
3. Esperá a que **todas** las invocaciones del lote devuelvan resultado antes de armar el
   siguiente lote.
4. Por cada resultado, parseá el bloque ` ```student-result `. Si no es parseable (subagente
   no devolvió el bloque esperado, crash, timeout), tratalo como si hubiera devuelto
   `"error": "Subagente no devolvio resultado valido"`. Publicá `subagent_completed` con
   `status: "ok"` o `"error"`, seguido de `pool_progress`.
5. Si `error != null`: agregá una alerta `{carnet, course_code: "", reason: "Error interno:
   <error>", status: "Error"}` para ese estudiante, y sus `requested_course_codes` quedan
   vacíos (no participa en las fases siguientes). **Nunca dejes que esto tumbe el lote ni la
   corrida** — seguí con el resto.
6. Si `error == null`: agregá sus `new_grades` al expediente en memoria del estudiante (se
   persistirán en el Paso 11), y guardá sus `requested_course_codes` para el despacho a
   `matricula-horario`.

Al agotar todos los lotes, publicá `pool_completed` con el conteo total de errores.

### Pasos 5-9 — Despacho del subagente `matricula-horario`

Publicá `phase_started` (fase `"horario_y_asignacion"`). Armá el prompt consolidado:
lista de `{carnet, requested_course_codes, promedio_historico}` de todos los estudiantes
con solicitud no vacía, los parámetros de escenario efectivos (`cupo_grupo`,
`minimo_apertura`, `max_aulas`, `capacidad_aula`), `periodo`, `teacher_start_index` (cursor
del Paso 3), el contenido completo de `nombres.md`, y el plan de estudios.

Invocá el `Task` tool **una sola vez**, apuntando a `matricula-horario`. Esperá su
resultado y parseá el bloque ` ```horario-result `.

Si `error != null` o el bloque no es parseable: **detené la corrida sin persistir ningún
archivo** y reportá el error al usuario — es una falla sistémica equivalente a período no
consecutivo, no una alerta rutinaria.

Si es válido: extraé `alerts`, `open_courses`, `closed_courses`, `groups_formed`,
`schedules`, `rosters`, `matricula_by_carnet`, `next_teacher_index`,
`new_teacher_records`. Publicá en orden `validation_done`+`alerts`, `demand_done`+`alerts`,
`grouping_done`, `scheduling_done`+`alerts`, `assignment_done`+`alerts` (separando las
alertas por la fase que las originó, usando su `reason`/`status` para clasificarlas —
`"Rechazada"` con motivo de prerrequisito/duplicada/ya aprobada/materia inexistente →
validación; `"Rechazada"` por cierre → demanda; `"Sin horario"` → scheduling; `"Sin
asignar"` → assignment), luego `phase_completed`.

### Paso 10 — Reunir alertas
Juntá las alertas de los subagentes de estudiante (errores internos) con las de
`matricula-horario` (pasos 5,6,8,9).

### Paso 11 — Persistir
Re-renderizá completo (nunca parchees texto) cada archivo tocado:
- `students/DDDDDD.md` de todo estudiante de esta corrida: notas nuevas (de
  `matricula-estudiante`) + entradas de matrícula (de `matricula_by_carnet` del resultado de
  `matricula-horario`) — formato exacto en sección 5.
- `periodos_lectivos/YYYY-PP.md` con `schedules`, `rosters`, alertas consolidadas.
- `profesores.md` con `next_teacher_index` como nuevo cursor y el registro acumulado
  (profesores previos + `new_teacher_records`).

## 5. Formato exacto de cada archivo de salida

### `students/DDDDDD.md`

```markdown
# Estudiante DDDDDD

## Matricula

| Periodo Lectivo | Codigo Materia | Grupo | Nombre Materia |
| --------------- | -------------- | ----- | -------------- |
| 2026-01         | MA001          | 01    | Matematicas I  |

## Expediente de Notas

| Periodo Lectivo | Codigo Materia | Nombre Materia | Nota (de 0 a 100) |
| --------------- | -------------- | --------------- | ----------------- |
| 2026-01         | MA001          | Matematicas I   | 85                |
```

El carnet va solo en el nombre de archivo y el encabezado `# Estudiante DDDDDD`. Si un
estudiante no tiene aún expediente de notas (recién creado), dejá esa tabla con solo el
encabezado y la fila separadora.

### `periodos_lectivos/YYYY-PP.md`

```markdown
# Periodo Lectivo YYYY-PP

## Horario

| Codigo Materia | Nombre Curso  | Grupo | Profesor   | Aula     | Horario                       |
| -------------- | ------------- | ----- | ---------- | -------- | ------------------------------ |
| MA001          | Matematicas I | 01    | Juan Perez | AULA-101 | L 07:00-08:40 / J 09:00-10:40 |

## Listas de Estudiantes por Materia y Grupo

### MA001 - Grupo 01

| Carné  | Apellidos       | Nombre |
| ------ | --------------- | ------ |
| 250005 | Aguilar Jimenes | Pedro  |

## Alertas para Revision Humana

| Carné  | Codigo Materia | Motivo | Estado |
| ------ | -------------- | ------ | ------ |
| 260031 | CS004          | ...    | ...    |
```

Una subsección `### CODIGO - Grupo NN` por cada combinación materia+grupo que tenga horario
asignado, en orden materia luego grupo; roster ordenado por apellido, luego nombre.

### `profesores.md`

```markdown
# Profesores

Proximo indice libre del pool: 7

| Indice Pool | Nombre Completo | Materia-Grupo |
| ----------- | ---------------- | ------------- |
| 3           | Colson Bridges    | MA001-01      |
```

Re-renderizá el archivo completo (cursor + registro acumulado) cada vez.

### `graduated/DDDDDD.md`

Mismo formato que `students/DDDDDD.md`, solo relocalizado sin modificar contenido.

### Formato de tabla

Pipe tables estándar. Criterio de aceptación: el archivo debe seguir siendo **parseable
como tabla Markdown por el modo default del proyecto** — headers exactos, estructura de
secciones `##`/`###` idéntica a los ejemplos.

## 6. Manejo de subagentes que fallan

- `matricula-estudiante` con `error != null` o resultado no parseable → alerta
  `status: "Error"` para ese estudiante únicamente, el resto de la corrida continúa
  normalmente (mismo contrato que `try/except` alrededor de `process_student` en el modo
  Python: un estudiante roto nunca tumba el lote ni la corrida).
- `matricula-horario` con `error != null` o resultado no parseable → falla sistémica de
  toda la corrida: detené la ejecución, no persistas ningún archivo, reportá el error al
  usuario. Es el único caso de falla de subagente que aborta (junto con período no
  consecutivo del Paso 2).

## 7. Manejo de errores y alertas (contenido, no de subagente)

Formato de alerta: `(carnet, codigo_materia, motivo, estado)`. Casos y estados:
`"Rechazada"` (prerrequisito, materia inexistente/ya aprobada/duplicada, curso cerrado),
`"Sin horario"` (grupo sin horario asignable), `"Sin asignar"` (conflicto de horario
individual insalvable), `"Error"` (subagente de estudiante con error interno).

Alertas "sistémicas" (afectan si la corrida se reporta como limpia): las de horario (`"No
fue posible asignar horario/aula/profesor sin conflictos"`, `"Conflicto de horario con otra
materia asignada al estudiante"`, `"Grupo sin horario asignado"`). El resto son rutinarias.

## 8. Criterio de éxito / salida

Al terminar, escribí un resumen en texto al usuario: período, estudiantes creados,
solicitudes válidas/rechazadas, cursos abiertos/cerrados, grupos formados, total de
alertas, y si hubo alertas sistémicas o la corrida quedó limpia. Publicá `run_completed` y
`cuatrimestre_summary` si el visualizador está activo.
