# Future work: multi-provider support for `--agents` mode

## Status quo

The `--agents` mode (`agent_harness/`) is built directly on Anthropic's
`claude_agent_sdk.ClaudeSDKClient`, not a provider-agnostic abstraction. In
`agent_harness/orchestrator.py`:

- `ClaudeAgentOptions(model=..., mcp_servers=..., allowed_tools=...,
  permission_mode="bypassPermissions")` talks to Claude specifically.
- The default model is `claude-sonnet-5`, overridable via `--model` /
  `MATRICULA_AGENT_MODEL`, but only to other **Claude** model names.
- Tool exposure goes through MCP (`mcp_servers` + `allowed_tools`), which is
  the Agent SDK's mechanism, not a generic function-calling format.
- Turn/streaming handling (`client.receive_response()`,
  `AssistantMessage`/`TextBlock`) uses Agent-SDK-specific types.
- Auth is whatever the Agent SDK uses (Anthropic API key or Claude Code OAuth
  session) — there's no pluggable auth/provider layer.

The Claude Agent SDK itself is Anthropic-only, so there is no config flag
that repoints this mode at OpenAI or any other provider today.

## What it would take to support OpenAI (or other providers)

This is a new orchestration engine, not a flag flip. Concretely:

1. **Swap the client.** Replace `ClaudeSDKClient`/`ClaudeAgentOptions` with an
   OpenAI-native option — the raw `openai` SDK's function-calling loop, or a
   provider-agnostic framework (LangGraph, OpenAI's `Agents` SDK, or a custom
   loop).
2. **Reimplement the tool-calling loop.** The Agent SDK's
   `mcp_servers`/`allowed_tools` mechanism has no direct OpenAI equivalent —
   OpenAI uses its own function-calling JSON schema format.
   `agent_harness/tools.py::build_tools()` would need a parallel
   implementation emitting OpenAI-style function specs instead of MCP tool
   definitions.
3. **Reuse `PhaseGate` as-is.** `agent_harness/gate.py::PhaseGate` is plain
   Python with no SDK dependency, so it should enforce the fixed PRD phase
   order unchanged regardless of which provider's tool-call results feed it.
4. **Rewrite the turn/streaming event loop.** `orchestrator.py`'s message loop
   (iterating `AssistantMessage`/`TextBlock`) is Agent-SDK-shaped; OpenAI's
   streaming/response objects differ and would need their own handling.
5. **New optional dependency.** Add an `openai` extra in `pyproject.toml`
   alongside (or instead of) the existing `agents` extra, keeping it opt-in
   the same way `agent_harness/__init__.py` lazily resolves
   `run_period_with_agent` via `__getattr__` so neither the base install nor
   the default CLI path requires any agent SDK.

## What stays untouched

None of the actual business logic changes. `orchestration/*.py` (validation,
demand, grouping, scheduling, assignment, alerts) is fully decoupled from the
SDK choice — `agent_harness/tools.py` already only wraps those functions as
thin tool adapters. The work is entirely additive: a new
`agent_harness/openai_orchestrator.py`-style module (new client, new
tool-schema translation, new event loop) that reuses `PhaseGate`,
`PipelineState`, and every `orchestration/*` function without modification.

## Suggested approach if picked up

Generalize `agent_harness/tools.py` to emit provider-neutral tool specs (name,
description, JSON schema, handler) once, then have thin per-provider
orchestrator front-ends translate that shared spec into each SDK's native
format:

- `agent_harness/orchestrator.py` — existing Claude Agent SDK front-end.
- `agent_harness/openai_orchestrator.py` — new OpenAI front-end, same
  `run_period_with_agent`-shaped signature, selected via `cli.py` alongside
  `--agents` (e.g. `--agents --provider openai`).

Both front-ends would drive the same `PipelineState` + `PhaseGate` and call
into the same `orchestration/*` functions, matching the existing boundary
described in `CLAUDE.md`'s "Agent-driven orchestration mode" section.
