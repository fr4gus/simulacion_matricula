# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

Implemented. `PRD.md` (in Spanish) is the authoritative domain specification, with a
**"Aclaraciones" section at the end resolving every ambiguity found during implementation**
(request cadence per period, group-assignment priority scope, unschedulable-group handling,
split-block day rules, 50+ profile accumulation, retake auto-requesting) — read that section
alongside the rest of the PRD, since it overrides anything that reads ambiguous above it.

The system is a **multi-agent enrollment (matricula) simulation harness**, explicitly without
any LLM wrapper — the "agents" are plain Python orchestration + a `ProcessPoolExecutor` pool of
per-student worker processes, not LLM-backed agents.

### Module map (`src/matricula/`)

- `config.py` — every PRD constant (PASS_GRADE, GROUP_CAPACITY, BLOCK_START_HOURS, DAY_CODES, …).
- `domain/` — pure, I/O-free: `models.py` (dataclasses), `study_plan.py` (hardcoded plan,
  validates course-code uniqueness + prerequisite-cycle absence at import time), `periods.py`
  (`Period` value type, `YYYY-PP` parsing, `is_consecutive`).
- `io/` — Markdown read/write pairs: `markdown_tables.py` (shared pipe-table parser/renderer),
  `student_md.py` (`students/DDDDDD.md`), `period_md.py` (`periodos_lectivos/YYYY-PP.md`),
  `history.py` (latest stored period, load-all-students).
- `simulation/` — `grades.py` (seeded 80%-pass grade simulation), `requests.py` (pure
  next-cuatrimestre + retake request-building logic), `worker.py` (`process_student()` — the
  single picklable top-level function dispatched per-student to the `ProcessPoolExecutor`; derives
  its RNG seed via `sha256(run_seed:carnet)`, never Python's salted `hash()`).
- `orchestration/` — one module per sequential pipeline phase, run in the main process after
  worker results are merged: `validation.py`, `demand.py`, `grouping.py` (priority only gates
  admission; group-slot assignment is round-robin/balanced), `scheduling.py` (deterministic,
  zero-RNG; prefers globally non-conflicting slots as a soft preference so a student's own
  courses don't collide, falls back to any teacher/room-conflict-free slot), `assignment.py`
  (per-student conflict-free group assignment), `alerts.py`, `runner.py` (`run_period()` —
  the top-level entry point wiring all 11 PRD steps together).
- `reporting/summary.py` — human-facing run summary + exit-code decision.
- `cli.py` / `__main__.py` — `python -m matricula run <period> [--seed N] [--base-dir PATH]
  [--workers N]`.

### Key design decisions worth knowing before touching this code

- **Concurrency boundary**: exactly one unit of parallel work — `process_student()` per student,
  doing grade simulation *and* request-building in the same call — via
  `ProcessPoolExecutor(submit/as_completed)` (never `map`, so one student's exception becomes an
  `Alert` instead of killing the batch). Every downstream phase (demand, grouping, scheduling,
  assignment) is intentionally sequential/single-process — they need shared global state
  (teacher/classroom pools, course rosters) that doesn't parallelize cleanly at this scale.
- **Determinism**: the only randomized step is grade simulation; scheduling is 100% deterministic
  (fixed iteration order over `_CANDIDATE_BLOCK_SETS` and classrooms). Runs are byte-identical
  across `--workers` counts for the same `--seed` — verified manually, not just asserted.
- **Exit codes**: `0` clean, `1` completed with systemic alerts (unschedulable group, unresolved
  individual conflict — see `orchestration/alerts.py::is_systemic`), `2` aborted before running
  (bad period format, non-consecutive period). Routine rejections (course closed, prereq unmet)
  never affect the exit code.
- **Persistence**: `students/*.md` and `periodos_lectivos/*.md` are the only source of truth;
  writers always re-render the full file from the in-memory dataclass rather than patching text.

## Domain model (from PRD.md)

**Academic periods**: format `YYYY-PP` where `PP` in `{01, 02, 03}`. After `2026-03` comes `2027-01`. Do not confuse "periodo lectivo" (calendar term) with "cuatrimestre" (position in the study plan/curriculum).

**Students**: carnet (student ID) is `DDDDDD` — two-digit year prefix + 4-digit sequence, e.g. `260001`-`260010` for the first 10 students admitted in `2026-01`, continuing `260011...` in `2026-02`, resetting to `270001` in `2027-01`. 10 new students enter every period. Each student has a record file `students/DDDDDD.md` containing a "Matricula" table (period, course code, group, course name) and an "expediente de notas" table (period, course code, course name, grade 0-100).

**Study plan**: fixed 4-cuatrimestre plan defined in `PRD.md` with course codes like `MA001`, `CS002`, prerequisites (e.g. `CS003` requires `MA001` and `CS002`). Passing grade is 70; below that the course must be repeated next period. Course-code uniqueness and absence of circular prerequisite dependencies are invariants the PRD explicitly asks to be validated.

**Course groups**: `ceil(valid_requests/10)` groups per course, max 10 students/group, balanced within 1 student difference; a course opens only with ≥5 valid requests. Group naming: `MA001-01`. Each group needs a unique teacher (new group ⇒ new teacher; a teacher can't teach two groups at the same time) and a classroom (`AULA-DDD` starting at 100, max 100 classrooms, capacity 20, no double-booking).

**Scheduling**: Mon-Fri, 07:00-17:00. Each course is 200 min/week, either one continuous 200-min block or two 100-min blocks on non-adjacent days, block start times aligned to 07:00/09:00/11:00/13:00/15:00.

**Priority/allocation**: valid requests ranked by historical grade average (descending), ties broken by lower carnet (older student) first.

## Enrollment process pipeline (Sec. "Proceso de Matricula")

The `matricula` skill/command takes a period and runs this pipeline end-to-end — implement/preserve this order:

1. Simulate grades for the previous period's enrollments (80% pass probability per course), if a previous period exists.
2. Verify the requested period is consecutive to stored history; if no history exists, this is the initializing run.
3. Load existing student records; create 10 new student records for this period (or the first 10 if this is the first run).
4. Build each student's ordered course request list — new students request cuatrimestre-1 courses; continuing students' requests must respect approved prerequisites.
5. Validate each request against the study plan + student record; split into valid/rejected, and raise an alert per rejection (carnet, course, reason, status).
6. Compute demand per course from valid requests only; close courses with <5 valid requests (those requests roll over as rejected, retried next period).
7. Create groups (`ceil(n/10)`, max 10/group, balanced) for each open course; assign priority by historical average, then ascending carnet.
8. Generate the full group schedule (teacher + classroom), checking teacher/classroom/block/day constraints.
9. Assign each student to their groups, avoiding individual schedule conflicts; unresolvable valid requests become alerts for human review.
10. Surface discrepancies/alerts via the interactive system for a human decision.
11. Once resolved, update student records' "Matricula" section and persist the period file with schedule, group rosters, and alerts.

Across simulated periods, the system should accumulate 50+ student profiles, with each student's last-completed cuatrimestre and grades staying internally consistent with prerequisite history (e.g. a student who finished cuatrimestre 2 must show passing grades for `MA001` and `CS002`).

## Output artifacts

- `students/DDDDDD.md` — one file per student: "Matricula" table + "expediente de notas" (grades) table, exact column formats are in `PRD.md` ("Expedientes de Estudiantes").
- `periodos_lectivos/YYYY-PP.md` — one file per period containing: the schedule table (course, name, group, teacher, classroom, horario string like `L 07:00-08:40 / J 09:00-10:40`), one roster table per course+group combo (sorted by apellido then nombre, never mixing groups/courses), and the alerts table (carnet, course, reason, status). Exact table formats are in `PRD.md` ("Resultado de la matricula") — match them precisely, since these are the system's human-facing output.
