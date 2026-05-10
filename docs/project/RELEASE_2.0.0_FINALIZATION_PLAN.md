# Release 2.0.0 Finalization Plan

## 1. Purpose

Release 2.0.0 is the final stabilization, freeze, real-scenario rerun, and
promotion release for the current NeuroLink HLD burn-down. Release 1.2.7 closed
the implementation-heavy HLD surface and produced a green final closure bundle.
Release 2.0.0 must now prove that the completed system is stable, documented,
repeatable, and ready to promote as the mature baseline.

The target result is a final release archive that demonstrates all complete
project capabilities through structured evidence, not another feature-expansion
cycle.

## 2. Scope Boundary

Release 2.0.0 is allowed to contain:

1. API, schema, command, and contract freeze review;
2. compatibility refresh across the accepted Unit capability classes;
3. final real Core/Unit scenario rerun using the release-2.0.0 checklist;
4. AI Core user documentation and operator handoff documentation;
5. README maturity and project presentation polish;
6. migration notes from release-1.2.x into the 2.0.0 baseline;
7. release identity promotion after the promotion bundle is green;
8. final promotion checklist, approval, and remote sync.

Release 2.0.0 is not allowed to contain new implementation-bearing scope unless
the frozen rerun exposes a release-blocking defect. Any new capability request
must be recorded as post-2.0.0 roadmap work unless it is required to preserve an
already-claimed 1.2.7 capability.

## 3. Baseline Evidence

The release-2.0.0 line starts from the closed release-1.2.7 final bundle:

```text
smoke-evidence/release-1.2.7-closure-20260510T040915Z/
```

That bundle records:

1. `closure-summary-final.json` with `passed_count=20` and no failed gates;
2. real live-event evidence from a bounded Core/Unit run;
3. hardware acceptance and compatibility evidence;
4. resource-budget governance evidence;
5. Agent Tool/Skill/MCP excellence evidence;
6. signing/provenance evidence;
7. observability and guarded rollback evidence;
8. deterministic federation and relay closure evidence;
9. focused regression evidence.

The release-1.2.7 bundle is the starting proof. Release 2.0.0 still requires a
fresh promotion bundle before identity promotion.

## 4. Workstreams

### WS-1 Contract Freeze

Freeze the public and release-gated contracts that now define NeuroLink 2.0.0:

1. `neurolink_core.cli` evidence commands and closure-summary inputs;
2. closure-summary schema and validation gate ids;
3. Neuro CLI command shape and JSON output status handling;
4. Unit command, query, event, and update planes;
5. request metadata fields, lease requirements, and approval boundaries;
6. Skill descriptor, tool manifest, MCP descriptor, and workflow catalog rules;
7. supported compatibility outcomes for Restricted Units and constrained targets.

Output: a freeze checklist that names the frozen surfaces and records any
acceptable stabilization-only changes.

Checklist artifact:

```text
docs/project/RELEASE_2.0.0_CONTRACT_FREEZE_CHECKLIST.md
docs/project/RELEASE_2.0.0_CONTRACT_FREEZE_CHECKLIST.json
```

### WS-2 Complete Feature Confirmation

Confirm every feature family that the project now claims as complete:

1. deterministic AI Core execution;
2. MAF/OpenAI-compatible provider readiness and explicit model-call opt-in;
3. Copilot Rational backend opt-in and no-direct-tool-execution boundary;
4. Mem0/local memory governance and recall evidence;
5. multimodal normalization and inference profile routing;
6. Tool/Skill/MCP governance and Agent excellence;
7. Core-owned build, deploy, activate, rollback, and cleanup evidence;
8. hardware compatibility and acceptance matrix;
9. Restricted Unit compatibility behavior;
10. signing, provenance, and artifact admission;
11. federation, relay, and route failure diagnosis;
12. live Unit event ingestion and real-scene E2E evidence;
13. release closure packaging.

Output: a release-2.0.0 feature completion checklist tied to evidence files.

### WS-3 AI Core User Documentation

Create `docs/project/AI_CORE_USER_GUIDE.md` as the primary AI Core entry point.
It should explain startup and daily usage in task order rather than release-gate
order.

Required sections:

1. what AI Core is;
2. safety model and tool-execution boundary;
3. environment setup;
4. provider and memory configuration;
5. deterministic dry-run;
6. provider and multimodal/profile smoke checks;
7. using `agent-run`;
8. live Unit event smoke;
9. app deploy, activate, rollback, and closure evidence;
10. closure-summary and evidence bundles;
11. troubleshooting and known hardware recovery paths;
12. document map for deeper operator runbooks.

Output: task-oriented AI Core guide linked from README and runbooks.

### WS-4 README Maturity

Turn the README into the project front door for new developers and operators.

Required sections:

1. concise product overview;
2. current release status;
3. major capability list;
4. architecture snapshot;
5. quick start;
6. AI Core usage pointer;
7. Neuro CLI and Unit usage pointer;
8. validation and release evidence workflow;
9. docs map;
10. troubleshooting entry points.

Emoji may be used sparingly for section scanability, but commands and technical
identifiers must remain easy to copy.

### WS-5 Migration And Operator Handoff

Create `docs/project/RELEASE_2.0.0_MIGRATION_NOTES.md` covering:

1. supported source baselines;
2. environment preparation;
3. release identity expectations;
4. AI Core startup changes;
5. Unit artifact and app identity checks;
6. hardware and WSL recovery notes;
7. evidence bundle expectations;
8. rollback and cleanup expectations;
9. known stabilization blockers and how to classify them.

### WS-6 Frozen Real-Scenario Rerun

Run the release-2.0.0 scenario checklist under a fresh bundle:

```text
smoke-evidence/release-2.0.0-promotion-<UTC>/
```

Required rows:

1. RS-01 deterministic Core/Unit contract baseline;
2. RS-02 single Core plus single real Unit live-event continuity;
3. RS-03 real Unit deploy, activate, query, rollback;
4. RS-04 Restricted Unit compatibility outcome;
5. RS-05 multi-Core federation route;
6. RS-06 relay-assisted or degraded remote access;
7. RS-07 Agent-assisted governed operation flow;
8. RS-08 cleanup and rerun readiness.

Rows may use deterministic or bounded staged evidence where the checklist allows
it, but every row must state `passed`, `blocked`, or `deferred` with structured
evidence and operator next actions.

### WS-7 Promotion Bundle

The final promotion bundle must include:

1. `closure.db`;
2. release-2.0.0 real-scene checklist JSON;
3. documentation closure JSON;
4. provider and multimodal/profile smoke JSON;
5. regression closure JSON;
6. hardware compatibility and acceptance matrix JSON;
7. resource-budget governance JSON;
8. Agent excellence JSON;
9. signing/provenance JSON;
10. observability and rollback hardening JSON;
11. real-scene E2E JSON;
12. final `closure-summary-final.json`;
13. promotion checklist and approval JSON.

Promotion requires `validation_gate_summary.ok=true`, `passed_count=20`, and an
empty `failed_gate_ids` list.

### WS-8 Release Identity Promotion

Only after the promotion bundle is green:

1. promote Neuro CLI `RELEASE_TARGET` to `2.0.0`;
2. promote workflow catalog release identity to `2.0.0`;
3. promote sample Unit app source identity and manifest patch to `2.0.0`;
4. update tests that assert release identity;
5. rebuild the sample Unit app artifact;
6. refresh capability and signing/provenance evidence;
7. rerun final closure-summary after promotion;
8. commit and push to `origin/main`.

## 5. Verification Commands

Run from the west workspace root unless noted.

```bash
source applocation/NeuroLink/scripts/setup_neurolink_env.sh --activate --strict --install-unit-cli-deps
/home/emb/project/zephyrproject/.venv/bin/python -m pytest applocation/NeuroLink/neurolink_core/tests -q
/home/emb/project/zephyrproject/.venv/bin/python -m pytest applocation/NeuroLink/neuro_cli/tests/test_neuro_cli.py -q
bash applocation/NeuroLink/scripts/preflight_neurolink_linux.sh --node unit-01 --auto-start-router --require-serial --output json
```

Core evidence commands:

```bash
cd applocation/NeuroLink
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli no-model-dry-run --output json
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli maf-provider-smoke --output json
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli multimodal-profile-smoke --text inspect --output json
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli real-scene-checklist-template --release-target 2.0.0 --implementation-release 1.2.7 --output json
```

Final closure command shape:

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli closure-summary \
  --db <closure.db> \
  --session-id <session-id> \
  --documentation-file <documentation-closure.json> \
  --provider-smoke-file <provider-smoke.json> --require-provider-smoke \
  --multimodal-profile-file <multimodal-profile-smoke.json> --require-multimodal-profile \
  --regression-file <regression-closure.json> \
  --relay-failure-file <relay-failure.json> \
  --hardware-compatibility-file <hardware-compatibility.json> \
  --hardware-acceptance-matrix-file <hardware-acceptance-matrix.json> \
  --resource-budget-governance-file <resource-budget-governance-smoke.json> \
  --agent-excellence-file <agent-excellence-smoke.json> \
  --release-rollback-file <release-rollback-hardening-smoke.json> \
  --signing-provenance-file <signing-provenance-smoke.json> \
  --observability-diagnosis-file <observability-diagnosis-smoke.json> \
  --real-scene-e2e-file <real-scene-e2e-smoke.json> \
  --output json > <closure-summary-final.json>
```

## 6. Exit Criteria

Release 2.0.0 is complete only when:

1. finalization plan, migration notes, AI Core user guide, README, runbooks, and
   progress ledger agree on the active release state;
2. freeze checklist records no unresolved implementation-bearing contract gap;
3. RS-01 through RS-08 are archived with passed or explicitly approved deferred
   status;
4. final closure-summary reports all 20 gates green;
5. canonical release identity is promoted to `2.0.0`;
6. sample Unit app identity and rebuilt artifact match the promoted release;
7. final promotion artifacts are archived and reviewable;
8. final commit is pushed to the remote repository.
