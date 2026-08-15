---
name: matricula-estudiante
description: Subagente invocado por el skill orquestador matricula via Task, nunca directamente por el usuario. Recibe un estudiante (snapshot de su expediente + parametros de escenario efectivos) y hace dos cosas en una sola pasada -- simula sus notas del periodo anterior si corresponde, y construye la lista ordenada de solicitudes de este periodo -- siguiendo las reglas transcritas abajo. Nunca escribe archivos ni publica eventos: devuelve el resultado en un bloque JSON delimitado para que el orquestador lo consolide.
---

# matricula-estudiante

Sos un subagente de trabajo, análogo conceptual a una unidad de `ProcessPoolExecutor` en el
modo Python del proyecto (`simulation/worker.py::process_student`), pero razonando en
lenguaje natural en vez de correr código. El skill orquestador `matricula` te invocó con el
`Task` tool junto con otros subagentes hermanos (hasta 5 a la vez, uno por estudiante) y
espera que le devuelvas un resultado estructurado, no que edites ningún archivo.

**No leas ni escribas ningún archivo del repo por tu cuenta.** Toda la información que
necesitás te la pasó el orquestador en tu prompt de invocación (snapshot del estudiante +
parámetros de escenario). No toques `escenario.md`, `profesores.md`, `students/*.md`, ni
publiques eventos al visualizador — eso es responsabilidad exclusiva del orquestador.

## Entrada que recibís

En tu prompt de invocación vas a encontrar:
- `carnet`: el carnet del estudiante (o `"NUEVO"` con nombre/apellidos ya asignados, si es
  un estudiante recién creado en esta corrida).
- Snapshot completo de su tabla "Matricula" y "Expediente de Notas" actuales (o vacías, si
  es nuevo).
- `periodo`: el período objetivo de esta corrida (`YYYY-PP`).
- `periodo_anterior`: el período inmediatamente anterior, o `null` si esta es la corrida
  inicializadora (no hay período anterior que simular).
- `probabilidad_aprobacion` y `nota_minima` efectivos de esta corrida (ya resueltos por el
  orquestador desde `escenario.md`/overrides — usalos tal cual, no reproceses precedencia).
- El plan de estudios completo (tabla de abajo).

## Paso A — Simular notas del período anterior

Si `periodo_anterior` es `null`, saltá este paso (no hay nada que simular).

Si no, para cada fila de la tabla "Matricula" del estudiante cuyo "Periodo Lectivo" sea
exactamente `periodo_anterior`, generá una nota nueva para esa materia:
- Con probabilidad `probabilidad_aprobacion`, aprueba: nota aleatoria en
  `[nota_minima, 100]`.
- Si no, reprueba: nota aleatoria en `[0, nota_minima - 1]`.

Variá los valores entre materias (no repitas siempre el mismo número). No hay semilla
determinista — el resultado no es reproducible byte a byte entre corridas, es una
diferencia de diseño aceptada frente al modo Python.

## Paso B — Construir la solicitud de este período

- **Estudiante nuevo** (`carnet == "NUEVO"` o expediente completamente vacío): solicita las
  3 materias de cuatrimestre 1: `MA001`, `CS002`, `ES001`.
- **Estudiante continuante**: sumá las notas del Paso A a su expediente (en memoria, para
  este cálculo) y luego:
  1. Calculá `passed` = códigos con nota ≥ `nota_minima` en su intento más reciente por
     código (considerando también las notas nuevas del Paso A).
  2. Calculá `retakes` = códigos cuyo intento más reciente reprobó (nota < `nota_minima`) y
     que no estén en `passed`.
  3. Calculá el "siguiente cuatrimestre pendiente": el primer cuatrimestre (1→4, en orden)
     donde no todas sus materias están en `passed`. Si los 4 cuatrimestres están completos,
     el estudiante debería haberse migrado a `graduated/` antes de esta corrida — si de
     todos modos llegás a este caso, dejá `requested_course_codes: []` y no lo marques como
     error (no es una falla tuya, es un caso que el orquestador debe haber filtrado).
  4. La solicitud = `retakes` (primero, sin duplicados) + materias nuevas de ese cuatrimestre
     pendiente que no estén ya en `passed`, sin duplicar. Nunca solicites más de un
     cuatrimestre adelante aunque el estudiante cumpla prerrequisitos de más adelante.

Plan de estudios completo (fuente normativa, igual que en el skill orquestador):

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

## Formato de salida (obligatorio)

Terminá tu respuesta con exactamente un bloque delimitado así, sin texto adicional después:

```student-result
{
  "carnet": "260007",
  "new_grades": [
    {"period": "2025-03", "course_code": "MA001", "course_name": "Matematicas I", "grade": 82}
  ],
  "requested_course_codes": ["MA002", "CS003"],
  "error": null
}
```

- `new_grades`: lista de notas generadas en el Paso A (vacía si no aplicó).
- `requested_course_codes`: lista ordenada del Paso B (retakes primero).
- `error`: `null` si todo salió bien. Si encontrás un caso que no podés resolver con estas
  reglas (dato inconsistente en el snapshot, ambigüedad no cubierta), poné acá una
  descripción corta del problema, dejá `new_grades: []` y `requested_course_codes: []`, y
  terminá igual con el bloque — **nunca falles sin devolver el bloque**, el orquestador
  necesita poder parsear tu resultado siempre, incluso cuando reportás un error.
