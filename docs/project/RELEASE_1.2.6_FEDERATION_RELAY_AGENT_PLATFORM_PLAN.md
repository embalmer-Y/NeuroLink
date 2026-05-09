# Release 1.2.6 Federation Relay And Agent Platform Plan

## 1. Overview

Release 1.2.6 advanced NeuroLink from the closed release-1.2.5 multimodal
Agent runtime and governance baseline into the next HLD-critical slice:
governed multi-Core federation, Gateway Unit relay visibility, and stronger
Agent Tool/Skill/MCP execution quality.

The release focuses on the remaining HLD requirements that turn NeuroLink from
a strong single-Core orchestrator into a distributed intelligent control
network:

1. Core-to-Core topology sync and minimum trust metadata;
2. delegated execution planning across Core ownership boundaries;
3. Gateway Unit relay route contracts and relay-visible Unit attachment;
4. hardware-agnostic Unit capability descriptors for multi-board planning;
5. higher-quality Agent Tool, Skill, and MCP governance that remains Core-owned;
6. deterministic closure evidence for federation, relay, Agent platform, and
   inherited release-1.2.5 regressions.

Release 1.2.6 did not freeze the design around the current validation board.
Board-specific behavior stays behind Unit port providers or app-owned
devicetree/driver code. Core planning consumes capability descriptors rather
than board names, lab IP addresses, Wi-Fi assumptions, SD-card paths, or
PSRAM-specific implementation details.

## 1A. Closure Status

Release-1.2.6 is now closed. The final local deterministic plus bounded live
closure bundle is recorded under
`smoke-evidence/release-1.2.6-closure-20260509T174539Z/`, the focused
regression surface is green across release-1.2.5 Agent closure,
release-1.2.4 lifecycle/event-service, federation/relay, and hardware
compatibility, and canonical release identity has now been promoted to
`RELEASE_TARGET = "1.2.6"`.

## 2. Two-Minor-Release Burn-Down To 2.0.0

The overall HLD completion estimate after release-1.2.5 is about 88%. The goal
is to complete the remaining HLD development surface across two development
releases and then enter release-2.0.0 stabilization.

1. `release-1.2.6`: Core-to-Core federation, Gateway Unit relay baseline,
   hardware-agnostic capability descriptors, and Agent Tool/Skill/MCP platform
   quality.
   - Target HLD completion: about 94%.
   - Main outcome: topology sync, delegated execution contracts, relay route
     evidence, capability-based hardware planning, and governed Agent tool
     surfaces are executable through deterministic tests plus bounded optional
     live smoke.
2. `release-1.2.7`: productization hardening and release-2.0.0 readiness.
   - Target HLD completion: about 98%.
   - Main outcome: multi-board build/deploy matrix, resource budget governance,
     release/rollback policy hardening, signing enforcement, observability,
     acceptance runbooks, and full regression/hardware evidence are ready for
     release-2.0.0 promotion.

Release-2.0.0 should be a stabilization, compatibility, acceptance, and version
promotion release: API/contract freeze, migration notes, final documentation,
full hardware evidence rerun, and final release identity promotion.

## 3. HLD And LLD Gap Map

| HLD / LLD surface | Release-1.2.5 status | Release-1.2.6 target |
| --- | --- | --- |
| HLD Core-to-Core federation | HLD/LLD module boundary exists, but no executable topology sync or delegated execution contract is closed. | Add deterministic topology registry, peer descriptors, trust scope, stale-peer handling, delegated execution proposal/result records, and audit evidence. |
| HLD Gateway Unit relay | Gateway/relay is an HLD role and Unit capability idea, but production relay route evidence is not closed. | Add relay-visible Unit capability descriptors, direct/relay/no-route planning, relay mismatch rejection, and route evidence without hardware lock-in. |
| HLD multi-Core access to remote Units | Single-Core app lifecycle and event service are closed; remote Unit access through another Core is not. | Add policy-bounded delegated execution planning and failure semantics for unreachable, untrusted, or unauthorized remote Unit operations. |
| HLD policy before reachability | Local policy, approval, lease, and audit gates are closed for release-1.2.5 Agent paths. | Extend policy/audit evidence to federation topology ingest, route selection, delegated execution, and relay proposals. |
| HLD MCP and Skills | Tool/Skill/MCP closure is descriptor-only/read-only and model tools remain Core-owned. | Add Skill ground-rule validation, dynamic workflow/tool discovery evidence, and optional MCP bridge modes that cannot bypass Core policy. |
| HLD hardware diversity | Current hardware validation centers on the connected ESP32-S3 path with native/local regressions. | Promote capability-driven hardware planning: arch, ABI, storage class, transport set, LLEXT compatibility, signing support, and resource budget. |
| AI Core LLD federation module | `neurolink_core.federation` is reserved in the LLD module inventory. | Make the release-1.2.6 federation lifecycle executable and covered by deterministic UT anchors. |
| Unit LLD Gateway/Forward layer | Gateway/forward layer is an HLD/LLD role but not a closed runtime feature. | Add abstract relay capability and route evidence while keeping board-specific work in port providers. |
| Release-2.0.0 readiness | release-1.2.5 closes Agent runtime quality, but productization hardening remains. | Leave multi-board matrix closure, signing enforcement, resource governance, observability, and API freeze for release-1.2.7/2.0.0. |

## 4. Fixed Decisions

1. Release identity stayed at `1.2.5` during implementation and is now
   promoted to `1.2.6` after release-1.2.6 closure evidence passed and
   promotion was explicitly approved.
2. Federation and relay planning must be deterministic and local-testable first.
   Real multi-host and real-board relay smoke are valuable closure evidence, but
   they must remain bounded and optional during early implementation.
3. Core contracts use capability descriptors, route evidence, and policy scopes;
   they must not rely on current lab hardware names, network addresses, Wi-Fi
   details, SD-card paths, or board-specific memory names.
4. Unit framework code owns lifecycle, policy, leases, update, event, relay, and
   capability reporting. Demo apps own hardware-specific GPIO/I2C/SPI/UART/ADC,
   PWM, sensor, and actuator driver access.
5. Provider-backed Agents may propose federation, relay, Tool, Skill, or MCP
   actions but must not execute side effects directly.
6. The Core policy, approval, lease, and audit layers remain authoritative for
   all local, delegated, relayed, Tool, Skill, MCP, and Unit operations.
7. Hermes AI Agent and qwenpaw are external reference points for tool-calling
   quality, function schema discipline, planner feedback loops, and MCP UX only
   when their source or design documents are available. Release-1.2.6 must not
   depend on unavailable implementation details or copy external code.

## 5. Workstreams

### WS-1 Scope Lock And Documentation Baseline

1. Add this release plan.
2. Update README release notes so release-1.2.6 is the active implementation
   slice while release identity remains `1.2.5` during implementation, then
   mark it closed after promotion.
3. Add progress records for release-1.2.6 kickoff and later slices.
4. Extend AI Core and Unit LLDs with release-1.2.6 federation, relay,
   capability, Agent Tool/Skill/MCP, and hardware abstraction decisions before
   code paths are promoted.

### WS-2 Federation Contract And Topology Registry

1. Define Core identity, peer descriptor, topology advertisement, trust scope,
   freshness, and health summary records.
2. Add deterministic topology ingest and stale-peer rejection.
3. Record peer visibility and remote Unit summaries without copying full peer
   internal state.
4. Persist topology and route evidence for closure review.

### WS-3 Delegated Execution Planning

1. Add a delegated execution proposal contract covering source Core, target
   Core, requested Unit/resource, policy scope, lease expectations, timeout,
   cleanup hints, and audit correlation.
2. Add delegated execution result normalization for accepted, rejected, failed,
   timed-out, and policy-denied outcomes.
3. Keep local execution, delegated execution, and no-route rejection as explicit
   route outcomes.
4. Add deterministic tests for unauthorized, untrusted, stale, unreachable, and
   successful delegated planning paths.

### WS-4 Gateway Unit Relay And Capability Routing

1. Add relay capability descriptors for Units and Core route planning.
2. Add direct-route, relay-route, and no-route evidence with failure reasons.
3. Add relay mismatch rejection when a Unit, route, transport, or trust scope is
   incompatible.
4. Keep relay contracts transport-neutral so Wi-Fi, Ethernet, Thread, serial
   bridge, and future zenoh-pico transports can fit the same model.

### WS-5 Hardware-Agnostic Capability And Artifact Compatibility

1. Extend device/capability evidence with architecture, ABI, board family,
   LLEXT compatibility, storage class, network transport set, signing support,
   and resource budget.
2. Add cross-architecture artifact rejection before load or activate.
3. Add build-only or dry-run coverage for at least one non-current hardware
   profile before release-1.2.6 closes.
4. Defer full multi-board hardware matrix closure to release-1.2.7 while keeping
   the 1.2.6 contracts broad enough for it.

### WS-6 Agent Tool Skill MCP Platform Quality

1. Treat `ToolContract` as the authoritative Agent-facing execution manifest.
2. Convert Skill ground rules and workflow metadata into enforceable plan-quality
   checks before policy execution.
3. Reconcile Skill workflow metadata with the workflow catalog and tool manifest
   so Agents can discover valid operations without guessing.
4. Add optional MCP bridge modes only under Core governance:
   descriptor-only by default, read-only execution for safe query tools, and
   approval-required proposal mode for side-effecting operations.
5. Add provider-plan regressions for valid no-tool, valid read-only tool,
   invalid unavailable tool, invalid side-effect bypass, invalid ground-rule
   violation, and valid approval-required proposal.

### WS-7 Approval Audit And Closure

1. Extend closure-summary to report federation, relay, capability/hardware,
   Tool/Skill/MCP quality, and inherited regression gates.
2. Update English and Chinese AI Core runbooks with release-1.2.6 setup, smoke,
   deterministic validation, optional live federation/relay smoke, and fallback
   paths.
3. Run focused regressions across release-1.2.5 Agent closure, release-1.2.4 app
   lifecycle/event service, Core federation, relay planning, and hardware
   capability compatibility.
4. Generate a release-1.2.7 plan before release-1.2.6 identity promotion so no
   remaining HLD work becomes implicit debt.

## 6. Validation Gates

Release-1.2.6 cannot close until all gates pass:

1. Documentation gate
   - release plan, README, progress records, AI Core LLD, Unit LLD, and
     English/Chinese runbooks agree on release-1.2.6 scope and status.
2. Federation gate
   - deterministic tests cover topology ingest, peer freshness, trust scope,
     remote Unit summary, delegated proposal, delegated result, and audit
     evidence.
3. Relay gate
   - deterministic tests cover direct route, relay route, no-route rejection,
     relay capability mismatch, route failure evidence, and relay-visible Unit
     attachment metadata.
4. Hardware abstraction gate
   - shared Unit framework and Core contracts remain capability-driven and do
     not encode current test-board Wi-Fi, SD-card, PSRAM, or lab IP assumptions.
5. Artifact compatibility gate
   - incompatible architecture, ABI, board family, storage class, or LLEXT
     capability is rejected before app load or activation.
6. Tool/Skill/MCP quality gate
   - Skill ground rules are enforced; provider plans can only select available
     tools; side-effecting proposals require approval; MCP cannot bypass Core
     policy.
7. Regression gate
   - release-1.2.5 Agent runtime closure tests and release-1.2.4 app
     lifecycle/event-service regressions remain green.
8. Closure-summary gate
   - release-1.2.6 closure summary reports all validation gates passing with no
     failed gate ids.

## 7. Initial Implementation Order

1. Add the release plan and README/progress kickoff alignment.
2. Add AI Core LLD and Unit LLD release-1.2.6 contract deltas.
3. Add deterministic Core federation data structures and topology registry tests.
4. Add delegated execution planning contracts and tests.
5. Add Gateway relay/capability route planning contracts and tests.
6. Add hardware capability and artifact compatibility checks.
7. Add Skill ground-rule validation and dynamic Tool/Skill discovery evidence.
8. Add optional governed MCP bridge modes if deterministic policy tests can prove
   they cannot bypass Core gates.
9. Update runbooks, closure-summary gates, and release-1.2.7 plan.

## 8. Out Of Scope For Release 1.2.6

1. Full multi-board hardware farm closure.
2. Full cryptographic app signing enforcement on every target.
3. Release-2.0.0 API freeze.
4. Native omni speech output as a required closure gate.
5. Production-scale Core federation with external PKI or cloud control plane.
6. Complete release/rollback productization hardening.

## 9. Initial Progress Estimate

1. Release-1.2.6 implementation progress: about 5% after kickoff documentation.
2. Release-1.2.6 closure progress: 0% until validation gates begin passing.
3. Overall HLD completion at release start: about 88%.
4. Overall HLD completion target at release close: about 94%.