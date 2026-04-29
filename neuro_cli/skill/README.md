# NeuroLink Neuro CLI Skill Project

## Purpose

This directory is the canonical release-1.1.8 home for the Neuro CLI skill
package. It keeps the Agent-facing skill contract, references, and templates
beside the CLI implementation that owns the commands.

The project-shared `.github/skills/neuro-cli/SKILL.md` file remains as the VS
Code Agent discovery adapter. It must point back to this directory rather than
owning a separate copy of the workflow contract.

## Structure

- `SKILL.md`: canonical skill frontmatter, boundaries, and workflow guidance.
- `references/workflows.md`: workflow-plan reference mirrored to the discovery adapter.
- `references/setup-linux.md`: zero-host Linux setup reference, expanded in release-1.1.8.
- `references/setup-windows.md`: zero-host Windows setup reference, expanded in release-1.1.8.
- `references/discovery-and-control.md`: discovery and protected-control reference, expanded in release-1.1.8.
- `assets/neuro_unit_app_template.c`: LLEXT app template for Agents.
- `assets/callback_handler.py`: audited callback handler template for Agents.

## Quick Usage

```bash
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py system init
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan preflight
```

## Notes

1. Wrapper enforces `--output json` by default.
2. Wrapper is intended for automation and skills orchestration.
3. Runtime transport behavior and command semantics remain owned by the canonical Neuro CLI entrypoint.
4. Discovery-adapter files under `.github/skills/neuro-cli` are tested mirrors or pointers, not the source of truth.
