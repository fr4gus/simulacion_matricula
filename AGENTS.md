# Repository Guidelines

## Project Structure & Module Organization

This repository currently contains the project specification in
`PRD.md`. The planned implementation is a Python multi-agent
orchestration system (without an LLM wrapper), but source and test directories
have not yet been created. When implementation begins, keep application code
under `src/`, tests under `tests/`, and generated student records under
`students/`. Keep fixtures and static datasets separate from generated output,
such as in `data/` and `fixtures/`.

## Build, Test, and Development Commands

No build system or dependency manifest is committed yet. Once Python code is
added, provide a reproducible environment (preferably `pyproject.toml`) and
document commands such as:

```bash
python -m venv .venv
python -m pytest
python -m <package_or_module>
```

Do not commit `.venv`, caches, or generated schedules. Add project-specific
commands here when the tooling is established.

## Coding Style & Naming Conventions

Use Python 3 with four-space indentation, type hints for public interfaces, and
automatic formatting/linting configured in `pyproject.toml` (for example, Ruff
and a formatter). Use `snake_case` for modules, functions, and variables,
`PascalCase` for classes, and descriptive domain names. Preserve the domain
rules in the specification: six-digit student filenames (`students/123456.md`),
course codes such as `MA001`, periods such as `2026-01`, and classroom IDs such
as `AULA-100`.

## Testing Guidelines

Use `pytest` when tests are introduced. Name files `test_*.py` and test
validation, prerequisite ordering, capacity and over-capacity handling, teacher
conflicts, classroom conflicts, and schedule rules (Monday–Friday, 07:00–17:00).
Include deterministic fixtures for invalid student requests and prerequisite
cycles. Run the full suite before submitting changes; add coverage expectations
when CI is configured.

## Commit & Pull Request Guidelines

There is no usable commit history yet, so adopt imperative, concise commit
subjects (for example, `Add prerequisite validation`) and keep unrelated changes
separate. Pull requests should explain the behavior changed, identify affected
domain rules, include tests or a reason tests are not applicable, and show
sample output when schedule or student-record formats change. Update the
specification or documentation whenever an assumption changes.

## Configuration & Data Safety

Keep secrets and local configuration out of the repository; use ignored `.env`
files and commit a safe example if configuration becomes necessary. Treat
`students/` and generated schedules as derived data, and avoid committing real
personal information.
