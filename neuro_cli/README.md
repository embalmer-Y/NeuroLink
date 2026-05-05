# NeuroLink Neuro CLI

This directory is the canonical home for the Neuro CLI host-control project.

Current release target: `1.2.1`. For release-1.2.1, Neuro CLI remains the stable Unit tool/control surface consumed by the ongoing `neurolink_core` Core-Agent track.

## Structure
- src: CLI implementation
- scripts: helper/wrapper scripts for automation
- tests: CLI test suite
- skill: skill-facing contract documents

## Canonical entrypoint
- applocation/NeuroLink/neuro_cli/src/neuro_cli.py

## Python dependency

The CLI imports the top-level Python module `zenoh`, which is provided by the
package listed in:

- applocation/NeuroLink/neuro_cli/requirements.txt

Install it into the active NeuroLink `.venv` before using `neuro_cli.py` or the
Linux smoke helper:

```bash
source applocation/NeuroLink/scripts/setup_neurolink_env.sh --activate --strict
python3 -m pip install -r applocation/NeuroLink/neuro_cli/requirements.txt
```

If you want the canonical bootstrap script to install the tracked CLI packages for
the active environment, use:

```bash
source applocation/NeuroLink/scripts/setup_neurolink_env.sh --activate --strict --install-neuro-cli-deps
```

## Skill entrypoint
- applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py

## Agent-facing release-1.2.1 surfaces

```bash
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py system tool-manifest
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py system state-sync
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py --output jsonl monitor agent-events --max-events 2
```
