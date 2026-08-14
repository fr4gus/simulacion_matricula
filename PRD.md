# Sistema Multiagentico para Simular Proceso de Matricula

## Descripcion

El objetivo del documento es describir un escenario ficticio donde se desea crear un sistema multiagentico que se encarge de procesar para un cuatrimestre especifico la generacion de horarios asi como la asignacion de estudiantes a los cupos de los cursos y generar para cada estudiante su horario de estudios.

Este documento va a servir como base para plantear la delimitacion de los factores como cursos, estudiantes, profesores y aulas.

## Objetivos para el Agente IA

1. Revisar el planteamiento y elevar cualquier inconsistencia que pudiera provocar que este sistema no pueda crear el horario de los cursos, ni de los estudiantes. Por ejemplo que los codigos de las materias no se repitan y que no exista una dependencia circular entre materias y sus requisitos.
2. Crear la orquestracion de agentes usando python para hacer que el sistema sea lo mas autonomo posible (no vamos a usar ningun wrapper LLM)

## Supuestos

1. La nota minima para pasar una materia es 70. Si la nota es inferior, el estudiante debe repetir el curso en el siguiente periodo lectivo.
1. Un estudiante puede matricular todas las materias que quiera siempre y cuando cumpla con los requisitos.
1. Las solicitudes de materias se atienden por el promedio de todas las notas historicas de cada estudiante. Entre mejor sea el promedio, mayor prioridad tendra para obtener un cupo. En caso de empate, tendra prioridad el carne menor, por ser el mas antiguo.
1. El cupo maximo por grupo es de 10 estudiantes. Si existen mas de 10 solicitudes validas, se crean `ceil(total/10)` grupos y se distribuyen los estudiantes de la forma mas equilibrada posible, con una diferencia maxima de un estudiante entre grupos. Una materia abre solamente si tiene al menos 5 solicitudes validas.
1. Los periodos lectivos inician en enero y hay tres por año: `01`, `02` y `03`. Por ejemplo, despues de `2026-03` sigue `2027-01`. Esta notacion (`año-periodo`) no debe confundirse con los cuatrimestres del plan de estudio. En los expedientes se utilizara "Periodo Lectivo" para indicar cuando obtuvo el estudiante una nota.
1. El horario de clases es de 7:00 a 17:00, de lunes a viernes. Cada materia se imparte durante 200 minutos por semana. Estos pueden dividirse en dos bloques de 100 minutos, con dias no adyacentes y con tiempo para trasladarse entre aulas. Los bloques pueden tener horarios de inicio diferentes, alineados a las 07:00, 09:00, 11:00, 13:00 o 15:00. Si no se divide, la materia se imparte en un bloque continuo de 200 minutos dentro del horario disponible.
1. En cada nuevo periodo lectivo se pueden ofrecer todos los cursos, pero una materia puede cerrarse si tiene menos de 5 solicitudes validas. Las solicitudes rechazadas por el cierre de una materia deben esperar al siguiente periodo lectivo. Cada materia abierta tiene uno o mas grupos. Se usara el codigo de la materia mas el numero de grupo, por ejemplo `MA001-01` para el grupo 1 de Matematicas I.
1. Cada grupo tiene un profesor asignado. Si se abre un grupo adicional de una materia, se le asigna un profesor nuevo. Un profesor no puede impartir dos grupos en el mismo horario.
1. Se asume un maximo de 100 aulas. Cada grupo debe tener un aula, horario y profesor, y no puede haber dos grupos en la misma aula al mismo tiempo. El formato del aula es `AULA-DDD`, donde `DDD` inicia en 100. La capacidad de cada aula es de 20 estudiantes.

## Proceso de Matricula

1. Un agente revisa las matriculas del periodo anterior, si existen, y genera las notas de manera aleatoria, con una probabilidad de aprobacion del 80% para cada materia.
2. Recibir el periodo lectivo y verificar que sea consecutivo respecto a los periodos almacenados. Si no existe informacion previa, inicializar la simulacion.
3. Cargar los expedientes existentes y crear 10 estudiantes nuevos para el periodo. En la primera ejecucion, crear los primeros 10 expedientes.
4. Generar o cargar la lista ordenada de solicitudes de cada estudiante. Para estudiantes nuevos, la solicitud inicial corresponde al primer cuatrimestre del plan. Las solicitudes posteriores deben respetar los prerrequisitos aprobados.
5. Validar cada solicitud contra el plan de estudios y el expediente del estudiante. Separar las solicitudes validas de las rechazadas y crear una alerta para cada rechazo, indicando carne, materia, motivo y estado.
6. Calcular la demanda de cada materia usando solamente las solicitudes validas. Cerrar las materias con menos de 5 solicitudes; esas solicitudes quedan rechazadas para el siguiente periodo.
7. Crear `ceil(total/10)` grupos para cada materia abierta y repartir los estudiantes de forma equilibrada, respetando un maximo de 10 por grupo. Priorizar por promedio historico y desempatar por carne ascendente.
8. Generar el horario de todos los grupos, asignando profesor y aula. Verificar que no existan conflictos de profesor o aula y que se cumplan los bloques, duraciones y dias permitidos.
9. Asignar cada estudiante a los grupos de sus materias validas, evitando conflictos de horario en su horario individual. Si no es posible asignar una solicitud valida sin conflicto, generar una alerta para revision humana.
10. Presentar las discrepancias o problemas encontrados mediante el sistema interactivo para que un humano decida como proceder.
11. Una vez resueltos los conflictos, actualizar los expedientes en la seccion de matricula y guardar el archivo del periodo lectivo con el horario, las listas de estudiantes y las alertas.

## EL Plan de Estudios

Cuatrimestre 1
| Codigo Materia | Nombre Materia | Requisitos |
|-|-|-|
| MA001 | Matematicas I | |
| CS002 | Intro a Compu | |
| ES001 | Humanidades | |

Cuatrimestre 2
| Codigo Materia | Nombre Materia | Requisitos |
|-|-|-|
| CS003 | Programacion I | MA001, CS002 |
| MA002 | Matematicas II | MA001 |
| ES010 | Ingles I | |

Cuatrimestre 3
| Codigo Materia | Nombre Materia | Requisitos |
|-|-|-|
| CS004 | Programacion II | CS003 |
| MA003 | Matematicas III | MA002 |
| ES020 | Ingles II | ES010 |

Cuatrimestre 4
| Codigo Materia | Nombre Materia | Requisitos |
|-|-|-|
| CS005 | Algoritmos | CS004 |
| MA004 | Matematicas IV | MA003 |
| CS020 | Redes | |

## Expedientes de Estudiantes

Un agente debe crear los expedientes de estudiantes ficticios asignando un carnet que empiece con los ultimos digitos del año (2026 sera 26); el resto de los numeros puede ser consecutivo. En cada periodo lectivo ingresan 10 estudiantes a la carrera. Por ejemplo, si la simulacion inicia en `2026-01`, se crean los carnets `260001` a `260010`. En `2026-02` se continua con `260011`, y en `2027-01` se reinicia la secuencia con `270001`.

Para mantener la informacion de cada estudiante se va a crear una carpeta "students/" que dentro de ella mantendra un archivo por estudiante con el numero de carné DDDDDD.md, por ejemplo 260020.md.

Se va a crear un skill o comando llamado "matricula" que recibe el periodo a tomar en cuenta. El agente debe corroborar que el periodo sea consecutivo en el caso de que ya exista informacion de periodos anteriores; en caso contrario, seria el primer periodo a ejecutar.
Si es el primer periodo existente, debe invocar a otros agentes que creen los primeros estudiantes con sus respectivos expedientes y crear la solicitud de cursos para ese periodo, que en ese caso seria para las materias del primer cuatrimestre del plan de estudios.

Una vez matriculadas las materias, el expediente va a tener una sección llamada "Matricula" que va a tener las materias a las que fue asignado

| Periodo Lectivo | Codigo Materia | Grupo | Nombre Materia |
| --------------- | -------------- | ----- | -------------- |
| 2025-03         | MA001          | 01    | Matematicas I  |

En subsecuentes ejecuciones, si ya existe datos en el expediente, de las materias que matriculo anteriormente debe simular las notas de la ultima matricula

Los periodos lectivos van a ser salvados como archivos `.md` en la carpeta `periodos_lectivos/` y toda la informacion de cada periodo estara en un archivo con el nombre del periodo lectivo, por ejemplo `2026-01.md`.

Cuando invoka el skill "matricula" va a simular todo el proceso de matricula (crear solicitudes, crear los horarios, notificar de los resultados)

Mediante la simulacion de varios periodos se deben crear 50 o mas perfiles y asignarles el ultimo cuatrimestre matriculado con las notas de las materias correspondientes, manteniendo la coherencia entre las materias requisito. Por ejemplo, un estudiante que completo el cuatrimestre 2 tiene que haber aprobado MA001 y CS002, con notas mayores o iguales a 70.

Dentro del archivo se mantendra el "expediente de notas" con el siguiente formato:

Periodo Lectivo (año-periodo) - Codigo Materia - Nombre Materia - Nota (de 0 a 100)

Ejemplo:

| Periodo Lectivo | Codigo Materia | Nombre Materia | Nota (de 0 a 100) |
| --------------- | -------------- | -------------- | ----------------- |
| 2025-03         | MA001          | Matematicas I  | 85                |

## Resultado de la matricula

El resultado de la matricula va en el documento descrito anteriormente para el periodo lectivo en la carpeta `periodos_lectivos/` con la siguiente informacion:

### Horario

El horario resultante debe seguir el siguiente formato de ejemplo:

| Codigo Materia | Nombre Curso  | Grupo | Profesor   | Aula     | Horario                       |
| -------------- | ------------- | ----- | ---------- | -------- | ----------------------------- |
| MA001          | Matematicas I | 01    | Juan Perez | AULA-101 | L 07:00-08:40 / J 09:00-10:40 |

### Listas de estudiantes por materia y grupo

Debe existir una lista independiente para cada combinación de materia y grupo. Los estudiantes de diferentes grupos o materias no deben mezclarse. Dentro de cada lista, ordenar por apellido y luego por nombre.

#### MA001 - Grupo 01

| Carné  | Apellidos       | Nombre |
| ------ | --------------- | ------ |
| 250005 | Aguilar Jimenes | Pedro  |
| 260015 | Benavides Perez | Juan   |

#### MA001 - Grupo 02

| Carné  | Apellidos       | Nombre |
| ------ | --------------- | ------ |
| 260020 | Campos Solano   | Ana    |

### Alertas para revision humana

Cada solicitud que no pueda ser atendida debe generar una alerta con el carne del estudiante, el codigo de la materia, el motivo del rechazo y el estado de la solicitud.
