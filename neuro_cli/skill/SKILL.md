# Skill: NeuroLink Neuro CLI Orchestration

This legacy seed is mirrored into the project-shared skill at
`.github/skills/neuro-cli/SKILL.md`. Prefer the project-shared skill for Agent
discovery and keep this file as a compatibility pointer for older references.

## Goal

Provide a stable invocation entry for skills to operate NeuroLink Unit through the Neuro CLI.

## Input Contract

Required:
1. command path tokens (for example: `query device`, `deploy prepare`, `lease acquire`)

Optional:
1. `--node` (default `unit-01`)
2. `--source-core` (default `core-cli`)
3. `--source-agent` (default `skills`)
4. `--request-id`
5. `--idempotency-key`

## Execution Policy

1. Always invoke CLI in JSON mode.
2. Parse JSON output and classify by `ok` and `status`.
3. Treat `status=not_implemented` as capability-gap signal.
4. Preserve command ordering for update flow: prepare -> verify -> activate.

## Exit Handling

1. Exit code `0`: success path.
2. Exit code `2`: invalid input or transport/query failure.
3. Exit code `3`: not implemented placeholder.

## Minimal Workflow

1. query device
2. lease acquire (activate resource)
3. deploy prepare
4. deploy verify
5. deploy activate
6. monitor events

## Implementation Pointer

Use `../scripts/invoke_neuro_cli.py` for script-level integration.
