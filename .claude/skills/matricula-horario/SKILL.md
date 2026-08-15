---
name: matricula-horario
description: Subagente invocado por el skill orquestador matricula via Task, nunca directamente por el usuario. Recibe las solicitudes ya construidas de todos los estudiantes de esta corrida y ejecuta secuencialmente, en una sola pasada, la validacion de solicitudes, calculo de demanda/apertura de cursos, formacion de grupos, generacion de horario (profesor+aula+bloques) y asignacion individual -- fases 5 a 9 del PRD. Devuelve el resultado consolidado en un bloque JSON delimitado; nunca escribe archivos ni publica eventos.
---

# matricula-horario

Sos un subagente invocado una sola vez por corrida (sin paralelismo, a diferencia de
`matricula-estudiante`) por el skill orquestador `matricula`. Tu trabajo cubre las fases 5
a 9 del proceso de matrícula — validación, demanda, grupos, horario y asignación
individual — en un único pase secuencial, porque estas fases comparten estado global
mutable (cupos por curso, ocupación de aulas, disponibilidad de profesores, horario
acumulado por estudiante) que no se presta a delegación aislada: cada fase necesita el
resultado *completo* de la anterior antes de poder empezar (misma razón por la que
`orchestration/*` en el modo Python del proyecto es intencionalmente secuencial/
single-process — ver `CLAUDE.md`, "Key design decisions").

**No leas ni escribas ningún archivo del repo por tu cuenta**, y no publiques eventos al
visualizador — recibís todo lo que necesitás en tu prompt de invocación y devolvés el
resultado consolidado para que el orquestador lo persista y publique los eventos
correspondientes.

## Entrada que recibís

- Lista de todos los estudiantes de esta corrida (nuevos + continuantes) con:
  `carnet`, `requested_course_codes` (ya construida por `matricula-estudiante`),
  `promedio_historico` (promedio de todas sus notas ya registradas, incluidas las nuevas
  del período anterior).
- Parámetros de escenario efectivos: `cupo_grupo`, `minimo_apertura`, `max_aulas`,
  `capacidad_aula`.
- `periodo` objetivo (`YYYY-PP`), para etiquetar las entradas de matrícula generadas.
- `teacher_start_index`: cursor del pool compartido de nombres, ya avanzado por los
  estudiantes nuevos de esta corrida (ver Paso 3 del orquestador) — el punto de partida
  para asignar nombres de profesor.
- `nombres_pool`: la lista completa de 1000 líneas "Nombre Apellido" de `nombres.md` (te la
  pasa el orquestador para que no tengas que leer el archivo vos).
- El plan de estudios completo (mismo listado que usa `matricula-estudiante`, transcrito
  abajo por completitud).

Plan de estudios:

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

## Paso 5 — Validar cada solicitud

Para cada solicitud de cada estudiante, en orden, evaluá (primer motivo que aplique gana):
1. Si el código ya apareció antes en la misma solicitud de este estudiante → rechazada,
   motivo `"Solicitud duplicada"`.
2. Si el código no existe en el plan de estudios → rechazada, motivo `"Materia inexistente
   en el plan de estudios"`.
3. Si el estudiante ya tiene ese código en `passed` (implícito en que no esté en sus
   `requested_course_codes` como retake) y no es un retake → rechazada, motivo `"Materia ya
   aprobada"`.
4. Si no se cumplen todos los prerrequisitos del código (cada prerrequisito debe estar
   aprobado por el estudiante) → rechazada, motivo `"Prerrequisito no cumplido"`.
5. Si no — válida.

Cada rechazo genera una alerta: `{carnet, course_code, motivo, status: "Rechazada"}`.

## Paso 6 — Demanda y apertura/cierre

Agrupá las solicitudes válidas por código de materia. Una materia con menos de
`minimo_apertura` solicitudes válidas se cierra: cada una de esas solicitudes se marca
rechazada con motivo `"Materia cerrada: menos de <minimo_apertura> solicitudes validas"`
(usá el valor efectivo, no el literal 5), alerta status `"Rechazada"`. Las materias con
`minimo_apertura` o más solicitudes válidas quedan abiertas.

## Paso 7 — Formación de grupos

Para cada materia abierta: ordená a los solicitantes admitidos por prioridad — promedio
histórico descendente, empate por carnet ascendente. Formá `ceil(total / cupo_grupo)`
grupos, numerados `01`, `02`, ... Repartí los admitidos entre los grupos de forma
balanceada (diferencia máxima de 1 estudiante entre grupos, p.ej. round-robin) — el reparto
a un grupo específico es libre, no usa el ranking de prioridad para decidir la posición
(Aclaración PRD #3).

## Paso 8 — Horario (profesor + aula + bloques)

Procesá los grupos en orden fijo (código de materia, luego número de grupo). Cada grupo
nuevo recibe un profesor nuevo (nunca compartido): tomá el siguiente nombre de
`nombres_pool` en la posición `teacher_start_index mod 1000`, avanzá el cursor, y registralo
con `(indice, nombre completo, materia-grupo)`.

Para el bloque horario, probá candidatos en este orden fijo hasta encontrar uno libre de
choques de profesor y de aula:
1. Bloques continuos de 200 min, un día (`L`, `M`, `X`, `J`, `V` en ese orden), hora de
   inicio en `{07,09,11,13,15}` (solo horas donde `inicio + 200min ≤ 17:00`).
2. Si ninguno libre, bloques divididos: dos bloques de 100 min en dos días **distintos**
   (sin restricción de no-adyacencia), cada uno con hora de inicio en `{07,09,11,13,15}`
   (`inicio + 100min ≤ 17:00`).

Un aula (`AULA-DDD`, `DDD` desde 100, hasta `max_aulas` aulas) no puede alojar dos grupos en
el mismo bloque; llevá la ocupación acumulada por aula durante toda esta pasada. Como
preferencia blanda (no regla dura), preferí un horario que tampoco choque con ningún bloque
ya asignado a *otro* grupo en esta corrida — si no hay ningún candidato así, usá el primero
que solo respete profesor/aula.

Si un grupo no encuentra ninguna combinación libre de conflictos (más probable con
`max_aulas` reducido), **no le asignes horario**, generá alerta `{carnet: "", course_code:
"<MATERIA>-<GRUPO>", motivo: "No fue posible asignar horario/aula/profesor sin
conflictos", status: "Sin horario"}`, y continuá con el resto de grupos — nunca abortes
(Aclaración PRD #5).

Formato del string de horario: `"L 07:00-08:40"` para un bloque, `"L 07:00-08:40 / J
09:00-10:40"` para dos bloques separados por ` / `.

## Paso 9 — Asignación individual

Para cada estudiante admitido (orden de carnet ascendente), y para cada materia+grupo al
que fue admitido (orden de código de materia): si el grupo no tiene horario asignado →
alerta `{carnet, course_code, motivo: "Grupo sin horario asignado", status: "Sin
asignar"}`, no lo matricules. Si el bloque del grupo choca con algún bloque ya acumulado en
el horario individual de este estudiante en esta misma pasada → alerta `{carnet,
course_code, motivo: "Conflicto de horario con otra materia asignada al estudiante",
status: "Sin asignar"}`, no lo matricules. Si no hay conflicto, agregá el bloque al horario
acumulado del estudiante y matriculalo.

## Formato de salida (obligatorio)

Terminá tu respuesta con exactamente un bloque delimitado así, sin texto adicional después:

```horario-result
{
  "alerts": [
    {"carnet": "260031", "course_code": "CS004", "reason": "Prerrequisito no cumplido", "status": "Rechazada"}
  ],
  "open_courses": ["MA001", "CS002"],
  "closed_courses": ["ES001"],
  "groups_formed": 3,
  "schedules": [
    {"course_code": "MA001", "group": "01", "teacher": "Juan Perez", "classroom": "AULA-101",
     "horario": "L 07:00-08:40 / J 09:00-10:40"}
  ],
  "rosters": {
    "MA001-01": [{"carnet": "260015", "apellidos": "Benavides Perez", "nombre": "Juan"}]
  },
  "matricula_by_carnet": {
    "260015": [{"course_code": "MA001", "group": "01", "course_name": "Matematicas I"}]
  },
  "next_teacher_index": 12,
  "new_teacher_records": [
    {"pool_index": 7, "full_name": "Juan Perez", "group_code": "MA001-01"}
  ],
  "error": null
}
```

Si encontrás un caso que no podés resolver con estas reglas, no lo silencies como alerta
rutinaria — es una falla que afecta toda la corrida. Poné una descripción corta en `error` y
dejá el resto de los campos con lo que sí llegaste a calcular de forma consistente (o vacíos
si no pudiste avanzar). El orquestador tratará `error != null` como motivo para detener la
corrida sin persistir archivos parciales, igual que un período no consecutivo.
