# NeuroLink Release 1.1.8 Pre-Research Baseline

## 1. Scope

Release 1.1.8 is a Neuro CLI reliability, completeness, and Agent-embedding
release on top of the closed release-1.1.7 hardware baseline. The release goal
is to make `neuro_cli` the dependable, self-describing control surface that any
Agent can embed as a skill for building, testing, discovering, controlling, and
troubleshooting NeuroLink Unit environments.

This release is not a firmware optimization release and is not a CBOR protocol
replacement release. Firmware changes are in scope only when they are required
to expose reliable CLI-visible status, discovery metadata, or control semantics
that cannot be represented correctly from the host side alone.

Primary objectives:

1. Move the canonical skill description, references, assets, and Agent-facing
   invocation contract into the `neuro_cli` project directory, while preserving
   project-shared discovery for `.github/skills/neuro-cli` through a mirror or
   pointer that cannot drift silently.
2. Expand the skill and CLI workflow guidance so a fresh Linux or Windows host
   with network access can build a complete `neuro_unit` compile, test, flash,
   smoke, deploy, and control environment from zero.
3. Make device remote discovery and remote control explicit enough for smaller
   Agents to execute without inference-heavy interpretation.
4. Preserve stable JSON output and failure classification for every Agent-facing
   path, including setup, discovery, lease, deploy, app invoke, callback, smoke,
   and release-evidence workflows.
5. Add validation that the skill content, workflow plans, wrapper behavior, and
   setup instructions remain aligned with live CLI commands.

Out of scope for kickoff:

1. Promoting `RELEASE_TARGET` from `1.1.7` to `1.1.8` before closure evidence.
2. Replacing Zenoh transport, CBOR-v2 Unit traffic, lease semantics, update
   semantics, or callback security policy.
3. Treating a human-readable runbook as sufficient Agent enablement. Release
   1.1.8 must produce machine-checkable contracts and deterministic workflow
   plans, not only prose.
4. Requiring hardware availability for purely local documentation, parser,
   wrapper, and setup-plan slices. Hardware remains required for final remote
   control closure.

## 2. Current Baseline

Release-1.1.7 is closed in the current workspace. The final progress entry
records hardware closure with serial-required preflight, full Linux smoke,
callback freshness, release identity promotion, focused CLI tests, script tests,
and memory evidence.

Canonical release marker:

1. `applocation/NeuroLink/neuro_cli/src/neuro_cli.py`
2. `RELEASE_TARGET = "1.1.7"`

Current Neuro CLI structure:

1. `applocation/NeuroLink/neuro_cli/src/neuro_cli.py`: canonical CLI entrypoint.
2. `applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py`: JSON-first
   wrapper for skills and automation.
3. `applocation/NeuroLink/neuro_cli/tests/`: CLI and wrapper regression suite.
4. `applocation/NeuroLink/neuro_cli/skill/`: legacy compatibility pointer.
5. `applocation/NeuroLink/.github/skills/neuro-cli/`: current project-shared
   skill discovery surface.

Current strengths inherited from release-1.1.7:

1. `invoke_neuro_cli.py` enforces JSON mode and classifies process failures,
   invalid JSON stdout, `ok=false`, top-level failure statuses, and nested reply
   payload failure statuses.
2. CLI JSON envelopes cover parse failures, session-open failures, handler
   failures, `no_reply`, and nested Unit `status: error` paths.
3. `workflow plan` exists for build, test, preflight, smoke, memory evidence,
   callback smoke, and release closure.
4. The project-shared skill describes high-level CLI usage and points Agents to
   workflow plans before running build or board operations.
5. Linux smoke and preflight paths already install tracked Neuro CLI Python
   dependencies when requested.

Known gaps to close in release-1.1.8:

1. Skill ownership is split: the real discovery skill lives under `.github`,
   while `neuro_cli/skill` is only a legacy pointer. This violates the new
   requirement that the skill description and concrete information live with the
   `neuro_cli` project.
2. Linux setup guidance assumes many tools already exist. It validates the
   environment but does not yet provide a complete zero-host bootstrap plan for
   installing system packages, Python environment, west, Zephyr modules, SDK,
   CLI dependencies, router prerequisites, and board/USB prerequisites.
3. Windows setup guidance is thinner than Linux guidance and depends on an
   existing conda environment. It does not yet explain a complete network-only
   path for Git, Python/conda or venv, west, CMake, Ninja, Zephyr SDK,
   PowerShell policy, WSL/USBIP when needed, and CLI dependencies.
4. Remote discovery is currently mostly implied by `query device`, preflight,
   router checks, and smoke evidence. Smaller Agents need a named discovery
   workflow with exact inputs, outputs, failure states, and next actions.
5. Remote control is currently spread across lease, deploy, app invoke,
   callback config, event monitor, and smoke docs. Smaller Agents need ordered
   control recipes with required preconditions, lease cleanup, expected JSON
   fields, and stop conditions.
6. Workflow plans contain useful commands but not enough structured metadata for
   low-parameter Agents: prerequisites, host support, destructive/non-destructive
   flags, requires hardware, requires serial, creates artifacts, expected JSON
   statuses, and recovery hints should be explicit.

## 3. Release Decisions

### Skill Ownership Decision

The `neuro_cli` project directory becomes the canonical source of truth for the
Neuro CLI skill. The `.github/skills/neuro-cli` path remains the project-shared
discovery location, but it must either mirror generated content from
`neuro_cli/skill` or clearly point to the canonical files with drift tests.

Required canonical skill package layout:

1. `neuro_cli/skill/SKILL.md`: full skill frontmatter and operating contract.
2. `neuro_cli/skill/references/setup-linux.md`: zero-host Linux bootstrap.
3. `neuro_cli/skill/references/setup-windows.md`: zero-host Windows bootstrap.
4. `neuro_cli/skill/references/workflows.md`: command workflows generated or
   checked against live CLI workflow plans.
5. `neuro_cli/skill/references/discovery-and-control.md`: remote discovery,
   selection, lease, deploy, invoke, callback, monitor, cleanup, and recovery
   recipes.
6. `neuro_cli/skill/assets/`: app and callback templates owned by the CLI skill
   package or mirrored from `.github/skills/neuro-cli/assets` with tests.

### Zero-Host Setup Decision

Release 1.1.8 must distinguish between environment validation and environment
construction. Existing setup scripts validate an environment and activate known
venv/conda paths. New skill guidance and workflow plans must describe how to
construct the environment from a host that has only the operating system and
network access.

For Linux, the zero-host path must cover:

1. Supported distribution assumptions and minimum shell tools.
2. System packages: Git, Python 3, venv/pip, CMake, Ninja, west, device rules,
   compilers, `clang-format`, `perl`, `usbutils`, serial permissions, and router
   prerequisites.
3. Workspace acquisition or validation for a west workspace containing Zephyr,
   modules, and `applocation/NeuroLink`.
4. Repository-local `.venv` creation and activation.
5. Python dependency installation from Zephyr and
   `neuro_cli/requirements.txt`.
6. Zephyr SDK installation or discovery.
7. `west update` expectations for required modules, especially `zenoh-pico`.
8. Unit build, Unit tests, Unit app build, CLI tests, preflight, router, smoke,
   and evidence commands.

For Windows, the zero-host path must cover:

1. Supported shell model: PowerShell as the user-facing entry, with WSL noted
   only where the validated board/router path requires it.
2. Tool acquisition with explicit choices: winget/chocolatey/manual installers
   for Git, Python or Miniforge/conda, CMake, Ninja, west, Zephyr SDK,
   PowerShell 7, USB/IP tooling when WSL routing is used, and serial drivers.
3. Workspace checkout or extraction into a west workspace.
4. Environment creation and activation without assuming a preexisting `zephyr`
   conda environment.
5. Windows compatibility script usage and when to cross into WSL for router,
   serial attach, or Linux-canonical evidence.
6. Neuro CLI dependency installation and wrapper invocation from PowerShell.
7. Build, test, smoke, and control commands with Windows path quoting examples.

### Low-Parameter Agent Decision

Every Agent-facing workflow must be executable from a small set of fields rather
than open-ended prose. A workflow plan should include:

1. `workflow`, `category`, `description`, and `release_target`.
2. `host_support`: Linux, Windows, WSL, or hardware-specific.
3. `requires_hardware`, `requires_serial`, `requires_router`, and
   `requires_network` booleans.
4. `destructive`: whether the workflow flashes firmware, deploys an app,
   changes callback config, or only queries state.
5. `preconditions`: commands or facts that must be true before execution.
6. `commands`: exact ordered command array.
7. `expected_success`: stable JSON fields or script summary fields.
8. `failure_statuses`: common statuses with next action hints.
9. `artifacts`: expected evidence outputs.
10. `cleanup`: lease release, process cleanup, or subscriber teardown steps.

The skill must instruct Agents to prefer `workflow plan <name>` output over
hand-written command assembly.

### Remote Discovery and Control Decision

Remote discovery and control must be split into explicit workflows.

Discovery levels:

1. Host discovery: validate local tools, Python environment, Zephyr SDK, and CLI
   dependencies.
2. Router discovery: detect or start the Zenoh router and report listening
   address/port.
3. Serial discovery: list visible board serial devices and classify WSL USB
   attach blockers separately from board protocol blockers.
4. Device discovery: identify reachable Unit nodes through `query device` or a
   future multi-node discovery helper.
5. App discovery: query apps, leases, and capabilities for a selected node.

Control recipes:

1. Read-only health: `query device`, `query apps`, `query leases`, event watch.
2. Protected deploy: acquire update lease, prepare, verify, activate, post-query,
   callback freshness, release lease.
3. App command: acquire app-control lease where required, invoke command, verify
   reply, monitor app-scoped callbacks, release lease.
4. Recovery: classify `serial_device_missing`, `no_reply_board_unreachable`,
   `session_open_failed`, router absence, callback timeout, nested
   `payload.status=error`, and stale artifact failures.

### Plan Reasonableness Analysis

The release-1.1.8 plan is reasonable if it is executed as a phased CLI and
skill-contract release, not as a broad host-installer or firmware feature
release. The scope is justified because release-1.1.7 already closed the core
hardware path, and the remaining weakness is the Agent-facing control surface:
the skill is split from the CLI project, setup guidance assumes a prepared host,
and discovery/control workflows still require too much human interpretation.

The plan would become too broad if release-1.1.8 tries to fully automate every
Windows system package, USB driver, WSL, and Zephyr SDK install path. Windows
support should be treated as a validated PowerShell and WSL guidance path in
this release, with explicit manual steps where the host requires administrator
approval, driver prompts, or package-manager policy decisions.

Release-1.1.8 MVP:

1. Make `neuro_cli/skill` the canonical skill package and keep
   `.github/skills/neuro-cli` as a tested discovery adapter or mirror.
2. Extend live `workflow plan` output with structured fields for host support,
   hardware requirements, destructive operations, preconditions, expected
   success, failure statuses, artifacts, and cleanup.
3. Add zero-host Linux and Windows setup references that are complete enough for
   a network-only host, while marking privileged/manual steps explicitly.
4. Define discovery workflows for host, router, serial, Unit, apps, and leases.
5. Define protected control workflows for health query, deploy, app invoke,
   callback configuration, callback smoke, event monitoring, and lease cleanup.
6. Add skill/workflow alignment validation so examples and references cannot
   drift from live CLI parser commands or workflow plan names.

Deferred beyond the MVP unless a later slice proves they are required:

1. Fully automated Windows toolchain installation across all host variants.
2. Multi-node or mesh discovery beyond the currently validated `unit-01` path.
3. Firmware-side discovery changes that can be represented by existing host-side
   query, preflight, and smoke outputs.
4. Protocol replacement, transport changes, or memory optimization work.
5. A new installer artifact; release-1.1.8 should first produce validated
   commands, scripts, references, and workflow contracts.

Implementation dependency order:

1. Inventory and freeze the live command surface before moving skill content.
2. Move the canonical skill package before adding more references, so new
   documentation lands in the future source of truth.
3. Extend `WORKFLOW_PLANS` metadata before writing Agent-facing setup,
   discovery, and control references that depend on those fields.
4. Add Linux setup before Windows setup, because Linux remains the canonical
   release evidence host and the Windows path can point back to Linux/WSL
   boundaries where required.
5. Define discovery before control, because safe control needs node, router,
   serial, app, and lease state to be known first.

Current implementation prerequisites found during `EXEC-181` inventory:

1. `WORKFLOW_PLANS` currently lives in `neuro_cli/src/neuro_cli.py` and returns
   only `category`, `description`, `commands`, and `artifacts` plus wrapper and
   protocol metadata.
2. Existing workflow commands still contain hardcoded `1.1.7` labels and app
   echo strings for `memory-evidence`, `callback-smoke`, and `release-closure`.
   A release-1.1.8 implementation must derive these from `RELEASE_TARGET` or
   update them in a controlled promotion slice.
3. `agent_skill.project_shared_path` currently points at
   `.github/skills/neuro-cli/SKILL.md`; release-1.1.8 must expose both the
   canonical `neuro_cli/skill` path and the project-shared discovery adapter so
   Agents do not follow stale metadata.
4. The CLI currently supports `workflow plan <name>` and `system workflow plan
   <name>`, but not a separate workflow list command. Any skill text must ask
   for known plan names or add and test a listing command before referencing it.
5. Existing setup scripts validate and activate environments; they do not yet
   construct a complete fresh host from operating-system defaults.

## 4. Workstreams

### WS-1 Kickoff Inventory and Contract Freeze

1. Record the 1.1.8 planning baseline and progress ledger entry.
2. Inventory current `neuro_cli` commands, workflow plans, skill files,
   setup scripts, Windows wrappers, and smoke/preflight behavior.
3. Freeze the release-1.1.8 Agent contract vocabulary before implementation:
   setup, discover, select node, health query, lease, deploy, invoke, callback,
   monitor, cleanup, evidence, release closure.
4. Keep `RELEASE_TARGET = "1.1.7"` until final closure.

### WS-2 Canonical Skill Package Under neuro_cli

1. Promote `neuro_cli/skill/SKILL.md` from compatibility pointer to canonical
   full skill definition with frontmatter.
2. Move or mirror workflow references, setup references, templates, and callback
   handler assets into `neuro_cli/skill`.
3. Keep `.github/skills/neuro-cli/SKILL.md` as the discovery adapter, with clear
   source-of-truth language pointing back to `neuro_cli/skill`.
4. Add tests that validate frontmatter, required reference files, asset paths,
   wrapper path, and no stale `.github`-only content.

### WS-3 Zero-Host Linux Bootstrap

1. Write a detailed Linux bootstrap reference for a network-only host.
2. Add `workflow plan setup-linux` with structured prerequisites and commands.
3. Decide whether to extend `setup_neurolink_env.sh` with a dry-run
   construction mode or keep installation commands in skill references only.
4. Validate the plan by checking commands for syntax and by running the portions
   that are safe in the current workspace.
5. Add a troubleshooting table for missing SDK, missing west, missing
   `zenoh-pico`, missing serial device, missing router, and missing Python
   `zenoh` module.

### WS-4 Zero-Host Windows Bootstrap

1. Write a detailed Windows bootstrap reference for a network-only host.
2. Add `workflow plan setup-windows` with structured prerequisites and commands.
3. Update or document `setup_neurolink_env.ps1` so it no longer assumes a
   preexisting `zephyr` conda environment without explaining how to create it.
4. Clarify when Windows runs native wrappers and when WSL is used for router,
   USB attach, or Linux-canonical evidence.
5. Add PowerShell parser or static validation where possible; record if `pwsh`
   is unavailable in the Linux development environment.

### WS-5 Structured Workflow Plan Schema

1. Extend workflow plan payloads with low-parameter Agent fields:
   `host_support`, `requires_hardware`, `requires_serial`, `requires_router`,
   `requires_network`, `destructive`, `preconditions`, `expected_success`,
   `failure_statuses`, and `cleanup`.
2. Add plans for `setup-linux`, `setup-windows`, `discover-host`,
   `discover-router`, `discover-serial`, `discover-device`, `discover-apps`,
   `control-health`, `control-deploy`, `control-app-invoke`, and
   `control-callback`.
3. Keep existing plan names backward compatible.
4. Add regression tests for the new fields and legacy plan compatibility.

### WS-6 Remote Discovery Semantics

1. Define the exact JSON shape for discovery outputs and failures.
2. Decide whether discovery is implemented as new CLI commands, workflow plans
   around existing scripts, or both.
3. Prefer read-only commands for discovery and clearly mark hardware-changing
   operations as control, not discovery.
4. Add remote discovery examples that include successful Unit reachability,
   router-only/no-board, serial-missing, board-unreachable, and app-not-running
   states.
5. Ensure preflight classifications remain aligned with live board/router
   behavior from previous release evidence.

### WS-7 Remote Control Recipes and Safety

1. Define protected control recipes with required lease acquisition and cleanup.
2. Make deploy, app invoke, callback config, callback smoke, and event monitor
   sequences unambiguous for Agent execution.
3. Ensure wrapper classification treats nested Unit errors as command failures.
4. Add examples for `query device`, `query apps`, `query leases`, deploy
   prepare/verify/activate, app callback config, app invoke, monitor events,
   and cleanup.
5. Keep callback handler execution explicit and audited.

### WS-8 CLI Reliability Completion

1. Audit all high-value handlers for stable JSON output under exceptions.
2. Add parser and output regressions for system, workflow, discovery, query,
   lease, deploy, update, app invoke, callback config, callback smoke, and
   monitor events.
3. Verify retry and timeout reporting for session open, query collection,
   subscriber setup, callback waiting, and handler execution.
4. Confirm human output does not leak into JSON stdout in wrapper-driven flows.
5. Add or update capability output so Agents can see supported setup,
   discovery, and control surfaces.

### WS-9 Skill Documentation Quality Gate

1. Add a skill validation test that checks all referenced commands exist as CLI
   parser commands or workflow plans.
2. Validate referenced files and assets from both `neuro_cli/skill` and
   `.github/skills/neuro-cli`.
3. Add sample invocation checks for Linux and Windows snippets where practical.
4. Ensure low-parameter Agent instructions avoid implied steps such as "set up
   the environment" without exact commands or decision points.

### WS-10 Closure and Release Identity

1. Run local CLI, wrapper, script, skill, and documentation validation gates.
2. Run Linux build/test gates required for confidence that setup commands still
   match the workspace.
3. Run hardware preflight, discovery, remote control smoke, deploy, callback
   freshness, and lease cleanup gates.
4. Capture final evidence and promote `RELEASE_TARGET` to `1.1.8` only after all
   closure gates pass.

### Detailed Execution Planning

Phase 1: Inventory, reasonableness, and contract freeze.

1. Confirm live parser commands, workflow plan names, skill paths, setup scripts,
   Windows wrappers, and smoke/preflight behavior.
2. Record hardcoded release strings and path assumptions that must be removed or
   consciously updated later.
3. Exit criteria: the 1.1.8 document states MVP, deferred scope, dependency
   order, and implementation prerequisites; no behavior changes are made.

Phase 2: Canonical skill package and discovery adapter.

1. Promote `neuro_cli/skill/SKILL.md` from compatibility pointer to canonical
   frontmatter-bearing skill definition.
2. Add `neuro_cli/skill/references` and `neuro_cli/skill/assets` as the source
   of truth for setup, workflow, discovery/control, app template, and callback
   handler guidance.
3. Keep `.github/skills/neuro-cli` discoverable as a pointer or tested mirror.
4. Exit criteria: skill resource validation proves required files exist and the
   wrapper path resolves from the workspace root.

Phase 3: Workflow plan schema and release-string hygiene.

1. Extend `WORKFLOW_PLANS` entries with the low-parameter Agent metadata defined
   in this document.
2. Preserve existing plan names and output fields for backward compatibility.
3. Replace or isolate hardcoded `1.1.7` workflow command strings so release
   evidence labels and callback echo checks cannot silently drift.
4. Exit criteria: focused CLI tests prove legacy plans still parse and new
   metadata fields are present for every workflow.

Phase 4: Setup references and setup plans.

1. Implement `setup-linux` first as the canonical fresh-host path.
2. Implement `setup-windows` as a PowerShell-first compatibility path with clear
   WSL and USB/IP boundaries.
3. Keep privileged package installation, driver prompts, and system policy
   changes documented as explicit operator steps rather than hidden automation.
4. Exit criteria: setup references contain exact commands, expected checks, and
   recovery notes; workflow plans return non-executing command arrays and
   preconditions.

Phase 5: Discovery and protected control.

1. Add discovery plans before control plans: host, router, serial, Unit, apps,
   and leases.
2. Add control plans only after discovery status fields and failure statuses are
   stable: health query, protected deploy, app invoke, callback, monitor, and
   cleanup.
3. Exit criteria: every destructive control plan declares `destructive: true`,
   required leases, expected success fields, failure statuses, and cleanup.

Phase 6: Alignment lint, local closure, and hardware closure.

1. Add a skill/workflow alignment gate that checks referenced workflow names,
   wrapper paths, assets, and command examples against live parser behavior.
2. Run local CLI, wrapper, script, skill, and build gates.
3. Run hardware discovery/control closure only after local gates pass.
4. Exit criteria: final evidence captures discovery, deploy/control, callback
   freshness, lease cleanup, and release identity promotion to `1.1.8`.

## 5. Acceptance Criteria

1. `neuro_cli/skill` is the canonical skill package and contains the full skill
   description, references, workflow guidance, and assets required by Agents.
2. `.github/skills/neuro-cli` remains discoverable and cannot drift from the
   canonical `neuro_cli/skill` content without tests failing.
3. A fresh Linux host with network access has a step-by-step path to install
   dependencies, create/activate the environment, initialize the west workspace,
   install CLI dependencies, build Unit firmware, run Unit/CLI tests, build the
   app, start/check router paths, run preflight, and run smoke/control flows.
4. A fresh Windows host with network access has a step-by-step path to install
   dependencies, create/activate the environment, use Windows compatibility
   wrappers, and bridge into WSL/USBIP where the validated board workflow
   requires it.
5. Workflow plans expose structured metadata that a low-parameter Agent can use
   without inferring hidden preconditions.
6. Remote discovery distinguishes host, router, serial, Unit reachability, app
   state, and lease state.
7. Remote control recipes specify exact command order, required inputs, expected
   success fields, failure states, and cleanup.
8. CLI and wrapper JSON contracts remain stable across success, process failure,
   invalid stdout, `ok=false`, `status=error`, nested `payload.status=error`,
   `no_reply`, `parse_failed`, `session_open_failed`, and `handler_failed`.
9. Final hardware closure proves discovery, protected deploy/control, callback
   freshness, and lease cleanup on real DNESP32S3B hardware.
10. Release identity is promoted to `1.1.8` only after local, skill, workflow,
    setup-documentation, script, and hardware gates pass.

## 6. Verification Gates

Local gates:

1. `/home/emb/project/zephyrproject/.venv/bin/python -m py_compile applocation/NeuroLink/neuro_cli/src/neuro_protocol.py applocation/NeuroLink/neuro_cli/src/neuro_cli.py applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py applocation/NeuroLink/neuro_cli/tests/test_neuro_cli.py applocation/NeuroLink/neuro_cli/tests/test_invoke_neuro_cli.py`
2. `/home/emb/project/zephyrproject/.venv/bin/python -m pytest applocation/NeuroLink/neuro_cli/tests/test_neuro_cli.py applocation/NeuroLink/neuro_cli/tests/test_invoke_neuro_cli.py -q`
3. `bash applocation/NeuroLink/tests/scripts/run_all_tests.sh`
4. `git -C applocation/NeuroLink diff --check`

Skill and workflow gates:

1. Validate `neuro_cli/skill/SKILL.md` frontmatter and required references.
2. Validate `.github/skills/neuro-cli` discovery adapter or mirror.
3. Run workflow-plan JSON checks for setup, discovery, control, callback,
   memory evidence, and release closure plans.
4. Validate wrapper classification for top-level and nested failure statuses.
5. Check that skill command examples point to live parser commands or workflow
   plans.

Setup gates:

1. Linux setup command snippets pass shell syntax checks where they are scripts.
2. Existing Linux environment validation still passes with
   `setup_neurolink_env.sh --activate --strict --install-neuro-cli-deps` when
   sourced in a configured workspace.
3. Windows PowerShell snippets/scripts pass parser checks when `pwsh` is
   available; otherwise record the validation gap explicitly.
4. Setup references document required manual steps that cannot be safely run by
   an Agent, such as installing system packages or accepting USB driver prompts.

Build and test gates:

1. `west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut_check -p always -t run`
2. `bash applocation/NeuroLink/neuro_unit/tests/unit/run_ut_linux.sh`
3. `bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit --no-c-style-check`
4. `bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-app --no-c-style-check`
5. `bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-edk --no-c-style-check`

Hardware gates:

1. USB/serial visibility or WSL USB attach evidence.
2. Router discovery or auto-start evidence.
3. Serial-required preflight.
4. Device discovery for `unit-01` with expected board and network metadata.
5. App and lease discovery.
6. Protected deploy prepare/verify/activate.
7. Post-activate query health.
8. App invoke or callback control recipe.
9. Callback freshness smoke with expected 1.1.8 app identity after final
   promotion slice.
10. Lease cleanup with `query leases` empty.

## 7. Initial Execution Slices

1. `EXEC-180`: release-1.1.8 kickoff baseline and planning ledger entry.
2. `EXEC-181`: inventory live CLI commands, workflow plans, skill references,
   setup scripts, Windows/Linux support gaps, hardcoded release strings, and
   refine MVP/deferred boundaries.
3. `EXEC-182`: promote canonical skill package into `neuro_cli/skill`, add
   required references/assets, and keep `.github/skills/neuro-cli` as a tested
   discovery adapter or mirror.
4. `EXEC-183`: extend workflow plan schema for low-parameter Agents while
   preserving existing plan names and legacy output fields.
5. `EXEC-184`: remove or isolate hardcoded `1.1.7` workflow command strings and
   update `agent_skill` metadata for canonical and project-shared skill paths.
6. `EXEC-185`: add zero-host Linux setup reference and `workflow plan setup-linux`.
7. `EXEC-186`: add zero-host Windows setup reference and `workflow plan setup-windows`.
8. `EXEC-187`: add remote discovery workflows and JSON contracts for host,
   router, serial, Unit, apps, and leases.
9. `EXEC-188`: add remote control recipes, safety/lease cleanup guidance, and
   control workflow plans.
10. `EXEC-189`: complete CLI reliability and skill/workflow alignment regressions
    across setup, discovery, control, callback, event, and wrapper paths.
11. `EXEC-190`: run local, skill, setup, workflow, script, and build gates.
12. `EXEC-191`: run hardware discovery/control closure and promote release
    identity to `1.1.8` if all evidence passes.

Slice numbering may split if implementation exposes an intermediate defect. Any
split must preserve the release boundary: no identity promotion and no claimed
Agent-complete setup/control flow until tests and evidence cover it.

## 8. Risks

1. Setup instructions can become stale faster than source code because package
   managers, Zephyr SDK installers, and Windows tooling change independently.
2. A skill that is valid for one Agent host may fail for another if it assumes a
   shell, path separator, Python executable, or package manager that is not
   present.
3. Mirroring skill content between `neuro_cli/skill` and `.github/skills` can
   drift unless tests explicitly check it.
4. Low-parameter Agents may execute destructive commands if workflow metadata
   does not clearly mark flash, deploy, callback config, and app control paths.
5. Device discovery over a router can confuse router reachability with board
   reachability unless serial, router, and Unit query states are separated.
6. Wrapper reliability can regress if human-readable diagnostics are printed to
   stdout in JSON mode.
7. Hardware closure still depends on USB serial visibility, WSL USB attach when
   applicable, router readiness, board Wi-Fi readiness, and fresh LLEXT artifact
   generation.

## 9. Rollback Strategy

1. Keep `.github/skills/neuro-cli` as a discovery adapter until the canonical
   `neuro_cli/skill` package has validation coverage.
2. Preserve existing workflow plan names and wrapper arguments for backward
   compatibility.
3. Add new setup/discovery/control workflow plans before changing existing
   command behavior.
4. If a setup automation change is risky, keep it as documented dry-run guidance
   until it is validated on a fresh host.
5. If hardware discovery/control changes fail, retain the release-1.1.7 CLI
   command set and record the failed evidence rather than masking it with prose.

## 10. Release Identity Policy

`applocation/NeuroLink/neuro_cli/src/neuro_cli.py` must remain at
`RELEASE_TARGET = "1.1.7"` throughout implementation. A final identity-promotion
slice may set it to `1.1.8` only after local gates, skill validation, setup
workflow validation, CLI/wrapper regressions, script gates, build gates,
serial-required preflight, remote discovery, protected remote control, callback
freshness, lease cleanup, and evidence capture pass.

## 11. Execution Status

### EXEC-180 Release-1.1.8 Baseline Planning

`EXEC-180` opens release-1.1.8 from the closed release-1.1.7 baseline. The
planning focus is Neuro CLI reliability and completeness as an embeddable Agent
skill, including canonical skill ownership under `neuro_cli`, zero-host Linux
and Windows setup guidance, low-parameter Agent workflow plans, and explicit
remote discovery/control recipes.

No source behavior, firmware behavior, setup script behavior, hardware state, or
release identity changes are included in this kickoff slice. The next slice
should inventory the live CLI/skill/setup surfaces and then promote the
canonical skill package into `neuro_cli/skill` with validation before expanding
setup and control workflows.

### EXEC-181 Plan Reasonableness and Live Inventory

`EXEC-181` refined the release-1.1.8 plan before behavior changes. The inventory
confirmed that live workflow plans are currently defined in `WORKFLOW_PLANS`
inside `neuro_cli/src/neuro_cli.py`, that existing workflow plans expose only
basic command/artifact fields, and that release-1.1.7 strings remain hardcoded
in memory-evidence, callback-smoke, and release-closure commands.

The slice added plan reasonableness analysis, MVP/deferred scope, dependency
ordering, implementation prerequisites, detailed execution phases, and refined
execution slices through `EXEC-191`. It made no runtime CLI, setup script,
firmware, hardware, or release identity changes.

### EXEC-182 Canonical Skill Package Migration

`EXEC-182` made `applocation/NeuroLink/neuro_cli/skill` the canonical home for
the Neuro CLI skill package. The canonical `SKILL.md` now carries the skill
frontmatter and operating contract, and the skill package owns references and
assets under `neuro_cli/skill/references` and `neuro_cli/skill/assets`.

The project-shared `.github/skills/neuro-cli/SKILL.md` remains as the VS Code
Agent discovery adapter and points back to the canonical skill package. Existing
workflow and asset files under `.github/skills/neuro-cli` are treated as tested
mirrors rather than the source of truth.

Added focused CLI tests that validate:

1. canonical `neuro_cli/skill` required resources exist,
2. canonical skill frontmatter includes `name: neuro-cli`,
3. the project-shared discovery adapter points to `neuro_cli/skill/SKILL.md`,
4. mirrored workflow and asset files match the canonical files.

Validation passed:

1. `/home/emb/project/zephyrproject/.venv/bin/python -m py_compile applocation/NeuroLink/neuro_cli/tests/test_neuro_cli.py`
2. `/home/emb/project/zephyrproject/.venv/bin/python -m pytest applocation/NeuroLink/neuro_cli/tests/test_neuro_cli.py -q` => `74 passed`
3. `/home/emb/project/zephyrproject/.venv/bin/python -m pytest applocation/NeuroLink/neuro_cli/tests/test_neuro_cli.py applocation/NeuroLink/neuro_cli/tests/test_invoke_neuro_cli.py -q` => `83 passed`

No runtime CLI behavior, setup script behavior, firmware behavior, hardware
state, or release identity changed. `RELEASE_TARGET` remains `1.1.7`.

### EXEC-183 Structured Workflow Plan Metadata

`EXEC-183` extended existing Neuro CLI workflow plans with low-parameter Agent
metadata while preserving the legacy `workflow plan <name>` command names and
legacy output fields. The plan payload now includes schema version
`1.1.8-workflow-plan-v1` plus structured fields for host support, hardware,
serial, router, network, destructive behavior, preconditions, expected success,
failure statuses, and cleanup.

This slice covers the existing workflow names only: `app-build`, `unit-build`,
`unit-edk`, `unit-tests`, `cli-tests`, `memory-evidence`, `preflight`, `smoke`,
`callback-smoke`, and `release-closure`. New setup, discovery, and protected
control workflow plan names remain assigned to later slices so they can be
implemented with their references and contracts together.

Added focused CLI regressions that validate every workflow plan includes the new
metadata fields and that critical safety semantics are explicit: preflight
requires hardware/serial/router but is non-destructive, callback smoke requires
hardware/router and is destructive, and CLI tests remain hardware-free with
Windows host support.

Validation passed:

1. `/home/emb/project/zephyrproject/.venv/bin/python -m py_compile applocation/NeuroLink/neuro_cli/src/neuro_cli.py applocation/NeuroLink/neuro_cli/tests/test_neuro_cli.py`
2. `/home/emb/project/zephyrproject/.venv/bin/python -m pytest applocation/NeuroLink/neuro_cli/tests/test_neuro_cli.py -q` => `76 passed`
3. `/home/emb/project/zephyrproject/.venv/bin/python -m pytest applocation/NeuroLink/neuro_cli/tests/test_neuro_cli.py applocation/NeuroLink/neuro_cli/tests/test_invoke_neuro_cli.py -q` => `85 passed`
4. `git -C applocation/NeuroLink diff --check`

No setup script behavior, firmware behavior, hardware state, or release identity
changed. `RELEASE_TARGET` remains `1.1.7`.

### EXEC-187 Remote Discovery Workflow Plans and JSON Contracts

`EXEC-187` added the first remote discovery slice for release-1.1.8. Per user
direction, this slice validates Linux/Python behavior only and does not claim
Windows or PowerShell validation. Windows setup validation remains a recorded
gap from `EXEC-186`, while this slice focuses on Linux-compatible workflow
plans, wrapper JSON output, and skill references.

Added six non-executing discovery workflow plans:

1. `discover-host`: local workspace, CLI, protocol, and canonical skill state.
2. `discover-router`: Linux preflight router listener classification.
3. `discover-serial`: Linux USB serial visibility classification.
4. `discover-device`: read-only Unit reachability through `query device`.
5. `discover-apps`: read-only app/runtime/update state through `query apps`.
6. `discover-leases`: read-only lease state through `query leases`.

Each discovery plan reports `category: discovery`, `executes_commands: false`,
host support, hardware/serial/router requirements, destructive state,
preconditions, expected success fields, failure statuses, cleanup, and a
machine-readable `json_contract` object. Contracts cover host `status: ready`,
router `router.listening`, serial `serial.present`, device reply payload
`status: ok`, apps `app_count/running_count/suspended_count/apps`, leases
`leases`, plus failure states such as `workspace_not_found`,
`router_not_listening`, `router_failed_to_start`, `serial_device_missing`,
`no_reply_board_unreachable`, `session_open_failed`, `no_reply`,
`parse_failed`, `error_reply`, `app_not_running`, `lease_conflict`, and nested
`payload.status: error`.

Updated the canonical discovery/control reference with discovery order,
workflow-plan examples, and JSON contracts for host, router, serial, device,
apps, and leases. Updated canonical and project-shared workflow references so
Agents see discovery plans before preflight, smoke, callback smoke, or protected
control.

Added regressions that validate parser support for all discovery plans,
structured discovery metadata, Linux wrapper/preflight command forms, JSON
contract presence, reference coverage, and workflow mirror alignment.

Linux validation passed:

1. `/home/emb/project/zephyrproject/.venv/bin/python -m py_compile applocation/NeuroLink/neuro_cli/src/neuro_cli.py applocation/NeuroLink/neuro_cli/tests/test_neuro_cli.py`
2. `/home/emb/project/zephyrproject/.venv/bin/python -m pytest applocation/NeuroLink/neuro_cli/tests/test_neuro_cli.py -q` => `88 passed`
3. `/home/emb/project/zephyrproject/.venv/bin/python -m pytest applocation/NeuroLink/neuro_cli/tests/test_neuro_cli.py applocation/NeuroLink/neuro_cli/tests/test_invoke_neuro_cli.py -q` => `97 passed`
4. `/home/emb/project/zephyrproject/.venv/bin/python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan discover-device` => `ok: true`, `executes_commands: false`
5. `/home/emb/project/zephyrproject/.venv/bin/python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan discover-apps` => `ok: true`, `executes_commands: false`
6. `git -C applocation/NeuroLink diff --check`

No setup script behavior, firmware behavior, hardware state, or release identity
changed. `RELEASE_TARGET` remains `1.1.7`.

### EXEC-188 Protected Remote Control Workflow Plans and Safety

`EXEC-188` added the protected remote control slice for release-1.1.8. Per user
direction, this slice continues Linux/Python validation only and does not claim
Windows, PowerShell, or hardware control execution. It defines the exact command
plans, safety metadata, JSON contracts, and cleanup expectations that Agents
must inspect before running remote control actions.

Added six non-executing control workflow plans:

1. `control-health`: read-only device, app, and lease health queries.
2. `control-deploy`: protected deploy prepare, verify, and activate sequence
   with update lease acquisition and cleanup.
3. `control-app-invoke`: protected app command invocation with app-control lease
   acquisition and cleanup.
4. `control-callback`: protected callback configuration, app invoke, event
   monitor, callback disable, and lease cleanup sequence.
5. `control-monitor`: app-scoped event monitoring with explicit optional handler
   audit requirements.
6. `control-cleanup`: known workflow lease release and final lease-state query.

Each control plan reports `category: control`, `executes_commands: false`, host
support, hardware/router requirements, destructive state, preconditions,
expected success fields, failure statuses, cleanup, and a machine-readable
`json_contract` object. Destructive plans explicitly mark `destructive: true`:
`control-deploy`, `control-app-invoke`, and `control-callback`. Read-only or
cleanup plans remain non-destructive, while still requiring hardware/router
reachability when they inspect Unit state.

The contracts cover protected update lease `update/app/neuro_unit_app/activate`,
app-control lease `app/neuro_unit_app/control`, deploy
prepare/verify/activate success fields, app invoke success fields, callback
configuration on/off, app-scoped callback event paths, explicit handler audit
semantics, cleanup lease ids, final `query leases` expectations, and failure
states including `lease_conflict`, `artifact_missing`, `artifact_stale`,
`prepare_failed`, `verify_failed`, `activate_failed`, `app_not_running`,
`callback_timeout`, `handler_failed`, `handler_timeout`,
`handler_output_truncated`, `lease_not_found`, and nested
`payload.status: error`.

Updated the canonical discovery/control reference with protected control order,
workflow-plan examples, and JSON contracts for health, deploy, app invoke,
callback, monitor, and cleanup. Updated canonical and project-shared workflow
references so Agents see control plans after discovery and before preflight,
smoke, callback smoke, or release closure. Added regressions that validate
parser support, destructive flags, lease boundaries, handler boundaries, cleanup
commands, JSON contract coverage, reference coverage, and canonical/project
shared mirror alignment.

Linux validation passed:

1. `/home/emb/project/zephyrproject/.venv/bin/python -m py_compile applocation/NeuroLink/neuro_cli/src/neuro_cli.py applocation/NeuroLink/neuro_cli/tests/test_neuro_cli.py`
2. `/home/emb/project/zephyrproject/.venv/bin/python -m pytest applocation/NeuroLink/neuro_cli/tests/test_neuro_cli.py -q` => `92 passed`
3. `/home/emb/project/zephyrproject/.venv/bin/python -m pytest applocation/NeuroLink/neuro_cli/tests/test_neuro_cli.py applocation/NeuroLink/neuro_cli/tests/test_invoke_neuro_cli.py -q` => `101 passed`
4. `/home/emb/project/zephyrproject/.venv/bin/python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan control-deploy` => `ok: true`, `executes_commands: false`, `destructive: true`
5. `/home/emb/project/zephyrproject/.venv/bin/python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan control-callback` => `ok: true`, `executes_commands: false`, `destructive: true`
6. `git -C applocation/NeuroLink diff --check`

No setup script behavior, firmware behavior, hardware state, hardware deploy,
hardware app invoke, hardware callback configuration, or release identity changed.
`RELEASE_TARGET` remains `1.1.7`.

### EXEC-189 CLI Reliability and Skill Workflow Alignment

`EXEC-189` completed the release-1.1.8 CLI reliability and skill/workflow
alignment slice, then ran the first Linux hardware discovery pass after the Unit
was reconnected. The local work focused on making the Agent-visible command
surface self-describing and mechanically checked against the live parser.

Code changes:

1. Added `build_workflow_surface()` to capabilities JSON. `system capabilities`
   now exposes the workflow plan schema version, canonical plan command forms,
   workflow categories, and every live workflow with category, host support,
   hardware/router/serial/network requirements, destructive flag, and plan
   command.
2. Fixed capabilities `agent_skill` metadata to resolve the NeuroLink root, so
   wrapper-driven `system capabilities` from the west workspace reports real
   canonical skill, project-shared adapter, and wrapper paths with existence
   checks set to true.
3. Extended the wrapper to accept and forward common CLI global retry/timeout
   options before the forwarded CLI command, including `--query-retries`,
   `--query-retry-backoff-ms`, `--query-retry-backoff-max-ms`, and `--timeout`.
   This keeps workflow plan examples executable through the wrapper.
4. Added alignment regressions that extract workflow plan names and wrapper
   examples from the canonical skill/reference files and project-shared adapter
   files, then verify referenced plan names exist in live `WORKFLOW_PLANS` and
   wrapper examples parse against the live CLI parser without wrapper-level
   `--output` duplication.

Hardware discovery results:

1. Initial serial-required Linux preflight failed with `serial_device_missing`:
   no `/dev/ttyACM*` or `/dev/ttyUSB*` was visible in WSL, while the router was
   listening on port `7447` and the LLEXT artifact was present.
2. `prepare_dnesp32s3b_wsl.sh --attach-only` attached Windows USB BUSID `8-4`
   into WSL and restored `/dev/ttyACM0`.
3. Re-running serial-required preflight then reached `no_reply_board_unreachable`:
   serial was present, router was listening on `0.0.0.0:7447`, but `query device`
   returned `no_reply`.
4. Full board preparation sent `app mount_storage` and
   `app network_connect cemetery goodluck1024` over UART. UART evidence at
   `applocation/NeuroLink/smoke-evidence/serial-diag/serial-capture-20260429T155211Z.log`
   shows `Wi-Fi connected` and `NETWORK_READY` with board IPv4 `192.168.2.67`,
   followed by repeated TCP probe failures to `tcp/192.168.2.95:7447`.
5. Host inspection showed current WSL/Windows LAN address `192.168.2.94`, while
   the board firmware still targets the previous router endpoint
   `192.168.2.95:7447`. A temporary WSL IP alias attempt for `192.168.2.95` was
   not completed because it required interactive `sudo`; no network alias was
   added.

Validation passed:

1. `/home/emb/project/zephyrproject/.venv/bin/python -m py_compile applocation/NeuroLink/neuro_cli/src/neuro_cli.py applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py applocation/NeuroLink/neuro_cli/tests/test_neuro_cli.py applocation/NeuroLink/neuro_cli/tests/test_invoke_neuro_cli.py`
2. `/home/emb/project/zephyrproject/.venv/bin/python -m pytest applocation/NeuroLink/neuro_cli/tests/test_neuro_cli.py -q` => `94 passed`
3. `/home/emb/project/zephyrproject/.venv/bin/python -m pytest applocation/NeuroLink/neuro_cli/tests/test_neuro_cli.py applocation/NeuroLink/neuro_cli/tests/test_invoke_neuro_cli.py -q` => `104 passed`
4. `/home/emb/project/zephyrproject/.venv/bin/python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py system capabilities` => `ok: true`, `workflow_surface` present, canonical skill and wrapper existence checks true
5. `/home/emb/project/zephyrproject/.venv/bin/python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan release-closure` => `ok: true`, `executes_commands: false`
6. `/home/emb/project/zephyrproject/.venv/bin/python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py --query-retries 3 query device` => wrapper argument parsing fixed; runtime result remains expected `no_reply` under the current board/router endpoint mismatch
7. `git -C applocation/NeuroLink diff --check`

Validation boundary:

1. Hardware deploy, app invoke, callback configuration, smoke, and lease cleanup
   were not executed in this slice because discovery did not reach Unit query
   readiness.
2. Windows/PowerShell validation remains intentionally out of scope for this
   Linux-only validation pass.
3. No setup script behavior, firmware behavior, destructive hardware state,
   release identity, or `RELEASE_TARGET` changed.

Next action: before `EXEC-190` or hardware closure, restore board-to-router
reachability by either running an operator-approved temporary host alias for
`192.168.2.95`, restoring the host to that address, or rebuilding/reflashing the
Unit with the current router endpoint `tcp/192.168.2.94:7447`; then rerun
serial-required preflight and discovery queries.

### EXEC-189B Hardware Reflash and Linux Retest

After the Unit endpoint drift was identified, the board was rebuilt and reflashed
for the current WSL/Windows LAN address. A one-off overlay set
`CONFIG_NEUROLINK_ZENOH_CONNECT="tcp/192.168.2.94:7447"`; the regenerated
`build/neurolink_unit/zephyr/.config` confirmed that endpoint. Flashing
`/dev/ttyACM0` through `build_neurolink.sh --preset flash-unit` succeeded:
esptool connected to ESP32-S3 `fc:01:2c:cf:ca:98`, wrote `808492` bytes,
verified the hash, and hard reset the board.

Linux hardware retest passed after the reflash:

1. Board preparation succeeded and wrote UART evidence to
   `applocation/NeuroLink/smoke-evidence/serial-diag/serial-capture-20260429T160006Z.log`.
2. Serial-required preflight returned `status=ready`: router listening on
   `7447`, `/dev/ttyACM0` present, app artifact present, and `query_device`
   successful.
3. Wrapper discovery passed for `query device`, `query apps`, and
   `query leases`. The Unit reports `session_ready: true`, `NETWORK_READY`,
   board IPv4 `192.168.2.67`, and initially empty app/lease lists.
4. Linux smoke passed with
   `bash applocation/NeuroLink/scripts/smoke_neurolink_linux.sh --install-missing-cli-deps --events-duration-sec 5`.
   Evidence was written to
   `applocation/NeuroLink/smoke-evidence/SMOKE-017B-LINUX-001-20260429-160227.ndjson`.
5. The smoke activation lease was explicitly released with the original
   `source_agent=rational` after a wrapper release as `skills` correctly failed
   with `lease holder mismatch`; final lease query returned `leases: []`.
6. Callback smoke passed when run with the app's actual expected echo
   `neuro_unit_app-1.1.7-cbor-v2`. The wrapper received callback events,
   released its callback lease, and final discovery showed device ready,
   `neuro_unit_app` running/active, and no leases.

Validation boundary: this retest changed the flashed board image but did not
promote release identity. `RELEASE_TARGET` remains `1.1.7`, and Windows
validation was not run.

### EXEC-190 Local Closure Gates

`EXEC-190` completed the final local Linux closure gates before release identity
promotion. Validation passed for:

1. Python compile of the protocol, CLI, wrapper, and focused tests.
2. Focused CLI and wrapper pytest suite: `104 passed`.
3. Script regression suite: `script_tests_passed=9`, `script_tests_failed=0`.
4. Clean build memory evidence at
   `applocation/NeuroLink/memory-evidence/exec-190-local-closure.{json,summary.txt}`:
   `release_target=1.1.7`, `dram0=377188`, `flash=673780`, `iram0=66216`,
   and `ext_ram=2847776`.
5. Clean-built Unit config confirmed
   `CONFIG_NEUROLINK_ZENOH_CONNECT="tcp/192.168.2.94:7447"`.
6. Rebuilt LLEXT artifact at `build/neurolink_unit/llext/neuro_unit_app.llext`.
7. Unit Linux UT: `result=PASS`, `twister_native_sim_rc=0`,
   `qemu_status=passed`, `qemu_build_rc=0`, and `qemu_run_rc=0`.
8. Wrapper `system capabilities` and `workflow plan release-closure` JSON.
9. `git -C applocation/NeuroLink diff --check`.

The board default endpoint was updated from `tcp/192.168.2.95:7447` to
`tcp/192.168.2.94:7447` so future clean builds match the current Linux/WSL
router endpoint used by the passing hardware evidence.

### EXEC-191 Hardware Closure and Release Identity Promotion

`EXEC-191` completed hardware closure and promoted release identity to 1.1.8.
The final clean-built Unit firmware was flashed to `/dev/ttyACM0`; esptool wrote
`808492` bytes, verified the hash, and hard reset ESP32-S3 `fc:01:2c:cf:ca:98`.
Board preparation wrote UART evidence to
`applocation/NeuroLink/smoke-evidence/serial-diag/serial-capture-20260429T161155Z.log`
and serial-required preflight returned `status=ready`.

Pre-promotion hardware closure passed:

1. Wrapper `query device`, `query apps`, and `query leases`.
2. Linux smoke with evidence
   `applocation/NeuroLink/smoke-evidence/SMOKE-017B-LINUX-001-20260429-161308.ndjson`.
3. Explicit release of smoke activation lease `lease-act-017b-001` with
   `source_agent=rational`.
4. Callback smoke using `neuro_unit_app-1.1.7-cbor-v2`, followed by final
   `leases: []`.

Release identity promotion then changed:

1. `neuro_cli/src/neuro_cli.py`: `RELEASE_TARGET = "1.1.8"`.
2. `subprojects/neuro_unit_app/src/main.c`: sample app version `1.1.8` and
   build id `neuro_unit_app-1.1.8-cbor-v2`.
3. Release-target regressions and script tests to expect `1.1.8`.
4. `README.md` to report release-1.1.8 as the closed release.

Post-promotion validation passed:

1. Python compile.
2. Focused CLI and wrapper pytest suite: `104 passed`.
3. Script regression suite: `9/9`.
4. Final memory evidence at
   `applocation/NeuroLink/memory-evidence/release-1.1.8-closure.{json,summary.txt}`:
   `release_target=1.1.8` and `dram0=377188`.
5. Rebuilt LLEXT artifact confirmed to contain `neuro_unit_app-1.1.8-cbor-v2`.
6. Wrapper `system capabilities` and `workflow plan release-closure` report
   `release_target: 1.1.8`.
7. Post-promotion preflight ready and Linux smoke passed with evidence
   `applocation/NeuroLink/smoke-evidence/SMOKE-017B-LINUX-001-20260429-161838.ndjson`.
8. Post-promotion callback smoke passed with expected echo
   `neuro_unit_app-1.1.8-cbor-v2`.
9. Final wrapper queries showed Unit `NETWORK_READY`, board IPv4
   `192.168.2.67`, `neuro_unit_app` running/active, and `leases: []`.

Windows validation was intentionally not run for this version per user
direction. Release-1.1.8 is closed against the current Linux and hardware
evidence.

### EXEC-184 Release-String Hygiene and Agent Skill Metadata

`EXEC-184` removed workflow-command release string drift by deriving memory
evidence labels, release-closure labels, and callback-smoke expected app echo
from `RELEASE_TARGET`. The release identity itself was not promoted; the derived
commands still resolve to release-1.1.7 values until the final closure slice
changes `RELEASE_TARGET`.

The slice also made Agent skill metadata explicit about both skill paths:
`canonical_path` points at `neuro_cli/skill/SKILL.md`, while
`project_shared_path` and `discovery_adapter_path` point at the VS Code Agent
adapter under `.github/skills/neuro-cli/SKILL.md`. The metadata now reports
existence checks, wrapper path, structured stdout support, source-of-truth state,
and callback handler execution policy through a shared helper used by system
init, workflow plan, and capabilities JSON.

Added regressions that validate:

1. capabilities JSON reports canonical and discovery-adapter skill metadata,
2. init diagnostics reports both canonical and project-shared skill files exist,
3. workflow plan metadata reports canonical source-of-truth and discovery
   adapter paths,
4. workflow command labels and app echo strings are derived from
   `RELEASE_TARGET`,
5. old workflow literals such as `release-1.1.7-memory-evidence`,
   `release-1.1.7-closure`, and `neuro_unit_app-1.1.7-cbor-v2` are absent from
   `neuro_cli.py` source.

Validation passed:

1. `/home/emb/project/zephyrproject/.venv/bin/python -m py_compile applocation/NeuroLink/neuro_cli/src/neuro_cli.py applocation/NeuroLink/neuro_cli/tests/test_neuro_cli.py`
2. `/home/emb/project/zephyrproject/.venv/bin/python -m pytest applocation/NeuroLink/neuro_cli/tests/test_neuro_cli.py -q` => `78 passed`
3. `/home/emb/project/zephyrproject/.venv/bin/python -m pytest applocation/NeuroLink/neuro_cli/tests/test_neuro_cli.py applocation/NeuroLink/neuro_cli/tests/test_invoke_neuro_cli.py -q` => `87 passed`
4. `git -C applocation/NeuroLink diff --check`

No setup script behavior, firmware behavior, hardware state, or release identity
changed. `RELEASE_TARGET` remains `1.1.7`.

### EXEC-185 Zero-Host Linux Setup Reference and Workflow Plan

`EXEC-185` expanded the canonical Linux setup reference from a placeholder into
a zero-host bootstrap guide for a networked Linux host. The reference now covers
host shape, operator-approved system packages, repository-local `.venv`
creation, Zephyr and Neuro CLI Python requirements, `west update`, Zephyr SDK
selection from `zephyr/SDK_VERSION`, strict environment validation, build/test
workflow discovery, hardware preflight boundaries, USB/serial permissions, and
failure recovery.

Added `workflow plan setup-linux` as a non-executing structured plan. It is
Linux-only, requires network access, does not require hardware/serial/router,
and is non-destructive. Its command list covers package installation review,
`.venv` creation, Python dependency installation, west module update, SDK version
inspection/export, environment validation, system diagnostics, and follow-on
workflow plan discovery for Unit build, Unit tests, app build, and preflight.

Updated workflow references so Agents see `workflow plan setup-linux` before
running setup validation commands. Added regressions that validate parser
support, structured metadata, command content, failure statuses, and canonical
Linux setup reference coverage.

Validation passed:

1. `/home/emb/project/zephyrproject/.venv/bin/python -m py_compile applocation/NeuroLink/neuro_cli/src/neuro_cli.py applocation/NeuroLink/neuro_cli/tests/test_neuro_cli.py`
2. `/home/emb/project/zephyrproject/.venv/bin/python -m pytest applocation/NeuroLink/neuro_cli/tests/test_neuro_cli.py -q` => `81 passed`
3. `/home/emb/project/zephyrproject/.venv/bin/python -m pytest applocation/NeuroLink/neuro_cli/tests/test_neuro_cli.py applocation/NeuroLink/neuro_cli/tests/test_invoke_neuro_cli.py -q` => `90 passed`
4. `/home/emb/project/zephyrproject/.venv/bin/python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan setup-linux`
5. `git -C applocation/NeuroLink diff --check`

No setup script behavior, firmware behavior, hardware state, or release identity
changed. `RELEASE_TARGET` remains `1.1.7`.

### EXEC-186 Zero-Host Windows Setup Reference and Workflow Plan

`EXEC-186` expanded the canonical Windows setup reference from a placeholder
into a PowerShell-first zero-host bootstrap guide. The reference now covers
supported host shape, operator-approved `winget` or manual installer choices,
repository-local `.venv` creation, PowerShell execution policy boundaries,
Zephyr and Neuro CLI Python requirements, `west update`, Zephyr SDK selection
from `zephyr/SDK_VERSION`, strict PowerShell validation, build/test workflow
discovery, WSL boundaries, and failure recovery.

Added `workflow plan setup-windows` as a non-executing structured plan. It is
Windows/WSL scoped, requires network access, does not require hardware, serial,
or router, and is non-destructive. Its command list covers installer review,
`.venv` creation, Python dependency installation, west module update, SDK version
inspection/export, PowerShell validation, system diagnostics, and follow-on
workflow plan discovery for Unit build, CLI tests, app build, and preflight.

Updated workflow references so Agents see `workflow plan setup-windows` beside
`setup-linux` before running validation commands. Added regressions that validate
parser support, structured metadata, command content, failure statuses, and
canonical Windows setup reference coverage.

Validation passed:

1. `/home/emb/project/zephyrproject/.venv/bin/python -m py_compile applocation/NeuroLink/neuro_cli/src/neuro_cli.py applocation/NeuroLink/neuro_cli/tests/test_neuro_cli.py`
2. `/home/emb/project/zephyrproject/.venv/bin/python -m pytest applocation/NeuroLink/neuro_cli/tests/test_neuro_cli.py -q` => `84 passed`
3. `/home/emb/project/zephyrproject/.venv/bin/python -m pytest applocation/NeuroLink/neuro_cli/tests/test_neuro_cli.py applocation/NeuroLink/neuro_cli/tests/test_invoke_neuro_cli.py -q` => `93 passed`
4. `/home/emb/project/zephyrproject/.venv/bin/python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan setup-windows`
5. `git -C applocation/NeuroLink diff --check`

PowerShell parser validation was not run in this Linux environment because
`pwsh` is not installed (`command -v pwsh` returned exit code 1). This is a
recorded validation gap for the Windows slice, not a claimed Windows host pass.

No setup script behavior, firmware behavior, hardware state, or release identity
changed. `RELEASE_TARGET` remains `1.1.7`.
