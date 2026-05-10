# Release 2.0.0 Migration Notes

## 1. Audience

These notes are for operators and developers moving from a release-1.2.x
NeuroLink workspace to the release-2.0.0 stabilized baseline.

Release 2.0.0 is not a new feature branch. It is the stabilized release line
that freezes and promotes the AI Core, Neuro CLI, Unit control plane, and
release evidence surfaces completed through release 1.2.7.

## 2. Supported Source Baselines

The expected migration sources are:

1. release-1.2.4 Core app build/deploy and live-event service baseline;
2. release-1.2.5 multimodal Agent runtime and memory governance baseline;
3. release-1.2.6 federation, relay, hardware abstraction, and Tool/Skill/MCP
   platform baseline;
4. release-1.2.7 HLD completion and release-2.0.0 readiness baseline.

Older release-1.1.x Unit/demo environments should first validate the Unit build,
preflight, and Neuro CLI paths before running AI Core release evidence.

## 3. Environment Preparation

Run setup from the west workspace root:

```bash
source applocation/NeuroLink/scripts/setup_neurolink_env.sh --activate --strict --install-unit-cli-deps
```

Install or refresh AI Core dependencies when needed:

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m pip install -r applocation/NeuroLink/neurolink_core/requirements.txt
```

For WSL hardware validation, attach and prepare the board before running live
rows:

```bash
bash applocation/NeuroLink/scripts/prepare_dnesp32s3b_wsl.sh --attach-only
bash applocation/NeuroLink/scripts/prepare_dnesp32s3b_wsl.sh --device /dev/ttyACM0 --node unit-01 --capture-duration-sec 30
bash applocation/NeuroLink/scripts/preflight_neurolink_linux.sh --node unit-01 --auto-start-router --require-serial --output json
```

## 4. Release Identity Expectations

Before final promotion, the repository could still report `release_target=1.2.7`.
That was intentional. The canonical identity is promoted to `2.0.0` only after
the fresh release-2.0.0 promotion bundle is green.

After promotion, verify:

```bash
/home/emb/project/zephyrproject/.venv/bin/python applocation/NeuroLink/neuro_cli/src/neuro_cli.py --output json system capabilities
```

Expected result after final promotion: `release_target=2.0.0`.

## 5. AI Core Runtime Changes

AI Core keeps the same safety model:

1. models never execute Unit tools directly;
2. Rational backends propose plans only;
3. Core policy validates tools, arguments, leases, and approvals;
4. side-effecting operations remain approval-gated;
5. all release evidence is structured JSON and audit-visible.

The primary user-facing AI Core startup guide is:

```text
docs/project/AI_CORE_USER_GUIDE.md
```

The detailed release evidence runbooks remain:

```text
docs/project/AI_CORE_RUNBOOK.md
docs/project/AI_CORE_RUNBOOK_ZH.md
```

## 6. Hardware And Transport Notes

Hardware-specific recovery belongs in operator evidence and troubleshooting,
not in shared Core/Unit contracts. For WSL and DNESP32S3B validation, the most
common recovery path is:

1. restore `/dev/ttyACM0` visibility;
2. confirm UART reaches `NETWORK_READY`;
3. inspect the Unit Zenoh endpoint;
4. update the endpoint if the host IP changed;
5. rerun preflight until it reports `status=ready`.

Serial endpoint inspection:

```bash
/home/emb/project/zephyrproject/.venv/bin/python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py serial zenoh show --port /dev/ttyACM0
/home/emb/project/zephyrproject/.venv/bin/python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py serial zenoh set tcp/<host-ip>:7447 --port /dev/ttyACM0
```

## 7. Evidence Bundle Expectations

Fresh release-2.0.0 promotion evidence should live under:

```text
smoke-evidence/release-2.0.0-promotion-<UTC>/
```

Minimum expected files:

1. `closure.db`;
2. `real-scene-checklist.json`;
3. `documentation-closure.json`;
4. `provider-smoke.json`;
5. `multimodal-profile-smoke.json`;
6. `hardware-compatibility.json`;
7. `hardware-acceptance-matrix.json`;
8. `resource-budget-governance-smoke.json`;
9. `agent-excellence-smoke.json`;
10. `signing-provenance-smoke.json`;
11. `observability-diagnosis-smoke.json`;
12. `release-rollback-hardening-smoke.json`;
13. `live-event-smoke.json`;
14. `real-scene-e2e-smoke.json`;
15. `closure-summary-final.json`;
16. promotion checklist and approval JSON.

Generated smoke evidence is normally ignored by Git. Commit only durable docs,
plans, checklists, and summaries that the repository already tracks.

## 8. Stabilization Blocker Classification

Classify rerun failures as follows:

1. `environment_blocker`: host, WSL, serial, router, or board availability issue;
2. `stabilization_defect`: already-claimed behavior fails under the frozen
   release surface;
3. `documentation_gap`: operator cannot follow the documented procedure;
4. `evidence_gap`: behavior works but does not produce closure-consumable JSON;
5. `new_scope_request`: requested behavior was not part of the frozen 1.2.7
   completion surface.

Only stabilization defects, documentation gaps, and evidence gaps should be
fixed in release 2.0.0. New scope requests should be recorded for post-2.0.0.

## 9. Promotion Readiness

Do not promote release identity until:

1. contract freeze audit is complete;
2. AI Core user guide and README are updated;
3. release-2.0.0 scenario rerun is archived;
4. final closure-summary is green;
5. sample Unit app identity and artifact are refreshed;
6. final promotion approval is recorded;
7. the final commit is pushed to the remote repository.
