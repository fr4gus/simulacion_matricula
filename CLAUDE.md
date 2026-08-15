# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

Implemented. `PRD.md` (in Spanish) is the authoritative domain specification, with a
**"Aclaraciones" section at the end resolving every ambiguity found during implementation**
(request cadence per period, group-assignment priority scope, unschedulable-group handling,
split-block day rules, 50+ profile accumulation, retake auto-requesting) — read that section
alongside the rest of the PRD, since it overrides anything that reads ambiguous above it.

The system is a **multi-agent enrollment (matricula) simulation harness** with two execution
modes:

1. **Default mode** — explicitly without any LLM wrapper: the "agents" are plain Python
   orchestration + a `ProcessPoolExecutor` pool of per-student worker processes, not
   LLM-backed agents. `python -m matricula run <period> [...]`.
2. **Skills mode** — `.claude/skills/matricula/SKILL.md`, an opt-in path where a Claude
   Code/Codex agent runs the entire 11-step pipeline itself, reading/writing the `.md`
   files directly per rules transcribed in the skill, with **no Python business-logic code
   involved at all** (not `orchestration/*`, not `io/*`, not `simulation/*`) — see "Skills-
   driven orchestration mode" below. This replaced an earlier `--agents` mode that wrapped
   the Python pipeline with the Claude Agent SDK; that mode has been removed.

### Module map (`src/matricula/`)

- `config.py` — every PRD constant (PASS_GRADE, GROUP_CAPACITY, BLOCK_START_HOURS, DAY_CODES, …).
- `domain/` — pure, I/O-free: `models.py` (dataclasses, including `TeacherRecord`), `study_plan.py`
  (hardcoded plan, validates course-code uniqueness + prerequisite-cycle absence at import time),
  `periods.py` (`Period` value type, `YYYY-PP` parsing, `is_consecutive`), `names.py` (parses
  `nombres.md`, at the repo root, into the 1000-entry `NAME_POOL` shared by students and teachers
  — see "Shared name pool" below).
- `io/` — Markdown read/write pairs: `markdown_tables.py` (shared pipe-table parser/renderer),
  `student_md.py` (`students/DDDDDD.md`), `period_md.py` (`periodos_lectivos/YYYY-PP.md`),
  `teacher_md.py` (`profesores.md` — teacher name registry + shared name-pool cursor),
  `history.py` (latest stored period, load-all-students, and
  `migrate_graduated_students()`/`count_graduated_students()` — see "Graduated students" below).
- `simulation/` — `grades.py` (seeded 80%-pass grade simulation), `requests.py` (pure
  next-cuatrimestre + retake request-building logic), `naming.py` (`allocate_names()` — pure,
  deterministic, cursor-based allocation from `NAME_POOL`, wraps around at 1000), `worker.py`
  (`process_student()` — the single picklable top-level function dispatched per-student to the
  `ProcessPoolExecutor`; derives its RNG seed via `sha256(run_seed:carnet)`, never Python's salted
  `hash()`).
- `orchestration/` — one module per sequential pipeline phase, run in the main process after
  worker results are merged: `validation.py`, `demand.py`, `grouping.py` (priority only gates
  admission; group-slot assignment is round-robin/balanced), `scheduling.py` (deterministic,
  zero-RNG; prefers globally non-conflicting slots as a soft preference so a student's own
  courses don't collide, falls back to any teacher/room-conflict-free slot), `assignment.py`
  (per-student conflict-free group assignment), `alerts.py`, `runner.py` (`run_period()` —
  the top-level entry point wiring all 11 PRD steps together).
- `reporting/summary.py` — human-facing run summary + exit-code decision.
- `cli.py` / `__main__.py` — `python -m matricula run <period> [--seed N] [--base-dir PATH]
  [--workers N] [--visualize] [--viz-port N] [--demo-delay S]`, plus `matricula viz [--port]
  [--host]` for the standalone visualizer. No LLM-related flags — see "Skills-driven
  orchestration mode" below for the separate, non-CLI path.

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

## Skills-driven orchestration mode

`.claude/skills/matricula/SKILL.md` is a second, independent way to run a period: instead
of `orchestration/*` + `runner.run_period()`, a Claude Code/Codex agent reads the skill's
instructions and runs the 11-step pipeline by **orchestrating subagents** — reading and
writing `students/*.md`, `periodos_lectivos/*.md`, and `profesores.md` directly with its
own reasoning (and its subagents'), per business rules transcribed in the skills from
`PRD.md`. This is **not** a thin wrapper: no skill in this mode calls into
`orchestration/*`, `io/*`, or `simulation/*` at all, and must not — the whole point is
exploring an orchestration model driven purely by skill instructions and real subagent
delegation (via the `Task` tool), portable across agent harnesses (Claude Code or Codex),
with zero Python business logic. It replaced an earlier `--agents` mode (`agent_harness/`,
Claude Agent SDK, tool-call wrappers around `orchestration/*`) that has been removed
entirely from this branch.

- **Invocation**: the skill takes `periodo` (required), `n_estudiantes` (optional,
  default 10 — configurable per PRD.md's new "Nota de arquitectura" section, unlike the
  original fixed-10 rule), `base_dir` (optional, see below), plus optional scenario
  overrides.
- **`base_dir`** defaults to `data/` at the repo root — a generated, gitignored directory,
  deliberately separate from source (never the invoking cwd or the repo root directly).
  `students/`, `periodos_lectivos/`, `profesores.md`, `escenario.md`, and `graduated/` all
  live under it; `nombres.md` stays a fixed repo-root reference file, never per-`base_dir`.
  Pass `base_dir=<path>` explicitly to point at another location (e.g. to keep several
  scenario runs side by side without collisions). `.gitignore` also covers
  `students/`/`periodos_lectivos/`/`profesores.md`/`escenario.md`/`graduated/` at the repo
  root as a safety net, in case a run targets `base_dir=.` or the Python default mode is
  invoked without `--base-dir`.
- **`escenario.md`** (base_dir root, alongside `profesores.md`): an optional Markdown table
  of previously-fixed PRD constants (`max_aulas`, `capacidad_aula`, `cupo_grupo`,
  `minimo_apertura`, `probabilidad_aprobacion`, `nota_minima`,
  `estudiantes_nuevos_por_periodo`) that the orchestrator skill resolves once, before
  dispatching any subagent, and passes down as already-resolved values in every subagent
  prompt (subagents never read `escenario.md` themselves). Precedence: explicit invocation
  override > `escenario.md` value > PRD default hardcoded in the skill. This exists
  specifically to let scenarios vary classroom/teacher capacity and stress-test the
  pipeline (e.g. `max_aulas=2` to force unschedulable-group alerts).
- **Visualizer integration**: only the orchestrator skill talks to `viz/` — subagents never
  publish events directly (they don't know `viz_port` or the HTTP protocol). It never
  starts the `viz/` server — the human must already have `matricula viz` running. It
  health-checks `GET /health` and, if up, POSTs the same event vocabulary `runner.py`
  emits (`run_started`, `pool_progress`, `pool_completed`, `validation_done`,
  `demand_done`, `grouping_done`, `scheduling_done`, `assignment_done`, `alerts`,
  `run_completed`, `cuatrimestre_summary`) plus four new event types specific to this mode
  (`subagent_started`, `subagent_completed`, `phase_started`, `phase_completed` — see
  "Multi-agent skill topology" below) to `POST /publish` via `curl`, tolerating a
  down/missing server the same way `viz/sink.py::HttpSink` does (warn once, never block or
  abort the run).
- Determinism is explicitly **not** preserved in this mode (an LLM decides calculation and
  narration timing) — same trade-off the removed `--agents` mode had; don't try to make it
  byte-reproducible the way the default mode is.

### Multi-agent skill topology

Three skill files, each independently auditable, only one of which (`matricula`) is ever
invoked directly by a human:

- **`.claude/skills/matricula/SKILL.md`** — the orchestrator, and the only public entry
  point (`PRD.md` fixes this name: *"un skill o comando llamado 'matricula'"*). Runs PRD
  steps 0, 2, 3, 10, 11 inline (cheap global-state work: migrating graduates, checking
  consecutiveness, generating carnets/names, consolidating alerts, persisting files) and
  dispatches everything else to the two skills below via the `Task` tool.
- **`.claude/skills/matricula-estudiante/SKILL.md`** — worker skill, one `Task` per
  student, up to 5 in flight at a time (the orchestrator batches the full student list into
  groups of ≤5 and waits for each batch to fully return before starting the next). Covers
  PRD steps 1+4 (simulate previous-period grades, build this period's request list) for a
  single student. Conceptually the skill-mode analogue of
  `simulation/worker.py::process_student()` run under `ProcessPoolExecutor` in the default
  mode — same contract that one student's failure never aborts the batch, expressed here as
  a `"error": "..."` field in a delimited ` ```student-result ` JSON block instead of a
  caught Python exception. Never reads/writes files or talks to the visualizer directly —
  everything it needs arrives in its `Task` prompt, and its result is consumed and
  persisted by the orchestrator.
- **`.claude/skills/matricula-horario/SKILL.md`** — worker skill, dispatched exactly
  **once** per run (no batching, no parallelism) via a single `Task`. Covers PRD steps 5-9
  (validation, demand, grouping, scheduling, individual assignment) in one sequential pass.
  This is deliberately **not** split into parallel subagents or one subagent per phase: each
  phase needs the complete output of the previous one (demand needs every validation
  result; grouping needs closed/open courses; scheduling needs the full group list;
  assignment needs the finished schedule) and all of them mutate shared global state
  (per-course seats, classroom occupancy, teacher availability, each student's accumulating
  individual schedule) — the exact same reason `orchestration/*` is intentionally
  single-process in the default mode (see "Key design decisions" above). Splitting these
  phases into isolated subagents would only introduce state races with no real parallelism
  gain, since they're reasoning/CPU-bound, not I/O-bound. Returns a delimited
  ` ```horario-result ` JSON block; if it reports `error != null` or returns something
  unparseable, the orchestrator treats it as a **systemic run failure** (same severity as a
  non-consecutive period) — stop, persist nothing, report to the user — unlike a single
  failed `matricula-estudiante` subagent, which only produces one alert and never aborts
  the run.
- **Result contract**: both worker skills end their response with exactly one delimited
  code block (` ```student-result ` / ` ```horario-result `) containing JSON — this is how
  the orchestrator collects structured results from several subagents without relying on
  intermediate files.
- **New visualizer events**, always published by the orchestrator only, never by a
  subagent: `subagent_started`/`subagent_completed` (`{role, id, batch_index, batch_size}` /
  `{role, id, status, batch_index}`, one pair per `matricula-estudiante` dispatch) and
  `phase_started`/`phase_completed` (`{phase: "horario_y_asignacion"}`, bracketing the
  single `matricula-horario` dispatch). `src/matricula/viz/server.py` and `sink.py` needed
  **no changes** for this — the server is a type-agnostic relay; only
  `viz/static/index.html` gained a "Subagentes en progreso" card section that reacts to
  these four event types.

## Shared name pool (students + teachers)

`nombres.md` (repo root) holds 1000 real-sounding full names ("Nombre Apellido"), one per
numbered list item, sourced from 1000randomnames.com — see that file's header for provenance.
Both new students and new teachers draw from this **single shared pool**, never separate ones:

- `domain/names.py::NAME_POOL` parses the file once into an immutable `tuple[(nombre, apellidos), ...]`
  in file order. No shuffling — "next free name" is a purely positional, deterministic notion.
- `simulation/naming.py::allocate_names(start_index, count)` is the pure allocator: given a
  starting cursor, returns the next `count` pool entries and the advanced cursor. Wraps around
  (modulo 1000) instead of failing if the pool is exhausted.
- `profesores.md` (repo root, alongside `students/` and `periodos_lectivos/`) is the persisted
  cursor **and** the full teacher registry — see `io/teacher_md.py::TeacherRegistry`. Its
  "Proximo indice libre del pool" line is the only source of truth for how many pool entries have
  been handed out across the whole simulation's history; `students/*.md` stores names as plain
  text with no pool index, so the cursor cannot be re-derived from disk any other way.
- `orchestration/runner.py::run_period()` reads this cursor first, allocates names for this
  period's new students, then passes the advanced cursor into
  `orchestration/scheduling.py::schedule_groups(groups, teacher_start_index=...)` — which
  returns `(schedules, alerts, teacher_records, next_free_index)` — and finally persists the
  merged `TeacherRegistry` (old + new records) back to `profesores.md`. The skill mode
  (`.claude/skills/matricula/SKILL.md`) follows the same protocol in prose — same shared
  cursor, same wraparound rule — since it reads/writes `profesores.md` directly instead of
  calling this code. Both paths must stay in lockstep on the protocol; a mismatch would
  silently start reusing pool indices across runs.
- The source data itself is not guaranteed unique (2 duplicate full-name pairs out of 1000, since
  the generator combines first/last names randomly) — "no repeats" here means no *pool index* is
  ever reused within the simulation's history, not that every rendered full name is distinct.

## Graduated students

Students who have passed every course in the study plan (`next_pending_cuatrimestre()` in
`simulation/requests.py` returns `None`) stop being part of the active simulation:

- `io/history.py::migrate_graduated_students(base_dir)` moves their `students/DDDDDD.md` file
  (unmodified, just relocated) to `graduated/DDDDDD.md`. `orchestration/runner.py::run_period()`
  calls it first thing, before `load_all_students()` — so a student who graduates *during* a
  run is still processed normally for that run (grades simulated, matricula written), and only
  stops being loaded starting the *next* run. The skill mode follows the same rule (Step 0 of
  its algorithm), just performed by the agent's own file operations instead of this function.
- `graduated/` is purely historical and out-of-pipeline: `load_all_students()` never reads it, so
  graduated students never occupy a `ProcessPoolExecutor` worker, are never asked to submit
  requests (moot anyway — `build_request_course_codes()` already returns `[]` once
  `next_pending_cuatrimestre()` is `None`), and never appear in the per-cuatrimestre census.
- The `graduados` count in the `cuatrimestre_summary` event (consumed by `viz/`) is still the
  full historical total — `io/history.py::count_graduated_students()` counts files in
  `graduated/` directly (no parsing, no pipeline involvement) so the metric doesn't regress to 0
  once graduates stop living in `students/`.
- Carnets are never reused: a graduated student's carnet was already consumed by an earlier
  period's `new_carnets()` call, so relocating the file doesn't risk a collision with future
  carnet allocation.

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

- `students/DDDDDD.md` — one file per *active* student: "Matricula" table + "expediente de notas" (grades) table, exact column formats are in `PRD.md` ("Expedientes de Estudiantes"). Same format as `graduated/DDDDDD.md` — see below.
- `periodos_lectivos/YYYY-PP.md` — one file per period containing: the schedule table (course, name, group, teacher, classroom, horario string like `L 07:00-08:40 / J 09:00-10:40`), one roster table per course+group combo (sorted by apellido then nombre, never mixing groups/courses), and the alerts table (carnet, course, reason, status). Exact table formats are in `PRD.md` ("Resultado de la matricula") — match them precisely, since these are the system's human-facing output.
- `graduated/DDDDDD.md` — one file per student who has passed every course in the study plan, relocated here (unchanged) from `students/`. Historical only, outside the pipeline — see "Graduated students" above.
- `profesores.md` — single file at `base_dir` root (not per-period): the shared name-pool cursor plus every teacher generated so far, across all periods. See "Shared name pool" above.


