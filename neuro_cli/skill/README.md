# NeuroLink Neuro CLI Skill Project

## Purpose

This project packages the Neuro CLI invocation contract as a reusable skill-facing engineering unit.

It does not replace the main CLI implementation. Instead, it standardizes how skills invoke and parse CLI behavior.

## Structure

- `SKILL.md`: skill contract, boundaries, and workflow guidance.
- `invoke_neuro_cli.py`: thin Python wrapper that executes `applocation/NeuroLink/neuro_cli/src/neuro_cli.py` in JSON mode.

## Quick Usage

```powershell
D:/Compiler/anaconda/envs/zephyr/python.exe applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py query device --node unit-01
```

## Notes

1. Wrapper enforces `--output json` by default.
2. Wrapper is intended for automation and skills orchestration.
3. Runtime transport behavior and command semantics remain owned by the canonical Neuro CLI entrypoint.
