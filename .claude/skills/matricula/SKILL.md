---
name: matricula
description: Ejecuta un periodo completo del proceso de matricula universitaria (PRD.md) leyendo y escribiendo directamente los archivos Markdown de students/, periodos_lectivos/ y profesores.md, sin invocar ningun script Python del proyecto -- toda la logica de negocio (validacion de prerrequisitos, demanda, formacion de grupos, horario, notas simuladas) se calcula con el razonamiento del propio agente segun las reglas transcritas en este skill. Usar cuando el usuario pida correr/simular un periodo lectivo, avanzar la matricula, o invoque "/matricula <periodo> [n-estudiantes] [overrides]".
---

# matricula

Este skill reimplementa en lenguaje natural el pipeline de 11 pasos del proceso de
matricula descrito en `PRD.md`. **No uses Bash para invocar `python -m matricula`, ni
importes o ejecutes nada de `src/matricula/orchestration/`, `src/matricula/io/`,
`src/matricula/simulation/` o `src/matricula/orchestration/runner.py`.** Ese es el modo
"default" del proyecto (sin LLM) y debe seguir siendo la referencia determinista e
independiente. Este skill es un camino paralelo: vos (el agente) leés los `.md`, hacés
todos los cálculos, y escribís los `.md` de vuelta, siguiendo exactamente las reglas de
abajo.

`src/matricula/domain/study_plan.py` y `PRD.md` son la fuente normativa de las reglas de
negocio — si algo en este documento y `PRD.md` difieren, `PRD.md` (incluida su sección
"Aclaraciones") gana.

## 1. Argumentos de invocación

- `periodo` (requerido): `YYYY-PP`, `PP` en `{01, 02, 03}`.
- `n_estudiantes` (opcional, default `10`): cantidad de estudiantes nuevos a crear en esta
  corrida. Esto es un cambio de comportamiento respecto al PRD original (que fijaba 10
  siempre) — ahora es parametrizable por invocación.
- Overrides de escenario opcionales, formato `clave=valor` (ver tabla de la sección 2):
  `max_aulas=`, `capacidad_aula=`, `cupo_grupo=`, `minimo_apertura=`,
  `probabilidad_aprobacion=`, `nota_minima=`.
- `viz_port` (opcional, default `8765`): puerto del visualizador standalone.

Ejemplo: `/matricula 2026-01 10` · `/matricula 2026-03 10 max_aulas=2`

## 2. Escenario: `escenario.md`

Archivo opcional en la raíz de datos (`base_dir`, junto a `students/`, `periodos_lectivos/`,
`profesores.md`), con los límites que hoy son constantes fijas en `PRD.md`/`config.py`.
Formato:

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

**Precedencia por parámetro** (de mayor a menor prioridad):
1. Override explícito pasado en la invocación de este skill (solo aplica a esa corrida).
2. Valor en la columna `Valor` de `escenario.md`, si el archivo existe y menciona ese parámetro.
3. Default PRD de la tabla de arriba.

Reglas:
- Si `escenario.md` no existe, **no lo crees automáticamente** — usá los defaults PRD y
  seguí. Solo creá o reescribí el archivo si el usuario pide explícitamente "guardar este
  escenario" o similar; en ese caso re-renderizá la tabla completa (nunca la parchees).
- Los overrides de invocación son puntuales: no los escribas de vuelta a `escenario.md`
  salvo pedido explícito del usuario.
- Al arrancar, reportá en un mensaje al usuario y en el evento `run_started` (sección 3)
  los valores efectivos que estás usando, marcando cuáles se desvían del default PRD y de
  dónde salió cada desviación (archivo o override) — así una corrida con restricciones
  reducidas queda trazable.
- `n_estudiantes` de la invocación tiene la misma precedencia que cualquier otro override
  sobre `estudiantes_nuevos_por_periodo`.

## 3. Protocolo de emisión de eventos al visualizador

El humano ya debe haber corrido `python -m matricula viz` (o `matricula viz`) de antemano.
Vos **no levantás el servidor** — solo publicás si detectás que está corriendo.

Al arrancar:
```bash
curl -s -o /dev/null -w "%{http_code}" --max-time 1 http://localhost:<viz_port>/health
```
Si no responde `200`, avisá una vez ("visualizador no disponible en el puerto <viz_port>,
continuo sin publicar eventos") y seguí la corrida normalmente — nunca bloquees ni abortes
por esto.

Si responde `200`, publicá en cada punto de progreso vía:
```bash
curl -s -X POST http://localhost:<viz_port>/publish \
  -H "Content-Type: application/json" \
  -d '<json>'
```
Mismo vocabulario y forma que usa el modo Python (`orchestration/runner.py`), en este
orden:

- `run_started` — `{"type": "run_started", "period": "2026-01", "total_students": 20}`
  (`total_students` = estudiantes activos existentes + nuevos de esta corrida).
- `pool_progress` — uno por estudiante procesado (notas simuladas + solicitud construida):
  `{"type": "pool_progress", "completed": N, "total": M}`.
- `pool_completed` — `{"type": "pool_completed", "completed": M, "total": M, "errors": 0}`.
- `validation_done` — `{"type": "validation_done", "valid": N, "rejected": N}`.
- `demand_done` — `{"type": "demand_done", "opened": N, "closed": N}`.
- `grouping_done` — `{"type": "grouping_done", "groups_formed": N}`.
- `scheduling_done` — `{"type": "scheduling_done", "scheduled": N, "unschedulable": N}`.
- `assignment_done` — `{"type": "assignment_done", "assigned_ok": N, "conflicts": N}`.
- `alerts` — solo las alertas **nuevas** de la fase que acaba de terminar (no acumuladas):
  `{"type": "alerts", "alerts": [{"carnet": "...", "course_code": "...", "reason": "...", "status": "..."}]}`.
  Emitilo después de `validation_done`, `demand_done`, `scheduling_done` y
  `assignment_done` si esa fase generó alertas nuevas.
- `run_completed` — al final:
  ```json
  {"type": "run_completed", "summary": {
    "period": "2026-01", "students_created": 10, "requests_valid": N,
    "requests_rejected": N, "courses_opened": N, "courses_closed": N,
    "groups_formed": N, "total_alerts": N, "exit_code": 0
  }}
  ```
  `exit_code`: `0` si no hay alertas sistémicas (ver sección 6), `1` si las hay.
- `cuatrimestre_summary` — censo global tras persistir (todos los estudiantes activos en
  `students/`, agrupados por cuatrimestre pendiente, más el total de graduados):
  ```json
  {"type": "cuatrimestre_summary", "cuatrimestre_counts": {
    "cuatrimestre_1": N, "cuatrimestre_2": N, "cuatrimestre_3": N, "cuatrimestre_4": N},
    "graduados": N, "total_students": N}
  ```

No emitas `agent_message` salvo que quieras narrar algo puntual al humano — el frontend lo
soporta, pero no es parte del contrato mínimo.

## 4. Algoritmo paso a paso

Determiná primero `base_dir` = directorio de trabajo actual (cwd) desde donde te invocaron.
Todas las rutas de abajo son relativas a `base_dir`.

### Paso 0 — Migrar graduados
Para cada `students/DDDDDD.md`, calculá el "siguiente cuatrimestre pendiente" (ver Paso 4).
Si es `null` (aprobó las 12 materias del plan, todas con nota ≥ `nota_minima` en su intento
más reciente), movés el archivo **sin modificar su contenido** a `graduated/DDDDDD.md`
(creá `graduated/` si no existe). Hacé esto **antes** de cargar el censo activo del resto
del pipeline — un graduado no debe ocupar cupo ni recibir solicitudes esta corrida.

### Paso 1 — Simular notas del período anterior
Determiná el período anterior (el que precede a `periodo` en la secuencia `01→02→03→año+1
01`). Para cada estudiante activo (`students/*.md`, ya sin los recién migrados) que tenga
una fila en su tabla "Matricula" con ese período anterior, generá una nota nueva en su
"Expediente de Notas" por cada materia matriculada entonces:
- Con probabilidad `probabilidad_aprobacion`, aprueba: nota aleatoria en `[nota_minima, 100]`.
- Si no, reprueba: nota aleatoria en `[0, nota_minima - 1]`.

Variá los valores entre estudiantes y materias (no uses siempre el mismo número). Esta
corrida no tiene semilla determinista — a diferencia del modo Python, el resultado no es
reproducible byte a byte entre corridas; es una diferencia de diseño aceptada.

Si `periodo` es la primera corrida sobre este `base_dir` (no hay `periodos_lectivos/*.md`
previos), no hay período anterior que simular — saltá este paso.

### Paso 2 — Verificar consecutividad
Listá `periodos_lectivos/*.md` existentes, tomá el de período más reciente (orden
`YYYY-PP` ascendente, con `01<02<03` y el año como primer criterio). Si existe y `periodo`
no es exactamente su siguiente consecutivo (`03` pasa a `01` del año siguiente), **detené
la ejecución sin escribir nada** y reportá el error al usuario (mismo criterio que
`domain/periods.py::is_consecutive`). Si no existe ningún período previo, esta es la
corrida inicializadora.

### Paso 3 — Crear estudiantes nuevos
Prefijo de carnet = últimos 2 dígitos del año de `periodo` (`2026` → `26`). Buscá, entre
todos los `students/*.md` existentes (activos y en `graduated/`, para nunca reusar un
carnet), el máximo secuencial ya usado con ese prefijo; si no hay ninguno, empezá en
`0001`. Creá `n_estudiantes` carnets consecutivos de 6 dígitos (`prefijo + secuencial de 4
dígitos`).

Nombres: abrí `profesores.md` (raíz del repo, no `base_dir` de datos si son distintos —
normalmente el mismo), leé la línea "Proximo indice libre del pool: N" (cursor). Abrí
`nombres.md` (raíz del repo), que tiene 1000 líneas numeradas "Nombre Apellido". Para cada
estudiante nuevo `i` (0-indexado), el nombre completo es la línea en la posición
`(N + i) mod 1000` (wraparound, nunca falla por agotamiento). Separá esa línea en `nombre`
(primera palabra o palabras hasta donde corresponda) y `apellidos` (resto) — seguí el
mismo criterio de partición que ya uses para nombres de profesor (ver Paso 8). Al terminar
de asignar todos los nombres de estudiantes de este paso, el cursor avanza a `N +
n_estudiantes`; ese valor intermedio se usa luego como punto de partida para los nombres de
profesor del Paso 8 (mismo pool compartido, un solo cursor, nunca reutilizado).

### Paso 4 — Construir solicitudes por estudiante
Para cada estudiante activo (existentes + nuevos):
- **Nuevo**: solicita las 3 materias de cuatrimestre 1 (`MA001`, `CS002`, `ES001`).
- **Continuante**: calculá `passed` = códigos con nota ≥ `nota_minima` en su intento más
  reciente por código. Calculá `retakes` = códigos cuyo intento más reciente reprobó
  (nota < `nota_minima`) y que no estén en `passed` (por si se recuperó en un intento
  posterior). Calculá el "siguiente cuatrimestre pendiente": el primer cuatrimestre
  (1→4, en orden) donde no todas sus materias están en `passed`; si los 4 cuatrimestres
  están completos, el estudiante ya se migró en el Paso 0 y no debería llegar aquí.
  La solicitud = `retakes` (primero, sin duplicados) + materias nuevas de ese cuatrimestre
  pendiente que no estén ya en `passed`, sin duplicar. Nunca solicita más de un
  cuatrimestre adelante aunque cumpla prerrequisitos de más adelante.

Plan de estudios completo (transcribir tal cual, es la fuente normativa):

| Cuatrimestre | Código | Nombre | Prerrequisitos |
| --- | --- | --- | --- |
| 1 | MA001 | Matematicas I | — |
| 1 | CS002 | Intro a Compu | — |
| 1 | ES001 | Humanidades | — |
| 2 | CS003 | Programacion I | MA001, CS002 |
| 2 | MA002 | Matematicas II | MA001 |
| 2 | ES010 | Ingles I | — |
| 3 | CS004 | Programacion II | CS003 |
| 3 | MA003 | Matematicas III | MA002 |
| 3 | ES020 | Ingles II | ES010 |
| 4 | CS005 | Algoritmos | CS004 |
| 4 | MA004 | Matematicas IV | MA003 |
| 4 | CS020 | Redes | — |

### Paso 5 — Validar cada solicitud
Para cada solicitud de cada estudiante, en orden, evaluá (primer motivo que aplique gana):
1. Si el código ya apareció antes en la misma solicitud de este estudiante → rechazada,
   motivo `"Solicitud duplicada"`.
2. Si el código no existe en el plan de estudios → rechazada, motivo `"Materia inexistente
   en el plan de estudios"`.
3. Si el código ya está en `passed` (nota ≥ `nota_minima`) y **no** es un retake (es decir,
   el intento más reciente ya aprobó) → rechazada, motivo `"Materia ya aprobada"`.
4. Si no se cumplen todos los prerrequisitos del código (cada prerrequisito debe estar en
   `passed`) → rechazada, motivo `"Prerrequisito no cumplido"`.
5. Si no — válida.

Cada rechazo genera una alerta: `{carnet, course_code, motivo, status: "Rechazada"}`.

### Paso 6 — Demanda y apertura/cierre
Agrupá las solicitudes válidas por código de materia. Una materia con menos de
`minimo_apertura` solicitudes válidas se cierra: cada una de esas solicitudes se marca
rechazada con motivo `"Materia cerrada: menos de X solicitudes validas"` (usá el valor
efectivo de `minimo_apertura`, no el literal 5), alerta status `"Rechazada"`. Las materias
con `minimo_apertura` o más solicitudes válidas quedan abiertas.

### Paso 7 — Formación de grupos
Para cada materia abierta: ordená a los solicitantes admitidos por prioridad — promedio
histórico de notas descendente, empate por carnet ascendente (más antiguo primero) — esto
solo importa si en algún momento hay más solicitantes que cupo total disponible; en este
sistema no hay techo de grupos, así que en la práctica todos entran. Formá
`ceil(total / cupo_grupo)` grupos, numerados `01`, `02`, ... Repartí los admitidos entre
los grupos de forma balanceada (diferencia máxima de 1 estudiante entre grupos, p.ej.
round-robin) — el reparto a un grupo específico es libre, no usa el ranking de prioridad
para decidir la posición (Aclaración PRD #3).

### Paso 8 — Horario (profesor + aula + bloques)
Procesá los grupos en orden fijo (código de materia, luego número de grupo). Cada grupo
nuevo recibe un profesor nuevo (nunca compartido, ni entre grupos de la misma materia):
tomá el siguiente nombre del pool compartido (mismo mecanismo que Paso 3, continuando el
cursor donde quedó tras los estudiantes), agregalo a `profesores.md` con su
`(indice, nombre completo, materia-grupo)`.

Para el bloque horario, probá candidatos en este orden fijo hasta encontrar uno libre de
choques de profesor y de aula:
1. Bloques continuos de 200 min, un día (`L`, `M`, `X`, `J`, `V` en ese orden), hora de
   inicio en `{07,09,11,13,15}` (solo horas donde `inicio + 200min ≤ 17:00`).
2. Si ninguno libre, bloques divididos: dos bloques de 100 min en dos días **distintos**
   (sin restricción de no-adyacencia — lunes+martes es válido), cada uno con hora de inicio
   en `{07,09,11,13,15}` (`inicio + 100min ≤ 17:00`).

Un profesor nunca puede tener dos grupos al mismo tiempo (es nuevo, así que solo compite
consigo mismo dentro de este grupo — no hay conflicto de profesor real, cada grupo tiene su
propio profesor). Un aula (`AULA-DDD`, `DDD` desde 100, hasta `max_aulas` aulas —
`AULA-100`..`AULA-<099+max_aulas>`) no puede alojar dos grupos en el mismo bloque; llevá la
ocupación acumulada por aula durante toda esta corrida. Como preferencia blanda (no regla
dura), preferí un horario que tampoco choque con ningún bloque ya asignado a *otro* grupo
en esta corrida — minimiza que un estudiante con varias materias del mismo cuatrimestre
tenga choques en el Paso 9; si no hay ningún candidato así, usá el primero que solo respete
profesor/aula.

Si un grupo no encuentra ninguna combinación de aula+horario libre de conflictos (esto es
más probable con `max_aulas` reducido), **no le asignes horario**, generá alerta
`{carnet: "", course_code: "<MATERIA>-<GRUPO>", motivo: "No fue posible asignar
horario/aula/profesor sin conflictos", status: "Sin horario"}`, y continuá con el resto de
grupos — nunca abortes la corrida completa (Aclaración PRD #5).

Formato del string de horario (columna "Horario" del período): `"L 07:00-08:40"` para un
bloque, `"L 07:00-08:40 / J 09:00-10:40"` para dos bloques separados por ` / ` (hora de fin
= hora inicio + duración, formato `HH:MM`).

### Paso 9 — Asignación individual
Para cada estudiante admitido (orden de carnet ascendente), y para cada materia+grupo al
que fue admitido (orden de código de materia): si el grupo no tiene horario asignado
(Paso 8 generó alerta) → alerta `{carnet, course_code, motivo: "Grupo sin horario
asignado", status: "Sin asignar"}`, no lo matricules. Si el bloque del grupo choca con
algún bloque ya acumulado en el horario individual de este estudiante en esta misma
corrida → alerta `{carnet, course_code, motivo: "Conflicto de horario con otra materia
asignada al estudiante", status: "Sin asignar"}`, no lo matricules. Si no hay conflicto,
agregá el bloque al horario acumulado del estudiante y matriculalo (esto es lo que va a la
tabla "Matricula" del estudiante y al roster del período).

### Paso 10 — Reunir alertas
Juntá todas las alertas generadas en los Pasos 5, 6, 8 y 9 (más cualquier caso no cubierto
explícitamente por estas reglas que decidas tratar como alerta — ver sección 6).

### Paso 11 — Persistir
Re-renderizá completo (nunca parchees texto) cada archivo tocado:
- `students/DDDDDD.md` de todo estudiante activo de esta corrida (nuevo o existente con
  cambios de notas/matrícula) — formato exacto en sección 5.
- `periodos_lectivos/YYYY-PP.md` con horario, rosters por materia+grupo, alertas.
- `profesores.md` con el cursor final del pool (avanzado por estudiantes + profesores de
  esta corrida) y el registro acumulado (profesores previos + los nuevos de esta corrida).

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

El carnet va solo en el nombre de archivo y el encabezado `# Estudiante DDDDDD`, no hace
falta repetirlo en el cuerpo. Si un estudiante no tiene aún expediente de notas (recién
creado), dejá la tabla de "Expediente de Notas" con solo el encabezado y la fila
separadora, sin filas de datos.

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
asignado, en orden materia luego grupo; roster ordenado por apellido, luego nombre. Nunca
mezcles estudiantes de distintos grupos/materias en la misma tabla.

### `profesores.md`

```markdown
# Profesores

Proximo indice libre del pool: 7

| Indice Pool | Nombre Completo | Materia-Grupo |
| ----------- | ---------------- | ------------- |
| 3           | Colson Bridges    | MA001-01      |
```

`Indice Pool` es la posición 0-999 en `nombres.md` de donde salió ese nombre — la clave que
evita reusar el mismo índice dos veces. Re-renderizá el archivo completo (cursor +
registro acumulado, no solo lo nuevo de esta corrida) cada vez.

### `graduated/DDDDDD.md`

Mismo formato que `students/DDDDDD.md`, solo relocalizado sin modificar contenido.

### Formato de tabla

Pipe tables estándar: `| Col1 | Col2 |`, fila separadora `| --- | --- |` (o con guiones
alineados al ancho de columna, como en los ejemplos de arriba — cualquiera de las dos
formas es válida). El criterio de aceptación es que el archivo siga siendo **parseable
como tabla Markdown por el modo default del proyecto** si alguien corre `python -m
matricula run` sobre el mismo directorio después — no hace falta paridad byte a byte, pero
sí headers exactos (mismo texto, mismo orden de columnas) y estructura de secciones `##`/`###`.

## 6. Manejo de errores y alertas

Formato de alerta: `(carnet, codigo_materia, motivo, estado)`. Casos:
- Prerrequisito no cumplido / materia inexistente / ya aprobada / duplicada → `"Rechazada"`.
- Curso cerrado por baja demanda → `"Rechazada"`.
- Grupo sin horario asignable → `"Sin horario"`.
- Conflicto de horario individual insalvable → `"Sin asignar"`.
- Cualquier caso que no puedas resolver con estas reglas (dato inconsistente, ambigüedad no
  cubierta): generá una alerta con motivo descriptivo y estado `"Error"`, y **seguí con el
  resto del período** — nunca abortes toda la corrida por un caso aislado.
- Único caso que sí aborta sin escribir nada: período no consecutivo (Paso 2).

Alertas "sistémicas" (afectan si la corrida se reporta como limpia o no): las de horario
(`"No fue posible asignar horario/aula/profesor sin conflictos"`, `"Conflicto de horario con
otra materia asignada al estudiante"`, `"Grupo sin horario asignado"`). El resto
(rechazos por prerrequisito, curso cerrado, etc.) son rutinarias — no implican que la
corrida haya fallado.

## 7. Criterio de éxito / salida

Al terminar, escribí un resumen en texto al usuario: período, estudiantes creados,
solicitudes válidas/rechazadas, cursos abiertos/cerrados, grupos formados, total de
alertas, y si hubo alertas sistémicas (equivalente al exit code 1 del modo Python) o la
corrida quedó limpia (equivalente a exit code 0). Publicá el evento `run_completed` y
`cuatrimestre_summary` si el visualizador está activo (sección 3).
