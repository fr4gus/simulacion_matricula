"""Constantes del dominio, tomadas directamente de PRD.md."""

from __future__ import annotations

# Notas y aprobacion
PASS_GRADE = 70
PASS_PROBABILITY = 0.80

# Grupos
GROUP_CAPACITY = 10
MIN_VALID_REQUESTS_TO_OPEN = 5

# Aulas
CLASSROOM_CAPACITY = 20
MAX_CLASSROOMS = 100
CLASSROOM_NUMBER_START = 100  # AULA-100 .. AULA-199

# Estudiantes nuevos por periodo
NEW_STUDENTS_PER_PERIOD = 10

# Horario: Lunes=0 ... Viernes=4 (datetime.weekday() convention)
SCHOOL_DAYS = (0, 1, 2, 3, 4)
DAY_CODES = {0: "L", 1: "M", 2: "X", 3: "J", 4: "V"}
DAY_NAMES_ES = {0: "Lunes", 1: "Martes", 2: "Miercoles", 3: "Jueves", 4: "Viernes"}

SCHOOL_START_HOUR = 7
SCHOOL_END_HOUR = 17
BLOCK_START_HOURS = (7, 9, 11, 13, 15)

# Duracion semanal de una materia y sus posibles particiones
COURSE_WEEKLY_MINUTES = 200
SPLIT_BLOCK_MINUTES = 100

# Periodos lectivos por anio
PERIODS_PER_YEAR = ("01", "02", "03")
