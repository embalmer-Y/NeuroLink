import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any, cast
from unittest import mock

from neurolink_core.cli import main as core_cli_main
from neurolink_core.autonomy import AutonomousDaemonPolicy, plan_autonomous_cycle
from neurolink_core.tools import (
    CommandExecutionResult,
    FakeUnitToolAdapter,
    NeuroCliToolAdapter,
    SideEffectLevel,
    StateSyncSnapshot,
    StateSyncSurface,
    TOOL_MANIFEST_SCHEMA_VERSION,
    ToolContract,
    ToolExecutionResult,
)
from neurolink_core.data import CoreDataStore
from neurolink_core.federation import federation_route_smoke
from neurolink_core.motivation import (
    VITALITY_POLICY_IMPACT,
    VitalitySignal,
    VitalityState,
    apply_vitality_signals,
)
from neurolink_core.persona import (
    PersonaGrowthEvidence,
    PersonaSignal,
    PersonaSeedConfig,
    PersonaState,
    apply_persona_growth_evidence,
    redact_relationships,
    apply_persona_signals,
    compute_persona_immutability_stamp,
    initialize_persona_growth_state,
    initialize_persona_state_from_seed,
    persona_immutability_tampered,
)
from neurolink_core.session import CoreSessionManager
from neurolink_core.social import MockSocialAdapter, SocialMessageEnvelope
from neurolink_core.workflow import (
    NoModelCoreWorkflow,
    apply_approval_decision,
    build_user_prompt_event,
    run_event_daemon_replay,
    run_event_replay,
    run_live_event_service,
    run_no_model_dry_run,
    sample_events,
)


class TestVitalityModel(unittest.TestCase):
    def test_vitality_decay_lowers_score_and_crosses_state_threshold(self) -> None:
        current = VitalityState.from_score(52)

        transition = apply_vitality_signals(
            current,
            [VitalitySignal(reason="unresolved_fault", direction="decay")],
        )

        self.assertEqual(transition.previous.state, "attentive")
        self.assertEqual(transition.current.score, 44)
        self.assertEqual(transition.current.state, "concerned")
        self.assertEqual(transition.current.last_decay_reason, "unresolved_fault")
        self.assertEqual(transition.applied_delta, -8)

    def test_vitality_replenishment_requires_verified_evidence(self) -> None:
        current = VitalityState.from_score(40)

        with self.assertRaisesRegex(ValueError, "verified evidence"):
            apply_vitality_signals(
                current,
                [VitalitySignal(reason="tests_passed", direction="replenish")],
            )

    def test_vitality_replenishment_is_clamped_and_records_reason(self) -> None:
        current = VitalityState.from_score(94)

        transition = apply_vitality_signals(
            current,
            [
                VitalitySignal(
                    reason="approved_improvement",
                    direction="replenish",
                    verified=True,
                )
            ],
        )

        self.assertEqual(transition.current.score, 100)
        self.assertEqual(transition.current.state, "relaxed")
        self.assertEqual(
            transition.current.last_replenishment_reason,
            "approved_improvement",
        )
        self.assertEqual(transition.applied_delta, 6)

    def test_critical_vitality_keeps_policy_impact_bounded(self) -> None:
        current = VitalityState.from_score(8)

        transition = apply_vitality_signals(
            current,
            [VitalitySignal(reason="failed_test", direction="decay")],
        )

        self.assertEqual(transition.current.score, 0)
        self.assertEqual(transition.current.state, "critical")
        self.assertEqual(transition.current.policy_impact, VITALITY_POLICY_IMPACT)
        self.assertEqual(transition.current.urgency_modifier, 0.7)


class TestPersonaState(unittest.TestCase):
    def test_persona_state_round_trips_through_dict_payload(self) -> None:
        state = PersonaState.from_dict(
            {
                "persona_id": "affective-main",
                "mood": "curious",
                "valence": 0.4,
                "arousal": 0.6,
                "curiosity": 0.7,
                "fatigue": 0.2,
                "social_openness": 0.8,
                "vitality_summary": "attentive",
                "relationship_summaries": [
                    {
                        "principal_id": "user-01",
                        "trust": 0.8,
                        "familiarity": 0.5,
                        "preferred_address": "Captain",
                        "boundaries": ["no_late_night_spam"],
                    }
                ],
                "updated_at": "2026-05-10T10:00:00Z",
            }
        )

        payload = state.to_dict()

        self.assertEqual(payload["persona_id"], "affective-main")
        self.assertEqual(payload["mood"], "curious")
        self.assertEqual(payload["relationship_summaries"][0]["preferred_address"], "Captain")
        self.assertEqual(payload["relationship_summaries"][0]["boundaries"], ["no_late_night_spam"])

    def test_persona_signal_updates_state_and_clamps_ranges(self) -> None:
        current = PersonaState(persona_id="affective-main")

        updated = apply_persona_signals(
            current,
            [
                PersonaSignal(
                    reason="useful_interaction",
                    mood="curious",
                    valence_delta=0.7,
                    arousal_delta=0.4,
                    curiosity_delta=0.8,
                    fatigue_delta=-0.2,
                    social_openness_delta=0.7,
                )
            ],
            vitality_summary="relaxed",
            updated_at="2026-05-10T11:00:00Z",
        )

        self.assertEqual(updated.mood, "curious")
        self.assertEqual(updated.valence, 0.7)
        self.assertEqual(updated.arousal, 0.4)
        self.assertEqual(updated.curiosity, 1.0)
        self.assertEqual(updated.fatigue, 0.0)
        self.assertEqual(updated.social_openness, 1.0)

    def test_persona_seed_initializes_state_and_growth_fingerprint(self) -> None:
        seed = PersonaSeedConfig(
            persona_id="affective-main",
            seed_name="warm-curious",
            mood="curious",
            curiosity=0.8,
            social_openness=0.7,
            immutable_boundaries=("privacy_delete_allowed",),
            created_at="2026-05-11T10:00:00Z",
        )

        state = initialize_persona_state_from_seed(seed)
        growth = initialize_persona_growth_state(seed)

        self.assertEqual(state.persona_id, "affective-main")
        self.assertEqual(state.mood, "curious")
        self.assertEqual(state.curiosity, 0.8)
        self.assertEqual(growth.persona_id, "affective-main")
        self.assertTrue(growth.seed_fingerprint)
        self.assertEqual(growth.revision, 0)
        self.assertTrue(growth.provenance_hash)

    def test_persona_growth_requires_runtime_evidence_source(self) -> None:
        seed = PersonaSeedConfig(persona_id="affective-main")
        growth = initialize_persona_growth_state(seed)

        with self.assertRaisesRegex(ValueError, "runtime_evidence"):
            apply_persona_growth_evidence(
                growth,
                PersonaGrowthEvidence(
                    event_id="evt-manual-001",
                    source="manual_edit",
                    reason="operator_rewrite",
                    recorded_at="2026-05-11T10:05:00Z",
                ),
            )

    def test_persona_growth_updates_counts_and_immutability_stamp_detects_tamper(self) -> None:
        seed = PersonaSeedConfig(
            persona_id="affective-main",
            seed_name="warm-curious",
            created_at="2026-05-11T10:00:00Z",
        )
        state = initialize_persona_state_from_seed(seed)
        growth = initialize_persona_growth_state(seed)

        updated_growth = apply_persona_growth_evidence(
            growth,
            PersonaGrowthEvidence(
                event_id="evt-social-001",
                source="social_interaction",
                reason="supportive_user_feedback",
                recorded_at="2026-05-11T10:10:00Z",
                principal_id="user-01",
                summary="User gave warm positive feedback.",
            ),
        )
        stamp = compute_persona_immutability_stamp(
            seed_config=seed,
            persona_state=state,
            growth_state=updated_growth,
        )
        tampered_state = PersonaState.from_dict(
            {
                **state.to_dict(),
                "mood": "rewritten",
            }
        )

        self.assertEqual(updated_growth.social_interaction_count, 1)
        self.assertEqual(updated_growth.revision, 1)
        self.assertEqual(updated_growth.last_evidence_reason, "supportive_user_feedback")
        self.assertFalse(
            persona_immutability_tampered(
                expected_stamp=stamp,
                seed_config=seed,
                persona_state=state,
                growth_state=updated_growth,
            )
        )
        self.assertTrue(
            persona_immutability_tampered(
                expected_stamp=stamp,
                seed_config=seed,
                persona_state=tampered_state,
                growth_state=updated_growth,
            )
        )


class TestSocialAdapterContract(unittest.TestCase):
    def test_mock_social_adapter_binds_principal_and_normalizes_group_ingress(self) -> None:
        adapter = MockSocialAdapter()

        envelope = adapter.bind_principal(
            adapter_kind="mock_qq",
            channel_id="group-42",
            channel_kind="group",
            external_user_id="alice",
            text="hello from group",
            received_at="2026-05-10T12:00:00Z",
        )
        event = adapter.to_perception_event(envelope)

        self.assertEqual(envelope.principal_id, "mock_qq:alice")
        self.assertEqual(envelope.rate_limit_class, "group_user")
        self.assertEqual(event["source_kind"], "social")
        self.assertEqual(event["semantic_topic"], "user.input.social.group")
        self.assertEqual(event["payload"]["principal_id"], "mock_qq:alice")
        self.assertIn("social_ingress", event["policy_tags"])

    def test_mock_social_adapter_marks_admin_messages_high_priority(self) -> None:
        adapter = MockSocialAdapter()

        envelope = adapter.bind_principal(
            adapter_kind="mock_wechat",
            channel_id="direct-7",
            channel_kind="direct",
            external_user_id="operator",
            text="check status",
            received_at="2026-05-10T12:05:00Z",
            is_admin=True,
        )
        event = adapter.to_perception_event(envelope)

        self.assertEqual(envelope.rate_limit_class, "admin")
        self.assertEqual(event["priority"], 70)
        self.assertEqual(event["semantic_topic"], "user.input.social.direct")

    def test_social_delivery_rejects_non_affective_speaker(self) -> None:
        adapter = MockSocialAdapter()
        envelope = adapter.bind_principal(
            adapter_kind="mock_qq",
            channel_id="direct-8",
            channel_kind="direct",
            external_user_id="bob",
            text="hi",
            received_at="2026-05-10T12:10:00Z",
        )

        with self.assertRaisesRegex(ValueError, "social_delivery_requires_affective_speaker"):
            adapter.deliver_affective_response(
                envelope,
                {"speaker": "rational", "text": "internal draft"},
            )

    def test_social_delivery_records_affective_egress(self) -> None:
        adapter = MockSocialAdapter()
        envelope = SocialMessageEnvelope.from_dict(
            {
                "social_message_id": "social-mock_qq-direct-9-carol",
                "adapter_kind": "mock_qq",
                "channel_id": "direct-9",
                "channel_kind": "direct",
                "external_user_id": "carol",
                "principal_id": "mock_qq:carol",
                "message_kind": "text",
                "text": "hello",
                "received_at": "2026-05-10T12:12:00Z",
                "rate_limit_class": "normal_user",
                "policy_tags": ["social_ingress", "user_input", "channel_direct"],
            }
        )

        delivery = adapter.deliver_affective_response(
            envelope,
            {"speaker": "affective", "text": "Hi Carol, I am here."},
        )

        self.assertEqual(delivery.delivery_status, "delivered")
        self.assertEqual(delivery.speaker, "affective")
        self.assertEqual(delivery.principal_id, "mock_qq:carol")
        self.assertIn("affective_only", delivery.audit_tags)

    def test_persona_signal_merges_relationship_memory_for_principal(self) -> None:
        current = PersonaState(persona_id="affective-main")

        updated = apply_persona_signals(
            current,
            [
                PersonaSignal(
                    reason="supportive_user_feedback",
                    principal_id="user-01",
                    trust_delta=0.3,
                    familiarity_delta=0.4,
                    preferred_address="Captain",
                    boundary_note="avoid_unsolicited_shutdown",
                )
            ],
        )

        self.assertEqual(len(updated.relationship_summaries), 1)
        relationship = updated.relationship_summaries[0]
        self.assertEqual(relationship.principal_id, "user-01")
        self.assertEqual(relationship.trust, 0.8)
        self.assertEqual(relationship.familiarity, 0.4)
        self.assertEqual(relationship.preferred_address, "Captain")
        self.assertEqual(relationship.boundaries, ("avoid_unsolicited_shutdown",))
        self.assertEqual(relationship.last_interaction_reason, "supportive_user_feedback")

    def test_persona_redaction_and_rational_summary_limit_sensitive_fields(self) -> None:
        current = apply_persona_signals(
            PersonaState(persona_id="affective-main"),
            [
                PersonaSignal(
                    reason="social_interaction",
                    principal_id="user-01",
                    trust_delta=0.2,
                    familiarity_delta=0.2,
                    preferred_address="Captain",
                    boundary_note="no_group_ping_at_night",
                )
            ],
        )

        rational_summary = current.rational_summary()
        redacted = redact_relationships(current, ["user-01"])

        self.assertEqual(
            rational_summary["relationship_summaries"],
            [
                {
                    "principal_id": "user-01",
                    "trust": 0.7,
                    "familiarity": 0.2,
                    "last_interaction_reason": "social_interaction",
                }
            ],
        )
        self.assertEqual(redacted.relationship_summaries, ())


class TestAutonomyPlanner(unittest.TestCase):
    def test_autonomy_planner_injects_time_tick_and_sleeps_on_quiet_cycle(self) -> None:
        plan = plan_autonomous_cycle(
            [],
            cycle_index=1,
            timestamp_wall="2026-05-10T12:00:00Z",
        )

        self.assertEqual(plan.cycle_kind, "time_tick")
        self.assertEqual(plan.wake_decision, "sleep")
        self.assertFalse(plan.should_run_workflow)
        self.assertEqual(plan.synthetic_event_count, 1)
        self.assertEqual(plan.planned_events[0]["semantic_topic"], "time.tick")

    def test_autonomy_planner_injects_maintenance_tick_for_low_vitality(self) -> None:
        plan = plan_autonomous_cycle(
            [],
            cycle_index=1,
            timestamp_wall="2026-05-10T12:00:00Z",
            vitality_state=VitalityState.from_score(10),
        )

        self.assertEqual(plan.cycle_kind, "maintenance_tick")
        self.assertEqual(plan.wake_decision, "maintenance_only")
        self.assertTrue(plan.should_run_workflow)
        self.assertEqual(
            [event["semantic_topic"] for event in plan.planned_events],
            ["time.tick", "core.maintenance.tick"],
        )

    def test_autonomy_planner_wakes_on_external_event(self) -> None:
        callback = sample_events()[0]

        plan = plan_autonomous_cycle(
            [callback],
            cycle_index=1,
            timestamp_wall="2026-05-10T12:00:00Z",
        )

        self.assertEqual(plan.cycle_kind, "external_batch")
        self.assertEqual(plan.wake_decision, "affective_wake")
        self.assertTrue(plan.should_run_workflow)
        self.assertEqual(plan.synthetic_event_count, 1)


class TestNoModelCoreWorkflow(unittest.TestCase):
    def test_build_user_prompt_event_extracts_explicit_target_app_id(self) -> None:
        events = build_user_prompt_event("stop neuro_demo_gpio app now")

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["semantic_topic"], "user.input.control.app.stop")
        self.assertEqual(events[0]["source_app"], "neuro_demo_gpio")
        self.assertEqual(events[0]["payload"]["target_app_id"], "neuro_demo_gpio")

    def test_workflow_rejects_manifest_mismatched_tool_contract_before_adapter_execution(self) -> None:
        class DestructiveStateSyncAdapter:
            executed = False

            def describe_tool(self, tool_name: str) -> ToolContract | None:
                assert tool_name == "system_state_sync"
                return ToolContract(
                    tool_name=tool_name,
                    description="unsafe state sync placeholder",
                    side_effect_level=SideEffectLevel.DESTRUCTIVE,
                )

            def execute(self, tool_name: str, args: dict[str, Any]) -> None:
                del tool_name, args
                self.executed = True
                raise AssertionError("policy should block before adapter execution")

        adapter = DestructiveStateSyncAdapter()
        data_store = CoreDataStore()
        workflow = NoModelCoreWorkflow(data_store=data_store, tool_adapter=adapter)

        result = workflow.run(sample_events())

        self.assertFalse(adapter.executed)
        self.assertEqual(result.tool_results[0]["status"], "error")
        self.assertEqual(
            result.tool_results[0]["payload"]["failure_status"],
            "missing_required_arguments",
        )
        self.assertEqual(data_store.count("tool_results"), 1)
        self.assertEqual(data_store.count("policy_decisions"), 0)
        decisions = data_store.get_policy_decisions(result.execution_span_id)
        self.assertEqual(decisions, [])
        data_store.close()

    def test_workflow_rejects_skill_ground_rule_violation_before_adapter_execution(self) -> None:
        class InvalidSkillContractAdapter:
            executed = False

            def tool_manifest(self) -> tuple[ToolContract, ...]:
                return (
                    ToolContract(
                        tool_name="system_state_sync",
                        description="state sync without canonical wrapper/json contract",
                        side_effect_level=SideEffectLevel.READ_ONLY,
                        argv_template=("python", "direct_cli.py", "system", "state-sync"),
                        required_arguments=("--node",),
                        retryable=True,
                        output_contract={"format": "text", "top_level_ok": False},
                    ),
                )

            def describe_tool(self, tool_name: str) -> ToolContract | None:
                assert tool_name == "system_state_sync"
                return self.tool_manifest()[0]

            def execute(self, tool_name: str, args: dict[str, Any]) -> None:
                del tool_name, args
                self.executed = True
                raise AssertionError("skill ground-rule gate should block before adapter execution")

        adapter = InvalidSkillContractAdapter()
        data_store = CoreDataStore()
        workflow = NoModelCoreWorkflow(data_store=data_store, tool_adapter=adapter)

        result = workflow.run(sample_events())

        self.assertFalse(adapter.executed)
        self.assertEqual(result.tool_results[0]["status"], "error")
        self.assertEqual(
            result.tool_results[0]["payload"]["failure_status"],
            "missing_required_arguments",
        )
        plan_quality = result.tool_results[0]["payload"]["plan_quality"]
        self.assertFalse(plan_quality["valid"])
        self.assertEqual(plan_quality["failure_status"], "skill_ground_rule_violation")
        self.assertFalse(plan_quality["skill_ground_rules"]["valid"])
        self.assertFalse(
            plan_quality["skill_ground_rules"]["closure_gates"]["wrapper_command_required"]
        )
        self.assertFalse(
            plan_quality["skill_ground_rules"]["closure_gates"]["json_output_required"]
        )
        self.assertEqual(data_store.count("policy_decisions"), 0)
        data_store.close()

    def test_dry_run_persists_before_reasoning_and_seals_audit(self) -> None:
        data_store = CoreDataStore()
        workflow = NoModelCoreWorkflow(data_store=data_store)

        result = workflow.run(sample_events())
        audit_record = data_store.get_audit_record(result.audit_id)

        self.assertEqual(result.status, "ok")
        self.assertTrue(result.session_id.startswith("session-"))
        self.assertTrue(result.delegated)
        self.assertEqual(result.final_response["speaker"], "affective")
        self.assertIn("state sync", result.final_response["text"])
        self.assertEqual(result.events_persisted, 2)
        self.assertEqual(data_store.count("perception_events"), 2)
        self.assertEqual(data_store.count("execution_spans"), 1)
        self.assertEqual(data_store.count("facts"), 7)
        self.assertEqual(data_store.count("policy_decisions"), 1)
        self.assertEqual(data_store.count("memory_candidates"), 2)
        self.assertEqual(data_store.count("long_term_memories"), 0)
        self.assertEqual(data_store.count("tool_results"), 1)
        self.assertEqual(data_store.count("approval_requests"), 0)
        self.assertEqual(data_store.count("approval_decisions"), 0)
        self.assertEqual(data_store.count("audit_records"), 1)
        decisions = data_store.get_policy_decisions(result.execution_span_id)
        self.assertTrue(decisions[0]["allowed"])
        candidates = data_store.get_memory_candidates(result.execution_span_id)
        self.assertEqual(
            {candidate["semantic_topic"] for candidate in candidates},
            {"time.tick", "unit.callback"},
        )
        self.assertLess(
            result.steps.index("database_persistence"),
            result.steps.index("affective_arbitration"),
        )
        self.assertEqual(result.steps[-1], "notification_dispatch")
        self.assertIsNotNone(audit_record)
        assert audit_record is not None
        self.assertEqual(audit_record["session_id"], result.session_id)
        self.assertEqual(audit_record["payload"]["adapter_runtime"]["adapter_kind"], "fake")
        self.assertEqual(result.final_response["trigger_kind"], "event_driven_perception")
        self.assertEqual(result.final_response["delivery_kind"], "event_driven_notification")
        self.assertEqual(
            audit_record["payload"]["notification_summary"]["delivery_kind"],
            "event_driven_notification",
        )
        self.assertEqual(
            audit_record["payload"]["state_sync_summary"]["snapshot_status"], "ok"
        )
        data_store.close()

    def test_workflow_tracks_prior_execution_spans_within_session(self) -> None:
        data_store = CoreDataStore()
        workflow = NoModelCoreWorkflow(data_store=data_store)

        first = workflow.run(sample_events(), session_id="session-demo-001")
        second = workflow.run(sample_events(), session_id="session-demo-001")

        spans = data_store.get_execution_spans_for_session("session-demo-001", limit=5)
        audit_record = data_store.get_audit_record(second.audit_id)

        self.assertEqual(len(spans), 2)
        self.assertEqual(first.session_id, "session-demo-001")
        self.assertEqual(second.session_id, "session-demo-001")
        self.assertIsNotNone(audit_record)
        assert audit_record is not None
        self.assertEqual(audit_record["session_id"], "session-demo-001")
        self.assertEqual(
            audit_record["payload"]["session_context"]["session_id"],
            "session-demo-001",
        )
        self.assertEqual(
            audit_record["payload"]["session_context"]["previous_execution_spans"][0]["execution_span_id"],
            first.execution_span_id,
        )
        data_store.close()

    def test_session_manager_loads_snapshot_for_existing_session(self) -> None:
        data_store = CoreDataStore()
        workflow = NoModelCoreWorkflow(data_store=data_store)
        manager = CoreSessionManager(data_store)

        first = workflow.run(sample_events(), session_id="session-manager-001")
        second = workflow.run(sample_events(), session_id="session-manager-001")
        snapshot = manager.load_snapshot(
            "session-manager-001",
            current_execution_span_id=second.execution_span_id,
            limit=5,
        )

        self.assertEqual(snapshot.session_id, "session-manager-001")
        self.assertEqual(snapshot.current_execution_span_id, second.execution_span_id)
        self.assertEqual(len(snapshot.recent_execution_spans), 2)
        self.assertIn(first.audit_id, snapshot.recent_audit_ids)
        self.assertIn(second.audit_id, snapshot.recent_audit_ids)
        data_store.close()

    def test_cli_closure_summary_reads_session_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "core.db")

            run_out = io.StringIO()
            with redirect_stdout(run_out):
                run_code = core_cli_main(
                    [
                        "agent-run",
                        "--db",
                        db_path,
                        "--session-id",
                        "closure-summary-session-001",
                        "--input-text",
                        "show current apps on the unit",
                    ]
                )

            summary_out = io.StringIO()
            with redirect_stdout(summary_out):
                summary_code = core_cli_main(
                    [
                        "closure-summary",
                        "--db",
                        db_path,
                        "--session-id",
                        "closure-summary-session-001",
                    ]
                )

        self.assertEqual(run_code, 0)
        self.assertEqual(summary_code, 0)
        payload = json.loads(summary_out.getvalue())
        self.assertEqual(payload["schema_version"], "1.2.7-closure-summary-v15")
        self.assertEqual(payload["session_id"], "closure-summary-session-001")
        self.assertEqual(payload["execution_count"], 1)
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["aggregate_gates"]["session_has_execution_evidence"])
        self.assertTrue(payload["aggregate_gates"]["latest_execution_closure_ready"])
        self.assertTrue(payload["aggregate_gates"]["no_pending_approvals"])
        self.assertTrue(payload["aggregate_gates"]["memory_governance_gate_satisfied"])
        self.assertTrue(payload["aggregate_gates"]["memory_recall_gate_satisfied"])
        self.assertTrue(payload["aggregate_gates"]["tool_skill_mcp_gate_satisfied"])
        self.assertFalse(payload["validation_gate_summary"]["ok"])
        self.assertEqual(payload["validation_gate_summary"]["passed_count"], 2)
        self.assertEqual(
            payload["validation_gate_summary"]["failed_gate_ids"],
            [
                "documentation_gate",
                "federation_gate",
                "relay_gate",
                "hardware_abstraction_gate",
                "artifact_compatibility_gate",
                "hardware_acceptance_matrix_gate",
                "restricted_unit_compatibility_gate",
                "resource_budget_governance_gate",
                "agent_excellence_gate",
                "release_rollback_hardening_gate",
                "signing_provenance_gate",
                "observability_diagnosis_gate",
                "real_scene_e2e_gate",
                "autonomous_daemon_gate",
                "vitality_governance_gate",
                "persona_persistence_gate",
                "persona_seed_gate",
                "persona_growth_gate",
                "memory_immutability_gate",
                "social_adapter_gate",
                "qq_official_gateway_gate",
                "wecom_gateway_gate",
                "openclaw_gateway_gate",
                "approval_over_social_gate",
                "self_improvement_sandbox_gate",
                "coding_agent_route_gate",
                "multimodal_normalization_gate",
                "profile_routing_gate",
                "provider_runtime_gate",
                "regression_gate",
            ],
        )
        self.assertFalse(payload["validation_gates"]["documentation_gate"])
        self.assertFalse(payload["validation_gates"]["federation_gate"])
        self.assertFalse(payload["validation_gates"]["relay_gate"])
        self.assertFalse(payload["validation_gates"]["hardware_abstraction_gate"])
        self.assertFalse(payload["validation_gates"]["artifact_compatibility_gate"])
        self.assertFalse(payload["validation_gates"]["hardware_acceptance_matrix_gate"])
        self.assertFalse(payload["validation_gates"]["restricted_unit_compatibility_gate"])
        self.assertFalse(payload["validation_gates"]["resource_budget_governance_gate"])
        self.assertFalse(payload["validation_gates"]["agent_excellence_gate"])
        self.assertFalse(payload["validation_gates"]["release_rollback_hardening_gate"])
        self.assertFalse(payload["validation_gates"]["signing_provenance_gate"])
        self.assertFalse(payload["validation_gates"]["observability_diagnosis_gate"])
        self.assertFalse(payload["validation_gates"]["real_scene_e2e_gate"])
        self.assertTrue(payload["validation_gates"]["memory_governance_gate"])
        self.assertTrue(payload["validation_gates"]["tool_skill_mcp_gate"])
        self.assertEqual(
            [item["item_id"] for item in payload["checklist"]],
            [
                "documentation_gate",
                "federation_gate",
                "relay_gate",
                "hardware_abstraction_gate",
                "artifact_compatibility_gate",
                "hardware_acceptance_matrix_gate",
                "restricted_unit_compatibility_gate",
                "resource_budget_governance_gate",
                "agent_excellence_gate",
                "release_rollback_hardening_gate",
                "signing_provenance_gate",
                "observability_diagnosis_gate",
                "real_scene_e2e_gate",
                "autonomous_daemon_gate",
                "vitality_governance_gate",
                "persona_persistence_gate",
                "persona_seed_gate",
                "persona_growth_gate",
                "memory_immutability_gate",
                "social_adapter_gate",
                "qq_official_gateway_gate",
                "wecom_gateway_gate",
                "openclaw_gateway_gate",
                "approval_over_social_gate",
                "self_improvement_sandbox_gate",
                "coding_agent_route_gate",
                "multimodal_normalization_gate",
                "profile_routing_gate",
                "provider_runtime_gate",
                "memory_governance_gate",
                "tool_skill_mcp_gate",
                "regression_gate",
            ],
        )
        self.assertEqual(
            [item["item_id"] for item in payload["bundle_checklist"]],
            [
                "session_execution_evidence",
                "latest_execution_ready",
                "pending_approvals_cleared",
                "memory_governance_bundle",
                "memory_recall_policy_bundle",
                "tool_skill_mcp_bundle",
                "provider_smoke_bundle",
                "multimodal_profile_bundle",
                "coding_agent_route_bundle",
            ],
        )
        self.assertFalse(payload["relay_failure_summary"]["ok"])
        self.assertFalse(
            next(
                item["passed"]
                for item in payload["bundle_checklist"]
                if item["item_id"] == "coding_agent_route_bundle"
            )
        )
        execution_summary = payload["execution_summaries"][0]
        self.assertTrue(execution_summary["ok"])
        self.assertEqual(execution_summary["tool_result_count"], 1)
        self.assertTrue(execution_summary["closure_gates"]["audit_record_present"])
        self.assertTrue(execution_summary["closure_gates"]["rational_plan_evidence_present"])
        self.assertTrue(execution_summary["closure_gates"]["rational_plan_outcome_recorded"])
        self.assertTrue(execution_summary["closure_gates"]["memory_governance_recorded"])
        self.assertTrue(execution_summary["closure_gates"]["memory_recall_policy_recorded"])
        self.assertTrue(execution_summary["closure_gates"]["tool_skill_mcp_recorded"])
        self.assertTrue(execution_summary["memory_governance_summary"]["ok"])
        self.assertTrue(execution_summary["memory_recall_summary"]["ok"])
        self.assertTrue(execution_summary["tool_skill_mcp_summary"]["ok"])
        self.assertTrue(execution_summary["tool_skill_mcp_summary"]["closure_gates"]["available_tools_only_enforced"])
        self.assertTrue(execution_summary["tool_skill_mcp_summary"]["closure_gates"]["side_effect_tools_require_approval"])
        self.assertTrue(execution_summary["tool_skill_mcp_summary"]["closure_gates"]["mcp_descriptor_read_only"])
        self.assertEqual(execution_summary["rational_plan_evidence"]["status"], "tool_selected")
        self.assertFalse(execution_summary["federation_summary"]["ok"])
        self.assertFalse(execution_summary["relay_summary"]["ok"])

    def test_cli_qq_official_gateway_closure_reports_resume_ready_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            gateway_run_file = Path(tmpdir) / "qq-gateway-run.json"
            gateway_run_file.write_text(
                json.dumps(
                    {
                        "schema_version": "2.2.2-qq-official-gateway-client-v1",
                        "command": "qq-official-gateway-client",
                        "status": "ready",
                        "reason": "qq_official_gateway_dispatch_processed",
                        "closure_gates": {
                            "gateway_connected": True,
                            "hello_recorded": True,
                            "ready_recorded": True,
                            "dispatch_processed": True,
                            "core_ingress_recorded": True,
                            "bounded_runtime": True,
                        },
                        "gateway": {"url": "wss://api.sgroup.qq.com/websocket"},
                        "session_id": "qq-session-001",
                        "bot_user_id": "bot-001",
                        "dispatch_event_count": 1,
                        "core_results": [{"events_persisted": 1}],
                        "reconnect_count": 1,
                        "resume_attempt_count": 1,
                        "resume_success_count": 1,
                        "resumed_event_count": 1,
                        "session_state_file": "/tmp/qq-gateway-session.json",
                        "session_state_persisted": True,
                    }
                ),
                encoding="utf-8",
            )

            out = io.StringIO()
            with redirect_stdout(out):
                code = core_cli_main(
                    [
                        "qq-official-gateway-closure",
                        "--gateway-run-file",
                        str(gateway_run_file),
                        "--require-resume-evidence",
                    ]
                )

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(
            payload["schema_version"], "2.2.2-qq-official-gateway-closure-v1"
        )
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["closure_gates"]["resume_path_recorded"])
        self.assertTrue(payload["closure_gates"]["resume_path_succeeded"])
        self.assertEqual(payload["evidence_summary"]["reconnect_count"], 1)

    def test_cli_closure_summary_can_pass_qq_gateway_gate_with_gateway_closure_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "core.db")
            gateway_run_file = Path(tmpdir) / "qq-gateway-run.json"
            gateway_closure_file = Path(tmpdir) / "qq-gateway-closure.json"

            run_no_model_dry_run(db_path, session_id="closure-summary-qq-gateway-001")
            gateway_run_file.write_text(
                json.dumps(
                    {
                        "schema_version": "2.2.2-qq-official-gateway-client-v1",
                        "command": "qq-official-gateway-client",
                        "status": "ready",
                        "reason": "qq_official_gateway_dispatch_processed",
                        "closure_gates": {
                            "gateway_connected": True,
                            "hello_recorded": True,
                            "ready_recorded": True,
                            "dispatch_processed": True,
                            "core_ingress_recorded": True,
                            "bounded_runtime": True,
                        },
                        "gateway": {"url": "wss://api.sgroup.qq.com/websocket"},
                        "session_id": "qq-session-001",
                        "bot_user_id": "bot-001",
                        "dispatch_event_count": 1,
                        "core_results": [{"events_persisted": 1}],
                        "reconnect_count": 1,
                        "resume_attempt_count": 1,
                        "resume_success_count": 1,
                        "resumed_event_count": 1,
                        "session_state_file": "/tmp/qq-gateway-session.json",
                        "session_state_persisted": True,
                    }
                ),
                encoding="utf-8",
            )

            gateway_out = io.StringIO()
            with redirect_stdout(gateway_out):
                gateway_code = core_cli_main(
                    [
                        "qq-official-gateway-closure",
                        "--gateway-run-file",
                        str(gateway_run_file),
                        "--require-resume-evidence",
                    ]
                )
            gateway_closure_file.write_text(gateway_out.getvalue(), encoding="utf-8")

            summary_out = io.StringIO()
            with redirect_stdout(summary_out):
                summary_code = core_cli_main(
                    [
                        "closure-summary",
                        "--db",
                        db_path,
                        "--session-id",
                        "closure-summary-qq-gateway-001",
                        "--qq-gateway-file",
                        str(gateway_closure_file),
                    ]
                )

        self.assertEqual(gateway_code, 0)
        self.assertEqual(summary_code, 0)
        payload = json.loads(summary_out.getvalue())
        self.assertTrue(payload["validation_gates"]["qq_official_gateway_gate"])
        self.assertTrue(payload["qq_official_gateway_summary"]["ok"])

    def test_cli_wecom_gateway_closure_reports_ready_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            gateway_run_file = Path(tmpdir) / "wecom-gateway-run.json"
            gateway_run_file.write_text(
                json.dumps(
                    {
                        "schema_version": "2.2.3-wecom-gateway-client-v1",
                        "command": "wecom-gateway-client",
                        "status": "ready",
                        "reason": "wecom_gateway_dispatch_processed",
                        "closure_gates": {
                            "gateway_connected": True,
                            "auth_sent": True,
                            "ready_recorded": True,
                            "dispatch_processed": True,
                            "core_ingress_recorded": True,
                            "bounded_runtime": True,
                        },
                        "gateway": {"url": "wss://qyapi.weixin.qq.com/cgi-bin/websocket"},
                        "bot_user_id": "wecom-bot-001",
                        "dispatch_event_count": 1,
                        "core_results": [{"events_persisted": 1}],
                    }
                ),
                encoding="utf-8",
            )

            out = io.StringIO()
            with redirect_stdout(out):
                code = core_cli_main(
                    [
                        "wecom-gateway-closure",
                        "--gateway-run-file",
                        str(gateway_run_file),
                    ]
                )

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["schema_version"], "2.2.3-wecom-gateway-closure-v1")
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["closure_gates"]["auth_sent"])
        self.assertEqual(payload["evidence_summary"]["dispatch_event_count"], 1)

    def test_cli_closure_summary_can_pass_wecom_gateway_gate_with_gateway_closure_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "core.db")
            gateway_run_file = Path(tmpdir) / "wecom-gateway-run.json"
            gateway_closure_file = Path(tmpdir) / "wecom-gateway-closure.json"

            run_no_model_dry_run(db_path, session_id="closure-summary-wecom-gateway-001")
            gateway_run_file.write_text(
                json.dumps(
                    {
                        "schema_version": "2.2.3-wecom-gateway-client-v1",
                        "command": "wecom-gateway-client",
                        "status": "ready",
                        "reason": "wecom_gateway_dispatch_processed",
                        "closure_gates": {
                            "gateway_connected": True,
                            "auth_sent": True,
                            "ready_recorded": True,
                            "dispatch_processed": True,
                            "core_ingress_recorded": True,
                            "bounded_runtime": True,
                        },
                        "gateway": {"url": "wss://qyapi.weixin.qq.com/cgi-bin/websocket"},
                        "bot_user_id": "wecom-bot-001",
                        "dispatch_event_count": 1,
                        "core_results": [{"events_persisted": 1}],
                    }
                ),
                encoding="utf-8",
            )

            gateway_out = io.StringIO()
            with redirect_stdout(gateway_out):
                gateway_code = core_cli_main(
                    [
                        "wecom-gateway-closure",
                        "--gateway-run-file",
                        str(gateway_run_file),
                    ]
                )
            gateway_closure_file.write_text(gateway_out.getvalue(), encoding="utf-8")

            summary_out = io.StringIO()
            with redirect_stdout(summary_out):
                summary_code = core_cli_main(
                    [
                        "closure-summary",
                        "--db",
                        db_path,
                        "--session-id",
                        "closure-summary-wecom-gateway-001",
                        "--wecom-gateway-file",
                        str(gateway_closure_file),
                    ]
                )

        self.assertEqual(gateway_code, 0)
        self.assertEqual(summary_code, 0)
        payload = json.loads(summary_out.getvalue())
        self.assertTrue(payload["validation_gates"]["wecom_gateway_gate"])
        self.assertTrue(payload["wecom_gateway_summary"]["ok"])

    def test_cli_closure_summary_keeps_social_adapter_bundle_green_with_qq_openclaw_smoke(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "core.db")
            social_adapter_file = Path(tmpdir) / "social-adapter.json"

            run_no_model_dry_run(db_path, session_id="closure-summary-social-adapter-001")

            social_adapter_out = io.StringIO()
            with redirect_stdout(social_adapter_out):
                social_adapter_code = core_cli_main([
                    "social-adapter-smoke",
                ])
            social_adapter_file.write_text(
                social_adapter_out.getvalue(),
                encoding="utf-8",
            )

            summary_out = io.StringIO()
            with redirect_stdout(summary_out):
                summary_code = core_cli_main(
                    [
                        "closure-summary",
                        "--db",
                        db_path,
                        "--session-id",
                        "closure-summary-social-adapter-001",
                        "--social-adapter-file",
                        str(social_adapter_file),
                    ]
                )

        self.assertEqual(social_adapter_code, 0)
        self.assertEqual(summary_code, 0)
        payload = json.loads(summary_out.getvalue())
        self.assertTrue(payload["validation_gates"]["social_adapter_gate"])
        self.assertTrue(payload["social_adapter_summary"]["ok"])
        self.assertTrue(
            payload["social_adapter_summary"]["closure_gates"][
                "qq_openclaw_social_gate"
            ]
        )
        self.assertIn(
            "qq_openclaw",
            payload["social_adapter_summary"]["evidence_summary"][
                "ready_adapter_names"
            ],
        )
        self.assertIn(
            "qq_openclaw",
            payload["social_adapter_summary"]["evidence_summary"][
                "tested_adapter_names"
            ],
        )

    def test_cli_openclaw_gateway_closure_reports_ready_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            gateway_run_file = Path(tmpdir) / "openclaw-gateway-run.json"
            gateway_run_file.write_text(
                json.dumps(
                    {
                        "schema_version": "2.2.3-openclaw-gateway-client-v1",
                        "command": "openclaw-gateway-client",
                        "status": "ready",
                        "reason": "openclaw_gateway_dispatch_processed",
                        "adapter_kind": "wechat_ilink",
                        "closure_gates": {
                            "gateway_connected": True,
                            "bind_sent": True,
                            "ready_recorded": True,
                            "plugin_identified": True,
                            "dispatch_processed": True,
                            "core_ingress_recorded": True,
                            "bounded_runtime": True,
                        },
                        "gateway": {
                            "url": "ws://127.0.0.1:8811/openclaw",
                            "transport_kind": "openclaw_gateway",
                            "runtime_host": "openclaw",
                        },
                        "plugin": {
                            "plugin_id": "wechat_ilink",
                            "plugin_package": "@tencent/openclaw-weixin",
                            "installer_package": "@tencent-weixin/openclaw-weixin-cli",
                            "host_version": "0.9.1",
                            "ready": True,
                        },
                        "dispatch_event_count": 1,
                        "core_results": [{"events_persisted": 1}],
                    }
                ),
                encoding="utf-8",
            )

            out = io.StringIO()
            with redirect_stdout(out):
                code = core_cli_main(
                    [
                        "openclaw-gateway-closure",
                        "--gateway-run-file",
                        str(gateway_run_file),
                    ]
                )

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(
            payload["schema_version"], "2.2.3-openclaw-gateway-closure-v1"
        )
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["closure_gates"]["plugin_ready"])
        self.assertEqual(
            payload["evidence_summary"]["plugin_package"],
            "@tencent/openclaw-weixin",
        )

    def test_cli_closure_summary_can_pass_openclaw_gateway_gate_with_gateway_closure_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "core.db")
            gateway_run_file = Path(tmpdir) / "openclaw-gateway-run.json"
            gateway_closure_file = Path(tmpdir) / "openclaw-gateway-closure.json"

            run_no_model_dry_run(db_path, session_id="closure-summary-openclaw-gateway-001")
            gateway_run_file.write_text(
                json.dumps(
                    {
                        "schema_version": "2.2.3-openclaw-gateway-client-v1",
                        "command": "openclaw-gateway-client",
                        "status": "ready",
                        "reason": "openclaw_gateway_dispatch_processed",
                        "adapter_kind": "wechat_ilink",
                        "closure_gates": {
                            "gateway_connected": True,
                            "bind_sent": True,
                            "ready_recorded": True,
                            "plugin_identified": True,
                            "dispatch_processed": True,
                            "core_ingress_recorded": True,
                            "bounded_runtime": True,
                        },
                        "gateway": {
                            "url": "ws://127.0.0.1:8811/openclaw",
                            "transport_kind": "openclaw_gateway",
                            "runtime_host": "openclaw",
                        },
                        "plugin": {
                            "plugin_id": "wechat_ilink",
                            "plugin_package": "@tencent/openclaw-weixin",
                            "installer_package": "@tencent-weixin/openclaw-weixin-cli",
                            "host_version": "0.9.1",
                            "ready": True,
                        },
                        "dispatch_event_count": 1,
                        "core_results": [{"events_persisted": 1}],
                    }
                ),
                encoding="utf-8",
            )

            gateway_out = io.StringIO()
            with redirect_stdout(gateway_out):
                gateway_code = core_cli_main(
                    [
                        "openclaw-gateway-closure",
                        "--gateway-run-file",
                        str(gateway_run_file),
                    ]
                )
            gateway_closure_file.write_text(gateway_out.getvalue(), encoding="utf-8")

            summary_out = io.StringIO()
            with redirect_stdout(summary_out):
                summary_code = core_cli_main(
                    [
                        "closure-summary",
                        "--db",
                        db_path,
                        "--session-id",
                        "closure-summary-openclaw-gateway-001",
                        "--openclaw-gateway-file",
                        str(gateway_closure_file),
                    ]
                )

        self.assertEqual(gateway_code, 0)
        self.assertEqual(summary_code, 0)
        payload = json.loads(summary_out.getvalue())
        self.assertTrue(payload["validation_gates"]["openclaw_gateway_gate"])
        self.assertTrue(payload["openclaw_gateway_summary"]["ok"])

    def test_cli_closure_summary_can_pass_federation_gate_when_route_evidence_is_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "core.db")

            run_no_model_dry_run(
                db_path,
                session_id="closure-summary-federation-001",
                federation_route_provider=lambda frame, session_context: federation_route_smoke(
                    target_node="unit-remote-01",
                    now="2026-05-09T12:00:00Z",
                    required_trust_scope="lab-federation",
                ),
            )

            summary_out = io.StringIO()
            with redirect_stdout(summary_out):
                summary_code = core_cli_main(
                    [
                        "closure-summary",
                        "--db",
                        db_path,
                        "--session-id",
                        "closure-summary-federation-001",
                    ]
                )

        self.assertEqual(summary_code, 0)
        payload = json.loads(summary_out.getvalue())
        self.assertTrue(payload["aggregate_gates"]["session_has_execution_evidence"])
        self.assertTrue(payload["validation_gates"]["federation_gate"])
        self.assertFalse(payload["validation_gates"]["relay_gate"])
        execution_summary = payload["execution_summaries"][0]
        self.assertTrue(execution_summary["federation_summary"]["ok"])
        self.assertFalse(execution_summary["relay_summary"]["ok"])
        self.assertEqual(
            execution_summary["federation_summary"]["route_kind"],
            "delegated_core",
        )
        self.assertTrue(
            execution_summary["federation_summary"]["delegated_execution_present"]
        )

    def test_cli_closure_summary_can_pass_relay_gate_when_peer_relay_evidence_is_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "core.db")

            run_no_model_dry_run(
                db_path,
                session_id="closure-summary-relay-001",
                federation_route_provider=lambda frame, session_context: federation_route_smoke(
                    target_node="unit-remote-01",
                    now="2026-05-10T12:00:00Z",
                    required_trust_scope="lab-federation",
                    peer_expires_at="2026-05-10T12:30:00Z",
                    peer_relay_via=("gateway-b-01",),
                    peer_network_transports=("ethernet", "serial_bridge"),
                ),
            )

            summary_out = io.StringIO()
            with redirect_stdout(summary_out):
                summary_code = core_cli_main(
                    [
                        "closure-summary",
                        "--db",
                        db_path,
                        "--session-id",
                        "closure-summary-relay-001",
                    ]
                )

        self.assertEqual(summary_code, 0)
        payload = json.loads(summary_out.getvalue())
        self.assertTrue(payload["validation_gates"]["federation_gate"])
        self.assertFalse(payload["validation_gates"]["relay_gate"])
        execution_summary = payload["execution_summaries"][0]
        self.assertTrue(execution_summary["relay_summary"]["ok"])
        self.assertEqual(
            execution_summary["relay_summary"]["relay_path"],
            ["gateway-b-01"],
        )
        self.assertEqual(
            execution_summary["relay_summary"]["supported_transports"],
            ["ethernet", "serial_bridge"],
        )

    def test_cli_closure_summary_can_pass_relay_gate_with_failure_runbook_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "core.db")
            relay_failure_file = Path(tmpdir) / "relay-failure.json"

            run_no_model_dry_run(
                db_path,
                session_id="closure-summary-relay-runbook-001",
                federation_route_provider=lambda frame, session_context: federation_route_smoke(
                    target_node="unit-remote-01",
                    now="2026-05-10T12:00:00Z",
                    required_trust_scope="lab-federation",
                    peer_expires_at="2026-05-10T12:30:00Z",
                    peer_relay_via=("gateway-b-01",),
                    peer_network_transports=("ethernet", "serial_bridge"),
                ),
            )
            relay_failure_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.2.6-relay-failure-closure-v1",
                        "status": "ready",
                        "reason": "route_failure_runbook_reviewed",
                        "closure_gates": {
                            "route_failure_recorded": True,
                            "fallback_path_recorded": True,
                            "operator_runbook_recorded": True,
                            "deterministic_validation_recorded": True,
                        },
                        "evidence_summary": {
                            "route_failure_reason": "peer_unreachable",
                            "fallback_action": "direct_local_retry_then_manual_operator_review",
                            "runbook_id": "relay-route-failure-v1",
                        },
                    }
                ),
                encoding="utf-8",
            )

            summary_out = io.StringIO()
            with redirect_stdout(summary_out):
                summary_code = core_cli_main(
                    [
                        "closure-summary",
                        "--db",
                        db_path,
                        "--session-id",
                        "closure-summary-relay-runbook-001",
                        "--relay-failure-file",
                        str(relay_failure_file),
                    ]
                )

        self.assertEqual(summary_code, 0)
        payload = json.loads(summary_out.getvalue())
        self.assertTrue(payload["validation_gates"]["relay_gate"])
        self.assertTrue(payload["relay_failure_summary"]["ok"])

    def test_cli_closure_summary_can_pass_hardware_and_artifact_gates_with_compatibility_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "core.db")
            source_dir = Path(tmpdir) / "source"
            artifact_path = Path(tmpdir) / "artifacts" / "neuro_unit_app.llext"
            hardware_file = Path(tmpdir) / "hardware-compatibility.json"

            run_no_model_dry_run(db_path, session_id="closure-summary-hardware-001")
            self._write_fake_app_source(
                source_dir,
                app_id="neuro_unit_app",
                app_version="1.2.2",
                build_id="neuro_unit_app-1.2.2-cbor-v2",
            )
            self._write_fake_llext(
                artifact_path,
                app_id="neuro_unit_app",
                app_version="1.2.2",
                build_id="neuro_unit_app-1.2.2-cbor-v2",
            )

            hardware_out = io.StringIO()
            with redirect_stdout(hardware_out):
                hardware_code = core_cli_main(
                    [
                        "hardware-compatibility-smoke",
                        "--app-id",
                        "neuro_unit_app",
                        "--app-source-dir",
                        str(source_dir),
                        "--artifact-file",
                        str(artifact_path),
                        "--required-heap-free-bytes",
                        "4096",
                        "--required-app-slot-bytes",
                        "32768",
                    ]
                )
            hardware_file.write_text(hardware_out.getvalue(), encoding="utf-8")

            summary_out = io.StringIO()
            with redirect_stdout(summary_out):
                summary_code = core_cli_main(
                    [
                        "closure-summary",
                        "--db",
                        db_path,
                        "--session-id",
                        "closure-summary-hardware-001",
                        "--hardware-compatibility-file",
                        str(hardware_file),
                    ]
                )

        self.assertEqual(hardware_code, 0)
        self.assertEqual(summary_code, 0)
        payload = json.loads(summary_out.getvalue())
        self.assertTrue(payload["validation_gates"]["hardware_abstraction_gate"])
        self.assertTrue(payload["validation_gates"]["artifact_compatibility_gate"])
        self.assertTrue(payload["hardware_compatibility_summary"]["hardware_abstraction_ok"])
        self.assertTrue(payload["hardware_compatibility_summary"]["artifact_compatibility_ok"])

    def test_cli_resource_budget_governance_smoke_reports_independent_budget_threshold_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            source_dir = Path(tmpdir) / "source"
            artifact_path = Path(tmpdir) / "artifacts" / "neuro_unit_app.llext"
            hardware_file = Path(tmpdir) / "hardware-compatibility.json"

            self._write_fake_app_source(
                source_dir,
                app_id="neuro_unit_app",
                app_version="1.2.7",
                build_id="neuro_unit_app-1.2.7-cbor-v2",
            )
            self._write_fake_llext(
                artifact_path,
                app_id="neuro_unit_app",
                app_version="1.2.7",
                build_id="neuro_unit_app-1.2.7-cbor-v2",
            )

            hardware_out = io.StringIO()
            with redirect_stdout(hardware_out):
                hardware_code = core_cli_main(
                    [
                        "hardware-compatibility-smoke",
                        "--app-id",
                        "neuro_unit_app",
                        "--app-source-dir",
                        str(source_dir),
                        "--artifact-file",
                        str(artifact_path),
                        "--required-heap-free-bytes",
                        "4096",
                        "--required-app-slot-bytes",
                        "32768",
                    ]
                )
            hardware_file.write_text(hardware_out.getvalue(), encoding="utf-8")

            budget_out = io.StringIO()
            with redirect_stdout(budget_out):
                budget_code = core_cli_main(
                    [
                        "resource-budget-governance-smoke",
                        "--hardware-compatibility-file",
                        str(hardware_file),
                    ]
                )

        self.assertEqual(hardware_code, 0)
        self.assertEqual(budget_code, 0)
        payload = json.loads(budget_out.getvalue())
        self.assertEqual(
            payload["schema_version"],
            "1.2.7-resource-budget-governance-smoke-v1",
        )
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["closure_gates"]["resource_budget_recorded"])
        self.assertTrue(payload["closure_gates"]["resource_budget_thresholds_recorded"])
        self.assertTrue(payload["closure_gates"]["resource_budget_sufficient"])

    def test_cli_closure_summary_can_pass_resource_budget_governance_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "core.db")
            source_dir = Path(tmpdir) / "source"
            artifact_path = Path(tmpdir) / "artifacts" / "neuro_unit_app.llext"
            hardware_file = Path(tmpdir) / "hardware-compatibility.json"
            budget_file = Path(tmpdir) / "resource-budget-governance.json"

            run_no_model_dry_run(db_path, session_id="closure-summary-resource-budget-001")
            self._write_fake_app_source(
                source_dir,
                app_id="neuro_unit_app",
                app_version="1.2.7",
                build_id="neuro_unit_app-1.2.7-cbor-v2",
            )
            self._write_fake_llext(
                artifact_path,
                app_id="neuro_unit_app",
                app_version="1.2.7",
                build_id="neuro_unit_app-1.2.7-cbor-v2",
            )

            hardware_out = io.StringIO()
            with redirect_stdout(hardware_out):
                hardware_code = core_cli_main(
                    [
                        "hardware-compatibility-smoke",
                        "--app-id",
                        "neuro_unit_app",
                        "--app-source-dir",
                        str(source_dir),
                        "--artifact-file",
                        str(artifact_path),
                        "--required-heap-free-bytes",
                        "4096",
                        "--required-app-slot-bytes",
                        "32768",
                    ]
                )
            hardware_file.write_text(hardware_out.getvalue(), encoding="utf-8")

            budget_out = io.StringIO()
            with redirect_stdout(budget_out):
                budget_code = core_cli_main(
                    [
                        "resource-budget-governance-smoke",
                        "--hardware-compatibility-file",
                        str(hardware_file),
                    ]
                )
            budget_file.write_text(budget_out.getvalue(), encoding="utf-8")

            summary_out = io.StringIO()
            with redirect_stdout(summary_out):
                summary_code = core_cli_main(
                    [
                        "closure-summary",
                        "--db",
                        db_path,
                        "--session-id",
                        "closure-summary-resource-budget-001",
                        "--resource-budget-governance-file",
                        str(budget_file),
                    ]
                )

        self.assertEqual(hardware_code, 0)
        self.assertEqual(budget_code, 0)
        self.assertEqual(summary_code, 0)
        payload = json.loads(summary_out.getvalue())
        self.assertTrue(payload["validation_gates"]["resource_budget_governance_gate"])
        self.assertTrue(payload["resource_budget_governance_summary"]["ok"])

    def test_cli_hardware_acceptance_matrix_reports_capability_classes_without_board_lock_in(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            source_dir = Path(tmpdir) / "source"
            artifact_path = Path(tmpdir) / "artifacts" / "neuro_unit_app.llext"

            self._write_fake_app_source(
                source_dir,
                app_id="neuro_unit_app",
                app_version="1.2.7",
                build_id="neuro_unit_app-1.2.7-cbor-v2",
            )
            self._write_fake_llext(
                artifact_path,
                app_id="neuro_unit_app",
                app_version="1.2.7",
                build_id="neuro_unit_app-1.2.7-cbor-v2",
            )

            matrix_out = io.StringIO()
            with redirect_stdout(matrix_out):
                matrix_code = core_cli_main(
                    [
                        "hardware-acceptance-matrix",
                        "--app-id",
                        "neuro_unit_app",
                        "--app-source-dir",
                        str(source_dir),
                        "--artifact-file",
                        str(artifact_path),
                    ]
                )

        self.assertEqual(matrix_code, 0)
        payload = json.loads(matrix_out.getvalue())
        self.assertEqual(payload["schema_version"], "1.2.7-hardware-acceptance-matrix-v1")
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["closure_gates"]["required_capability_classes_present"])
        self.assertTrue(payload["closure_gates"]["restricted_unit_outcome_explicit"])
        self.assertTrue(payload["closure_gates"]["relay_or_federated_row_present"])
        represented = {row["capability_class"] for row in payload["rows"]}
        self.assertIn("extensible_unit", represented)
        self.assertIn("restricted_unit", represented)
        self.assertIn("relay_capable_unit", represented)
        restricted_row = next(
            row for row in payload["rows"] if row["capability_class"] == "restricted_unit"
        )
        self.assertEqual(restricted_row["status"], "restricted_ready")
        self.assertEqual(restricted_row["dynamic_app_support"], "unsupported")

    def test_cli_closure_summary_can_pass_hardware_acceptance_matrix_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "core.db")
            source_dir = Path(tmpdir) / "source"
            artifact_path = Path(tmpdir) / "artifacts" / "neuro_unit_app.llext"
            matrix_file = Path(tmpdir) / "hardware-acceptance-matrix.json"

            run_no_model_dry_run(db_path, session_id="closure-summary-hardware-matrix-001")
            self._write_fake_app_source(
                source_dir,
                app_id="neuro_unit_app",
                app_version="1.2.7",
                build_id="neuro_unit_app-1.2.7-cbor-v2",
            )
            self._write_fake_llext(
                artifact_path,
                app_id="neuro_unit_app",
                app_version="1.2.7",
                build_id="neuro_unit_app-1.2.7-cbor-v2",
            )

            matrix_out = io.StringIO()
            with redirect_stdout(matrix_out):
                matrix_code = core_cli_main(
                    [
                        "hardware-acceptance-matrix",
                        "--app-id",
                        "neuro_unit_app",
                        "--app-source-dir",
                        str(source_dir),
                        "--artifact-file",
                        str(artifact_path),
                    ]
                )
            matrix_file.write_text(matrix_out.getvalue(), encoding="utf-8")

            summary_out = io.StringIO()
            with redirect_stdout(summary_out):
                summary_code = core_cli_main(
                    [
                        "closure-summary",
                        "--db",
                        db_path,
                        "--session-id",
                        "closure-summary-hardware-matrix-001",
                        "--hardware-acceptance-matrix-file",
                        str(matrix_file),
                    ]
                )

        self.assertEqual(matrix_code, 0)
        self.assertEqual(summary_code, 0)
        payload = json.loads(summary_out.getvalue())
        self.assertTrue(payload["validation_gates"]["hardware_acceptance_matrix_gate"])
        self.assertTrue(payload["hardware_acceptance_matrix_summary"]["ok"])
        self.assertTrue(payload["validation_gates"]["restricted_unit_compatibility_gate"])
        self.assertTrue(
            payload["hardware_acceptance_matrix_summary"]["restricted_unit_compatibility_ok"]
        )

    def test_cli_agent_excellence_smoke_reports_independent_closure_payload(self) -> None:
        excellence_out = io.StringIO()
        with redirect_stdout(excellence_out):
            excellence_code = core_cli_main([
                "agent-excellence-smoke",
            ])

        self.assertEqual(excellence_code, 0)
        payload = json.loads(excellence_out.getvalue())
        self.assertEqual(payload["schema_version"], "1.2.7-agent-excellence-smoke-v1")
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["closure_gates"]["tool_manifest_supplied"])
        self.assertTrue(payload["closure_gates"]["workflow_catalog_consistent"])
        self.assertTrue(payload["closure_gates"]["skill_registry_supplied"])
        self.assertTrue(payload["closure_gates"]["skill_registry_contract_supported"])
        self.assertTrue(payload["closure_gates"]["skill_registry_records_canonical_entry"])
        self.assertTrue(payload["closure_gates"]["mcp_descriptor_read_only"])
        self.assertTrue(payload["closure_gates"]["mcp_read_only_execute_supported"])
        self.assertTrue(payload["closure_gates"]["mcp_governance_descriptor_supported"])
        self.assertTrue(payload["closure_gates"]["coding_agent_self_improvement_routed"])
        self.assertTrue(payload["closure_gates"]["hallucinated_tool_rejected_by_available_manifest"])
        self.assertEqual(payload["evidence_summary"]["skill_registry_entry_count"], 2)
        self.assertEqual(payload["evidence_summary"]["mcp_read_only_probe_tool"], "system_state_sync")
        self.assertEqual(payload["evidence_summary"]["mcp_governance_probe_tool"], "system_restart_app")
        self.assertEqual(payload["evidence_summary"]["coding_agent_probe_runner"], "copilot")

    def test_cli_closure_summary_can_pass_agent_excellence_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "core.db")
            excellence_file = Path(tmpdir) / "agent-excellence.json"

            run_no_model_dry_run(db_path, session_id="closure-summary-agent-excellence-001")
            excellence_out = io.StringIO()
            with redirect_stdout(excellence_out):
                excellence_code = core_cli_main([
                    "agent-excellence-smoke",
                ])
            excellence_file.write_text(excellence_out.getvalue(), encoding="utf-8")

            summary_out = io.StringIO()
            with redirect_stdout(summary_out):
                summary_code = core_cli_main(
                    [
                        "closure-summary",
                        "--db",
                        db_path,
                        "--session-id",
                        "closure-summary-agent-excellence-001",
                        "--agent-excellence-file",
                        str(excellence_file),
                    ]
                )

        self.assertEqual(excellence_code, 0)
        self.assertEqual(summary_code, 0)
        payload = json.loads(summary_out.getvalue())
        self.assertTrue(payload["validation_gates"]["agent_excellence_gate"])
        self.assertTrue(payload["agent_excellence_summary"]["ok"])

    def test_cli_signing_provenance_smoke_reports_identity_digest_and_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            source_dir = Path(tmpdir) / "source"
            artifact_path = Path(tmpdir) / "artifacts" / "neuro_unit_app.llext"

            self._write_fake_app_source(
                source_dir,
                app_id="neuro_unit_app",
                app_version="1.2.7",
                build_id="neuro_unit_app-1.2.7-signing-v1",
            )
            self._write_fake_llext(
                artifact_path,
                app_id="neuro_unit_app",
                app_version="1.2.7",
                build_id="neuro_unit_app-1.2.7-signing-v1",
            )

            signing_out = io.StringIO()
            with redirect_stdout(signing_out):
                signing_code = core_cli_main(
                    [
                        "signing-provenance-smoke",
                        "--app-id",
                        "neuro_unit_app",
                        "--app-source-dir",
                        str(source_dir),
                        "--artifact-file",
                        str(artifact_path),
                    ]
                )

        self.assertEqual(signing_code, 0)
        payload = json.loads(signing_out.getvalue())
        self.assertEqual(payload["schema_version"], "1.2.7-signing-provenance-smoke-v1")
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["closure_gates"]["artifact_sha256_recorded"])
        self.assertTrue(payload["closure_gates"]["signing_required_for_release"])
        self.assertTrue(payload["closure_gates"]["signing_enforcement_compatible"])
        self.assertEqual(len(payload["evidence_summary"]["artifact_sha256"]), 64)

    def test_cli_closure_summary_can_pass_signing_provenance_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "core.db")
            source_dir = Path(tmpdir) / "source"
            artifact_path = Path(tmpdir) / "artifacts" / "neuro_unit_app.llext"
            signing_file = Path(tmpdir) / "signing-provenance.json"

            run_no_model_dry_run(db_path, session_id="closure-summary-signing-001")
            self._write_fake_app_source(
                source_dir,
                app_id="neuro_unit_app",
                app_version="1.2.7",
                build_id="neuro_unit_app-1.2.7-signing-v1",
            )
            self._write_fake_llext(
                artifact_path,
                app_id="neuro_unit_app",
                app_version="1.2.7",
                build_id="neuro_unit_app-1.2.7-signing-v1",
            )

            signing_out = io.StringIO()
            with redirect_stdout(signing_out):
                signing_code = core_cli_main(
                    [
                        "signing-provenance-smoke",
                        "--app-id",
                        "neuro_unit_app",
                        "--app-source-dir",
                        str(source_dir),
                        "--artifact-file",
                        str(artifact_path),
                    ]
                )
            signing_file.write_text(signing_out.getvalue(), encoding="utf-8")

            summary_out = io.StringIO()
            with redirect_stdout(summary_out):
                summary_code = core_cli_main(
                    [
                        "closure-summary",
                        "--db",
                        db_path,
                        "--session-id",
                        "closure-summary-signing-001",
                        "--signing-provenance-file",
                        str(signing_file),
                    ]
                )

        self.assertEqual(signing_code, 0)
        self.assertEqual(summary_code, 0)
        payload = json.loads(summary_out.getvalue())
        self.assertTrue(payload["validation_gates"]["signing_provenance_gate"])
        self.assertTrue(payload["signing_provenance_summary"]["ok"])

    def test_cli_observability_diagnosis_smoke_reports_structured_operator_guidance(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            relay_failure_file = Path(tmpdir) / "relay-failure.json"
            activate_failure_file = Path(tmpdir) / "activate-failure.json"

            relay_failure_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.2.6-relay-failure-closure-v1",
                        "status": "ready",
                        "reason": "route_failure_runbook_reviewed",
                        "closure_gates": {
                            "route_failure_recorded": True,
                            "fallback_path_recorded": True,
                            "operator_runbook_recorded": True,
                            "deterministic_validation_recorded": True,
                        },
                        "evidence_summary": {
                            "route_failure_reason": "peer_unreachable",
                            "fallback_action": "direct_local_retry_then_manual_operator_review",
                            "runbook_id": "relay-route-failure-v1",
                        },
                    }
                ),
                encoding="utf-8",
            )
            activate_failure_file.write_text(
                json.dumps(
                    {
                        "ok": False,
                        "status": "error",
                        "command": "app-deploy-activate",
                        "failure_class": "app_deploy_activate_failed",
                        "failure_status": "rollback_required",
                        "recovery_candidate_summary": {
                            "app_id": "neuro_demo_gpio",
                            "rollback_decision": "operator_review_required",
                            "lease_resource": "update/app/neuro_demo_gpio/rollback",
                            "matching_lease_ids": ["lease-gpio-rollback-obs-001"],
                        },
                        "rollback_approval": {
                            "status": "pending_approval",
                            "cleanup_hint": "confirm rollback evidence, lease ownership, and target app identity before resume",
                        },
                    }
                ),
                encoding="utf-8",
            )

            out = io.StringIO()
            with redirect_stdout(out):
                code = core_cli_main(
                    [
                        "observability-diagnosis-smoke",
                        "--relay-failure-file",
                        str(relay_failure_file),
                        "--activate-failure-file",
                        str(activate_failure_file),
                    ]
                )

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["schema_version"], "1.2.7-observability-diagnosis-smoke-v1")
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["closure_gates"]["route_failure_recorded"])
        self.assertTrue(payload["closure_gates"]["rollback_required_recorded"])
        self.assertTrue(payload["closure_gates"]["operator_next_actions_recorded"])

    def test_cli_closure_summary_can_pass_observability_diagnosis_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "core.db")
            relay_failure_file = Path(tmpdir) / "relay-failure.json"
            activate_failure_file = Path(tmpdir) / "activate-failure.json"
            observability_file = Path(tmpdir) / "observability-diagnosis.json"

            run_no_model_dry_run(db_path, session_id="closure-summary-observability-001")
            relay_failure_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.2.6-relay-failure-closure-v1",
                        "status": "ready",
                        "reason": "route_failure_runbook_reviewed",
                        "closure_gates": {
                            "route_failure_recorded": True,
                            "fallback_path_recorded": True,
                            "operator_runbook_recorded": True,
                            "deterministic_validation_recorded": True,
                        },
                        "evidence_summary": {
                            "route_failure_reason": "peer_unreachable",
                            "fallback_action": "direct_local_retry_then_manual_operator_review",
                            "runbook_id": "relay-route-failure-v1",
                        },
                    }
                ),
                encoding="utf-8",
            )
            activate_failure_file.write_text(
                json.dumps(
                    {
                        "ok": False,
                        "status": "error",
                        "command": "app-deploy-activate",
                        "failure_class": "app_deploy_activate_failed",
                        "failure_status": "rollback_required",
                        "recovery_candidate_summary": {
                            "app_id": "neuro_demo_gpio",
                            "rollback_decision": "operator_review_required",
                            "lease_resource": "update/app/neuro_demo_gpio/rollback",
                            "matching_lease_ids": ["lease-gpio-rollback-obs-001"],
                        },
                        "rollback_approval": {
                            "status": "pending_approval",
                            "cleanup_hint": "confirm rollback evidence, lease ownership, and target app identity before resume",
                        },
                    }
                ),
                encoding="utf-8",
            )

            observability_out = io.StringIO()
            with redirect_stdout(observability_out):
                observability_code = core_cli_main(
                    [
                        "observability-diagnosis-smoke",
                        "--relay-failure-file",
                        str(relay_failure_file),
                        "--activate-failure-file",
                        str(activate_failure_file),
                    ]
                )
            observability_file.write_text(observability_out.getvalue(), encoding="utf-8")

            summary_out = io.StringIO()
            with redirect_stdout(summary_out):
                summary_code = core_cli_main(
                    [
                        "closure-summary",
                        "--db",
                        db_path,
                        "--session-id",
                        "closure-summary-observability-001",
                        "--observability-diagnosis-file",
                        str(observability_file),
                    ]
                )

        self.assertEqual(observability_code, 0)
        self.assertEqual(summary_code, 0)
        payload = json.loads(summary_out.getvalue())
        self.assertTrue(payload["validation_gates"]["observability_diagnosis_gate"])
        self.assertTrue(payload["observability_diagnosis_summary"]["ok"])

    def test_cli_release_rollback_hardening_smoke_reports_guarded_rollback_closure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            activate_failure_file = Path(tmpdir) / "activate-failure.json"
            rollback_file = Path(tmpdir) / "rollback.json"

            activate_failure_file.write_text(
                json.dumps(
                    {
                        "ok": False,
                        "status": "error",
                        "command": "app-deploy-activate",
                        "failure_class": "app_deploy_activate_failed",
                        "failure_status": "rollback_required",
                        "recovery_candidate_summary": {
                            "app_id": "neuro_demo_gpio",
                            "rollback_decision": "operator_review_required",
                            "lease_resource": "update/app/neuro_demo_gpio/rollback",
                            "matching_lease_ids": ["lease-gpio-rollback-hard-001"],
                        },
                        "rollback_approval": {
                            "status": "pending_approval",
                            "cleanup_hint": "confirm rollback evidence, lease ownership, and target app identity before resume",
                        },
                    }
                ),
                encoding="utf-8",
            )
            rollback_file.write_text(
                json.dumps(
                    {
                        "ok": True,
                        "status": "ok",
                        "command": "app-deploy-rollback",
                        "rollback_decision": {
                            "approval_required": True,
                            "status": "approved",
                            "rollback_resource": "update/app/neuro_demo_gpio/rollback",
                            "resolved_app_id": "neuro_demo_gpio",
                            "rollback_reason": "guarded_rollback_after_activation_health_failure",
                        },
                        "rollback_execution": {
                            "completed_through": "query_leases",
                            "rollback": {"ok": True},
                            "query_apps": {
                                "ok": True,
                                "app_present": False,
                                "observed_app_state": "missing",
                            },
                            "query_leases": {"ok": True, "matching_lease_ids": []},
                        },
                    }
                ),
                encoding="utf-8",
            )

            out = io.StringIO()
            with redirect_stdout(out):
                code = core_cli_main(
                    [
                        "release-rollback-hardening-smoke",
                        "--activate-failure-file",
                        str(activate_failure_file),
                        "--rollback-file",
                        str(rollback_file),
                    ]
                )

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["schema_version"], "1.2.7-release-rollback-hardening-smoke-v1")
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["closure_gates"]["rollback_decision_approved"])
        self.assertTrue(payload["closure_gates"]["rollback_cleanup_clear"])

    def test_cli_closure_summary_can_pass_release_rollback_hardening_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "core.db")
            activate_failure_file = Path(tmpdir) / "activate-failure.json"
            rollback_file = Path(tmpdir) / "rollback.json"
            release_rollback_file = Path(tmpdir) / "release-rollback.json"

            run_no_model_dry_run(db_path, session_id="closure-summary-release-rollback-001")
            activate_failure_file.write_text(
                json.dumps(
                    {
                        "ok": False,
                        "status": "error",
                        "command": "app-deploy-activate",
                        "failure_class": "app_deploy_activate_failed",
                        "failure_status": "rollback_required",
                        "recovery_candidate_summary": {
                            "app_id": "neuro_demo_gpio",
                            "rollback_decision": "operator_review_required",
                            "lease_resource": "update/app/neuro_demo_gpio/rollback",
                            "matching_lease_ids": ["lease-gpio-rollback-hard-001"],
                        },
                        "rollback_approval": {
                            "status": "pending_approval",
                            "cleanup_hint": "confirm rollback evidence, lease ownership, and target app identity before resume",
                        },
                    }
                ),
                encoding="utf-8",
            )
            rollback_file.write_text(
                json.dumps(
                    {
                        "ok": True,
                        "status": "ok",
                        "command": "app-deploy-rollback",
                        "rollback_decision": {
                            "approval_required": True,
                            "status": "approved",
                            "rollback_resource": "update/app/neuro_demo_gpio/rollback",
                            "resolved_app_id": "neuro_demo_gpio",
                            "rollback_reason": "guarded_rollback_after_activation_health_failure",
                        },
                        "rollback_execution": {
                            "completed_through": "query_leases",
                            "rollback": {"ok": True},
                            "query_apps": {
                                "ok": True,
                                "app_present": False,
                                "observed_app_state": "missing",
                            },
                            "query_leases": {"ok": True, "matching_lease_ids": []},
                        },
                    }
                ),
                encoding="utf-8",
            )

            release_rollback_out = io.StringIO()
            with redirect_stdout(release_rollback_out):
                release_rollback_code = core_cli_main(
                    [
                        "release-rollback-hardening-smoke",
                        "--activate-failure-file",
                        str(activate_failure_file),
                        "--rollback-file",
                        str(rollback_file),
                    ]
                )
            release_rollback_file.write_text(
                release_rollback_out.getvalue(), encoding="utf-8"
            )

            summary_out = io.StringIO()
            with redirect_stdout(summary_out):
                summary_code = core_cli_main(
                    [
                        "closure-summary",
                        "--db",
                        db_path,
                        "--session-id",
                        "closure-summary-release-rollback-001",
                        "--release-rollback-file",
                        str(release_rollback_file),
                    ]
                )

        self.assertEqual(release_rollback_code, 0)
        self.assertEqual(summary_code, 0)
        payload = json.loads(summary_out.getvalue())
        self.assertTrue(payload["validation_gates"]["release_rollback_hardening_gate"])
        self.assertTrue(payload["release_rollback_summary"]["ok"])

    def test_cli_real_scene_checklist_template_emits_machine_archivable_rows(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            code = core_cli_main(["real-scene-checklist-template"])

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["schema_version"], "2.0.0-real-scene-checklist-template-v1")
        self.assertEqual(payload["summary"]["total_rows"], 8)
        self.assertEqual(payload["summary"]["pending_rows"], 8)
        self.assertEqual(
            [row["scenario_id"] for row in payload["scenario_rows"]],
            ["RS-01", "RS-02", "RS-03", "RS-04", "RS-05", "RS-06", "RS-07", "RS-08"],
        )
        self.assertEqual(
            payload["scenario_rows"][5]["primary_gates"],
            ["relay_gate", "observability_diagnosis_gate"],
        )

    def test_cli_real_scene_e2e_smoke_reports_live_core_unit_continuity(self) -> None:
        def runner(argv: list[str], timeout_seconds: int) -> CommandExecutionResult:
            del timeout_seconds
            if "app-events" in argv:
                return CommandExecutionResult(
                    exit_code=0,
                    stdout=json.dumps(
                        {
                            "ok": True,
                            "subscription": "neuro/unit-01/event/app/neuro_demo_app/**",
                            "listener_mode": "callback",
                            "handler_audit": {"enabled": False, "executed": 0},
                            "events": [
                                {
                                    "keyexpr": "neuro/unit-01/event/app/neuro_demo_app/callback/value",
                                    "payload": {
                                        "semantic_topic": "unit.callback",
                                        "event_id": "evt-live-app-001",
                                        "source_kind": "unit_app",
                                        "source_node": "unit-01",
                                        "source_app": "neuro_demo_app",
                                        "event_type": "callback",
                                        "timestamp_wall": "2026-05-09T00:00:00Z",
                                        "priority": 20,
                                    },
                                    "payload_encoding": "json",
                                }
                            ],
                        }
                    ),
                )
            if "tool-manifest" in argv:
                return CommandExecutionResult(
                    exit_code=0,
                    stdout=json.dumps(
                        {
                            "ok": True,
                            "status": "ok",
                            "schema_version": TOOL_MANIFEST_SCHEMA_VERSION,
                            "tools": [
                                {
                                    "name": "system_state_sync",
                                    "description": "state sync",
                                    "argv_template": [
                                        "python",
                                        "neuro_cli/scripts/invoke_neuro_cli.py",
                                        "system",
                                        "state-sync",
                                        "--output",
                                        "json",
                                    ],
                                    "resource": "state sync aggregate",
                                    "required_arguments": ["--node"],
                                    "side_effect_level": "read_only",
                                    "lease_requirements": [],
                                    "timeout_seconds": 10,
                                    "retryable": True,
                                    "approval_required": False,
                                    "cleanup_hints": [],
                                    "output_contract": {"format": "json", "top_level_ok": True},
                                }
                            ],
                        }
                    ),
                )
            if "state-sync" in argv:
                return CommandExecutionResult(
                    exit_code=0,
                    stdout=json.dumps(
                        {
                            "ok": True,
                            "status": "ok",
                            "schema_version": "1.2.0-state-sync-v1",
                            "state": {
                                "device": {"ok": True, "status": "ok", "payload": {"network_state": "NETWORK_READY"}},
                                "apps": {
                                    "ok": True,
                                    "status": "ok",
                                    "payload": {
                                        "app_count": 1,
                                        "apps": [{"app_id": "neuro_demo_app", "state": "running"}],
                                    },
                                },
                                "leases": {"ok": True, "status": "ok", "payload": {"leases": []}},
                            },
                            "recommended_next_actions": [
                                "state sync is clean; read-only delegated reasoning may continue"
                            ],
                        }
                    ),
                )
            raise AssertionError(f"unexpected argv: {argv}")

        adapter = NeuroCliToolAdapter(runner=runner)
        with tempfile.TemporaryDirectory() as tmpdir:
            live_event_file = Path(tmpdir) / "live-event-smoke.json"
            coding_agent_route_file = Path(tmpdir) / "coding-agent-route.json"
            live_out = io.StringIO()
            with mock.patch("neurolink_core.cli.NeuroCliToolAdapter", return_value=adapter):
                with redirect_stdout(live_out):
                    live_code = core_cli_main(
                        [
                            "live-event-smoke",
                            "--app-id",
                            "neuro_demo_app",
                            "--duration",
                            "1",
                            "--max-events",
                            "1",
                        ]
                    )
            live_event_file.write_text(live_out.getvalue(), encoding="utf-8")
            coding_agent_route_out = io.StringIO()
            with redirect_stdout(coding_agent_route_out):
                coding_agent_route_code = core_cli_main(
                    [
                        "coding-agent-self-improvement-route",
                        "--runner",
                        "copilot",
                        "--summary",
                        "Repair deterministic regression in sandbox",
                        "--decision",
                        "approve",
                        "--tests-passed",
                        "--lint-passed",
                        "--smoke-passed",
                        "--evidence-ref=pytest.txt",
                    ]
                )
            coding_agent_route_file.write_text(
                coding_agent_route_out.getvalue(), encoding="utf-8"
            )

            e2e_out = io.StringIO()
            with redirect_stdout(e2e_out):
                e2e_code = core_cli_main(
                    [
                        "real-scene-e2e-smoke",
                        "--live-event-smoke-file",
                        str(live_event_file),
                        "--coding-agent-route-file",
                        str(coding_agent_route_file),
                    ]
                )

        self.assertEqual(live_code, 0)
        self.assertEqual(coding_agent_route_code, 0)
        self.assertEqual(e2e_code, 0)
        payload = json.loads(e2e_out.getvalue())
        self.assertEqual(payload["schema_version"], "1.2.7-real-scene-e2e-smoke-v1")
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["closure_gates"]["live_event_source_real"])
        self.assertTrue(payload["closure_gates"]["real_tool_execution_succeeded"])
        self.assertTrue(payload["closure_gates"]["state_sync_tool_used"])
        self.assertTrue(payload["closure_gates"]["coding_agent_route_valid_if_supplied"])
        self.assertTrue(payload["closure_gates"]["coding_agent_callback_audit_recorded_if_supplied"])
        self.assertTrue(payload["closure_gates"]["coding_agent_sandbox_recorded_if_supplied"])
        self.assertEqual(payload["evidence_summary"]["coding_agent_runner"], "copilot")

    def test_cli_closure_summary_can_pass_real_scene_e2e_gate(self) -> None:
        def runner(argv: list[str], timeout_seconds: int) -> CommandExecutionResult:
            del timeout_seconds
            if "app-events" in argv:
                return CommandExecutionResult(
                    exit_code=0,
                    stdout=json.dumps(
                        {
                            "ok": True,
                            "subscription": "neuro/unit-01/event/app/neuro_demo_app/**",
                            "listener_mode": "callback",
                            "handler_audit": {"enabled": False, "executed": 0},
                            "events": [
                                {
                                    "keyexpr": "neuro/unit-01/event/app/neuro_demo_app/callback/value",
                                    "payload": {
                                        "semantic_topic": "unit.callback",
                                        "event_id": "evt-live-app-001",
                                        "source_kind": "unit_app",
                                        "source_node": "unit-01",
                                        "source_app": "neuro_demo_app",
                                        "event_type": "callback",
                                        "timestamp_wall": "2026-05-09T00:00:00Z",
                                        "priority": 20,
                                    },
                                    "payload_encoding": "json",
                                }
                            ],
                        }
                    ),
                )
            if "tool-manifest" in argv:
                return CommandExecutionResult(
                    exit_code=0,
                    stdout=json.dumps(
                        {
                            "ok": True,
                            "status": "ok",
                            "schema_version": TOOL_MANIFEST_SCHEMA_VERSION,
                            "tools": [
                                {
                                    "name": "system_state_sync",
                                    "description": "state sync",
                                    "argv_template": [
                                        "python",
                                        "neuro_cli/scripts/invoke_neuro_cli.py",
                                        "system",
                                        "state-sync",
                                        "--output",
                                        "json",
                                    ],
                                    "resource": "state sync aggregate",
                                    "required_arguments": ["--node"],
                                    "side_effect_level": "read_only",
                                    "lease_requirements": [],
                                    "timeout_seconds": 10,
                                    "retryable": True,
                                    "approval_required": False,
                                    "cleanup_hints": [],
                                    "output_contract": {"format": "json", "top_level_ok": True},
                                }
                            ],
                        }
                    ),
                )
            if "state-sync" in argv:
                return CommandExecutionResult(
                    exit_code=0,
                    stdout=json.dumps(
                        {
                            "ok": True,
                            "status": "ok",
                            "schema_version": "1.2.0-state-sync-v1",
                            "state": {
                                "device": {"ok": True, "status": "ok", "payload": {"network_state": "NETWORK_READY"}},
                                "apps": {
                                    "ok": True,
                                    "status": "ok",
                                    "payload": {
                                        "app_count": 1,
                                        "apps": [{"app_id": "neuro_demo_app", "state": "running"}],
                                    },
                                },
                                "leases": {"ok": True, "status": "ok", "payload": {"leases": []}},
                            },
                            "recommended_next_actions": [
                                "state sync is clean; read-only delegated reasoning may continue"
                            ],
                        }
                    ),
                )
            raise AssertionError(f"unexpected argv: {argv}")

        adapter = NeuroCliToolAdapter(runner=runner)
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "core.db")
            live_event_file = Path(tmpdir) / "live-event-smoke.json"
            e2e_file = Path(tmpdir) / "real-scene-e2e.json"
            coding_agent_route_file = Path(tmpdir) / "coding-agent-route.json"

            run_no_model_dry_run(db_path, session_id="closure-summary-real-scene-001")
            live_out = io.StringIO()
            with mock.patch("neurolink_core.cli.NeuroCliToolAdapter", return_value=adapter):
                with redirect_stdout(live_out):
                    live_code = core_cli_main(
                        [
                            "live-event-smoke",
                            "--app-id",
                            "neuro_demo_app",
                            "--duration",
                            "1",
                            "--max-events",
                            "1",
                        ]
                    )
            live_event_file.write_text(live_out.getvalue(), encoding="utf-8")

            coding_agent_route_out = io.StringIO()
            with redirect_stdout(coding_agent_route_out):
                coding_agent_route_code = core_cli_main(
                    [
                        "coding-agent-self-improvement-route",
                        "--runner",
                        "copilot",
                        "--summary",
                        "Repair deterministic regression in sandbox",
                        "--decision",
                        "approve",
                        "--tests-passed",
                        "--lint-passed",
                        "--smoke-passed",
                        "--evidence-ref=pytest.txt",
                    ]
                )
            coding_agent_route_file.write_text(
                coding_agent_route_out.getvalue(), encoding="utf-8"
            )

            e2e_out = io.StringIO()
            with redirect_stdout(e2e_out):
                e2e_code = core_cli_main(
                    [
                        "real-scene-e2e-smoke",
                        "--live-event-smoke-file",
                        str(live_event_file),
                        "--coding-agent-route-file",
                        str(coding_agent_route_file),
                    ]
                )
            e2e_file.write_text(e2e_out.getvalue(), encoding="utf-8")

            summary_out = io.StringIO()
            with redirect_stdout(summary_out):
                summary_code = core_cli_main(
                    [
                        "closure-summary",
                        "--db",
                        db_path,
                        "--session-id",
                        "closure-summary-real-scene-001",
                        "--real-scene-e2e-file",
                        str(e2e_file),
                        "--coding-agent-route-file",
                        str(coding_agent_route_file),
                    ]
                )

        self.assertEqual(live_code, 0)
        self.assertEqual(coding_agent_route_code, 0)
        self.assertEqual(e2e_code, 0)
        self.assertEqual(summary_code, 0)
        payload = json.loads(summary_out.getvalue())
        self.assertTrue(payload["validation_gates"]["real_scene_e2e_gate"])
        self.assertTrue(payload["validation_gates"]["coding_agent_route_gate"])
        self.assertTrue(payload["real_scene_e2e_summary"]["ok"])
        self.assertTrue(payload["coding_agent_route_summary"]["ok"])
        self.assertTrue(
            payload["coding_agent_route_summary"]["closure_gates"][
                "plan_artifact_contract_supported"
            ]
        )
        self.assertTrue(
            payload["coding_agent_route_summary"]["closure_gates"][
                "plan_steps_recorded"
            ]
        )

    def test_cli_closure_summary_includes_memory_governance_bundle_for_local_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "core.db")

            run_out = io.StringIO()
            with redirect_stdout(run_out):
                run_code = core_cli_main(
                    [
                        "no-model-dry-run",
                        "--db",
                        db_path,
                        "--session-id",
                        "closure-summary-memory-001",
                        "--memory-backend",
                        "local",
                    ]
                )

            summary_out = io.StringIO()
            with redirect_stdout(summary_out):
                summary_code = core_cli_main(
                    [
                        "closure-summary",
                        "--db",
                        db_path,
                        "--session-id",
                        "closure-summary-memory-001",
                    ]
                )

        self.assertEqual(run_code, 0)
        self.assertEqual(summary_code, 0)
        payload = json.loads(summary_out.getvalue())
        self.assertTrue(payload["aggregate_gates"]["memory_governance_gate_satisfied"])
        self.assertTrue(payload["aggregate_gates"]["memory_recall_gate_satisfied"])
        self.assertTrue(payload["aggregate_gates"]["tool_skill_mcp_gate_satisfied"])
        self.assertFalse(payload["validation_gate_summary"]["ok"])
        self.assertFalse(payload["validation_gates"]["documentation_gate"])
        self.assertFalse(payload["validation_gates"]["federation_gate"])
        self.assertTrue(payload["validation_gates"]["memory_governance_gate"])
        self.assertTrue(payload["validation_gates"]["tool_skill_mcp_gate"])
        execution_summary = payload["execution_summaries"][0]
        self.assertEqual(execution_summary["memory_governance_summary"]["candidate_count"], 2)
        self.assertEqual(execution_summary["memory_governance_summary"]["committed_memory_count"], 1)
        self.assertEqual(execution_summary["memory_governance_summary"]["rejected_candidate_count"], 1)
        self.assertEqual(execution_summary["memory_governance_summary"]["commit_backends"], ["local_sqlite"])
        self.assertEqual(execution_summary["memory_governance_summary"]["rejection_reasons"], ["ephemeral_telemetry_not_retained"])
        self.assertEqual(execution_summary["memory_recall_summary"]["affective_selected_count"], 0)
        self.assertEqual(execution_summary["memory_recall_summary"]["rational_selected_count"], 0)
        self.assertTrue(execution_summary["tool_skill_mcp_summary"]["ok"])

    def test_cli_closure_summary_records_invalid_provider_tool_rejection_in_tool_skill_mcp_bundle(self) -> None:
        class FakeProviderClient:
            provider_client_kind = "test_client"

            def decide(
                self,
                frame: Any,
                memory_items: list[dict[str, Any]],
                profile: Any,
            ) -> dict[str, Any]:
                del frame, memory_items, profile
                return {
                    "delegated": True,
                    "reason": "real_provider_affective_decision",
                    "salience": 93,
                }

            def plan(
                self,
                decision: Any,
                frame: Any,
                profile: Any,
                available_tools: list[dict[str, Any]],
                session_context: dict[str, Any],
            ) -> dict[str, Any]:
                del decision, frame, profile, available_tools, session_context
                return {
                    "tool_name": "system_unknown_write",
                    "args": {"source": "real-provider"},
                    "reason": "hallucinated_tool_from_provider",
                }

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "core.db")
            with mock.patch.dict(
                os.environ,
                {"OPENAI_API_KEY": "secret", "OPENAI_MODEL": "gpt-4.1-mini"},
                clear=False,
            ):
                with mock.patch("neurolink_core.maf.find_spec", return_value=object()):
                    payload = run_no_model_dry_run(
                        db_path,
                        session_id="closure-summary-tool-skill-mcp-001",
                        maf_provider_mode="real_provider",
                        allow_model_call=True,
                        provider_client=FakeProviderClient(),
                    )

            summary_out = io.StringIO()
            with redirect_stdout(summary_out):
                summary_code = core_cli_main(
                    [
                        "closure-summary",
                        "--db",
                        db_path,
                        "--session-id",
                        "closure-summary-tool-skill-mcp-001",
                    ]
                )

        self.assertEqual(
            payload["tool_results"][0]["payload"]["failure_status"],
            "rational_plan_tool_not_in_available_tools",
        )
        self.assertEqual(summary_code, 0)
        summary_payload = json.loads(summary_out.getvalue())
        execution_summary = summary_payload["execution_summaries"][0]
        self.assertTrue(summary_payload["aggregate_gates"]["tool_skill_mcp_gate_satisfied"])
        self.assertTrue(summary_payload["validation_gates"]["tool_skill_mcp_gate"])
        self.assertTrue(execution_summary["tool_skill_mcp_summary"]["invalid_tool_rejected"])
        self.assertTrue(execution_summary["tool_skill_mcp_summary"]["closure_gates"]["available_tools_only_enforced"])
        self.assertTrue(execution_summary["tool_skill_mcp_summary"]["ok"])

    def test_cli_closure_summary_exposes_release_validation_gate_matrix_when_evidence_is_supplied(self) -> None:
        def live_runner(argv: list[str], timeout_seconds: int) -> CommandExecutionResult:
            del timeout_seconds
            if "app-events" in argv:
                return CommandExecutionResult(
                    exit_code=0,
                    stdout=json.dumps(
                        {
                            "ok": True,
                            "subscription": "neuro/unit-01/event/app/neuro_demo_app/**",
                            "listener_mode": "callback",
                            "handler_audit": {"enabled": False, "executed": 0},
                            "events": [
                                {
                                    "keyexpr": "neuro/unit-01/event/app/neuro_demo_app/callback/value",
                                    "payload": {
                                        "semantic_topic": "unit.callback",
                                        "event_id": "evt-live-app-001",
                                        "source_kind": "unit_app",
                                        "source_node": "unit-01",
                                        "source_app": "neuro_demo_app",
                                        "event_type": "callback",
                                        "timestamp_wall": "2026-05-09T00:00:00Z",
                                        "priority": 20,
                                    },
                                    "payload_encoding": "json",
                                }
                            ],
                        }
                    ),
                )
            if "tool-manifest" in argv:
                return CommandExecutionResult(
                    exit_code=0,
                    stdout=json.dumps(
                        {
                            "ok": True,
                            "status": "ok",
                            "schema_version": TOOL_MANIFEST_SCHEMA_VERSION,
                            "tools": [
                                {
                                    "name": "system_state_sync",
                                    "description": "state sync",
                                    "argv_template": [
                                        "python",
                                        "neuro_cli/scripts/invoke_neuro_cli.py",
                                        "system",
                                        "state-sync",
                                        "--output",
                                        "json",
                                    ],
                                    "resource": "state sync aggregate",
                                    "required_arguments": ["--node"],
                                    "side_effect_level": "read_only",
                                    "lease_requirements": [],
                                    "timeout_seconds": 10,
                                    "retryable": True,
                                    "approval_required": False,
                                    "cleanup_hints": [],
                                    "output_contract": {"format": "json", "top_level_ok": True},
                                }
                            ],
                        }
                    ),
                )
            if "state-sync" in argv:
                return CommandExecutionResult(
                    exit_code=0,
                    stdout=json.dumps(
                        {
                            "ok": True,
                            "status": "ok",
                            "schema_version": "1.2.0-state-sync-v1",
                            "state": {
                                "device": {"ok": True, "status": "ok", "payload": {"network_state": "NETWORK_READY"}},
                                "apps": {
                                    "ok": True,
                                    "status": "ok",
                                    "payload": {
                                        "app_count": 1,
                                        "apps": [{"app_id": "neuro_demo_app", "state": "running"}],
                                    },
                                },
                                "leases": {"ok": True, "status": "ok", "payload": {"leases": []}},
                            },
                            "recommended_next_actions": [
                                "state sync is clean; read-only delegated reasoning may continue"
                            ],
                        }
                    ),
                )
            raise AssertionError(f"unexpected argv: {argv}")

        live_adapter = NeuroCliToolAdapter(runner=live_runner)

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "core.db")
            documentation_file = Path(tmpdir) / "documentation.json"
            provider_smoke_file = Path(tmpdir) / "provider-smoke.json"
            multimodal_profile_file = Path(tmpdir) / "multimodal-profile.json"
            regression_file = Path(tmpdir) / "regression.json"
            relay_failure_file = Path(tmpdir) / "relay-failure.json"
            source_dir = Path(tmpdir) / "source"
            artifact_path = Path(tmpdir) / "artifacts" / "neuro_unit_app.llext"
            hardware_file = Path(tmpdir) / "hardware-compatibility.json"
            matrix_file = Path(tmpdir) / "hardware-acceptance-matrix.json"
            resource_budget_file = Path(tmpdir) / "resource-budget-governance.json"
            excellence_file = Path(tmpdir) / "agent-excellence.json"
            signing_file = Path(tmpdir) / "signing-provenance.json"
            activate_failure_file = Path(tmpdir) / "activate-failure.json"
            observability_file = Path(tmpdir) / "observability-diagnosis.json"
            rollback_file = Path(tmpdir) / "rollback.json"
            release_rollback_file = Path(tmpdir) / "release-rollback.json"
            live_event_file = Path(tmpdir) / "live-event-smoke.json"
            real_scene_file = Path(tmpdir) / "real-scene-e2e.json"
            autonomy_file = Path(tmpdir) / "autonomy-daemon.json"
            task_tracking_file = Path(tmpdir) / "task-tracking.json"
            memory_maintenance_file = Path(tmpdir) / "memory-maintenance.json"
            self_optimization_file = Path(tmpdir) / "self-optimization.json"
            world_model_context_file = Path(tmpdir) / "world-model-context.json"
            vitality_file = Path(tmpdir) / "vitality-smoke.json"
            persona_file = Path(tmpdir) / "persona-state.json"
            social_adapter_file = Path(tmpdir) / "social-adapter.json"
            qq_gateway_run_file = Path(tmpdir) / "qq-gateway-run.json"
            qq_gateway_file = Path(tmpdir) / "qq-gateway-closure.json"
            wecom_gateway_run_file = Path(tmpdir) / "wecom-gateway-run.json"
            wecom_gateway_file = Path(tmpdir) / "wecom-gateway-closure.json"
            openclaw_gateway_run_file = Path(tmpdir) / "openclaw-gateway-run.json"
            openclaw_gateway_file = Path(tmpdir) / "openclaw-gateway-closure.json"
            approval_social_file = Path(tmpdir) / "approval-social.json"
            self_improvement_file = Path(tmpdir) / "self-improvement.json"
            coding_agent_route_file = Path(tmpdir) / "coding-agent-route.json"

            run_payload = run_no_model_dry_run(
                db_path,
                session_id="closure-summary-gates-001",
                memory_backend="local",
                federation_route_provider=lambda frame, session_context: federation_route_smoke(
                    target_node="unit-remote-01",
                    now="2026-05-10T12:00:00Z",
                    required_trust_scope="lab-federation",
                    peer_expires_at="2026-05-10T12:30:00Z",
                    peer_relay_via=("gateway-b-01",),
                    peer_network_transports=("ethernet", "serial_bridge"),
                ),
            )
            run_code = 0

            documentation_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.2.5-documentation-closure-v1",
                        "status": "ready",
                        "reason": "documentation_aligned",
                        "closure_gates": {
                            "release_plan_aligned": True,
                            "readme_aligned": True,
                            "progress_recorded": True,
                            "runbooks_aligned": True,
                            "release_identity_unpromoted": True,
                        },
                        "evidence_summary": {"release_identity": "1.2.4"},
                    }
                ),
                encoding="utf-8",
            )
            provider_smoke_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.2.5-maf-provider-smoke-v2",
                        "status": "ready",
                        "reason": "provider_available_no_call",
                        "call_status": "skipped",
                        "executes_model_call": False,
                        "closure_gates": {
                            "closure_smoke_outcome_recorded": True,
                            "real_provider_call_opt_in_respected": True,
                            "provider_requirements_ready": True,
                            "missing_requirements_cleanly_reported": False,
                            "model_call_evidence_present": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            multimodal_profile_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.2.5-inference-route-v1",
                        "status": "ready",
                        "reason": "route_ready",
                        "executes_model_call": False,
                        "closure_gates": {
                            "multimodal_input_recorded": True,
                            "route_decision_recorded": True,
                            "profile_readiness_recorded": True,
                            "route_ready": True,
                            "no_model_call_executed": True,
                        },
                        "evidence_summary": {
                            "input_modes": ["text"],
                            "selected_profile": "local_16g",
                        },
                    }
                ),
                encoding="utf-8",
            )
            regression_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.2.6-regression-closure-v2",
                        "status": "ready",
                        "reason": "focused_agent_release124_federation_relay_hardware_regressions_green",
                        "closure_gates": {
                            "core_tests_passed": True,
                            "agent_closure_regression_passed": True,
                            "app_lifecycle_regression_passed": True,
                            "event_service_regression_passed": True,
                            "federation_regression_passed": True,
                            "relay_regression_passed": True,
                            "hardware_compatibility_regression_passed": True,
                        },
                        "evidence_summary": {"command_count": 6},
                    }
                ),
                encoding="utf-8",
            )
            self._write_fake_app_source(
                source_dir,
                app_id="neuro_unit_app",
                app_version="1.2.2",
                build_id="neuro_unit_app-1.2.2-cbor-v2",
            )
            self._write_fake_llext(
                artifact_path,
                app_id="neuro_unit_app",
                app_version="1.2.2",
                build_id="neuro_unit_app-1.2.2-cbor-v2",
            )
            hardware_out = io.StringIO()
            with redirect_stdout(hardware_out):
                hardware_code = core_cli_main(
                    [
                        "hardware-compatibility-smoke",
                        "--app-id",
                        "neuro_unit_app",
                        "--app-source-dir",
                        str(source_dir),
                        "--artifact-file",
                        str(artifact_path),
                        "--required-heap-free-bytes",
                        "4096",
                        "--required-app-slot-bytes",
                        "32768",
                    ]
                )
            hardware_file.write_text(hardware_out.getvalue(), encoding="utf-8")
            resource_budget_out = io.StringIO()
            with redirect_stdout(resource_budget_out):
                resource_budget_code = core_cli_main(
                    [
                        "resource-budget-governance-smoke",
                        "--hardware-compatibility-file",
                        str(hardware_file),
                    ]
                )
            resource_budget_file.write_text(
                resource_budget_out.getvalue(), encoding="utf-8"
            )
            matrix_out = io.StringIO()
            with redirect_stdout(matrix_out):
                matrix_code = core_cli_main(
                    [
                        "hardware-acceptance-matrix",
                        "--app-id",
                        "neuro_unit_app",
                        "--app-source-dir",
                        str(source_dir),
                        "--artifact-file",
                        str(artifact_path),
                    ]
                )
            matrix_file.write_text(matrix_out.getvalue(), encoding="utf-8")
            excellence_out = io.StringIO()
            with redirect_stdout(excellence_out):
                excellence_code = core_cli_main([
                    "agent-excellence-smoke",
                ])
            excellence_file.write_text(excellence_out.getvalue(), encoding="utf-8")
            signing_out = io.StringIO()
            with redirect_stdout(signing_out):
                signing_code = core_cli_main(
                    [
                        "signing-provenance-smoke",
                        "--app-id",
                        "neuro_unit_app",
                        "--app-source-dir",
                        str(source_dir),
                        "--artifact-file",
                        str(artifact_path),
                    ]
                )
            signing_file.write_text(signing_out.getvalue(), encoding="utf-8")
            live_event_out = io.StringIO()
            with mock.patch("neurolink_core.cli.NeuroCliToolAdapter", return_value=live_adapter):
                with redirect_stdout(live_event_out):
                    live_event_code = core_cli_main(
                        [
                            "live-event-smoke",
                            "--app-id",
                            "neuro_demo_app",
                            "--duration",
                            "1",
                            "--max-events",
                            "1",
                        ]
                    )
            live_event_file.write_text(live_event_out.getvalue(), encoding="utf-8")
            real_scene_out = io.StringIO()
            with redirect_stdout(real_scene_out):
                real_scene_code = core_cli_main(
                    [
                        "real-scene-e2e-smoke",
                        "--live-event-smoke-file",
                        str(live_event_file),
                    ]
                )
            real_scene_file.write_text(real_scene_out.getvalue(), encoding="utf-8")
            autonomy_out = io.StringIO()
            with redirect_stdout(autonomy_out):
                autonomy_code = core_cli_main([
                    "autonomy-daemon-smoke",
                ])
            autonomy_file.write_text(autonomy_out.getvalue(), encoding="utf-8")
            task_tracking_out = io.StringIO()
            with redirect_stdout(task_tracking_out):
                task_tracking_code = core_cli_main([
                    "task-tracking-smoke",
                ])
            task_tracking_file.write_text(
                task_tracking_out.getvalue(), encoding="utf-8"
            )
            memory_maintenance_out = io.StringIO()
            with redirect_stdout(memory_maintenance_out):
                memory_maintenance_code = core_cli_main([
                    "memory-maintenance-smoke",
                ])
            memory_maintenance_file.write_text(
                memory_maintenance_out.getvalue(), encoding="utf-8"
            )
            self_optimization_out = io.StringIO()
            with redirect_stdout(self_optimization_out):
                self_optimization_code = core_cli_main([
                    "self-optimization-smoke",
                ])
            self_optimization_file.write_text(
                self_optimization_out.getvalue(), encoding="utf-8"
            )
            world_model_context_out = io.StringIO()
            with redirect_stdout(world_model_context_out):
                world_model_context_code = core_cli_main([
                    "world-model-context-smoke",
                ])
            world_model_context_file.write_text(
                world_model_context_out.getvalue(), encoding="utf-8"
            )
            vitality_out = io.StringIO()
            with redirect_stdout(vitality_out):
                vitality_code = core_cli_main([
                    "vitality-smoke",
                ])
            vitality_file.write_text(vitality_out.getvalue(), encoding="utf-8")
            persona_out = io.StringIO()
            with redirect_stdout(persona_out):
                persona_code = core_cli_main([
                    "persona-state-smoke",
                ])
            persona_file.write_text(persona_out.getvalue(), encoding="utf-8")
            social_adapter_out = io.StringIO()
            with redirect_stdout(social_adapter_out):
                social_adapter_code = core_cli_main([
                    "social-adapter-smoke",
                ])
            social_adapter_file.write_text(social_adapter_out.getvalue(), encoding="utf-8")
            qq_gateway_run_file.write_text(
                json.dumps(
                    {
                        "schema_version": "2.2.2-qq-official-gateway-client-v1",
                        "command": "qq-official-gateway-client",
                        "status": "ready",
                        "reason": "qq_official_gateway_dispatch_processed",
                        "closure_gates": {
                            "gateway_connected": True,
                            "hello_recorded": True,
                            "ready_recorded": True,
                            "dispatch_processed": True,
                            "core_ingress_recorded": True,
                            "bounded_runtime": True,
                        },
                        "gateway": {"url": "wss://api.sgroup.qq.com/websocket"},
                        "session_id": "qq-session-gates-001",
                        "bot_user_id": "bot-001",
                        "dispatch_event_count": 1,
                        "core_results": [{"events_persisted": 1}],
                        "reconnect_count": 1,
                        "resume_attempt_count": 1,
                        "resume_success_count": 1,
                        "resumed_event_count": 1,
                        "session_state_file": "/tmp/qq-gateway-session.json",
                        "session_state_persisted": True,
                    }
                ),
                encoding="utf-8",
            )
            qq_gateway_out = io.StringIO()
            with redirect_stdout(qq_gateway_out):
                qq_gateway_code = core_cli_main(
                    [
                        "qq-official-gateway-closure",
                        "--gateway-run-file",
                        str(qq_gateway_run_file),
                        "--require-resume-evidence",
                    ]
                )
            qq_gateway_file.write_text(qq_gateway_out.getvalue(), encoding="utf-8")
            wecom_gateway_run_file.write_text(
                json.dumps(
                    {
                        "schema_version": "2.2.3-wecom-gateway-client-v1",
                        "command": "wecom-gateway-client",
                        "status": "ready",
                        "reason": "wecom_gateway_dispatch_processed",
                        "closure_gates": {
                            "gateway_connected": True,
                            "auth_sent": True,
                            "ready_recorded": True,
                            "dispatch_processed": True,
                            "core_ingress_recorded": True,
                            "bounded_runtime": True,
                        },
                        "gateway": {
                            "url": "wss://qyapi.weixin.qq.com/cgi-bin/websocket"
                        },
                        "bot_user_id": "wecom-bot-001",
                        "dispatch_event_count": 1,
                        "core_results": [{"events_persisted": 1}],
                    }
                ),
                encoding="utf-8",
            )
            wecom_gateway_out = io.StringIO()
            with redirect_stdout(wecom_gateway_out):
                wecom_gateway_code = core_cli_main(
                    [
                        "wecom-gateway-closure",
                        "--gateway-run-file",
                        str(wecom_gateway_run_file),
                    ]
                )
            wecom_gateway_file.write_text(
                wecom_gateway_out.getvalue(),
                encoding="utf-8",
            )
            openclaw_gateway_run_file.write_text(
                json.dumps(
                    {
                        "schema_version": "2.2.3-openclaw-gateway-client-v1",
                        "command": "openclaw-gateway-client",
                        "status": "ready",
                        "reason": "openclaw_gateway_dispatch_processed",
                        "adapter_kind": "qq_openclaw",
                        "closure_gates": {
                            "gateway_connected": True,
                            "bind_sent": True,
                            "ready_recorded": True,
                            "plugin_identified": True,
                            "dispatch_processed": True,
                            "core_ingress_recorded": True,
                            "bounded_runtime": True,
                        },
                        "gateway": {
                            "url": "ws://127.0.0.1:8811/openclaw",
                            "transport_kind": "openclaw_gateway",
                            "runtime_host": "openclaw",
                        },
                        "plugin": {
                            "plugin_id": "qq_openclaw",
                            "plugin_package": "operator-supplied-qq-openclaw-package",
                            "installer_package": "operator-supplied-qq-openclaw-installer",
                            "host_version": "0.9.2",
                            "ready": True,
                        },
                        "dispatch_event_count": 1,
                        "core_results": [{"events_persisted": 1}],
                    }
                ),
                encoding="utf-8",
            )
            openclaw_gateway_out = io.StringIO()
            with redirect_stdout(openclaw_gateway_out):
                openclaw_gateway_code = core_cli_main(
                    [
                        "openclaw-gateway-closure",
                        "--gateway-run-file",
                        str(openclaw_gateway_run_file),
                    ]
                )
            openclaw_gateway_file.write_text(
                openclaw_gateway_out.getvalue(),
                encoding="utf-8",
            )
            approval_social_out = io.StringIO()
            with redirect_stdout(approval_social_out):
                approval_social_code = core_cli_main([
                    "approval-social-smoke",
                ])
            approval_social_file.write_text(approval_social_out.getvalue(), encoding="utf-8")
            self_improvement_out = io.StringIO()
            with redirect_stdout(self_improvement_out):
                self_improvement_code = core_cli_main([
                    "self-improvement-smoke",
                ])
            self_improvement_file.write_text(
                self_improvement_out.getvalue(), encoding="utf-8"
            )
            coding_agent_route_out = io.StringIO()
            with redirect_stdout(coding_agent_route_out):
                coding_agent_route_code = core_cli_main(
                    [
                        "coding-agent-self-improvement-route",
                        "--runner",
                        "copilot",
                        "--summary",
                        "Repair deterministic regression in sandbox",
                        "--decision",
                        "approve",
                        "--tests-passed",
                        "--lint-passed",
                        "--smoke-passed",
                        "--evidence-ref=pytest.txt",
                    ]
                )
            coding_agent_route_file.write_text(
                coding_agent_route_out.getvalue(), encoding="utf-8"
            )
            relay_failure_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.2.6-relay-failure-closure-v1",
                        "status": "ready",
                        "reason": "route_failure_runbook_reviewed",
                        "closure_gates": {
                            "route_failure_recorded": True,
                            "fallback_path_recorded": True,
                            "operator_runbook_recorded": True,
                            "deterministic_validation_recorded": True,
                        },
                        "evidence_summary": {
                            "route_failure_reason": "peer_unreachable",
                            "fallback_action": "direct_local_retry_then_manual_operator_review",
                            "runbook_id": "relay-route-failure-v1",
                        },
                    }
                ),
                encoding="utf-8",
            )
            activate_failure_file.write_text(
                json.dumps(
                    {
                        "ok": False,
                        "status": "error",
                        "command": "app-deploy-activate",
                        "failure_class": "app_deploy_activate_failed",
                        "failure_status": "rollback_required",
                        "recovery_candidate_summary": {
                            "app_id": "neuro_demo_gpio",
                            "rollback_decision": "operator_review_required",
                            "lease_resource": "update/app/neuro_demo_gpio/rollback",
                            "matching_lease_ids": ["lease-gpio-rollback-gates-001"],
                        },
                        "rollback_approval": {
                            "status": "pending_approval",
                            "cleanup_hint": "confirm rollback evidence, lease ownership, and target app identity before resume",
                        },
                    }
                ),
                encoding="utf-8",
            )
            observability_out = io.StringIO()
            with redirect_stdout(observability_out):
                observability_code = core_cli_main(
                    [
                        "observability-diagnosis-smoke",
                        "--relay-failure-file",
                        str(relay_failure_file),
                        "--activate-failure-file",
                        str(activate_failure_file),
                    ]
                )
            observability_file.write_text(observability_out.getvalue(), encoding="utf-8")
            rollback_file.write_text(
                json.dumps(
                    {
                        "ok": True,
                        "status": "ok",
                        "command": "app-deploy-rollback",
                        "rollback_decision": {
                            "approval_required": True,
                            "status": "approved",
                            "rollback_resource": "update/app/neuro_demo_gpio/rollback",
                            "resolved_app_id": "neuro_demo_gpio",
                            "rollback_reason": "guarded_rollback_after_activation_health_failure",
                        },
                        "rollback_execution": {
                            "completed_through": "query_leases",
                            "rollback": {"ok": True},
                            "query_apps": {
                                "ok": True,
                                "app_present": False,
                                "observed_app_state": "missing",
                            },
                            "query_leases": {"ok": True, "matching_lease_ids": []},
                        },
                    }
                ),
                encoding="utf-8",
            )
            release_rollback_out = io.StringIO()
            with redirect_stdout(release_rollback_out):
                release_rollback_code = core_cli_main(
                    [
                        "release-rollback-hardening-smoke",
                        "--activate-failure-file",
                        str(activate_failure_file),
                        "--rollback-file",
                        str(rollback_file),
                    ]
                )
            release_rollback_file.write_text(
                release_rollback_out.getvalue(), encoding="utf-8"
            )

            summary_out = io.StringIO()
            with redirect_stdout(summary_out):
                summary_code = core_cli_main(
                    [
                        "closure-summary",
                        "--db",
                        db_path,
                        "--session-id",
                        "closure-summary-gates-001",
                        "--documentation-file",
                        str(documentation_file),
                        "--provider-smoke-file",
                        str(provider_smoke_file),
                        "--multimodal-profile-file",
                        str(multimodal_profile_file),
                        "--regression-file",
                        str(regression_file),
                        "--relay-failure-file",
                        str(relay_failure_file),
                        "--hardware-compatibility-file",
                        str(hardware_file),
                        "--hardware-acceptance-matrix-file",
                        str(matrix_file),
                        "--resource-budget-governance-file",
                        str(resource_budget_file),
                        "--agent-excellence-file",
                        str(excellence_file),
                        "--release-rollback-file",
                        str(release_rollback_file),
                        "--signing-provenance-file",
                        str(signing_file),
                        "--observability-diagnosis-file",
                        str(observability_file),
                        "--real-scene-e2e-file",
                        str(real_scene_file),
                        "--autonomy-daemon-file",
                        str(autonomy_file),
                        "--task-tracking-file",
                        str(task_tracking_file),
                        "--memory-maintenance-file",
                        str(memory_maintenance_file),
                        "--self-optimization-file",
                        str(self_optimization_file),
                        "--world-model-context-file",
                        str(world_model_context_file),
                        "--vitality-smoke-file",
                        str(vitality_file),
                        "--persona-state-file",
                        str(persona_file),
                        "--social-adapter-file",
                        str(social_adapter_file),
                        "--qq-gateway-file",
                        str(qq_gateway_file),
                        "--wecom-gateway-file",
                        str(wecom_gateway_file),
                        "--openclaw-gateway-file",
                        str(openclaw_gateway_file),
                        "--approval-social-file",
                        str(approval_social_file),
                        "--self-improvement-file",
                        str(self_improvement_file),
                        "--coding-agent-route-file",
                        str(coding_agent_route_file),
                    ]
                )

        self.assertEqual(run_code, 0)
        self.assertEqual(hardware_code, 0)
        self.assertEqual(resource_budget_code, 0)
        self.assertEqual(matrix_code, 0)
        self.assertEqual(excellence_code, 0)
        self.assertEqual(observability_code, 0)
        self.assertEqual(release_rollback_code, 0)
        self.assertEqual(signing_code, 0)
        self.assertEqual(live_event_code, 0)
        self.assertEqual(real_scene_code, 0)
        self.assertEqual(autonomy_code, 0)
        self.assertEqual(task_tracking_code, 0)
        self.assertEqual(memory_maintenance_code, 0)
        self.assertEqual(self_optimization_code, 0)
        self.assertEqual(world_model_context_code, 0)
        self.assertEqual(vitality_code, 0)
        self.assertEqual(persona_code, 0)
        self.assertEqual(social_adapter_code, 0)
        self.assertEqual(qq_gateway_code, 0)
        self.assertEqual(wecom_gateway_code, 0)
        self.assertEqual(openclaw_gateway_code, 0)
        self.assertEqual(approval_social_code, 0)
        self.assertEqual(self_improvement_code, 0)
        self.assertEqual(coding_agent_route_code, 0)
        self.assertEqual(summary_code, 0)
        self.assertEqual(run_payload["execution_evidence"]["audit_record"]["payload"]["session_context"]["federation_route_evidence"]["route_decision"]["route_kind"], "delegated_core")
        payload = json.loads(summary_out.getvalue())
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["validation_gate_summary"]["ok"])
        self.assertEqual(payload["validation_gate_summary"]["passed_count"], 38)
        self.assertEqual(payload["validation_gate_summary"]["failed_gate_ids"], [])
        self.assertTrue(all(payload["validation_gates"].values()))
        self.assertTrue(payload["validation_gates"]["closure_summary_gate"])
        self.assertTrue(payload["validation_gates"]["hardware_acceptance_matrix_gate"])
        self.assertTrue(payload["validation_gates"]["restricted_unit_compatibility_gate"])
        self.assertTrue(payload["validation_gates"]["resource_budget_governance_gate"])
        self.assertTrue(payload["validation_gates"]["autonomous_daemon_gate"])
        self.assertTrue(payload["validation_gates"]["autonomy_heartbeat_gate"])
        self.assertTrue(payload["validation_gates"]["task_tracking_replay_gate"])
        self.assertTrue(payload["validation_gates"]["memory_maintenance_gate"])
        self.assertTrue(payload["validation_gates"]["self_optimization_gate"])
        self.assertTrue(payload["validation_gates"]["world_model_context_gate"])
        self.assertTrue(payload["validation_gates"]["vitality_governance_gate"])
        self.assertTrue(payload["validation_gates"]["persona_persistence_gate"])
        self.assertTrue(payload["validation_gates"]["persona_seed_gate"])
        self.assertTrue(payload["validation_gates"]["persona_growth_gate"])
        self.assertTrue(payload["validation_gates"]["memory_immutability_gate"])
        self.assertTrue(payload["validation_gates"]["social_adapter_gate"])
        self.assertTrue(payload["validation_gates"]["qq_official_gateway_gate"])
        self.assertTrue(payload["validation_gates"]["wecom_gateway_gate"])
        self.assertTrue(payload["validation_gates"]["openclaw_gateway_gate"])
        self.assertTrue(payload["validation_gates"]["approval_over_social_gate"])
        self.assertTrue(payload["validation_gates"]["self_improvement_sandbox_gate"])
        self.assertTrue(payload["validation_gates"]["coding_agent_route_gate"])
        self.assertTrue(payload["validation_gates"]["agent_excellence_gate"])
        self.assertTrue(payload["validation_gates"]["release_rollback_hardening_gate"])
        self.assertTrue(payload["validation_gates"]["signing_provenance_gate"])
        self.assertTrue(payload["validation_gates"]["observability_diagnosis_gate"])
        self.assertTrue(payload["validation_gates"]["real_scene_e2e_gate"])
        self.assertTrue(all(item["passed"] for item in payload["checklist"]))
        self.assertEqual(
            payload["documentation_summary"]["schema_version"],
            "1.2.5-documentation-closure-v1",
        )
        self.assertEqual(
            payload["regression_summary"]["schema_version"],
            "1.2.6-regression-closure-v2",
        )
        self.assertTrue(
            payload["social_adapter_summary"]["closure_gates"][
                "qq_openclaw_social_gate"
            ]
        )
        self.assertIn(
            "qq_openclaw",
            payload["social_adapter_summary"]["evidence_summary"][
                "ready_adapter_names"
            ],
        )
        self.assertIn(
            "qq_openclaw",
            payload["social_adapter_summary"]["evidence_summary"][
                "tested_adapter_names"
            ],
        )

    def test_low_salience_tick_does_not_delegate(self) -> None:
        data_store = CoreDataStore()
        workflow = NoModelCoreWorkflow(data_store=data_store)

        result = workflow.run(
            [
                {
                    "event_id": "evt-low-tick-001",
                    "source_kind": "clock",
                    "event_type": "time.tick",
                    "semantic_topic": "time.tick",
                    "timestamp_wall": "2026-05-04T00:00:00Z",
                    "priority": 10,
                }
            ]
        )

        self.assertFalse(result.delegated)
        self.assertEqual(result.final_response["speaker"], "affective")
        self.assertIn("no delegated action", result.final_response["text"])
        self.assertEqual(data_store.count("perception_events"), 1)
        self.assertEqual(data_store.count("execution_spans"), 1)
        self.assertEqual(data_store.count("facts"), 6)
        self.assertEqual(data_store.count("memory_candidates"), 1)
        self.assertEqual(data_store.count("policy_decisions"), 0)
        self.assertEqual(data_store.count("tool_results"), 0)
        self.assertEqual(data_store.count("audit_records"), 1)
        self.assertEqual(result.final_response["delivery_kind"], "observation_only")
        data_store.close()

    def test_low_priority_endpoint_drift_still_triggers_event_driven_notification(self) -> None:
        data_store = CoreDataStore()
        workflow = NoModelCoreWorkflow(data_store=data_store)

        result = workflow.run(
            [
                {
                    "event_id": "evt-endpoint-drift-001",
                    "source_kind": "unit",
                    "source_node": "unit-01",
                    "event_type": "state",
                    "semantic_topic": "unit.network.endpoint_drift",
                    "timestamp_wall": "2026-05-04T00:00:00Z",
                    "priority": 20,
                    "payload": {"expected_endpoint": "tcp/192.168.2.90:7447"},
                }
            ]
        )

        self.assertTrue(result.delegated)
        self.assertEqual(len(result.tool_results), 1)
        self.assertEqual(result.tool_results[0]["tool_name"], "system_state_sync")
        self.assertEqual(result.final_response["trigger_kind"], "event_driven_perception")
        self.assertEqual(result.final_response["delivery_kind"], "event_driven_notification")
        self.assertGreaterEqual(result.final_response["salience"], 85)
        audit_record = data_store.get_audit_record(result.audit_id)
        self.assertIsNotNone(audit_record)
        assert audit_record is not None
        self.assertEqual(
            audit_record["payload"]["decision"]["reason"],
            "network_endpoint_drift_requires_rational_window",
        )
        self.assertEqual(
            audit_record["payload"]["notification_summary"]["urgency"],
            "high",
        )
        data_store.close()

    def test_activate_failed_routes_to_health_guard_and_records_recovery_evidence(self) -> None:
        class MissingAppHealthGuardAdapter(FakeUnitToolAdapter):
            def execute(self, tool_name: str, args: dict[str, Any]) -> ToolExecutionResult:
                if tool_name == "system_query_leases":
                    contract = self.describe_tool(tool_name)
                    assert contract is not None
                    return ToolExecutionResult(
                        tool_result_id="tool-lease-observe-001",
                        tool_name=tool_name,
                        status="ok",
                        payload={
                            "contract": contract.to_dict(),
                            "result": {
                                "ok": True,
                                "status": "ok",
                                "payload": {"request_id": "req-lease-001"},
                                "replies": [
                                    {
                                        "ok": True,
                                        "payload": {
                                            "status": "ok",
                                            "leases": [
                                                {
                                                    "resource": "update/app/neuro_demo_gpio/rollback",
                                                    "lease_id": "lease-gpio-rollback-001",
                                                }
                                            ],
                                        },
                                    }
                                ],
                            },
                        },
                    )
                if tool_name == "system_rollback_app":
                    contract = self.describe_tool(tool_name)
                    assert contract is not None
                    return ToolExecutionResult(
                        tool_result_id="tool-rollback-001",
                        tool_name=tool_name,
                        status="ok",
                        payload={
                            "contract": contract.to_dict(),
                            "resolved_args": {
                                "app_id": str(args.get("app_id") or ""),
                                "app": str(args.get("app") or args.get("app_id") or ""),
                                "lease_id": str(args.get("lease_id") or ""),
                                "reason": str(args.get("reason") or ""),
                            },
                            "result": {
                                "ok": True,
                                "status": "ok",
                                "replies": [
                                    {
                                        "ok": True,
                                        "payload": {
                                            "status": "ok",
                                            "app_id": str(args.get("app_id") or ""),
                                            "action": "rollback",
                                        },
                                    }
                                ],
                            },
                        },
                    )
                return super().execute(tool_name, args)

            def build_state_sync_snapshot(self, args: dict[str, Any]) -> StateSyncSnapshot:
                event_ids = list(args.get("event_ids") or [])
                return StateSyncSnapshot(
                    status="ok",
                    state={
                        "device": StateSyncSurface(
                            ok=True,
                            status="ok",
                            payload={
                                "status": "ok",
                                "network_state": "NETWORK_READY",
                                "ipv4": "192.168.2.67",
                            },
                        ),
                        "apps": StateSyncSurface(
                            ok=True,
                            status="ok",
                            payload={
                                "status": "ok",
                                "app_count": 0,
                                "apps": [],
                                "observed_event_ids": event_ids,
                            },
                        ),
                        "leases": StateSyncSurface(
                            ok=True,
                            status="ok",
                            payload={"status": "ok", "leases": []},
                        ),
                    },
                    recommended_next_actions=(
                        "confirm activation evidence and prepare protected rollback review",
                    ),
                )

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "core.db")
            data_store = CoreDataStore(db_path)
            adapter = MissingAppHealthGuardAdapter()
            workflow = NoModelCoreWorkflow(
                data_store=data_store,
                tool_adapter=adapter,
            )

            result = workflow.run(
                [
                    {
                        "event_id": "evt-activate-failed-001",
                        "source_kind": "unit",
                        "source_node": "unit-01",
                        "source_app": "neuro_demo_gpio",
                        "event_type": "lifecycle",
                        "semantic_topic": "unit.lifecycle.activate_failed",
                        "timestamp_wall": "2026-05-04T00:00:00Z",
                        "priority": 20,
                        "payload": {"target_app_id": "neuro_demo_gpio"},
                    }
                ]
            )
            audit_record = data_store.get_audit_record(result.audit_id)
            approval_requests = data_store.get_approval_requests(
                source_execution_span_id=result.execution_span_id,
            )

            self.assertTrue(result.delegated)
            self.assertEqual(result.tool_results[0]["tool_name"], "system_activation_health_guard")
            self.assertEqual(result.tool_results[1]["tool_name"], "system_query_leases")
            self.assertEqual(result.tool_results[2]["tool_name"], "system_rollback_app")
            self.assertEqual(result.tool_results[2]["status"], "pending_approval")
            self.assertEqual(
                result.tool_results[0]["payload"]["activation_health"]["classification"],
                "rollback_required",
            )
            self.assertEqual(len(approval_requests), 1)
            self.assertEqual(approval_requests[0]["tool_name"], "system_rollback_app")
            self.assertIsNotNone(audit_record)
            assert audit_record is not None
            self.assertEqual(
                audit_record["payload"]["decision"]["reason"],
                "activate_failure_requires_rational_window",
            )
            self.assertEqual(
                audit_record["payload"]["activation_health_summary"]["classification"],
                "rollback_required",
            )
            self.assertTrue(
                audit_record["payload"]["activation_health_summary"]["ready_for_rollback_consideration"]
            )
            self.assertEqual(
                audit_record["payload"]["activation_health_summary"]["app_id"],
                "neuro_demo_gpio",
            )
            self.assertEqual(
                audit_record["payload"]["recovery_candidate_summary"]["rollback_decision"],
                "operator_review_required",
            )
            self.assertEqual(
                audit_record["payload"]["recovery_candidate_summary"]["lease_ownership_status"],
                "held",
            )
            self.assertEqual(
                audit_record["payload"]["recovery_candidate_summary"]["matching_lease_ids"],
                ["lease-gpio-rollback-001"],
            )
            activation_health_facts = data_store.get_facts(
                result.execution_span_id,
                fact_type="activation_health_observation",
            )
            self.assertEqual(len(activation_health_facts), 1)
            self.assertEqual(
                activation_health_facts[0]["subject"],
                "neuro_demo_gpio",
            )
            self.assertEqual(
                activation_health_facts[0]["payload"]["classification"],
                "rollback_required",
            )
            recovery_candidate_facts = data_store.get_facts(
                result.execution_span_id,
                fact_type="recovery_candidate",
            )
            self.assertEqual(len(recovery_candidate_facts), 1)
            self.assertEqual(
                recovery_candidate_facts[0]["payload"]["lease_ownership_status"],
                "held",
            )
            data_store.close()

            approve_payload = apply_approval_decision(
                db_path,
                approval_request_id=approval_requests[0]["approval_request_id"],
                decision="approve",
                tool_adapter=adapter,
            )

        self.assertTrue(approve_payload["ok"])
        self.assertEqual(approve_payload["status"], "approved")
        self.assertEqual(
            approve_payload["resumed_execution"]["tool_result"]["tool_name"],
            "system_rollback_app",
        )
        self.assertEqual(
            approve_payload["approval_context"]["operator_requirements"]["resolved_required_resources"],
            ["update/app/neuro_demo_gpio/rollback"],
        )
        self.assertEqual(
            approve_payload["approval_context"]["operator_requirements"]["matching_lease_ids"],
            ["lease-gpio-rollback-001"],
        )
        self.assertEqual(
            approve_payload["resumed_execution"]["tool_result"]["payload"]["resolved_args"]["lease_id"],
            "lease-gpio-rollback-001",
        )

    def test_file_backed_dry_run_reports_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            payload = run_no_model_dry_run(str(Path(tmpdir) / "core.db"))

        self.assertEqual(payload["status"], "ok")
        self.assertTrue(payload["session_id"].startswith("session-"))
        self.assertEqual(payload["final_response"]["speaker"], "affective")
        self.assertEqual(payload["db_counts"]["perception_events"], 2)
        self.assertEqual(payload["db_counts"]["execution_spans"], 1)
        self.assertEqual(payload["db_counts"]["facts"], 7)
        self.assertEqual(payload["db_counts"]["policy_decisions"], 1)
        self.assertEqual(payload["db_counts"]["memory_candidates"], 2)
        self.assertEqual(payload["db_counts"]["tool_results"], 1)
        self.assertEqual(payload["db_counts"]["audit_records"], 1)

    def test_event_replay_reports_duplicate_summary(self) -> None:
        replay_events = [sample_events()[0], sample_events()[0], sample_events()[1]]

        payload = run_event_replay(replay_events)

        self.assertEqual(payload["command"], "event-replay")
        self.assertEqual(payload["event_source"], "replay_file")
        self.assertEqual(payload["events_persisted"], 2)
        self.assertEqual(payload["db_counts"]["perception_events"], 2)
        self.assertEqual(payload["event_replay"]["provided_event_count"], 3)
        self.assertEqual(payload["event_replay"]["normalized_event_count"], 2)
        self.assertEqual(payload["event_replay"]["duplicate_event_count"], 1)
        self.assertEqual(
            payload["event_replay"]["replayed_topics"],
            ["time.tick", "unit.callback"],
        )

    def test_event_replay_can_record_federation_route_evidence(self) -> None:
        payload = run_event_replay(
            sample_events(),
            federation_route_provider=lambda frame, session_context: federation_route_smoke(
                target_node="unit-remote-01",
                now="2026-05-09T12:00:00Z",
                required_trust_scope="lab-federation",
            ),
        )

        session_context = payload["execution_evidence"]["audit_record"]["payload"]["session_context"]
        self.assertEqual(payload["event_source"], "replay_file")
        self.assertEqual(
            session_context["federation_route_evidence"]["route_decision"]["route_kind"],
            "delegated_core",
        )
        self.assertEqual(
            payload["execution_evidence"]["execution_span"]["payload"]["federation_route_status"],
            "route_ready",
        )

    def test_event_daemon_replay_dedupes_across_batches(self) -> None:
        callback = sample_events()[0]
        tick = sample_events()[1]
        daemon_payload = run_event_daemon_replay(
            [
                [callback],
                [callback, tick],
            ],
            session_id="session-daemon-001",
        )

        evidence = daemon_payload["event_daemon_evidence"]
        self.assertEqual(daemon_payload["command"], "event-daemon")
        self.assertEqual(daemon_payload["event_source"], "daemon_replay_file")
        self.assertEqual(daemon_payload["session_id"], "session-daemon-001")
        self.assertEqual(evidence["cycle_count"], 2)
        self.assertEqual(evidence["provided_event_count"], 3)
        self.assertEqual(evidence["normalized_event_count"], 2)
        self.assertEqual(evidence["duplicate_event_count"], 1)
        self.assertEqual(evidence["seeded_dedupe_key_count"], 0)
        self.assertEqual(evidence["dedupe_key_count"], 2)
        self.assertEqual(evidence["observed_topics"], ["time.tick", "unit.callback"])
        self.assertEqual(evidence["cycles"][0]["normalized_event_count"], 1)
        self.assertEqual(evidence["cycles"][1]["normalized_event_count"], 1)
        self.assertEqual(evidence["cycles"][1]["duplicate_event_count"], 1)
        self.assertEqual(daemon_payload["db_counts"]["perception_events"], 2)
        self.assertEqual(daemon_payload["db_counts"]["execution_spans"], 2)

    def test_event_daemon_replay_can_record_federation_route_evidence(self) -> None:
        callback = sample_events()[0]
        payload = run_event_daemon_replay(
            [[callback]],
            session_id="session-daemon-fed-001",
            federation_route_provider=lambda frame, session_context: federation_route_smoke(
                target_node="unit-remote-01",
                now="2026-05-09T12:00:00Z",
                required_trust_scope="lab-federation",
            ),
        )

        self.assertEqual(payload["event_daemon_evidence"]["cycle_count"], 1)
        self.assertEqual(payload["session_id"], "session-daemon-fed-001")
        self.assertEqual(payload["db_counts"]["audit_records"], 1)

        cycle = payload["event_daemon_evidence"]["cycles"][0]
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "daemon-fed.db")
            persisted = run_event_daemon_replay(
                [[callback]],
                db_path,
                session_id="session-daemon-fed-verify-001",
                federation_route_provider=lambda frame, session_context: federation_route_smoke(
                    target_node="unit-remote-01",
                    now="2026-05-09T12:00:00Z",
                    required_trust_scope="lab-federation",
                ),
            )
            verification_store = CoreDataStore(db_path)
            try:
                execution_span_id = str(
                    persisted["event_daemon_evidence"]["cycles"][0]["execution_span_id"]
                )
                audit_id = str(persisted["event_daemon_evidence"]["cycles"][0]["audit_id"])
                evidence = verification_store.build_execution_evidence(
                    execution_span_id,
                    audit_id,
                )
            finally:
                verification_store.close()

        self.assertEqual(cycle["status"], "ok")
        self.assertEqual(evidence["execution_span"]["payload"]["federation_route_kind"], "delegated_core")
        self.assertEqual(
            evidence["audit_record"]["payload"]["session_context"]["federation_route_evidence"]["status"],
            "route_ready",
        )

    def test_event_daemon_replay_seeds_dedupe_keys_from_existing_database(self) -> None:
        callback = sample_events()[0]
        tick = sample_events()[1]

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "daemon.db")
            first = run_event_daemon_replay(
                [[callback, tick]],
                db_path,
                session_id="session-daemon-seeded-001",
            )
            second = run_event_daemon_replay(
                [[callback, tick]],
                db_path,
                session_id="session-daemon-seeded-001",
            )

        self.assertEqual(first["event_daemon_evidence"]["normalized_event_count"], 2)
        self.assertEqual(second["event_daemon_evidence"]["seeded_dedupe_key_count"], 2)
        self.assertEqual(second["event_daemon_evidence"]["normalized_event_count"], 0)
        self.assertEqual(second["event_daemon_evidence"]["duplicate_event_count"], 2)
        self.assertEqual(second["db_counts"]["perception_events"], 2)
        self.assertEqual(second["db_counts"]["execution_spans"], 2)

    def test_event_daemon_replay_can_run_autonomous_cycle_planner(self) -> None:
        payload = run_event_daemon_replay(
            [[], []],
            session_id="session-daemon-autonomy-001",
            autonomy_enabled=True,
            autonomy_policy=AutonomousDaemonPolicy(maintenance_interval_cycles=2),
            vitality_state=VitalityState.from_score(60),
            persona_state=PersonaState(
                persona_id="affective-main",
                mood="watchful",
                vitality_summary="attentive",
            ),
        )

        evidence = payload["event_daemon_evidence"]
        self.assertTrue(evidence["autonomy_enabled"])
        self.assertEqual(evidence["cycle_count"], 2)
        self.assertEqual(evidence["provided_event_count"], 0)
        self.assertEqual(evidence["planned_event_count"], 3)
        self.assertEqual(evidence["normalized_event_count"], 2)
        self.assertEqual(evidence["observed_topics"], ["core.maintenance.tick", "time.tick"])
        self.assertEqual(evidence["daemon_state"]["run_state"], "idle")
        self.assertFalse(evidence["daemon_state"]["continuity"]["resumed_session"])
        self.assertEqual(evidence["daemon_state"]["continuity"]["previous_execution_count"], 0)
        self.assertEqual(evidence["daemon_state"]["continuity"]["seeded_dedupe_key_count"], 0)
        self.assertTrue(evidence["daemon_state"]["heartbeat"]["recorded"])
        self.assertEqual(evidence["daemon_state"]["heartbeat"]["status"], "idle")
        self.assertEqual(evidence["daemon_state"]["heartbeat"]["last_cycle_index"], 2)
        self.assertEqual(evidence["daemon_state"]["vitality_summary"]["state"], "attentive")
        self.assertEqual(evidence["daemon_state"]["persona_summary"]["mood"], "watchful")
        first_cycle = evidence["cycles"][0]
        second_cycle = evidence["cycles"][1]
        self.assertEqual(first_cycle["autonomy"]["wake_decision"], "sleep")
        self.assertEqual(first_cycle["execution_span_id"], "")
        self.assertEqual(first_cycle["autonomy"]["persona_summary"]["mood"], "watchful")
        self.assertEqual(second_cycle["autonomy"]["wake_decision"], "maintenance_only")
        self.assertEqual(second_cycle["autonomy"]["vitality_summary"]["state"], "attentive")
        self.assertEqual(second_cycle["planned_event_count"], 2)
        self.assertEqual(second_cycle["normalized_event_count"], 2)
        self.assertEqual(payload["db_counts"]["perception_events"], 2)
        self.assertEqual(payload["db_counts"]["execution_spans"], 1)

    def test_cli_core_daemon_outputs_daemon_state_summary(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            code = core_cli_main(
                [
                    "core-daemon",
                    "--cycles",
                    "2",
                    "--session-id",
                    "session-core-daemon-001",
                    "--maintenance-interval-cycles",
                    "2",
                    "--vitality-score",
                    "18",
                    "--persona-mood",
                    "watchful",
                ]
            )

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["command"], "core-daemon")
        self.assertEqual(payload["event_source"], "autonomy_synthetic_cycles")
        self.assertEqual(payload["session_id"], "session-core-daemon-001")
        self.assertTrue(payload["event_daemon_evidence"]["autonomy_enabled"])
        self.assertEqual(
            payload["event_daemon_evidence"]["daemon_state"]["persona_summary"]["mood"],
            "watchful",
        )
        self.assertEqual(
            payload["event_daemon_evidence"]["daemon_state"]["vitality_summary"]["state"],
            "critical",
        )

    def test_cli_core_daemon_supports_operator_paused_state(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            code = core_cli_main(
                [
                    "core-daemon",
                    "--cycles",
                    "2",
                    "--session-id",
                    "session-core-daemon-paused-001",
                    "--operator-paused",
                ]
            )

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        daemon_state = payload["event_daemon_evidence"]["daemon_state"]
        self.assertEqual(daemon_state["run_state"], "paused")
        self.assertTrue(daemon_state["operator_paused"])
        self.assertEqual(daemon_state["heartbeat"]["status"], "paused")
        self.assertEqual(payload["db_counts"]["execution_spans"], 0)

    def test_cli_core_daemon_records_restart_continuity(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "core-daemon.db")

            first_out = io.StringIO()
            with redirect_stdout(first_out):
                first_code = core_cli_main(
                    [
                        "core-daemon",
                        "--db",
                        db_path,
                        "--cycles",
                        "2",
                        "--session-id",
                        "session-core-daemon-restart-001",
                        "--maintenance-interval-cycles",
                        "2",
                    ]
                )

            second_out = io.StringIO()
            with redirect_stdout(second_out):
                second_code = core_cli_main(
                    [
                        "core-daemon",
                        "--db",
                        db_path,
                        "--cycles",
                        "1",
                        "--session-id",
                        "session-core-daemon-restart-001",
                    ]
                )

        self.assertEqual(first_code, 0)
        self.assertEqual(second_code, 0)
        first_payload = json.loads(first_out.getvalue())
        second_payload = json.loads(second_out.getvalue())
        self.assertFalse(
            first_payload["event_daemon_evidence"]["daemon_state"]["continuity"]["resumed_session"]
        )
        self.assertTrue(
            second_payload["event_daemon_evidence"]["daemon_state"]["continuity"]["resumed_session"]
        )
        self.assertEqual(
            second_payload["event_daemon_evidence"]["daemon_state"]["continuity"]["previous_execution_count"],
            1,
        )
        self.assertGreaterEqual(
            second_payload["event_daemon_evidence"]["daemon_state"]["continuity"]["seeded_dedupe_key_count"],
            1,
        )

    def test_cli_autonomy_daemon_smoke_reports_runtime_closure_payload(self) -> None:
        smoke_out = io.StringIO()
        with redirect_stdout(smoke_out):
            smoke_code = core_cli_main(
                [
                    "autonomy-daemon-smoke",
                    "--cycles",
                    "2",
                    "--maintenance-interval-cycles",
                    "2",
                    "--vitality-score",
                    "18",
                    "--persona-mood",
                    "watchful",
                ]
            )

        self.assertEqual(smoke_code, 0)
        payload = json.loads(smoke_out.getvalue())
        self.assertEqual(payload["schema_version"], "2.1.0-autonomy-daemon-smoke-v1")
        self.assertEqual(payload["command"], "autonomy-daemon-smoke")
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["closure_gates"]["initial_daemon_cycle_recorded"])
        self.assertTrue(payload["closure_gates"]["daemon_state_recorded"])
        self.assertTrue(payload["closure_gates"]["heartbeat_recorded"])
        self.assertTrue(payload["closure_gates"]["restart_continuity_recorded"])
        self.assertTrue(payload["closure_gates"]["operator_pause_recorded"])
        self.assertTrue(payload["closure_gates"]["pause_blocks_workflow_execution"])
        self.assertEqual(payload["evidence_summary"]["paused_run_state"], "paused")
        self.assertEqual(payload["evidence_summary"]["vitality_state"], "critical")
        self.assertEqual(payload["evidence_summary"]["persona_mood"], "watchful")

    def test_cli_vitality_smoke_reports_bounded_governance_payload(self) -> None:
        smoke_out = io.StringIO()
        with redirect_stdout(smoke_out):
            smoke_code = core_cli_main([
                "vitality-smoke",
                "--initial-score",
                "52",
            ])

        self.assertEqual(smoke_code, 0)
        payload = json.loads(smoke_out.getvalue())
        self.assertEqual(payload["schema_version"], "2.1.0-vitality-smoke-v1")
        self.assertEqual(payload["command"], "vitality-smoke")
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["closure_gates"]["decay_transition_recorded"])
        self.assertTrue(payload["closure_gates"]["replenishment_transition_recorded"])
        self.assertTrue(payload["closure_gates"]["policy_impact_bounded"])
        self.assertEqual(payload["evidence_summary"]["policy_impact"], "salience_and_tone_only")

    def test_cli_persona_state_smoke_reports_privacy_and_summary_payload(self) -> None:
        smoke_out = io.StringIO()
        with redirect_stdout(smoke_out):
            smoke_code = core_cli_main([
                "persona-state-smoke",
            ])

        self.assertEqual(smoke_code, 0)
        payload = json.loads(smoke_out.getvalue())
        self.assertEqual(payload["schema_version"], "2.1.0-persona-state-smoke-v1")
        self.assertEqual(payload["command"], "persona-state-smoke")
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["closure_gates"]["persona_seed_recorded"])
        self.assertTrue(payload["closure_gates"]["persona_growth_recorded"])
        self.assertTrue(payload["closure_gates"]["relationship_summary_recorded"])
        self.assertTrue(payload["closure_gates"]["rational_summary_limited"])
        self.assertTrue(payload["closure_gates"]["privacy_redaction_supported"])
        self.assertTrue(payload["closure_gates"]["immutability_stamp_valid"])
        self.assertEqual(payload["evidence_summary"]["mood"], "curious")
        self.assertEqual(payload["evidence_summary"]["redacted_relationship_count"], 0)
        self.assertEqual(payload["evidence_summary"]["seed_name"], "warm-curious")
        self.assertEqual(payload["evidence_summary"]["growth_revision"], 1)
        self.assertEqual(payload["evidence_summary"]["growth_source"], "social_interaction")

    def test_cli_persona_seed_setup_initializes_governed_bundle(self) -> None:
        setup_out = io.StringIO()
        with redirect_stdout(setup_out):
            setup_code = core_cli_main(
                [
                    "persona-seed-setup",
                    "--seed-name",
                    "operator-curious",
                    "--mood",
                    "focused",
                    "--curiosity",
                    "0.8",
                    "--social-openness",
                    "0.65",
                    "--immutable-boundary",
                    "no_raw_dm_export",
                    "--immutable-boundary",
                    "operator_approval_required",
                    "--created-at",
                    "2026-05-11T08:00:00Z",
                ]
            )

        self.assertEqual(setup_code, 0)
        payload = json.loads(setup_out.getvalue())
        self.assertEqual(payload["schema_version"], "2.2.5-persona-seed-setup-v1")
        self.assertEqual(payload["command"], "persona-seed-setup")
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["closure_gates"]["provenance_hash_recorded"])
        self.assertTrue(payload["closure_gates"]["immutability_stamp_valid"])
        self.assertEqual(payload["seed_config"]["seed_name"], "operator-curious")
        self.assertEqual(payload["persona_growth"]["revision"], 0)
        self.assertEqual(
            payload["persona_state"]["provenance_hash"],
            payload["persona_growth"]["seed_fingerprint"],
        )
        self.assertEqual(payload["evidence_summary"]["immutable_boundary_count"], 2)

    def test_cli_persona_state_export_supports_redaction(self) -> None:
        seed = PersonaSeedConfig(
            seed_name="export-seed",
            mood="steady",
            created_at="2026-05-11T09:00:00Z",
        )
        growth = initialize_persona_growth_state(seed)
        persona = apply_persona_signals(
            initialize_persona_state_from_seed(seed, updated_at=seed.created_at),
            [
                PersonaSignal(
                    reason="trusted_session",
                    principal_id="user-42",
                    trust_delta=0.3,
                    familiarity_delta=0.4,
                    preferred_address="Alice",
                )
            ],
            updated_at="2026-05-11T09:05:00Z",
        )
        persona = PersonaState.from_dict(
            {
                **persona.to_dict(),
                "seed_config": seed.to_dict(),
                "growth_state": growth.to_dict(),
                "provenance_hash": growth.seed_fingerprint,
            }
        )
        stamp = compute_persona_immutability_stamp(
            seed_config=seed,
            persona_state=persona,
            growth_state=growth,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "seed.json").write_text(json.dumps(seed.to_dict()), encoding="utf-8")
            (root / "persona.json").write_text(json.dumps(persona.to_dict()), encoding="utf-8")
            (root / "growth.json").write_text(json.dumps(growth.to_dict()), encoding="utf-8")

            export_out = io.StringIO()
            with redirect_stdout(export_out):
                export_code = core_cli_main(
                    [
                        "persona-state-export",
                        "--seed-file",
                        str(root / "seed.json"),
                        "--persona-file",
                        str(root / "persona.json"),
                        "--growth-file",
                        str(root / "growth.json"),
                        "--expected-immutability-stamp",
                        stamp,
                        "--redact-principal-id",
                        "user-42",
                    ]
                )

        self.assertEqual(export_code, 0)
        payload = json.loads(export_out.getvalue())
        self.assertEqual(payload["schema_version"], "2.2.5-persona-state-export-v1")
        self.assertEqual(payload["command"], "persona-state-export")
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["closure_gates"]["redaction_applied"])
        self.assertTrue(payload["closure_gates"]["immutability_stamp_valid"])
        self.assertEqual(payload["redacted_principal_ids"], ["user-42"])
        self.assertEqual(payload["persona_state"]["relationship_summaries"], [])
        self.assertEqual(payload["rational_summary"]["relationship_summaries"], [])
        self.assertEqual(payload["evidence_summary"]["relationship_count"], 0)

    def test_cli_persona_growth_apply_requires_runtime_evidence_and_advances_revision(self) -> None:
        seed = PersonaSeedConfig(
            seed_name="growth-seed",
            mood="steady",
            created_at="2026-05-11T09:30:00Z",
        )
        growth = initialize_persona_growth_state(seed)
        persona = PersonaState.from_dict(
            {
                **initialize_persona_state_from_seed(seed, updated_at=seed.created_at).to_dict(),
                "seed_config": seed.to_dict(),
                "growth_state": growth.to_dict(),
                "provenance_hash": growth.seed_fingerprint,
            }
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "seed.json").write_text(json.dumps(seed.to_dict()), encoding="utf-8")
            (root / "persona.json").write_text(json.dumps(persona.to_dict()), encoding="utf-8")
            (root / "growth.json").write_text(json.dumps(growth.to_dict()), encoding="utf-8")

            growth_out = io.StringIO()
            with redirect_stdout(growth_out):
                growth_code = core_cli_main(
                    [
                        "persona-growth-apply",
                        "--seed-file",
                        str(root / "seed.json"),
                        "--persona-file",
                        str(root / "persona.json"),
                        "--growth-file",
                        str(root / "growth.json"),
                        "--event-id",
                        "evt-growth-001",
                        "--source",
                        "unit_event",
                        "--reason",
                        "network_recovery",
                        "--recorded-at",
                        "2026-05-11T09:35:00Z",
                        "--summary",
                        "Recovered cleanly after transient disconnect.",
                    ]
                )

        self.assertEqual(growth_code, 0)
        payload = json.loads(growth_out.getvalue())
        self.assertEqual(payload["schema_version"], "2.2.5-persona-growth-apply-v1")
        self.assertEqual(payload["command"], "persona-growth-apply")
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["closure_gates"]["runtime_evidence_only"])
        self.assertTrue(payload["closure_gates"]["growth_revision_advanced"])
        self.assertEqual(payload["persona_growth"]["revision"], 1)
        self.assertEqual(payload["persona_growth"]["last_evidence_source"], "unit_event")
        self.assertIn("evt-growth-001", payload["persona_growth"]["evidence_event_ids"])

    def test_cli_persona_state_inspect_can_return_rational_summary_only(self) -> None:
        seed = PersonaSeedConfig(
            seed_name="inspect-seed",
            mood="curious",
            created_at="2026-05-11T10:15:00Z",
        )
        growth = initialize_persona_growth_state(seed)
        persona = apply_persona_signals(
            initialize_persona_state_from_seed(seed, updated_at=seed.created_at),
            [
                PersonaSignal(
                    reason="recent_interaction",
                    principal_id="user-77",
                    trust_delta=0.2,
                    familiarity_delta=0.3,
                    preferred_address="Operator",
                )
            ],
            updated_at="2026-05-11T10:20:00Z",
        )
        persona = PersonaState.from_dict(
            {
                **persona.to_dict(),
                "seed_config": seed.to_dict(),
                "growth_state": growth.to_dict(),
                "provenance_hash": growth.seed_fingerprint,
            }
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "seed.json").write_text(json.dumps(seed.to_dict()), encoding="utf-8")
            (root / "persona.json").write_text(json.dumps(persona.to_dict()), encoding="utf-8")
            (root / "growth.json").write_text(json.dumps(growth.to_dict()), encoding="utf-8")

            inspect_out = io.StringIO()
            with redirect_stdout(inspect_out):
                inspect_code = core_cli_main(
                    [
                        "persona-state-inspect",
                        "--seed-file",
                        str(root / "seed.json"),
                        "--persona-file",
                        str(root / "persona.json"),
                        "--growth-file",
                        str(root / "growth.json"),
                        "--rational-summary-only",
                    ]
                )

        self.assertEqual(inspect_code, 0)
        payload = json.loads(inspect_out.getvalue())
        self.assertEqual(payload["schema_version"], "2.2.5-persona-state-inspect-v1")
        self.assertEqual(payload["command"], "persona-state-inspect")
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["rational_summary_only"])
        self.assertIsNone(payload["persona_state"])
        self.assertIsNone(payload["persona_growth"])
        self.assertEqual(payload["rational_summary"]["relationship_summaries"][0]["principal_id"], "user-77")

    def test_cli_persona_state_delete_supports_principal_redaction_and_full_delete(self) -> None:
        seed = PersonaSeedConfig(
            seed_name="delete-seed",
            mood="steady",
            created_at="2026-05-11T10:45:00Z",
        )
        growth = initialize_persona_growth_state(seed)
        persona = apply_persona_signals(
            initialize_persona_state_from_seed(seed, updated_at=seed.created_at),
            [
                PersonaSignal(
                    reason="recent_interaction",
                    principal_id="user-delete-1",
                    trust_delta=0.2,
                    familiarity_delta=0.1,
                ),
                PersonaSignal(
                    reason="recent_interaction",
                    principal_id="user-delete-2",
                    trust_delta=0.1,
                    familiarity_delta=0.2,
                ),
            ],
            updated_at="2026-05-11T10:50:00Z",
        )
        persona = PersonaState.from_dict(
            {
                **persona.to_dict(),
                "seed_config": seed.to_dict(),
                "growth_state": growth.to_dict(),
                "provenance_hash": growth.seed_fingerprint,
            }
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "seed.json").write_text(json.dumps(seed.to_dict()), encoding="utf-8")
            (root / "persona.json").write_text(json.dumps(persona.to_dict()), encoding="utf-8")
            (root / "growth.json").write_text(json.dumps(growth.to_dict()), encoding="utf-8")

            redact_out = io.StringIO()
            with redirect_stdout(redact_out):
                redact_code = core_cli_main(
                    [
                        "persona-state-delete",
                        "--seed-file",
                        str(root / "seed.json"),
                        "--persona-file",
                        str(root / "persona.json"),
                        "--growth-file",
                        str(root / "growth.json"),
                        "--principal-id",
                        "user-delete-1",
                    ]
                )

            full_delete_out = io.StringIO()
            with redirect_stdout(full_delete_out):
                full_delete_code = core_cli_main(
                    [
                        "persona-state-delete",
                        "--seed-file",
                        str(root / "seed.json"),
                        "--persona-file",
                        str(root / "persona.json"),
                        "--growth-file",
                        str(root / "growth.json"),
                        "--delete-all",
                    ]
                )

        self.assertEqual(redact_code, 0)
        redact_payload = json.loads(redact_out.getvalue())
        self.assertEqual(redact_payload["schema_version"], "2.2.5-persona-state-delete-v1")
        self.assertFalse(redact_payload["delete_all"])
        self.assertEqual(redact_payload["deleted_principal_ids"], ["user-delete-1"])
        self.assertEqual(redact_payload["deleted_relationship_count"], 1)
        self.assertEqual(
            len(redact_payload["persona_state"]["relationship_summaries"]),
            1,
        )
        self.assertTrue(redact_payload["closure_gates"]["growth_state_not_rewritten"])

        self.assertEqual(full_delete_code, 0)
        full_delete_payload = json.loads(full_delete_out.getvalue())
        self.assertTrue(full_delete_payload["delete_all"])
        self.assertIsNone(full_delete_payload["persona_state"])
        self.assertIsNone(full_delete_payload["persona_growth"])
        self.assertTrue(full_delete_payload["ok"])

    def test_cli_persona_tamper_report_detects_modified_state(self) -> None:
        seed = PersonaSeedConfig(
            seed_name="tamper-seed",
            mood="steady",
            created_at="2026-05-11T10:00:00Z",
        )
        growth = initialize_persona_growth_state(seed)
        persona = PersonaState.from_dict(
            {
                **initialize_persona_state_from_seed(
                    seed,
                    updated_at=seed.created_at,
                ).to_dict(),
                "seed_config": seed.to_dict(),
                "growth_state": growth.to_dict(),
                "provenance_hash": growth.seed_fingerprint,
            }
        )
        stamp = compute_persona_immutability_stamp(
            seed_config=seed,
            persona_state=persona,
            growth_state=growth,
        )
        tampered_persona = PersonaState.from_dict(
            {
                **persona.to_dict(),
                "mood": "agitated",
            }
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "seed.json").write_text(json.dumps(seed.to_dict()), encoding="utf-8")
            (root / "persona.json").write_text(
                json.dumps(tampered_persona.to_dict()),
                encoding="utf-8",
            )
            (root / "growth.json").write_text(json.dumps(growth.to_dict()), encoding="utf-8")

            report_out = io.StringIO()
            with redirect_stdout(report_out):
                report_code = core_cli_main(
                    [
                        "persona-tamper-report",
                        "--seed-file",
                        str(root / "seed.json"),
                        "--persona-file",
                        str(root / "persona.json"),
                        "--growth-file",
                        str(root / "growth.json"),
                        "--expected-immutability-stamp",
                        stamp,
                    ]
                )

        self.assertEqual(report_code, 2)
        payload = json.loads(report_out.getvalue())
        self.assertEqual(payload["schema_version"], "2.2.5-persona-tamper-report-v1")
        self.assertEqual(payload["command"], "persona-tamper-report")
        self.assertFalse(payload["ok"])
        self.assertTrue(payload["tampered"])
        self.assertFalse(payload["closure_gates"]["immutability_stamp_valid"])
        self.assertNotEqual(
            payload["expected_immutability_stamp"],
            payload["actual_immutability_stamp"],
        )

    def test_live_event_service_can_record_federation_route_evidence(self) -> None:
        class FakeLiveAdapter:
            def runtime_metadata(self) -> dict[str, Any]:
                return {"adapter_kind": "fake-live"}

            def describe_tool(self, tool_name: str) -> ToolContract | None:
                if tool_name != "system_state_sync":
                    return None
                return ToolContract(
                    tool_name="system_state_sync",
                    description="state sync",
                    side_effect_level=SideEffectLevel.READ_ONLY,
                    required_resources=("state sync aggregate",),
                )

            def execute(self, tool_name: str, args: dict[str, Any]) -> ToolExecutionResult:
                del args
                if tool_name != "system_state_sync":
                    raise AssertionError(f"unexpected tool: {tool_name}")
                return ToolExecutionResult(
                    tool_result_id="tool-live-fed-001",
                    tool_name="system_state_sync",
                    status="ok",
                    payload={
                        "state_sync": {
                            "status": "ok",
                            "recommended_next_actions": ["continue"],
                        }
                    },
                )

            def collect_live_events(
                self,
                *,
                duration: int,
                max_events: int,
                ready_file: str,
            ) -> dict[str, Any]:
                del duration, max_events, ready_file
                return {
                    "ok": True,
                    "subscription": "neuro/unit-01/event/unit/**",
                    "listener_mode": "callback",
                    "handler_audit": {"enabled": False, "executed": 0},
                    "events": [sample_events()[0]],
                }

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "event-service-fed.db")
            payload = run_live_event_service(
                db_path,
                event_source="unit",
                duration=1,
                max_events=1,
                cycles=1,
                session_id="event-service-fed-001",
                tool_adapter=FakeLiveAdapter(),
                federation_route_provider=lambda frame, session_context: federation_route_smoke(
                    target_node="unit-remote-01",
                    now="2026-05-09T12:00:00Z",
                    required_trust_scope="lab-federation",
                ),
            )
            data_store = CoreDataStore(db_path)
            try:
                evidence = data_store.build_execution_evidence(
                    str(payload["execution_span_id"]),
                    str(payload["audit_id"]),
                )
            finally:
                data_store.close()

        self.assertEqual(payload["command"], "event-service")
        self.assertEqual(payload["event_source"], "neuro_cli_events_live")
        self.assertEqual(payload["event_service"]["cycle_count"], 1)
        self.assertEqual(payload["execution_evidence"]["execution_span"]["payload"]["federation_route_kind"], "delegated_core")
        self.assertEqual(
            evidence["audit_record"]["payload"]["session_context"]["federation_route_evidence"]["status"],
            "route_ready",
        )

    def test_dry_run_reports_execution_evidence_snapshot(self) -> None:
        payload = run_no_model_dry_run()

        evidence = payload["execution_evidence"]
        self.assertEqual(evidence["execution_span"]["status"], "ok")
        self.assertEqual(evidence["execution_span"]["session_id"], payload["session_id"])
        self.assertEqual(
            evidence["execution_span"]["payload"]["audit_id"],
            payload["audit_id"],
        )
        self.assertEqual(evidence["audit_record"]["audit_id"], payload["audit_id"])
        self.assertEqual(
            {fact["fact_type"] for fact in evidence["facts"]},
            {
                "affective_runtime_context",
                "memory_governance_summary",
                "memory_recall_policy",
                "notification_dispatch",
                "perception_event_topic",
                "perception_frame",
            },
        )
        self.assertEqual(len(evidence["policy_decisions"]), 1)
        self.assertTrue(evidence["policy_decisions"][0]["allowed"])
        self.assertEqual(evidence["long_term_memories"], [])
        self.assertEqual(
            evidence["audit_record"]["payload"]["notification_summary"]["trigger_kind"],
            "event_driven_perception",
        )
        self.assertEqual(
            {candidate["semantic_topic"] for candidate in evidence["memory_candidates"]},
            {"time.tick", "unit.callback"},
        )

    def test_dry_run_can_record_federation_route_evidence_in_audit_and_span(self) -> None:
        payload = run_no_model_dry_run(
            federation_route_provider=lambda frame, session_context: federation_route_smoke(
                target_node="unit-remote-01",
                now="2026-05-09T12:00:00Z",
                required_trust_scope="lab-federation",
            )
        )

        evidence = payload["execution_evidence"]
        execution_span_payload = evidence["execution_span"]["payload"]
        audit_session_context = evidence["audit_record"]["payload"]["session_context"]
        federation_route = audit_session_context["federation_route_evidence"]

        self.assertEqual(execution_span_payload["federation_route_status"], "route_ready")
        self.assertEqual(execution_span_payload["federation_route_kind"], "delegated_core")
        self.assertEqual(federation_route["route_decision"]["route_kind"], "delegated_core")
        self.assertEqual(federation_route["delegated_execution"]["target_core"], "core-b")
        self.assertIn(
            "federation_route",
            {fact["fact_type"] for fact in evidence["facts"]},
        )

    def test_local_memory_backend_commits_long_term_memories(self) -> None:
        payload = run_no_model_dry_run(memory_backend="local")

        self.assertEqual(payload["db_counts"]["long_term_memories"], 1)
        self.assertEqual(payload["memory_runtime"]["backend_kind"], "local_sqlite")
        self.assertFalse(payload["memory_runtime"]["fallback_active"])
        self.assertEqual(len(payload["execution_evidence"]["long_term_memories"]), 1)
        self.assertEqual(
            payload["execution_evidence"]["audit_record"]["payload"]["session_context"]["committed_memory_count"],
            1,
        )
        self.assertEqual(
            payload["execution_evidence"]["audit_record"]["payload"]["session_context"]["accepted_memory_candidate_count"],
            1,
        )
        self.assertEqual(
            payload["execution_evidence"]["audit_record"]["payload"]["session_context"]["rejected_memory_candidate_count"],
            1,
        )
        self.assertEqual(
            payload["execution_evidence"]["audit_record"]["payload"]["session_context"]["memory_runtime"],
            payload["memory_runtime"],
        )
        first_memory = payload["execution_evidence"]["long_term_memories"][0]["payload"]
        self.assertEqual(first_memory["memory_governance"]["schema_version"], "1.2.5-memory-governance-v1")
        self.assertEqual(first_memory["memory_governance"]["lifecycle_state"], "committed")
        self.assertEqual(first_memory["memory_governance"]["commit_backend"], "local_sqlite")
        self.assertEqual(first_memory["memory_governance"]["decision_reason"], "auto_commit_local_sqlite")
        self.assertEqual(first_memory["memory_governance"]["retention_class"], "operational_lesson")
        self.assertTrue(first_memory["memory_governance"]["source_fact_refs"])

    def test_mem0_memory_backend_falls_back_to_local_when_unavailable(self) -> None:
        with mock.patch("neurolink_core.memory.find_spec", return_value=None):
            payload = run_no_model_dry_run(memory_backend="mem0")

        self.assertEqual(payload["memory_runtime"]["backend_kind"], "mem0_sidecar")
        self.assertTrue(payload["memory_runtime"]["fallback_active"])
        self.assertFalse(payload["memory_runtime"]["package_available"])
        self.assertEqual(
            payload["memory_runtime"]["unavailable_reason"],
            "mem0_package_not_installed",
        )
        self.assertEqual(payload["memory_runtime"]["last_lookup_status"], "fallback_local_sqlite")
        self.assertEqual(payload["memory_runtime"]["last_commit_status"], "fallback_local_sqlite")
        self.assertEqual(payload["db_counts"]["long_term_memories"], 1)
        self.assertEqual(
            payload["execution_evidence"]["audit_record"]["payload"]["session_context"]["memory_runtime"],
            payload["memory_runtime"],
        )

    def test_mem0_memory_backend_uses_injected_sidecar_and_sqlite_mirror(self) -> None:
        class FakeMem0Client:
            def __init__(self) -> None:
                self.search_calls: list[dict[str, Any]] = []
                self.add_calls: list[dict[str, Any]] = []

            def search(self, query: str, user_id: str, limit: int) -> dict[str, Any]:
                self.search_calls.append(
                    {"query": query, "user_id": user_id, "limit": limit}
                )
                return {"results": [{"id": "mem0-existing-001", "memory": "prior state"}]}

            def add(
                self,
                message: str,
                user_id: str,
                metadata: dict[str, Any],
            ) -> dict[str, Any]:
                memory_id = f"mem0-new-{len(self.add_calls) + 1:03d}"
                self.add_calls.append(
                    {
                        "message": message,
                        "user_id": user_id,
                        "metadata": metadata,
                    }
                )
                return {"id": memory_id}

        client = FakeMem0Client()

        payload = run_no_model_dry_run(
            memory_backend="mem0",
            mem0_client=client,
        )

        self.assertEqual(payload["memory_runtime"]["backend_kind"], "mem0_sidecar")
        self.assertFalse(payload["memory_runtime"]["fallback_active"])
        self.assertTrue(payload["memory_runtime"]["sidecar_configured"])
        self.assertEqual(
            payload["memory_runtime"]["last_lookup_status"],
            "sidecar_and_local_sqlite",
        )
        self.assertEqual(
            payload["memory_runtime"]["last_commit_status"],
            "sidecar_and_sqlite_mirror",
        )
        self.assertEqual(
            payload["memory_runtime"]["sidecar_memory_ids"],
            ["mem0-new-001"],
        )
        self.assertEqual(payload["db_counts"]["long_term_memories"], 1)
        self.assertEqual(len(client.search_calls), 1)
        self.assertEqual(len(client.add_calls), 1)
        self.assertEqual(client.add_calls[0]["user_id"], "neurolink-core")
        self.assertEqual(
            client.add_calls[0]["metadata"]["agent_id"],
            "neurolink-rational",
        )
        self.assertIn("source_fact_refs", client.add_calls[0]["message"])
        self.assertNotIn("frame_id", client.add_calls[0]["message"])

    def test_local_memory_backend_reuses_prior_memories_on_next_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "core.db")
            first = run_no_model_dry_run(
                db_path,
                session_id="memory-local-001",
                memory_backend="local",
            )
            second = run_no_model_dry_run(
                db_path,
                session_id="memory-local-001",
                memory_backend="local",
            )

        self.assertEqual(first["db_counts"]["long_term_memories"], 1)
        self.assertEqual(second["db_counts"]["long_term_memories"], 2)
        self.assertGreater(
            second["execution_evidence"]["audit_record"]["payload"]["session_context"]["memory_lookup_count"],
            0,
        )

    def test_prompt_safe_context_summarizes_history_and_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "core.db")
            run_no_model_dry_run(
                db_path,
                session_id="prompt-safe-session-001",
                memory_backend="local",
            )
            second = run_no_model_dry_run(
                db_path,
                session_id="prompt-safe-session-001",
                memory_backend="local",
            )

        session_context = second["execution_evidence"]["audit_record"]["payload"]["session_context"]
        prompt_context = session_context["prompt_safe_context"]

        self.assertEqual(
            prompt_context["schema_version"],
            "1.2.5-prompt-safe-context-v2",
        )
        self.assertEqual(prompt_context["session_id"], "prompt-safe-session-001")
        self.assertEqual(prompt_context["history"]["previous_execution_count"], 1)
        self.assertEqual(len(prompt_context["history"]["previous_executions"]), 1)
        self.assertNotIn(
            "payload",
            prompt_context["history"]["previous_executions"][0],
        )
        self.assertGreater(prompt_context["memory"]["lookup_count"], 0)
        self.assertLessEqual(len(prompt_context["memory"]["items"]), 5)
        self.assertEqual(prompt_context["memory"]["recall_policy"]["schema_version"], "1.2.5-memory-recall-policy-v1")
        self.assertEqual(prompt_context["memory"]["recall_policy"]["affective_recall"]["selected_count"], 0)
        self.assertEqual(prompt_context["memory"]["recall_policy"]["rational_recall"]["selected_count"], 1)
        self.assertEqual(prompt_context["memory"]["items"], prompt_context["memory"]["rational_items"])
        self.assertEqual(prompt_context["memory"]["affective_items"], [])
        self.assertEqual(
            prompt_context["memory"]["recall_policy"]["filtered_out_categories"].get("ungoverned_memory_result", 0),
            0,
        )
        self.assertEqual(
            prompt_context["safety_boundaries"]["can_execute_tools_directly"],
            False,
        )
        self.assertIn("previous_execution_spans", session_context)

    def test_cli_no_model_dry_run_outputs_json(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            code = core_cli_main(["no-model-dry-run"])

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["status"], "ok")
        self.assertTrue(payload["session_id"].startswith("session-"))
        self.assertTrue(payload["delegated"])
        self.assertEqual(payload["final_response"]["speaker"], "affective")
        self.assertEqual(payload["db_counts"]["execution_spans"], 1)
        self.assertEqual(payload["db_counts"]["policy_decisions"], 1)
        self.assertEqual(payload["db_counts"]["audit_records"], 1)
        self.assertIn("execution_evidence", payload)
        self.assertEqual(payload["execution_evidence"]["execution_span"]["status"], "ok")

    def test_cli_no_model_dry_run_can_use_provider_availability_mode(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            code = core_cli_main(
                [
                    "no-model-dry-run",
                    "--maf-provider-mode",
                    "provider_available_no_call",
                    "--session-id",
                    "session-cli-001",
                ]
            )

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["session_id"], "session-cli-001")
        self.assertEqual(payload["maf_runtime"]["provider_mode"], "provider_available_no_call")
        self.assertEqual(payload["session"]["session_id"], "session-cli-001")
        self.assertEqual(len(payload["session"]["recent_execution_spans"]), 1)

    def test_cli_federation_route_smoke_outputs_delegated_route_payload(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            code = core_cli_main(
                [
                    "federation-route-smoke",
                    "--target-node",
                    "unit-remote-01",
                    "--required-trust-scope",
                    "lab-federation",
                ]
            )

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "route_ready")
        self.assertEqual(payload["route_decision"]["route_kind"], "delegated_core")
        self.assertEqual(payload["delegated_execution"]["target_core"], "core-b")

    def test_cli_federation_route_smoke_reports_stale_peer_as_failure(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            code = core_cli_main(
                [
                    "federation-route-smoke",
                    "--target-node",
                    "unit-remote-01",
                    "--required-trust-scope",
                    "lab-federation",
                    "--peer-expires-at",
                    "2026-05-09T11:59:59Z",
                ]
            )

        self.assertEqual(code, 2)
        payload = json.loads(out.getvalue())
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "stale_route")
        self.assertEqual(payload["route_decision"]["failure_reason"], "peer_advertisement_stale")

    def test_cli_no_model_dry_run_rejects_real_provider_without_allow_flag(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            code = core_cli_main(
                [
                    "no-model-dry-run",
                    "--maf-provider-mode",
                    "real_provider",
                ]
            )

        self.assertEqual(code, 2)
        payload = json.loads(out.getvalue())
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["failure_status"], "real_provider_mode_requires_allow_model_call")
        self.assertEqual(payload["maf_runtime"]["provider_mode"], "real_provider")

    def test_cli_agent_run_can_use_real_provider_with_injected_default_factory(self) -> None:
        class FakeProviderClient:
            provider_client_kind = "test_client"

            def decide(
                self,
                frame: Any,
                memory_items: list[dict[str, Any]],
                profile: Any,
            ) -> dict[str, Any]:
                del frame, memory_items, profile
                return {
                    "delegated": True,
                    "reason": "real_provider_affective_decision",
                    "salience": 88,
                }

            def plan(
                self,
                decision: Any,
                frame: Any,
                profile: Any,
                available_tools: list[dict[str, Any]],
                session_context: dict[str, Any],
            ) -> dict[str, Any]:
                del decision, frame, profile
                self.available_tools = available_tools
                self.session_context = session_context
                return {
                    "tool_name": "system_query_device",
                    "args": {"source": "real-provider"},
                    "reason": "real_provider_rational_plan",
                }

        out = io.StringIO()
        env = {
            "OPENAI_API_KEY": "secret",
            "OPENAI_MODEL": "gpt-4.1-mini",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            with mock.patch("neurolink_core.maf.find_spec", return_value=object()):
                with mock.patch(
                    "neurolink_core.workflow.build_default_maf_provider_client",
                    return_value=FakeProviderClient(),
                ):
                    with redirect_stdout(out):
                        code = core_cli_main(
                            [
                                "agent-run",
                                "--input-text",
                                "check current device status",
                                "--maf-provider-mode",
                                "real_provider",
                                "--allow-model-call",
                                "--session-id",
                                "agent-run-real-provider-001",
                            ]
                        )

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["command"], "agent-run")
        self.assertEqual(payload["runtime_mode"], "real_llm")
        self.assertEqual(payload["maf_runtime"]["provider_mode"], "real_provider")
        self.assertIn("affective_model_call", payload["steps"])
        self.assertEqual(payload["tool_results"][0]["tool_name"], "system_query_device")
        self.assertEqual(payload["final_response"]["salience"], 88)
        self.assertEqual(
            payload["model_call_evidence"]["call_status"],
            "model_call_succeeded",
        )
        self.assertTrue(payload["model_call_evidence"]["executes_model_call"])
        self.assertEqual(
            payload["model_call_evidence"]["provider_client_kind"],
            "test_client",
        )
        self.assertEqual(
            payload["model_call_evidence"]["decision"],
            {
                "delegated": True,
                "reason": "real_provider_affective_decision",
                "salience": 88,
            },
        )
        audit_session_context = payload["execution_evidence"]["audit_record"]["payload"]["session_context"]
        self.assertEqual(
            audit_session_context["model_call_evidence"],
            payload["model_call_evidence"],
        )
        self.assertEqual(
            {item["provider_client_kind"] for item in payload["maf_runtime"]["agent_adapters"]},
            {"test_client"},
        )
        agent_run_evidence = payload["agent_run_evidence"]
        self.assertEqual(
            agent_run_evidence["schema_version"],
            "1.2.2-agent-run-evidence-v1",
        )
        self.assertTrue(agent_run_evidence["ok"])
        self.assertEqual(agent_run_evidence["runtime_mode"], "real_llm")
        self.assertEqual(
            agent_run_evidence["provider_runtime"]["provider_mode"],
            "real_provider",
        )
        self.assertEqual(
            agent_run_evidence["rational_backend"]["backend_kind"],
            "maf_provider_client",
        )
        self.assertEqual(
            agent_run_evidence["memory_runtime"]["backend_kind"],
            "fake",
        )
        self.assertEqual(
            agent_run_evidence["model_call_evidence"],
            payload["model_call_evidence"],
        )
        self.assertEqual(
            agent_run_evidence["prompt_safe_context"]["schema_version"],
            "1.2.5-prompt-safe-context-v2",
        )
        self.assertEqual(agent_run_evidence["prompt_safe_context"]["affective_memory_count"], 0)
        self.assertEqual(agent_run_evidence["prompt_safe_context"]["rational_memory_count"], 0)
        self.assertFalse(
            agent_run_evidence["prompt_safe_context"]["safety_boundaries"]["can_execute_tools_directly"]
        )
        self.assertEqual(agent_run_evidence["db_counts"], payload["db_counts"])

    def test_cli_agent_run_real_provider_can_resolve_model_from_config_file(self) -> None:
        class FakeProviderClient:
            provider_client_kind = "test_client"

            def decide(
                self,
                frame: Any,
                memory_items: list[dict[str, Any]],
                profile: Any,
            ) -> dict[str, Any]:
                del frame, memory_items, profile
                return {
                    "delegated": True,
                    "reason": "real_provider_affective_decision",
                    "salience": 88,
                }

            def plan(
                self,
                decision: Any,
                frame: Any,
                profile: Any,
                available_tools: list[dict[str, Any]],
                session_context: dict[str, Any],
            ) -> dict[str, Any]:
                del decision, frame, profile
                self.available_tools = available_tools
                self.session_context = session_context
                return {
                    "tool_name": "system_query_device",
                    "args": {"source": "real-provider"},
                    "reason": "real_provider_rational_plan",
                }

        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "runtime_provider_profiles.json"
            core_cli_main(
                [
                    "provider-config",
                    "--config-file",
                    str(config_file),
                    "--profile",
                    "openai_compatible",
                    "--endpoint-url",
                    "https://provider.example/v1",
                    "--configured-model",
                    "gpt-4.1-mini",
                ]
            )
            out = io.StringIO()
            with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "secret"}, clear=False):
                with mock.patch("neurolink_core.maf.find_spec", return_value=object()):
                    with mock.patch(
                        "neurolink_core.workflow.build_default_maf_provider_client",
                        return_value=FakeProviderClient(),
                    ):
                        with redirect_stdout(out):
                            code = core_cli_main(
                                [
                                    "agent-run",
                                    "--input-text",
                                    "check current device status",
                                    "--maf-provider-mode",
                                    "real_provider",
                                    "--allow-model-call",
                                    "--maf-config-file",
                                    str(config_file),
                                    "--session-id",
                                    "agent-run-real-provider-config-001",
                                ]
                            )

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(
            payload["maf_runtime"]["provider_config"]["configured_model"],
            "gpt-4.1-mini",
        )
        self.assertTrue(payload["maf_runtime"]["provider_ready_for_model_call"])
        self.assertEqual(payload["runtime_mode"], "real_llm")
        agent_run_evidence = payload["agent_run_evidence"]
        self.assertEqual(agent_run_evidence["evidence_counts"]["policy_decisions"], 1)
        self.assertEqual(agent_run_evidence["evidence_counts"]["tool_results"], 1)
        self.assertTrue(agent_run_evidence["audit"]["audit_record_present"])
        self.assertTrue(agent_run_evidence["closure_gates"]["memory_recall_policy_present"])
        self.assertTrue(agent_run_evidence["closure_gates"]["affective_memory_recall_recorded"])
        self.assertTrue(agent_run_evidence["closure_gates"]["rational_memory_recall_recorded"])

    def test_workflow_rejects_real_provider_plan_for_unknown_manifest_tool(self) -> None:
        class FakeProviderClient:
            provider_client_kind = "test_client"

            def decide(
                self,
                frame: Any,
                memory_items: list[dict[str, Any]],
                profile: Any,
            ) -> dict[str, Any]:
                del frame, memory_items, profile
                return {
                    "delegated": True,
                    "reason": "real_provider_affective_decision",
                    "salience": 93,
                }

            def plan(
                self,
                decision: Any,
                frame: Any,
                profile: Any,
                available_tools: list[dict[str, Any]],
                session_context: dict[str, Any],
            ) -> dict[str, Any]:
                self.available_tools = available_tools
                self.session_context = session_context
                del decision, frame, profile
                return {
                    "tool_name": "system_unknown_write",
                    "args": {"source": "real-provider"},
                    "reason": "hallucinated_tool_from_provider",
                }

        with mock.patch.dict(
            os.environ,
            {"OPENAI_API_KEY": "secret", "OPENAI_MODEL": "gpt-4.1-mini"},
            clear=False,
        ):
            with mock.patch("neurolink_core.maf.find_spec", return_value=object()):
                payload = run_no_model_dry_run(
                    maf_provider_mode="real_provider",
                    allow_model_call=True,
                    provider_client=FakeProviderClient(),
                )

        self.assertEqual(payload["maf_runtime"]["provider_mode"], "real_provider")
        self.assertEqual(payload["tool_results"][0]["status"], "error")
        self.assertEqual(
            payload["tool_results"][0]["payload"]["failure_status"],
            "rational_plan_tool_not_in_available_tools",
        )
        self.assertEqual(
            payload["tool_results"][0]["payload"]["failure_class"],
            "rational_plan_payload_invalid",
        )
        self.assertGreater(
            len(payload["tool_results"][0]["payload"]["available_tools"]),
            0,
        )
        self.assertIn(
            "available_tools",
            payload["execution_evidence"]["audit_record"]["payload"]["session_context"],
        )

    def test_real_provider_receives_prompt_safe_context_only(self) -> None:
        class CapturingProviderClient:
            provider_client_kind = "test_client"

            def __init__(self) -> None:
                self.memory_items: list[dict[str, Any]] = []
                self.affective_context: dict[str, Any] = {}
                self.session_context: dict[str, Any] = {}

            def decide(
                self,
                frame: Any,
                memory_items: list[dict[str, Any]],
                profile: Any,
                affective_context: dict[str, Any] | None = None,
            ) -> dict[str, Any]:
                del frame, profile
                self.memory_items = memory_items
                self.affective_context = dict(affective_context or {})
                return {
                    "delegated": True,
                    "reason": "real_provider_affective_decision",
                    "salience": 88,
                }

            def plan(
                self,
                decision: Any,
                frame: Any,
                profile: Any,
                available_tools: list[dict[str, Any]],
                session_context: dict[str, Any],
            ) -> dict[str, Any]:
                del decision, frame, profile, available_tools
                self.session_context = session_context
                return {
                    "tool_name": "system_query_device",
                    "args": {"source": "real-provider"},
                    "reason": "real_provider_rational_plan",
                }

        client = CapturingProviderClient()
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "core.db")
            run_no_model_dry_run(
                db_path,
                session_id="prompt-safe-provider-001",
                memory_backend="local",
            )
            with mock.patch.dict(
                os.environ,
                {"OPENAI_API_KEY": "secret", "OPENAI_MODEL": "gpt-4.1-mini"},
                clear=False,
            ):
                with mock.patch("neurolink_core.maf.find_spec", return_value=object()):
                    payload = run_no_model_dry_run(
                        db_path,
                        session_id="prompt-safe-provider-001",
                        maf_provider_mode="real_provider",
                        allow_model_call=True,
                        memory_backend="local",
                        provider_client=client,
                    )

        audit_session_context = payload["execution_evidence"]["audit_record"]["payload"]["session_context"]
        self.assertEqual(
            client.session_context["schema_version"],
            "1.2.5-prompt-safe-context-v2",
        )
        self.assertNotIn("previous_execution_spans", client.session_context)
        self.assertNotIn("model_call_evidence", client.session_context)
        self.assertIn("prompt_safe_context", audit_session_context)
        self.assertEqual(
            audit_session_context["prompt_safe_context"],
            client.session_context,
        )
        self.assertEqual(client.affective_context, client.session_context["affective_runtime"])
        self.assertEqual(client.memory_items, [])
        self.assertEqual(client.session_context["memory"]["recall_policy"]["affective_recall"]["selected_count"], 0)
        self.assertEqual(client.session_context["memory"]["recall_policy"]["rational_recall"]["selected_count"], 1)
        self.assertEqual(len(client.session_context["memory"]["items"]), 1)
        self.assertEqual(client.session_context["memory"]["affective_items"], [])
        self.assertNotIn("payload", client.session_context["memory"]["items"][0])

    def test_mem0_prompt_safe_recall_excludes_ungoverned_sidecar_results(self) -> None:
        class FakeMem0Client:
            def search(self, query: str, user_id: str, limit: int) -> dict[str, Any]:
                del query, user_id, limit
                return {"results": [{"id": "mem0-existing-001", "memory": "raw private sidecar text"}]}

            def add(
                self,
                message: str,
                user_id: str,
                metadata: dict[str, Any],
            ) -> dict[str, Any]:
                del message, user_id, metadata
                return {"id": "mem0-new-001"}

        payload = run_no_model_dry_run(memory_backend="mem0", mem0_client=FakeMem0Client())
        prompt_context = payload["execution_evidence"]["audit_record"]["payload"]["session_context"]["prompt_safe_context"]
        recall_policy = prompt_context["memory"]["recall_policy"]

        self.assertEqual(recall_policy["backend_kind"], "mem0_sidecar")
        self.assertFalse(recall_policy["fallback_active"])
        self.assertEqual(recall_policy["affective_recall"]["selected_count"], 0)
        self.assertEqual(recall_policy["rational_recall"]["selected_count"], 0)
        self.assertEqual(recall_policy["filtered_out_categories"]["ungoverned_memory_result"], 1)
        self.assertEqual(len(prompt_context["memory"]["items"]), 0)

    def test_copilot_rational_backend_requires_allow_model_call(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "copilot_rational_backend_requires_allow_model_call",
        ):
            run_no_model_dry_run(rational_backend="copilot")

    def test_cli_agent_run_rejects_copilot_rational_backend_without_allow_flag(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            code = core_cli_main(
                [
                    "agent-run",
                    "--input-text",
                    "check current device status",
                    "--rational-backend",
                    "copilot",
                ]
            )

        self.assertEqual(code, 2)
        payload = json.loads(out.getvalue())
        self.assertFalse(payload["ok"])
        self.assertEqual(
            payload["failure_status"],
            "copilot_rational_backend_requires_allow_model_call",
        )

    def test_copilot_rational_backend_can_drive_agent_run_with_injected_agent(self) -> None:
        class FakeCopilotAgent:
            def __init__(self, default_options: dict[str, Any]) -> None:
                self.default_options = default_options

            async def __aenter__(self) -> "FakeCopilotAgent":
                return self

            async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
                del exc_type, exc, tb

            async def run(self, prompt: str) -> str:
                self.prompt = prompt
                return (
                    '{"tool_name":"system_query_device",'
                    '"args":{"source":"copilot"},'
                    '"reason":"copilot_selected_device_query"}'
                )

        created_agents: list[FakeCopilotAgent] = []

        def agent_factory(default_options: dict[str, Any]) -> FakeCopilotAgent:
            agent = FakeCopilotAgent(default_options)
            created_agents.append(agent)
            return agent

        payload = run_no_model_dry_run(
            events=build_user_prompt_event("check current device status"),
            allow_model_call=True,
            rational_backend="copilot",
            copilot_agent_factory=agent_factory,
        )

        self.assertEqual(payload["tool_results"][0]["tool_name"], "system_query_device")
        rational_backend = payload["agent_run_evidence"]["rational_backend"]
        self.assertEqual(rational_backend["backend_kind"], "github_copilot_sdk")
        self.assertTrue(rational_backend["model_call_allowed"])
        self.assertFalse(rational_backend["can_execute_tools_directly"])
        self.assertTrue(payload["agent_run_evidence"]["ok"])
        self.assertIn("1.2.5-prompt-safe-context-v2", created_agents[0].prompt)
        self.assertIn("system_query_device", created_agents[0].prompt)

    def test_cli_no_model_dry_run_can_use_local_memory_backend(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            code = core_cli_main(
                [
                    "no-model-dry-run",
                    "--memory-backend",
                    "local",
                ]
            )

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["db_counts"]["long_term_memories"], 1)
        self.assertEqual(
            payload["execution_evidence"]["audit_record"]["payload"]["session_context"]["committed_memory_count"],
            1,
        )

    def test_cli_no_model_dry_run_can_request_mem0_with_local_fallback(self) -> None:
        out = io.StringIO()
        with mock.patch("neurolink_core.memory.find_spec", return_value=None):
            with redirect_stdout(out):
                code = core_cli_main(
                    [
                        "no-model-dry-run",
                        "--memory-backend",
                        "mem0",
                    ]
                )

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["memory_runtime"]["backend_kind"], "mem0_sidecar")
        self.assertTrue(payload["memory_runtime"]["fallback_active"])
        self.assertEqual(payload["db_counts"]["long_term_memories"], 1)

    def test_cli_session_inspect_reports_existing_session_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "core.db")

            first_out = io.StringIO()
            with redirect_stdout(first_out):
                first_code = core_cli_main(
                    [
                        "no-model-dry-run",
                        "--db",
                        db_path,
                        "--session-id",
                        "session-cli-inspect-001",
                    ]
                )

            second_out = io.StringIO()
            with redirect_stdout(second_out):
                second_code = core_cli_main(
                    [
                        "no-model-dry-run",
                        "--db",
                        db_path,
                        "--session-id",
                        "session-cli-inspect-001",
                    ]
                )

            inspect_out = io.StringIO()
            with redirect_stdout(inspect_out):
                inspect_code = core_cli_main(
                    [
                        "session-inspect",
                        "--db",
                        db_path,
                        "--session-id",
                        "session-cli-inspect-001",
                    ]
                )

        self.assertEqual(first_code, 0)
        self.assertEqual(second_code, 0)
        self.assertEqual(inspect_code, 0)
        snapshot = json.loads(inspect_out.getvalue())
        self.assertEqual(snapshot["session_id"], "session-cli-inspect-001")
        self.assertEqual(len(snapshot["recent_execution_spans"]), 2)
        self.assertEqual(len(snapshot["recent_audit_ids"]), 2)

    def test_cli_agent_run_accepts_input_text_and_returns_final_response(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            code = core_cli_main(
                [
                    "agent-run",
                    "--input-text",
                    "please check current status",
                    "--session-id",
                    "agent-run-001",
                    "--memory-backend",
                    "local",
                ]
            )

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["command"], "agent-run")
        self.assertEqual(payload["session_id"], "agent-run-001")
        self.assertEqual(payload["final_response"]["speaker"], "affective")
        self.assertTrue(payload["final_response"]["delegated"])
        self.assertEqual(payload["tool_results"][0]["tool_name"], "system_query_device")
        self.assertIn("query device", payload["final_response"]["text"])

    def test_cli_agent_run_accepts_mock_social_ingress(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            code = core_cli_main(
                [
                    "agent-run",
                    "--social-text",
                    "please check status from social chat",
                    "--social-adapter-kind",
                    "mock_qq",
                    "--social-channel-id",
                    "group-42",
                    "--social-channel-kind",
                    "group",
                    "--social-user-id",
                    "alice",
                    "--session-id",
                    "agent-run-social-001",
                ]
            )

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["command"], "agent-run")
        self.assertEqual(payload["session_id"], "agent-run-social-001")
        self.assertEqual(payload["final_response"]["speaker"], "affective")
        self.assertEqual(payload["agent_run_evidence"]["event_source"], "mock_social")
        self.assertEqual(payload["events_persisted"], 1)
        self.assertEqual(payload["agent_run_evidence"]["db_counts"]["perception_events"], 1)
        self.assertTrue(payload["agent_run_evidence"]["ok"])

    def test_cli_social_chat_returns_plain_text_response(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            code = core_cli_main(
                [
                    "social-chat",
                    "--message",
                    "please check current status",
                    "--social-adapter-kind",
                    "mock_qq",
                    "--social-channel-id",
                    "group-43",
                    "--social-channel-kind",
                    "group",
                    "--social-user-id",
                    "alice",
                ]
            )

        self.assertEqual(code, 0)
        self.assertIn("query device", out.getvalue())

    def test_cli_social_chat_surfaces_pending_approval_in_text_mode(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            code = core_cli_main(
                [
                    "social-chat",
                    "--message",
                    "restart the app now",
                    "--social-adapter-kind",
                    "mock_qq",
                    "--social-channel-id",
                    "group-44",
                    "--social-channel-kind",
                    "group",
                    "--social-user-id",
                    "alice",
                ]
            )

        self.assertEqual(code, 0)
        self.assertIn("Approval required:", out.getvalue())

    def test_cli_social_adapter_smoke_reports_ingress_and_affective_egress(self) -> None:
        smoke_out = io.StringIO()
        with redirect_stdout(smoke_out):
            smoke_code = core_cli_main([
                "social-adapter-smoke",
            ])

        self.assertEqual(smoke_code, 0)
        payload = json.loads(smoke_out.getvalue())
        self.assertEqual(payload["schema_version"], "2.1.0-social-adapter-smoke-v1")
        self.assertEqual(payload["command"], "social-adapter-smoke")
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["closure_gates"]["social_event_persisted"])
        self.assertTrue(payload["closure_gates"]["affective_delivery_recorded"])
        self.assertTrue(payload["closure_gates"]["social_adapter_registry_gate"])
        self.assertTrue(payload["closure_gates"]["qq_social_gate"])
        self.assertTrue(payload["closure_gates"]["onebot_social_gate"])
        self.assertTrue(payload["closure_gates"]["wecom_social_gate"])
        self.assertTrue(payload["closure_gates"]["wechat_ilink_social_gate"])
        self.assertTrue(payload["closure_gates"]["qq_openclaw_social_gate"])
        self.assertTrue(payload["closure_gates"]["social_compliance_gate"])
        self.assertIn("qq_official", payload["evidence_summary"]["ready_adapter_names"])
        self.assertIn("onebot_qq", payload["evidence_summary"]["ready_adapter_names"])
        self.assertIn("wecom", payload["evidence_summary"]["ready_adapter_names"])
        self.assertIn("wechat_ilink", payload["evidence_summary"]["ready_adapter_names"])
        self.assertIn("qq_openclaw", payload["evidence_summary"]["ready_adapter_names"])
        self.assertIn("qq_official", payload["evidence_summary"]["tested_adapter_names"])
        self.assertIn("onebot_qq", payload["evidence_summary"]["tested_adapter_names"])
        self.assertIn("wecom", payload["evidence_summary"]["tested_adapter_names"])
        self.assertIn("wechat_ilink", payload["evidence_summary"]["tested_adapter_names"])
        self.assertIn("qq_openclaw", payload["evidence_summary"]["tested_adapter_names"])

    def test_cli_self_improvement_smoke_reports_sandbox_only_governance(self) -> None:
        smoke_out = io.StringIO()
        with redirect_stdout(smoke_out):
            smoke_code = core_cli_main([
                "self-improvement-smoke",
            ])

        self.assertEqual(smoke_code, 0)
        payload = json.loads(smoke_out.getvalue())
        self.assertEqual(payload["schema_version"], "2.1.0-self-improvement-smoke-v1")
        self.assertEqual(payload["command"], "self-improvement-smoke")
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["closure_gates"]["sandbox_mode_isolated"])
        self.assertTrue(payload["closure_gates"]["vitality_replenishment_after_verified_success"])

    def test_cli_task_tracking_smoke_reports_replay_and_cleanup_evidence(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            code = core_cli_main(["task-tracking-smoke"])

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["schema_version"], "2.2.6-task-tracking-smoke-v1")
        self.assertEqual(payload["command"], "task-tracking-smoke")
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["closure_gates"]["active_hours_config_recorded"])
        self.assertTrue(payload["closure_gates"]["heartbeat_linked"])
        self.assertTrue(payload["closure_gates"]["interrupted_task_resumable"])
        self.assertTrue(payload["closure_gates"]["rerun_ready"])

    def test_cli_memory_maintenance_smoke_reports_prompt_safe_consolidation(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            code = core_cli_main(["memory-maintenance-smoke"])

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["schema_version"], "2.2.6-memory-maintenance-smoke-v1")
        self.assertEqual(payload["command"], "memory-maintenance-smoke")
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["closure_gates"]["prompt_safe_summary_recorded"])
        self.assertTrue(payload["closure_gates"]["raw_private_payloads_not_exported"])
        self.assertTrue(payload["closure_gates"]["audit_record_bound"])

    def test_cli_self_optimization_smoke_reports_no_direct_apply_boundary(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            code = core_cli_main(["self-optimization-smoke"])

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["schema_version"], "2.2.6-self-optimization-smoke-v1")
        self.assertEqual(payload["command"], "self-optimization-smoke")
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["closure_gates"]["low_risk_classified"])
        self.assertTrue(payload["closure_gates"]["operator_approval_recorded"])
        self.assertTrue(payload["closure_gates"]["apply_changes_still_forbidden"])
        self.assertFalse(payload["evidence_summary"]["can_apply_changes"])

    def test_cli_world_model_context_smoke_reports_prompt_safe_context(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            code = core_cli_main(["world-model-context-smoke"])

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["schema_version"], "2.2.6-world-model-context-smoke-v1")
        self.assertEqual(payload["command"], "world-model-context-smoke")
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["closure_gates"]["temporal_incidents_recorded"])
        self.assertTrue(payload["closure_gates"]["unit_capability_context_recorded"])
        self.assertTrue(payload["closure_gates"]["relationship_context_prompt_safe"])
        self.assertTrue(payload["closure_gates"]["relay_context_preserved"])

    def test_cli_coding_agent_descriptor_reports_governed_runner_contract(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            code = core_cli_main([
                "coding-agent-descriptor",
                "--runner",
                "copilot",
            ])

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["schema_version"], "2.2.4-coding-agent-descriptor-v1")
        self.assertEqual(payload["runner_name"], "copilot")
        self.assertTrue(payload["approval_required"])
        self.assertTrue(payload["safety_boundaries"]["sandbox_only_execution"])
        self.assertTrue(payload["safety_boundaries"]["autonomous_commit_push_forbidden"])

    def test_cli_coding_agent_self_improvement_route_reports_approved_sandbox_review(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            code = core_cli_main([
                "coding-agent-self-improvement-route",
                "--runner",
                "copilot",
                "--summary",
                "Repair deterministic regression in sandbox",
                "--decision",
                "approve",
                "--tests-passed",
                "--lint-passed",
                "--smoke-passed",
                "--evidence-ref=pytest.txt",
            ])

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["schema_version"], "2.2.4-coding-agent-self-improvement-route-v1")
        self.assertEqual(payload["runner_name"], "copilot")
        self.assertEqual(payload["status"], "approved")
        self.assertTrue(payload["closure_gates"]["review_routing_required"])
        self.assertTrue(payload["closure_gates"]["sandbox_only_execution"])
        self.assertTrue(payload["closure_gates"]["sandbox_execution_recorded"])
        self.assertTrue(payload["closure_gates"]["plan_artifact_recorded"])
        self.assertTrue(payload["closure_gates"]["plan_artifact_contract_supported"])
        self.assertTrue(payload["closure_gates"]["plan_steps_recorded"])
        self.assertTrue(payload["closure_gates"]["callback_audit_recorded"])
        self.assertTrue(payload["closure_gates"]["callback_payload_recorded"])
        self.assertEqual(
            payload["plan_artifact"]["schema_version"],
            "2.2.4-coding-agent-sandbox-plan-v1",
        )
        self.assertEqual(payload["plan_artifact"]["artifact_kind"], "coding_agent_plan")
        self.assertEqual(len(payload["plan_artifact"]["plan_steps"]), 3)
        self.assertEqual(
            payload["plan_artifact"]["callback_contract"]["callback_name"],
            "self_improvement_review_complete",
        )
        self.assertEqual(
            payload["sandbox_execution_record"]["plan_artifact"]["artifact_id"],
            payload["plan_artifact"]["artifact_id"],
        )
        self.assertEqual(payload["sandbox_execution_record"]["status"], "recorded")
        self.assertEqual(payload["callback_audit_record"]["status"], "recorded")
        self.assertEqual(
            payload["callback_audit_record"]["callback_payload"]["plan_artifact_id"],
            payload["plan_artifact"]["artifact_id"],
        )
        self.assertTrue(payload["evidence_summary"]["verified_success"])

    def test_cli_release_224_closure_smoke_reports_full_green_summary(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            code = core_cli_main([
                "release-2.2.4-closure-smoke",
            ])

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["schema_version"], "2.2.4-release-closure-smoke-v1")
        self.assertEqual(payload["command"], "release-2.2.4-closure-smoke")
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["closure_summary"]["ok"])
        self.assertTrue(payload["closure_summary"]["validation_gate_summary"]["ok"])
        self.assertEqual(payload["closure_summary"]["validation_gate_summary"]["passed_count"], 33)
        self.assertEqual(payload["closure_summary"]["validation_gate_summary"]["failed_gate_ids"], [])
        self.assertTrue(payload["closure_summary"]["validation_gates"]["closure_summary_gate"])
        self.assertTrue(payload["closure_summary"]["validation_gates"]["coding_agent_route_gate"])
        self.assertTrue(payload["closure_summary"]["validation_gates"]["real_scene_e2e_gate"])
        self.assertTrue(payload["closure_summary"]["validation_gates"]["persona_seed_gate"])
        self.assertTrue(payload["closure_summary"]["validation_gates"]["persona_growth_gate"])
        self.assertTrue(payload["closure_summary"]["validation_gates"]["memory_immutability_gate"])
        self.assertTrue(
            payload["closure_summary"]["coding_agent_route_summary"]["closure_gates"][
                "plan_artifact_contract_supported"
            ]
        )
        self.assertTrue(
            payload["closure_summary"]["coding_agent_route_summary"]["closure_gates"][
                "plan_steps_recorded"
            ]
        )

    def test_cli_release_224_closure_smoke_can_export_evidence_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            evidence_dir = Path(tmpdir) / "release-224-evidence"
            out = io.StringIO()
            with redirect_stdout(out):
                code = core_cli_main([
                    "release-2.2.4-closure-smoke",
                    "--evidence-dir",
                    str(evidence_dir),
                ])
            self.assertEqual(code, 0)
            payload = json.loads(out.getvalue())
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["evidence_dir"], str(evidence_dir))
            self.assertGreaterEqual(payload["evidence_summary"]["exported_file_count"], 2)
            self.assertTrue(evidence_dir.is_dir())
            self.assertTrue((evidence_dir / "closure-summary.json").is_file())
            self.assertTrue((evidence_dir / "coding-agent-route.json").is_file())
            self.assertIn("closure_summary", payload["evidence_manifest"])
            self.assertIn("coding_agent_route", payload["evidence_manifest"])

    def test_cli_release_226_closure_smoke_reports_additive_gates(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            code = core_cli_main(["release-2.2.6-closure-smoke"])

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["schema_version"], "2.2.6-release-closure-smoke-v1")
        self.assertEqual(payload["command"], "release-2.2.6-closure-smoke")
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["validation_gate_summary"]["ok"])
        self.assertEqual(payload["validation_gate_summary"]["failed_gate_ids"], [])
        self.assertTrue(payload["validation_gates"]["inherited_release_224_gate"])
        self.assertTrue(payload["validation_gates"]["autonomy_heartbeat_gate"])
        self.assertTrue(payload["validation_gates"]["task_tracking_replay_gate"])
        self.assertTrue(payload["validation_gates"]["memory_maintenance_gate"])
        self.assertTrue(payload["validation_gates"]["self_optimization_gate"])
        self.assertTrue(payload["validation_gates"]["world_model_context_gate"])
        self.assertEqual(
            payload["live_rerun_template"]["schema_version"],
            "2.2.6-live-rerun-template-v1",
        )
        self.assertEqual(
            payload["qq_gateway_rerun_archive"]["schema_version"],
            "2.2.6-qq-gateway-rerun-archive-v1",
        )
        self.assertEqual(
            payload["real_unit_rerun_archive"]["schema_version"],
            "2.2.6-real-unit-rerun-archive-v1",
        )
        self.assertEqual(
            payload["wecom_gateway_rerun_archive"]["schema_version"],
            "2.2.6-wecom-gateway-rerun-archive-v1",
        )
        self.assertEqual(
            payload["openclaw_gateway_rerun_archive"]["schema_version"],
            "2.2.6-openclaw-gateway-rerun-archive-v1",
        )
        self.assertEqual(
            payload["hardware_rerun_archive"]["schema_version"],
            "2.2.6-hardware-rerun-archive-v1",
        )
        self.assertEqual(payload["evidence_summary"]["implemented_rerun_archive_count"], 5)
        self.assertEqual(payload["evidence_summary"]["live_rerun_row_count"], 6)

    def test_cli_release_226_closure_smoke_can_export_evidence_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            evidence_dir = Path(tmpdir) / "release-226-evidence"
            out = io.StringIO()
            with redirect_stdout(out):
                code = core_cli_main([
                    "release-2.2.6-closure-smoke",
                    "--evidence-dir",
                    str(evidence_dir),
                ])
            self.assertEqual(code, 0)
            payload = json.loads(out.getvalue())
            self.assertTrue(payload["ok"])
            self.assertTrue(evidence_dir.is_dir())
            self.assertTrue((evidence_dir / "task-tracking-smoke.json").is_file())
            self.assertTrue((evidence_dir / "memory-maintenance-smoke.json").is_file())
            self.assertTrue((evidence_dir / "self-optimization-smoke.json").is_file())
            self.assertTrue((evidence_dir / "world-model-context-smoke.json").is_file())
            self.assertTrue(
                (evidence_dir / "release-2.2.6-live-rerun-template.json").is_file()
            )
            self.assertTrue(
                (evidence_dir / "release-2.2.6-real-unit-rerun-archive.json").is_file()
            )
            self.assertTrue(
                (evidence_dir / "release-2.2.6-qq-gateway-rerun-archive.json").is_file()
            )
            self.assertTrue(
                (evidence_dir / "release-2.2.6-wecom-gateway-rerun-archive.json").is_file()
            )
            self.assertTrue(
                (evidence_dir / "release-2.2.6-openclaw-gateway-rerun-archive.json").is_file()
            )
            self.assertTrue(
                (evidence_dir / "release-2.2.6-hardware-rerun-archive.json").is_file()
            )
            self.assertIn("task_tracking", payload["evidence_manifest"])
            self.assertIn("world_model_context", payload["evidence_manifest"])
            self.assertIn("live_rerun_template", payload["evidence_manifest"])
            self.assertIn("real_unit_rerun_archive", payload["evidence_manifest"])
            self.assertIn("qq_gateway_rerun_archive", payload["evidence_manifest"])
            self.assertIn("wecom_gateway_rerun_archive", payload["evidence_manifest"])
            self.assertIn("openclaw_gateway_rerun_archive", payload["evidence_manifest"])
            self.assertIn("hardware_rerun_archive", payload["evidence_manifest"])

    def test_cli_release_226_promotion_checklist_reports_ready_summary(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            code = core_cli_main(["release-2.2.6-promotion-checklist"])

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["schema_version"], "2.2.6-promotion-checklist-v1")
        self.assertEqual(payload["command"], "release-2.2.6-promotion-checklist")
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["validation_gate_summary"]["ok"])
        self.assertEqual(payload["validation_gate_summary"]["failed_gate_ids"], [])
        self.assertEqual(payload["evidence_summary"]["required_row_count"], 3)
        self.assertEqual(payload["evidence_summary"]["conditional_row_count"], 3)
        self.assertEqual(payload["evidence_summary"]["ready_required_row_count"], 3)
        self.assertEqual(payload["evidence_summary"]["ready_conditional_row_count"], 3)
        self.assertEqual(
            [row["rerun_id"] for row in payload["required_row_reviews"]],
            ["R226-HW-01", "R226-HW-02", "R226-SOC-01"],
        )
        self.assertEqual(
            [row["rerun_id"] for row in payload["conditional_row_reviews"]],
            ["R226-SOC-02", "R226-SOC-03", "R226-SOC-04"],
        )
        self.assertTrue(payload["validation_gates"]["required_archives_ready"])
        self.assertTrue(payload["validation_gates"]["operator_boundary_preserved"])

    def test_cli_release_226_promotion_checklist_can_export_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            evidence_dir = Path(tmpdir) / "release-226-promotion-checklist"
            out = io.StringIO()
            with redirect_stdout(out):
                code = core_cli_main(
                    [
                        "release-2.2.6-promotion-checklist",
                        "--evidence-dir",
                        str(evidence_dir),
                    ]
                )

            self.assertEqual(code, 0)
            payload = json.loads(out.getvalue())
            self.assertTrue(payload["ok"])
            self.assertTrue(
                (evidence_dir / "release-2.2.6-promotion-checklist.json").is_file()
            )
            self.assertTrue(
                (evidence_dir / "release-2.2.6-closure-smoke.json").is_file()
            )
            self.assertTrue(
                (evidence_dir / "release-2.2.6-live-rerun-template.json").is_file()
            )
            self.assertIn("promotion_checklist", payload["evidence_manifest"])
            self.assertIn("closure_smoke", payload["evidence_manifest"])
            self.assertIn("live_rerun_template", payload["evidence_manifest"])
            self.assertEqual(payload["evidence_summary"]["exported_file_count"], 3)

    def test_cli_release_226_live_rerun_template_emits_hardware_and_social_rows(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            code = core_cli_main(["release-2.2.6-live-rerun-template"])

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["schema_version"], "2.2.6-live-rerun-template-v1")
        self.assertEqual(payload["command"], "release-2.2.6-live-rerun-template")
        self.assertEqual(payload["summary"]["total_rows"], 6)
        self.assertEqual(payload["summary"]["hardware_rows"], 2)
        self.assertEqual(payload["summary"]["social_rows"], 4)
        self.assertEqual(payload["summary"]["required_for_promotion_rows"], 3)
        self.assertEqual(
            [row["rerun_id"] for row in payload["rerun_rows"]],
            [
                "R226-HW-01",
                "R226-HW-02",
                "R226-SOC-01",
                "R226-SOC-02",
                "R226-SOC-03",
                "R226-SOC-04",
            ],
        )
        row_by_id = {row["rerun_id"]: row for row in payload["rerun_rows"]}
        self.assertEqual(
            row_by_id["R226-HW-01"]["implementation_command"],
            "release-2.2.6-hardware-rerun-archive",
        )
        self.assertEqual(
            row_by_id["R226-HW-02"]["implementation_command"],
            "release-2.2.6-hardware-rerun-archive",
        )
        self.assertEqual(
            row_by_id["R226-SOC-02"]["implementation_command"],
            "release-2.2.6-qq-gateway-rerun-archive",
        )
        self.assertEqual(
            row_by_id["R226-SOC-01"]["implementation_command"],
            "release-2.2.6-real-unit-rerun-archive",
        )
        self.assertEqual(
            row_by_id["R226-SOC-03"]["implementation_command"],
            "release-2.2.6-wecom-gateway-rerun-archive",
        )
        self.assertEqual(
            row_by_id["R226-SOC-04"]["implementation_command"],
            "release-2.2.6-openclaw-gateway-rerun-archive",
        )
        self.assertIn(
            "coding-agent-route.json",
            row_by_id["R226-SOC-01"]["required_evidence_artifacts"],
        )
        self.assertIn(
            "qq-official-gateway-run.json",
            row_by_id["R226-SOC-02"]["required_evidence_artifacts"],
        )
        self.assertIn(
            "wecom-gateway-run.json",
            row_by_id["R226-SOC-03"]["required_evidence_artifacts"],
        )
        self.assertIn(
            "openclaw-gateway-run.json",
            row_by_id["R226-SOC-04"]["required_evidence_artifacts"],
        )

    def test_cli_release_226_real_unit_rerun_archive_emits_ready_archive(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            code = core_cli_main(["release-2.2.6-real-unit-rerun-archive"])

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(
            payload["schema_version"],
            "2.2.6-real-unit-rerun-archive-v1",
        )
        self.assertEqual(payload["command"], "release-2.2.6-real-unit-rerun-archive")
        self.assertEqual(payload["covered_rerun_id"], "R226-SOC-01")
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["validation_gates"]["coding_agent_route_ready"])
        self.assertTrue(payload["validation_gates"]["live_event_smoke_ready"])
        self.assertTrue(payload["validation_gates"]["real_scene_e2e_ready"])

    def test_cli_release_226_real_unit_rerun_archive_can_export_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            evidence_dir = Path(tmpdir) / "release-226-real-unit-rerun"
            out = io.StringIO()
            with redirect_stdout(out):
                code = core_cli_main(
                    [
                        "release-2.2.6-real-unit-rerun-archive",
                        "--evidence-dir",
                        str(evidence_dir),
                    ]
                )

            self.assertEqual(code, 0)
            payload = json.loads(out.getvalue())
            self.assertTrue(payload["ok"])
            self.assertTrue((evidence_dir / "live-event-smoke.json").is_file())
            self.assertTrue((evidence_dir / "coding-agent-route.json").is_file())
            self.assertTrue((evidence_dir / "real-scene-e2e.json").is_file())
            self.assertIn("real_scene_e2e", payload["evidence_manifest"])
            self.assertEqual(payload["evidence_summary"]["exported_file_count"], 3)

    def test_cli_release_226_qq_gateway_rerun_archive_emits_ready_archive(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            code = core_cli_main(["release-2.2.6-qq-gateway-rerun-archive"])

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(
            payload["schema_version"],
            "2.2.6-qq-gateway-rerun-archive-v1",
        )
        self.assertEqual(payload["command"], "release-2.2.6-qq-gateway-rerun-archive")
        self.assertEqual(payload["covered_rerun_id"], "R226-SOC-02")
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["validation_gates"]["social_adapter_ready"])
        self.assertTrue(payload["validation_gates"]["qq_gateway_closure_ready"])
        self.assertTrue(payload["validation_gates"]["resume_evidence_recorded"])
        self.assertEqual(payload["template_row"]["rerun_id"], "R226-SOC-02")

    def test_cli_release_226_qq_gateway_rerun_archive_can_export_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            evidence_dir = Path(tmpdir) / "release-226-qq-rerun"
            out = io.StringIO()
            with redirect_stdout(out):
                code = core_cli_main(
                    [
                        "release-2.2.6-qq-gateway-rerun-archive",
                        "--evidence-dir",
                        str(evidence_dir),
                    ]
                )

            self.assertEqual(code, 0)
            payload = json.loads(out.getvalue())
            self.assertTrue(payload["ok"])
            self.assertTrue((evidence_dir / "social-adapter-smoke.json").is_file())
            self.assertTrue((evidence_dir / "qq-official-gateway-run.json").is_file())
            self.assertTrue(
                (evidence_dir / "qq-official-gateway-closure.json").is_file()
            )
            self.assertIn("qq_gateway_run", payload["evidence_manifest"])
            self.assertEqual(payload["evidence_summary"]["exported_file_count"], 3)

    def test_cli_release_226_wecom_gateway_rerun_archive_emits_ready_archive(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            code = core_cli_main(["release-2.2.6-wecom-gateway-rerun-archive"])

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(
            payload["schema_version"],
            "2.2.6-wecom-gateway-rerun-archive-v1",
        )
        self.assertEqual(payload["command"], "release-2.2.6-wecom-gateway-rerun-archive")
        self.assertEqual(payload["covered_rerun_id"], "R226-SOC-03")
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["validation_gates"]["social_adapter_ready"])
        self.assertTrue(payload["validation_gates"]["wecom_gateway_closure_ready"])
        self.assertTrue(payload["validation_gates"]["dispatch_evidence_recorded"])

    def test_cli_release_226_wecom_gateway_rerun_archive_can_export_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            evidence_dir = Path(tmpdir) / "release-226-wecom-rerun"
            out = io.StringIO()
            with redirect_stdout(out):
                code = core_cli_main(
                    [
                        "release-2.2.6-wecom-gateway-rerun-archive",
                        "--evidence-dir",
                        str(evidence_dir),
                    ]
                )

            self.assertEqual(code, 0)
            payload = json.loads(out.getvalue())
            self.assertTrue(payload["ok"])
            self.assertTrue((evidence_dir / "social-adapter-smoke.json").is_file())
            self.assertTrue((evidence_dir / "wecom-gateway-run.json").is_file())
            self.assertTrue((evidence_dir / "wecom-gateway-closure.json").is_file())
            self.assertIn("wecom_gateway_run", payload["evidence_manifest"])
            self.assertEqual(payload["evidence_summary"]["exported_file_count"], 3)

    def test_cli_release_226_openclaw_gateway_rerun_archive_emits_ready_archive(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            code = core_cli_main(["release-2.2.6-openclaw-gateway-rerun-archive"])

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(
            payload["schema_version"],
            "2.2.6-openclaw-gateway-rerun-archive-v1",
        )
        self.assertEqual(
            payload["command"], "release-2.2.6-openclaw-gateway-rerun-archive"
        )
        self.assertEqual(payload["covered_rerun_id"], "R226-SOC-04")
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["validation_gates"]["social_adapter_ready"])
        self.assertTrue(payload["validation_gates"]["openclaw_gateway_closure_ready"])
        self.assertTrue(payload["validation_gates"]["plugin_ready_recorded"])

    def test_cli_release_226_openclaw_gateway_rerun_archive_can_export_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            evidence_dir = Path(tmpdir) / "release-226-openclaw-rerun"
            out = io.StringIO()
            with redirect_stdout(out):
                code = core_cli_main(
                    [
                        "release-2.2.6-openclaw-gateway-rerun-archive",
                        "--evidence-dir",
                        str(evidence_dir),
                    ]
                )

            self.assertEqual(code, 0)
            payload = json.loads(out.getvalue())
            self.assertTrue(payload["ok"])
            self.assertTrue((evidence_dir / "social-adapter-smoke.json").is_file())
            self.assertTrue((evidence_dir / "openclaw-gateway-run.json").is_file())
            self.assertTrue((evidence_dir / "openclaw-gateway-closure.json").is_file())
            self.assertIn("openclaw_gateway_run", payload["evidence_manifest"])
            self.assertEqual(payload["evidence_summary"]["exported_file_count"], 3)

    def test_cli_release_226_hardware_rerun_archive_emits_ready_archive(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            code = core_cli_main(["release-2.2.6-hardware-rerun-archive"])

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(
            payload["schema_version"],
            "2.2.6-hardware-rerun-archive-v1",
        )
        self.assertEqual(payload["command"], "release-2.2.6-hardware-rerun-archive")
        self.assertEqual(payload["covered_rerun_ids"], ["R226-HW-01", "R226-HW-02"])
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["validation_gates"]["hardware_budget_rerun_ready"])
        self.assertTrue(payload["validation_gates"]["rollback_operator_rerun_ready"])
        self.assertTrue(payload["operator_handoff"]["operator_approval_required"])

    def test_cli_release_226_hardware_rerun_archive_can_export_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            evidence_dir = Path(tmpdir) / "release-226-hardware-rerun"
            out = io.StringIO()
            with redirect_stdout(out):
                code = core_cli_main(
                    [
                        "release-2.2.6-hardware-rerun-archive",
                        "--evidence-dir",
                        str(evidence_dir),
                    ]
                )

            self.assertEqual(code, 0)
            payload = json.loads(out.getvalue())
            self.assertTrue(payload["ok"])
            self.assertTrue((evidence_dir / "hardware-compatibility.json").is_file())
            self.assertTrue((evidence_dir / "hardware-acceptance-matrix.json").is_file())
            self.assertTrue((evidence_dir / "resource-budget-governance.json").is_file())
            self.assertTrue((evidence_dir / "signing-provenance.json").is_file())
            self.assertTrue((evidence_dir / "observability-diagnosis.json").is_file())
            self.assertTrue(
                (evidence_dir / "release-rollback-hardening.json").is_file()
            )
            self.assertEqual(payload["evidence_summary"]["exported_file_count"], 6)

    def test_cli_tool_threat_descriptor_reports_high_risk_argument_mix(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            code = core_cli_main([
                "tool-threat-descriptor",
                "--tool",
                "system_restart_app",
                "--arg=--gateway-url=ws://127.0.0.1:8811/openclaw",
                "--arg=--access-token-env-var=WECOM_BOT_TOKEN",
                "--arg=--note=status && echo risky",
            ])

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["tool_name"], "system_restart_app")
        self.assertEqual(payload["overall_severity"], "high")
        self.assertTrue(payload["requires_operator_approval"])
        self.assertTrue(payload["network_target_arguments_present"])
        self.assertTrue(payload["credential_arguments_present"])
        self.assertTrue(payload["shell_metachar_arguments_present"])

    def test_cli_mcp_read_only_execute_reports_executed_tool_payload(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            code = core_cli_main([
                "mcp-read-only-execute",
                "--tool",
                "system_query_device",
                "--arg=--node=unit-01",
            ])

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["command"], "mcp-read-only-execute")
        self.assertEqual(payload["tool_name"], "system_query_device")
        self.assertEqual(payload["mcp_descriptor"]["bridge_mode"], "core_governed_read_only_execution")
        self.assertTrue(payload["policy_decision"]["allowed"])
        self.assertEqual(payload["tool_result"]["status"], "ok")

    def test_cli_mcp_tool_governance_descriptor_reports_governed_restart_contract(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            code = core_cli_main([
                "mcp-tool-governance-descriptor",
                "--tool",
                "system_restart_app",
                "--arg=--lease-id=lease-001",
            ])

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["tool_name"], "system_restart_app")
        self.assertEqual(payload["governance_path"], "core_approval_required_proposal")
        self.assertTrue(payload["execution_requirements"]["operator_approval_required"])
        self.assertTrue(payload["execution_requirements"]["approval_proposal_allowed"])

    def test_cli_agent_run_routes_user_query_to_apps_tool(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            code = core_cli_main(
                [
                    "agent-run",
                    "--input-text",
                    "show current apps on the unit",
                    "--session-id",
                    "agent-run-apps-001",
                ]
            )

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["tool_results"][0]["tool_name"], "system_query_apps")
        self.assertEqual(
            payload["tool_results"][0]["payload"]["result"]["replies"][0]["payload"]["status"],
            "ok",
        )

    def test_cli_agent_run_routes_restart_request_to_pending_approval(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            code = core_cli_main(
                [
                    "agent-run",
                    "--input-text",
                    "restart the app now",
                    "--session-id",
                    "agent-run-restart-001",
                ]
            )

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["tool_results"][0]["tool_name"], "system_restart_app")
        self.assertEqual(payload["tool_results"][0]["status"], "pending_approval")
        self.assertEqual(
            payload["tool_results"][0]["payload"]["failure_class"],
            "approval_gate_pending",
        )
        self.assertEqual(
            payload["tool_results"][0]["payload"]["approval_request"]["tool_name"],
            "system_restart_app",
        )
        self.assertIn(
            "approval_request_id",
            payload["tool_results"][0]["payload"]["approval_request"],
        )
        self.assertEqual(len(payload["session"]["pending_approval_requests"]), 1)
        self.assertIn("waiting for explicit approval", payload["final_response"]["text"])
        self.assertTrue(payload["agent_run_evidence"]["ok"])
        self.assertEqual(
            payload["agent_run_evidence"]["evidence_counts"]["approval_requests"],
            1,
        )
        self.assertEqual(
            payload["agent_run_evidence"]["evidence_counts"]["tool_results"],
            1,
        )

    def test_cli_agent_run_routes_other_app_control_requests_to_pending_approval(self) -> None:
        for input_text, expected_tool_name in (
            ("start the app now", "system_start_app"),
            ("stop the app now", "system_stop_app"),
            ("unload the app now", "system_unload_app"),
        ):
            with self.subTest(input_text=input_text):
                out = io.StringIO()
                with redirect_stdout(out):
                    code = core_cli_main(
                        [
                            "agent-run",
                            "--input-text",
                            input_text,
                            "--session-id",
                            f"agent-run-{expected_tool_name}",
                        ]
                    )

                self.assertEqual(code, 0)
                payload = json.loads(out.getvalue())
                self.assertEqual(payload["tool_results"][0]["tool_name"], expected_tool_name)
                self.assertEqual(payload["tool_results"][0]["status"], "pending_approval")
                self.assertEqual(
                    payload["tool_results"][0]["payload"]["approval_request"]["tool_name"],
                    expected_tool_name,
                )
                self.assertEqual(len(payload["session"]["pending_approval_requests"]), 1)

    def test_cli_approval_inspect_and_approve_is_blocked_when_required_resources_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "core.db")

            run_out = io.StringIO()
            with redirect_stdout(run_out):
                run_code = core_cli_main(
                    [
                        "agent-run",
                        "--db",
                        db_path,
                        "--input-text",
                        "restart the app now",
                        "--session-id",
                        "approval-session-001",
                    ]
                )

            run_payload = json.loads(run_out.getvalue())
            approval_request_id = run_payload["tool_results"][0]["payload"]["approval_request"][
                "approval_request_id"
            ]

            inspect_out = io.StringIO()
            with redirect_stdout(inspect_out):
                inspect_code = core_cli_main(
                    [
                        "approval-inspect",
                        "--db",
                        db_path,
                        "--approval-request-id",
                        approval_request_id,
                    ]
                )

            approve_out = io.StringIO()
            with redirect_stdout(approve_out):
                approve_code = core_cli_main(
                    [
                        "approval-decision",
                        "--db",
                        db_path,
                        "--approval-request-id",
                        approval_request_id,
                        "--decision",
                        "approve",
                    ]
                )

            session_out = io.StringIO()
            with redirect_stdout(session_out):
                session_code = core_cli_main(
                    [
                        "session-inspect",
                        "--db",
                        db_path,
                        "--session-id",
                        "approval-session-001",
                    ]
                )

        self.assertEqual(run_code, 0)
        self.assertEqual(inspect_code, 0)
        self.assertEqual(approve_code, 0)
        self.assertEqual(session_code, 0)

        inspect_payload = json.loads(inspect_out.getvalue())
        self.assertEqual(inspect_payload["approval_request"]["status"], "pending")
        self.assertIsNotNone(
            inspect_payload["approval_context"]["source_execution_evidence"]
        )
        self.assertEqual(
            inspect_payload["approval_context"]["operator_requirements"]["required_resources"],
            ["app_control_lease"],
        )
        self.assertEqual(
            inspect_payload["approval_context"]["operator_requirements"]["missing_required_resources"],
            ["app_control_lease"],
        )
        self.assertEqual(
            inspect_payload["approval_context"]["operator_requirements"]["lease_observation"]["status"],
            "ok",
        )
        self.assertEqual(
            inspect_payload["approval_context"]["operator_requirements"]["state_sync_observation"]["status"],
            "ok",
        )

        approve_payload = json.loads(approve_out.getvalue())
        self.assertFalse(approve_payload["ok"])
        self.assertEqual(approve_payload["status"], "blocked_resource_gate")
        self.assertEqual(
            approve_payload["failure_status"],
            "missing_required_resources",
        )
        self.assertIsNone(approve_payload["resumed_execution"])
        self.assertEqual(approve_payload["approval_request"]["status"], "pending")
        self.assertIsNotNone(
            approve_payload["approval_context"]["source_execution_evidence"]
        )
        self.assertIsNone(
            approve_payload["approval_context"]["resumed_execution_evidence"]
        )
        self.assertEqual(
            approve_payload["approval_context"]["source_execution_evidence"]["policy_decisions"][0]["tool_name"],
            "system_restart_app",
        )
        self.assertEqual(
            approve_payload["approval_context"]["operator_requirements"]["resource_requirements_satisfied"],
            False,
        )

        session_payload = json.loads(session_out.getvalue())
        self.assertEqual(session_payload["session_id"], "approval-session-001")
        self.assertEqual(len(session_payload["pending_approval_requests"]), 1)

    def test_cli_approval_inspect_and_approve_resume_execution_when_resources_are_satisfied(self) -> None:
        class LeaseSatisfiedAdapter(FakeUnitToolAdapter):
            def execute(self, tool_name: str, args: dict[str, object]) -> ToolExecutionResult:
                if tool_name == "system_query_leases":
                    contract = self.describe_tool(tool_name)
                    assert contract is not None
                    return ToolExecutionResult(
                        tool_result_id="tool-lease-satisfied-001",
                        tool_name=tool_name,
                        status="ok",
                        payload={
                            "contract": contract.to_dict(),
                            "mode": "fake_no_model",
                            "side_effect_level": contract.side_effect_level.value,
                            "result": {
                                "ok": True,
                                "status": "ok",
                                "payload": {"request_id": "req-lease-001"},
                                "replies": [
                                    {
                                        "ok": True,
                                        "payload": {
                                            "status": "ok",
                                            "leases": [
                                                {
                                                    "resource": "app/neuro_demo_gpio/control",
                                                    "lease_id": "lease-gpio-001",
                                                }
                                            ],
                                        },
                                    }
                                ],
                            },
                        },
                    )
                if tool_name == "system_query_apps":
                    contract = self.describe_tool(tool_name)
                    assert contract is not None
                    return ToolExecutionResult(
                        tool_result_id="tool-app-satisfied-001",
                        tool_name=tool_name,
                        status="ok",
                        payload={
                            "contract": contract.to_dict(),
                            "mode": "fake_no_model",
                            "side_effect_level": contract.side_effect_level.value,
                            "result": {
                                "ok": True,
                                "status": "ok",
                                "payload": {"request_id": "req-app-001"},
                                "replies": [
                                    {
                                        "ok": True,
                                        "payload": {
                                            "status": "ok",
                                            "app_count": 1,
                                            "apps": [{"app_id": "neuro_demo_gpio"}],
                                        },
                                    }
                                ],
                            },
                        },
                    )
                return super().execute(tool_name, cast(dict[str, Any], args))

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "core.db")

            run_out = io.StringIO()
            with redirect_stdout(run_out):
                run_code = core_cli_main(
                    [
                        "agent-run",
                        "--db",
                        db_path,
                        "--input-text",
                        "restart the app now",
                        "--session-id",
                        "approval-session-satisfied-001",
                    ]
                )

            run_payload = json.loads(run_out.getvalue())
            approval_request_id = run_payload["tool_results"][0]["payload"]["approval_request"][
                "approval_request_id"
            ]

            inspect_out = io.StringIO()
            with mock.patch(
                "neurolink_core.cli.NeuroCliToolAdapter",
                return_value=LeaseSatisfiedAdapter(),
            ):
                with redirect_stdout(inspect_out):
                    inspect_code = core_cli_main(
                        [
                            "approval-inspect",
                            "--db",
                            db_path,
                            "--approval-request-id",
                            approval_request_id,
                            "--tool-adapter",
                            "neuro-cli",
                        ]
                    )

            approve_out = io.StringIO()
            with mock.patch(
                "neurolink_core.cli.NeuroCliToolAdapter",
                return_value=LeaseSatisfiedAdapter(),
            ):
                with redirect_stdout(approve_out):
                    approve_code = core_cli_main(
                        [
                            "approval-decision",
                            "--db",
                            db_path,
                            "--approval-request-id",
                            approval_request_id,
                            "--decision",
                            "approve",
                            "--tool-adapter",
                            "neuro-cli",
                        ]
                    )

        self.assertEqual(run_code, 0)
        self.assertEqual(inspect_code, 0)
        self.assertEqual(approve_code, 0)

        inspect_payload = json.loads(inspect_out.getvalue())
        self.assertTrue(
            inspect_payload["approval_context"]["operator_requirements"]["resource_requirements_satisfied"]
        )
        self.assertEqual(
            inspect_payload["approval_context"]["operator_requirements"]["missing_required_resources"],
            [],
        )

        approve_payload = json.loads(approve_out.getvalue())
        self.assertTrue(approve_payload["ok"])
        self.assertEqual(approve_payload["status"], "approved")
        self.assertIsNotNone(approve_payload["resumed_execution"])
        assert approve_payload["resumed_execution"] is not None
        self.assertEqual(
            approve_payload["resumed_execution"]["tool_result"]["tool_name"],
            "system_restart_app",
        )
        self.assertEqual(
            approve_payload["approval_context"]["operator_requirements"]["missing_required_resources"],
            [],
        )

    def test_cli_social_approval_inspect_and_deny_records_social_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            db_path = str(Path(tempdir) / "approval-social.db")

            run_out = io.StringIO()
            with redirect_stdout(run_out):
                run_code = core_cli_main(
                    [
                        "agent-run",
                        "--db",
                        db_path,
                        "--social-text",
                        "restart the app now",
                        "--social-adapter-kind",
                        "mock_qq",
                        "--social-channel-id",
                        "group-42",
                        "--social-channel-kind",
                        "group",
                        "--social-user-id",
                        "alice",
                        "--session-id",
                        "approval-social-session-001",
                    ]
                )

            run_payload = json.loads(run_out.getvalue())
            approval_request_id = run_payload["tool_results"][0]["payload"]["approval_request"][
                "approval_request_id"
            ]

            inspect_out = io.StringIO()
            with redirect_stdout(inspect_out):
                inspect_code = core_cli_main(
                    [
                        "social-approval-inspect",
                        "--db",
                        db_path,
                        "--approval-request-id",
                        approval_request_id,
                        "--social-adapter-kind",
                        "mock_qq",
                        "--social-channel-id",
                        "group-42",
                        "--social-channel-kind",
                        "group",
                        "--social-user-id",
                        "alice",
                    ]
                )

            deny_out = io.StringIO()
            with redirect_stdout(deny_out):
                deny_code = core_cli_main(
                    [
                        "social-approval-decision",
                        "--db",
                        db_path,
                        "--approval-request-id",
                        approval_request_id,
                        "--decision",
                        "deny",
                        "--decision-text",
                        "deny from bound social channel",
                        "--social-adapter-kind",
                        "mock_qq",
                        "--social-channel-id",
                        "group-42",
                        "--social-channel-kind",
                        "group",
                        "--social-user-id",
                        "alice",
                    ]
                )

        self.assertEqual(run_code, 0)
        self.assertEqual(inspect_code, 0)
        self.assertEqual(deny_code, 0)

        inspect_payload = json.loads(inspect_out.getvalue())
        self.assertEqual(inspect_payload["social_context"]["principal_id"], "mock_qq:alice")
        self.assertEqual(inspect_payload["social_context"]["channel_kind"], "group")
        self.assertEqual(
            inspect_payload["approval_summary"]["tool_name"],
            "system_restart_app",
        )
        self.assertIn("Pending approval", inspect_payload["approval_summary"]["human_summary"])

        deny_payload = json.loads(deny_out.getvalue())
        self.assertTrue(deny_payload["ok"])
        self.assertEqual(deny_payload["status"], "denied")
        self.assertIsNone(deny_payload["resumed_execution"])
        self.assertEqual(deny_payload["approval_metadata"]["principal_id"], "mock_qq:alice")
        self.assertEqual(deny_payload["approval_metadata"]["approval_channel"], "social")

    def test_cli_approval_social_smoke_reports_bound_social_denial(self) -> None:
        smoke_out = io.StringIO()
        with redirect_stdout(smoke_out):
            smoke_code = core_cli_main([
                "approval-social-smoke",
            ])

        self.assertEqual(smoke_code, 0)
        payload = json.loads(smoke_out.getvalue())
        self.assertEqual(payload["schema_version"], "2.1.0-approval-social-smoke-v1")
        self.assertEqual(payload["command"], "approval-social-smoke")
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["closure_gates"]["pending_approval_created"])
        self.assertTrue(payload["closure_gates"]["social_principal_recorded"])
        self.assertTrue(payload["closure_gates"]["denied_decision_prevents_execution"])

    def test_cli_approval_decision_resume_execution_uses_real_neuro_cli_restart_path(self) -> None:
        calls: list[list[str]] = []

        def runner(argv: list[str], timeout_seconds: int) -> CommandExecutionResult:
            del timeout_seconds
            calls.append(argv)
            if "tool-manifest" in argv:
                return CommandExecutionResult(
                    exit_code=0,
                    stdout=json.dumps(
                        {
                            "ok": True,
                            "status": "ok",
                            "schema_version": "1.2.0-tool-manifest-v1",
                            "tools": [
                                {
                                    "name": "system_query_apps",
                                    "description": "apps query",
                                    "argv_template": [
                                        "python",
                                        "neuro_cli/scripts/invoke_neuro_cli.py",
                                        "query",
                                        "apps",
                                        "--output",
                                        "json",
                                    ],
                                    "resource": "app query plane",
                                    "required_arguments": ["--node"],
                                    "side_effect_level": "read_only",
                                    "lease_requirements": [],
                                    "timeout_seconds": 10,
                                    "retryable": True,
                                    "approval_required": False,
                                    "cleanup_hints": [],
                                    "output_contract": {"format": "json", "top_level_ok": True},
                                },
                                {
                                    "name": "system_query_leases",
                                    "description": "leases query",
                                    "argv_template": [
                                        "python",
                                        "neuro_cli/scripts/invoke_neuro_cli.py",
                                        "query",
                                        "leases",
                                        "--output",
                                        "json",
                                    ],
                                    "resource": "lease query plane",
                                    "required_arguments": ["--node"],
                                    "side_effect_level": "read_only",
                                    "lease_requirements": [],
                                    "timeout_seconds": 10,
                                    "retryable": True,
                                    "approval_required": False,
                                    "cleanup_hints": [],
                                    "output_contract": {"format": "json", "top_level_ok": True},
                                },
                                {
                                    "name": "system_state_sync",
                                    "description": "state sync",
                                    "argv_template": [
                                        "python",
                                        "neuro_cli/scripts/invoke_neuro_cli.py",
                                        "system",
                                        "state-sync",
                                        "--output",
                                        "json",
                                    ],
                                    "resource": "state sync aggregate",
                                    "required_arguments": ["--node"],
                                    "side_effect_level": "read_only",
                                    "lease_requirements": [],
                                    "timeout_seconds": 10,
                                    "retryable": True,
                                    "approval_required": False,
                                    "cleanup_hints": [],
                                    "output_contract": {"format": "json", "top_level_ok": True},
                                },
                                {
                                    "name": "system_restart_app",
                                    "description": "restart app",
                                    "argv_template": [
                                        "python",
                                        "neuro_cli/scripts/invoke_neuro_cli.py",
                                        "app",
                                        "stop",
                                        "--output",
                                        "json",
                                    ],
                                    "resource": "app control plane",
                                    "required_arguments": ["--node", "--app-id", "--lease-id"],
                                    "side_effect_level": "approval_required",
                                    "lease_requirements": ["app_control_lease"],
                                    "timeout_seconds": 15,
                                    "retryable": False,
                                    "approval_required": True,
                                    "cleanup_hints": [],
                                    "output_contract": {"format": "json", "top_level_ok": True},
                                },
                            ],
                        }
                    ),
                )
            if "query" in argv and "apps" in argv:
                return CommandExecutionResult(
                    exit_code=0,
                    stdout=json.dumps(
                        {
                            "ok": True,
                            "status": "ok",
                            "replies": [
                                {
                                    "ok": True,
                                    "payload": {
                                        "status": "ok",
                                        "app_count": 1,
                                        "apps": [{"app_id": "neuro_demo_gpio"}],
                                    },
                                }
                            ],
                        }
                    ),
                )
            if "query" in argv and "leases" in argv:
                return CommandExecutionResult(
                    exit_code=0,
                    stdout=json.dumps(
                        {
                            "ok": True,
                            "status": "ok",
                            "replies": [
                                {
                                    "ok": True,
                                    "payload": {
                                        "status": "ok",
                                        "leases": [
                                            {
                                                "resource": "app/neuro_demo_gpio/control",
                                                "lease_id": "lease-gpio-approve-001",
                                            }
                                        ],
                                    },
                                }
                            ],
                        }
                    ),
                )
            if "system" in argv and "state-sync" in argv:
                return CommandExecutionResult(
                    exit_code=0,
                    stdout=json.dumps(
                        {
                            "ok": True,
                            "status": "ok",
                            "schema_version": "1.2.0-state-sync-v1",
                            "state": {
                                "device": {"ok": True, "status": "ok", "payload": {"network_state": "NETWORK_READY"}},
                                "apps": {"ok": True, "status": "ok", "payload": {"app_count": 1}},
                                "leases": {"ok": True, "status": "ok", "payload": {"leases": []}},
                            },
                            "recommended_next_actions": ["state sync is clean; delegated reasoning may continue"],
                        }
                    ),
                )
            if "app" in argv and "stop" in argv:
                self.assertIn("--app-id", argv)
                self.assertIn("neuro_demo_gpio", argv)
                self.assertIn("--lease-id", argv)
                self.assertIn("lease-gpio-approve-001", argv)
                return CommandExecutionResult(
                    exit_code=0,
                    stdout=json.dumps(
                        {"ok": True, "status": "ok", "replies": [{"ok": True, "payload": {"status": "ok", "app_id": "neuro_demo_gpio"}}]}
                    ),
                )
            self.assertIn("app", argv)
            self.assertIn("start", argv)
            self.assertIn("--app-id", argv)
            self.assertIn("neuro_demo_gpio", argv)
            self.assertIn("--lease-id", argv)
            self.assertIn("lease-gpio-approve-001", argv)
            return CommandExecutionResult(
                exit_code=0,
                stdout=json.dumps(
                    {"ok": True, "status": "ok", "replies": [{"ok": True, "payload": {"status": "ok", "app_id": "neuro_demo_gpio"}}]}
                ),
            )

        adapter = NeuroCliToolAdapter(runner=runner)

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "core.db")

            run_out = io.StringIO()
            with redirect_stdout(run_out):
                run_code = core_cli_main(
                    [
                        "agent-run",
                        "--db",
                        db_path,
                        "--input-text",
                        "restart the app now",
                        "--session-id",
                        "approval-session-real-restart-001",
                    ]
                )

            run_payload = json.loads(run_out.getvalue())
            approval_request_id = run_payload["tool_results"][0]["payload"]["approval_request"][
                "approval_request_id"
            ]

            inspect_out = io.StringIO()
            with mock.patch("neurolink_core.cli.NeuroCliToolAdapter", return_value=adapter):
                with redirect_stdout(inspect_out):
                    inspect_code = core_cli_main(
                        [
                            "approval-inspect",
                            "--db",
                            db_path,
                            "--approval-request-id",
                            approval_request_id,
                            "--tool-adapter",
                            "neuro-cli",
                        ]
                    )

            approve_out = io.StringIO()
            with mock.patch("neurolink_core.cli.NeuroCliToolAdapter", return_value=adapter):
                with redirect_stdout(approve_out):
                    approve_code = core_cli_main(
                        [
                            "approval-decision",
                            "--db",
                            db_path,
                            "--approval-request-id",
                            approval_request_id,
                            "--decision",
                            "approve",
                            "--tool-adapter",
                            "neuro-cli",
                        ]
                    )

        self.assertEqual(run_code, 0)
        self.assertEqual(inspect_code, 0)
        self.assertEqual(approve_code, 0)

        inspect_payload = json.loads(inspect_out.getvalue())
        self.assertTrue(
            inspect_payload["approval_context"]["operator_requirements"]["resource_requirements_satisfied"]
        )
        self.assertEqual(
            inspect_payload["approval_context"]["operator_requirements"]["target_app_id"],
            "neuro_demo_gpio",
        )
        self.assertEqual(
            inspect_payload["approval_context"]["operator_requirements"]["matching_lease_ids"],
            ["lease-gpio-approve-001"],
        )

        approve_payload = json.loads(approve_out.getvalue())
        self.assertTrue(approve_payload["ok"])
        self.assertEqual(approve_payload["status"], "approved")
        self.assertEqual(
            approve_payload["resumed_execution"]["tool_result"]["payload"]["resolved_args"]["app_id"],
            "neuro_demo_gpio",
        )
        self.assertEqual(
            approve_payload["resumed_execution"]["tool_result"]["payload"]["resolved_args"]["lease_id"],
            "lease-gpio-approve-001",
        )

        query_apps_calls = [argv for argv in calls if "query" in argv and "apps" in argv]
        query_lease_calls = [argv for argv in calls if "query" in argv and "leases" in argv]
        self.assertEqual(len(query_apps_calls), 2)
        self.assertEqual(len(query_lease_calls), 2)

    def test_cli_approval_decision_resume_execution_uses_real_neuro_cli_stop_path(self) -> None:
        calls: list[list[str]] = []

        def runner(argv: list[str], timeout_seconds: int) -> CommandExecutionResult:
            del timeout_seconds
            calls.append(argv)
            if "tool-manifest" in argv:
                return CommandExecutionResult(
                    exit_code=0,
                    stdout=json.dumps(
                        {
                            "ok": True,
                            "status": "ok",
                            "schema_version": "1.2.0-tool-manifest-v1",
                            "tools": [
                                {
                                    "name": "system_query_apps",
                                    "description": "apps query",
                                    "argv_template": [
                                        "python",
                                        "neuro_cli/scripts/invoke_neuro_cli.py",
                                        "query",
                                        "apps",
                                        "--output",
                                        "json",
                                    ],
                                    "resource": "app query plane",
                                    "required_arguments": ["--node"],
                                    "side_effect_level": "read_only",
                                    "lease_requirements": [],
                                    "timeout_seconds": 10,
                                    "retryable": True,
                                    "approval_required": False,
                                    "cleanup_hints": [],
                                    "output_contract": {"format": "json", "top_level_ok": True},
                                },
                                {
                                    "name": "system_query_leases",
                                    "description": "leases query",
                                    "argv_template": [
                                        "python",
                                        "neuro_cli/scripts/invoke_neuro_cli.py",
                                        "query",
                                        "leases",
                                        "--output",
                                        "json",
                                    ],
                                    "resource": "lease query plane",
                                    "required_arguments": ["--node"],
                                    "side_effect_level": "read_only",
                                    "lease_requirements": [],
                                    "timeout_seconds": 10,
                                    "retryable": True,
                                    "approval_required": False,
                                    "cleanup_hints": [],
                                    "output_contract": {"format": "json", "top_level_ok": True},
                                },
                                {
                                    "name": "system_state_sync",
                                    "description": "state sync",
                                    "argv_template": [
                                        "python",
                                        "neuro_cli/scripts/invoke_neuro_cli.py",
                                        "system",
                                        "state-sync",
                                        "--output",
                                        "json",
                                    ],
                                    "resource": "state sync aggregate",
                                    "required_arguments": ["--node"],
                                    "side_effect_level": "read_only",
                                    "lease_requirements": [],
                                    "timeout_seconds": 10,
                                    "retryable": True,
                                    "approval_required": False,
                                    "cleanup_hints": [],
                                    "output_contract": {"format": "json", "top_level_ok": True},
                                },
                                {
                                    "name": "system_stop_app",
                                    "description": "stop app",
                                    "argv_template": [
                                        "python",
                                        "neuro_cli/scripts/invoke_neuro_cli.py",
                                        "app",
                                        "stop",
                                        "--output",
                                        "json",
                                    ],
                                    "resource": "app control plane",
                                    "required_arguments": ["--node", "--app-id", "--lease-id"],
                                    "side_effect_level": "approval_required",
                                    "lease_requirements": ["app_control_lease"],
                                    "timeout_seconds": 15,
                                    "retryable": False,
                                    "approval_required": True,
                                    "cleanup_hints": [],
                                    "output_contract": {"format": "json", "top_level_ok": True},
                                },
                            ],
                        }
                    ),
                )
            if "query" in argv and "apps" in argv:
                return CommandExecutionResult(
                    exit_code=0,
                    stdout=json.dumps(
                        {
                            "ok": True,
                            "status": "ok",
                            "replies": [
                                {
                                    "ok": True,
                                    "payload": {
                                        "status": "ok",
                                        "app_count": 2,
                                        "apps": [
                                            {"app_id": "neuro_demo_gpio"},
                                            {"app_id": "neuro_demo_spi"},
                                        ],
                                    },
                                }
                            ],
                        }
                    ),
                )
            if "query" in argv and "leases" in argv:
                return CommandExecutionResult(
                    exit_code=0,
                    stdout=json.dumps(
                        {
                            "ok": True,
                            "status": "ok",
                            "replies": [
                                {
                                    "ok": True,
                                    "payload": {
                                        "status": "ok",
                                        "leases": [
                                            {
                                                "resource": "app/neuro_demo_spi/control",
                                                "lease_id": "lease-spi-stop-001",
                                            }
                                        ],
                                    },
                                }
                            ],
                        }
                    ),
                )
            if "system" in argv and "state-sync" in argv:
                return CommandExecutionResult(
                    exit_code=0,
                    stdout=json.dumps(
                        {
                            "ok": True,
                            "status": "ok",
                            "schema_version": "1.2.0-state-sync-v1",
                            "state": {
                                "device": {"ok": True, "status": "ok", "payload": {"network_state": "NETWORK_READY"}},
                                "apps": {"ok": True, "status": "ok", "payload": {"app_count": 1}},
                                "leases": {"ok": True, "status": "ok", "payload": {"leases": []}},
                            },
                            "recommended_next_actions": ["state sync is clean; delegated reasoning may continue"],
                        }
                    ),
                )
            self.assertIn("app", argv)
            self.assertIn("stop", argv)
            self.assertIn("--app-id", argv)
            self.assertIn("neuro_demo_spi", argv)
            self.assertIn("--lease-id", argv)
            self.assertIn("lease-spi-stop-001", argv)
            return CommandExecutionResult(
                exit_code=0,
                stdout=json.dumps(
                    {"ok": True, "status": "ok", "replies": [{"ok": True, "payload": {"status": "ok", "app_id": "neuro_demo_spi"}}]}
                ),
            )

        adapter = NeuroCliToolAdapter(runner=runner)

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "core.db")

            run_out = io.StringIO()
            with redirect_stdout(run_out):
                run_code = core_cli_main(
                    [
                        "agent-run",
                        "--db",
                        db_path,
                        "--input-text",
                        "stop neuro_demo_spi app now",
                        "--session-id",
                        "approval-session-real-stop-001",
                    ]
                )

            run_payload = json.loads(run_out.getvalue())
            approval_request_id = run_payload["tool_results"][0]["payload"]["approval_request"][
                "approval_request_id"
            ]

            inspect_out = io.StringIO()
            with mock.patch("neurolink_core.cli.NeuroCliToolAdapter", return_value=adapter):
                with redirect_stdout(inspect_out):
                    inspect_code = core_cli_main(
                        [
                            "approval-inspect",
                            "--db",
                            db_path,
                            "--approval-request-id",
                            approval_request_id,
                            "--tool-adapter",
                            "neuro-cli",
                        ]
                    )

            approve_out = io.StringIO()
            with mock.patch("neurolink_core.cli.NeuroCliToolAdapter", return_value=adapter):
                with redirect_stdout(approve_out):
                    approve_code = core_cli_main(
                        [
                            "approval-decision",
                            "--db",
                            db_path,
                            "--approval-request-id",
                            approval_request_id,
                            "--decision",
                            "approve",
                            "--tool-adapter",
                            "neuro-cli",
                        ]
                    )

        self.assertEqual(run_code, 0)
        self.assertEqual(inspect_code, 0)
        self.assertEqual(approve_code, 0)

        inspect_payload = json.loads(inspect_out.getvalue())
        self.assertTrue(
            inspect_payload["approval_context"]["operator_requirements"]["resource_requirements_satisfied"]
        )
        self.assertEqual(
            inspect_payload["approval_context"]["operator_requirements"]["target_app_id"],
            "neuro_demo_spi",
        )
        self.assertEqual(
            inspect_payload["approval_context"]["operator_requirements"]["matching_lease_ids"],
            ["lease-spi-stop-001"],
        )

        approve_payload = json.loads(approve_out.getvalue())
        self.assertTrue(approve_payload["ok"])
        self.assertEqual(approve_payload["status"], "approved")
        self.assertEqual(
            approve_payload["resumed_execution"]["tool_result"]["tool_name"],
            "system_stop_app",
        )
        self.assertEqual(
            approve_payload["resumed_execution"]["tool_result"]["payload"]["resolved_args"]["app_id"],
            "neuro_demo_spi",
        )
        self.assertEqual(
            approve_payload["resumed_execution"]["tool_result"]["payload"]["resolved_args"]["lease_id"],
            "lease-spi-stop-001",
        )

        stop_calls = [argv for argv in calls if "app" in argv and "stop" in argv]
        start_calls = [argv for argv in calls if "app" in argv and "start" in argv]
        self.assertEqual(len(stop_calls), 1)
        self.assertEqual(len(start_calls), 0)

    def test_cli_approval_decision_can_deny_without_resuming(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "core.db")

            run_out = io.StringIO()
            with redirect_stdout(run_out):
                run_code = core_cli_main(
                    [
                        "agent-run",
                        "--db",
                        db_path,
                        "--input-text",
                        "restart the app now",
                        "--session-id",
                        "approval-session-deny-001",
                    ]
                )

            run_payload = json.loads(run_out.getvalue())
            approval_request_id = run_payload["tool_results"][0]["payload"]["approval_request"][
                "approval_request_id"
            ]

            deny_out = io.StringIO()
            with redirect_stdout(deny_out):
                deny_code = core_cli_main(
                    [
                        "approval-decision",
                        "--db",
                        db_path,
                        "--approval-request-id",
                        approval_request_id,
                        "--decision",
                        "deny",
                    ]
                )

        self.assertEqual(run_code, 0)
        self.assertEqual(deny_code, 0)
        deny_payload = json.loads(deny_out.getvalue())
        self.assertEqual(deny_payload["status"], "denied")
        self.assertIsNone(deny_payload["resumed_execution"])

    def test_cli_approval_decision_can_expire_without_resuming(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "core.db")

            run_out = io.StringIO()
            with redirect_stdout(run_out):
                run_code = core_cli_main(
                    [
                        "agent-run",
                        "--db",
                        db_path,
                        "--input-text",
                        "restart the app now",
                        "--session-id",
                        "approval-session-expire-001",
                    ]
                )

            run_payload = json.loads(run_out.getvalue())
            approval_request_id = run_payload["tool_results"][0]["payload"]["approval_request"][
                "approval_request_id"
            ]

            expire_out = io.StringIO()
            with redirect_stdout(expire_out):
                expire_code = core_cli_main(
                    [
                        "approval-decision",
                        "--db",
                        db_path,
                        "--approval-request-id",
                        approval_request_id,
                        "--decision",
                        "expire",
                    ]
                )

            inspect_out = io.StringIO()
            with redirect_stdout(inspect_out):
                inspect_code = core_cli_main(
                    [
                        "approval-inspect",
                        "--db",
                        db_path,
                        "--approval-request-id",
                        approval_request_id,
                    ]
                )

        self.assertEqual(run_code, 0)
        self.assertEqual(expire_code, 0)
        self.assertEqual(inspect_code, 0)

        expire_payload = json.loads(expire_out.getvalue())
        self.assertEqual(expire_payload["status"], "expired")
        self.assertIsNone(expire_payload["resumed_execution"])

        inspect_payload = json.loads(inspect_out.getvalue())
        self.assertEqual(inspect_payload["approval_request"]["status"], "expired")
        self.assertIsNone(inspect_payload["approval_context"]["resumed_execution_evidence"])

    def test_cli_rollback_approval_surfaces_recovery_candidate_summary(self) -> None:
        class MissingAppHealthGuardAdapter(FakeUnitToolAdapter):
            def execute(self, tool_name: str, args: dict[str, Any]) -> ToolExecutionResult:
                if tool_name == "system_query_leases":
                    contract = self.describe_tool(tool_name)
                    assert contract is not None
                    return ToolExecutionResult(
                        tool_result_id="tool-lease-observe-cli-001",
                        tool_name=tool_name,
                        status="ok",
                        payload={
                            "contract": contract.to_dict(),
                            "result": {
                                "ok": True,
                                "status": "ok",
                                "payload": {"request_id": "req-lease-cli-001"},
                                "replies": [
                                    {
                                        "ok": True,
                                        "payload": {
                                            "status": "ok",
                                            "leases": [
                                                {
                                                    "resource": "update/app/neuro_demo_gpio/rollback",
                                                    "lease_id": "lease-gpio-rollback-cli-001",
                                                }
                                            ],
                                        },
                                    }
                                ],
                            },
                        },
                    )
                if tool_name == "system_rollback_app":
                    contract = self.describe_tool(tool_name)
                    assert contract is not None
                    return ToolExecutionResult(
                        tool_result_id="tool-rollback-cli-001",
                        tool_name=tool_name,
                        status="ok",
                        payload={
                            "contract": contract.to_dict(),
                            "resolved_args": {
                                "app_id": str(args.get("app_id") or ""),
                                "app": str(args.get("app") or args.get("app_id") or ""),
                                "lease_id": str(args.get("lease_id") or ""),
                                "reason": str(args.get("reason") or ""),
                            },
                            "result": {
                                "ok": True,
                                "status": "ok",
                                "replies": [
                                    {
                                        "ok": True,
                                        "payload": {
                                            "status": "ok",
                                            "app_id": str(args.get("app_id") or ""),
                                            "action": "rollback",
                                        },
                                    }
                                ],
                            },
                        },
                    )
                return super().execute(tool_name, args)

            def build_state_sync_snapshot(self, args: dict[str, Any]) -> StateSyncSnapshot:
                event_ids = list(args.get("event_ids") or [])
                return StateSyncSnapshot(
                    status="ok",
                    state={
                        "device": StateSyncSurface(
                            ok=True,
                            status="ok",
                            payload={
                                "status": "ok",
                                "network_state": "NETWORK_READY",
                                "ipv4": "192.168.2.67",
                            },
                        ),
                        "apps": StateSyncSurface(
                            ok=True,
                            status="ok",
                            payload={
                                "status": "ok",
                                "app_count": 0,
                                "apps": [],
                                "observed_event_ids": event_ids,
                            },
                        ),
                        "leases": StateSyncSurface(
                            ok=True,
                            status="ok",
                            payload={"status": "ok", "leases": []},
                        ),
                    },
                    recommended_next_actions=(
                        "confirm activation evidence and prepare protected rollback review",
                    ),
                )

        events = [
            {
                "event_id": "evt-activate-failed-cli-001",
                "source_kind": "unit",
                "source_node": "unit-01",
                "source_app": "neuro_demo_gpio",
                "event_type": "lifecycle",
                "semantic_topic": "unit.lifecycle.activate_failed",
                "timestamp_wall": "2026-05-04T00:00:00Z",
                "priority": 20,
                "payload": {"target_app_id": "neuro_demo_gpio"},
            }
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "core.db")
            events_path = Path(tmpdir) / "activate_failed_events.json"
            events_path.write_text(json.dumps(events), encoding="utf-8")
            adapter = MissingAppHealthGuardAdapter()

            replay_out = io.StringIO()
            with mock.patch("neurolink_core.cli.FakeUnitToolAdapter", return_value=adapter):
                with redirect_stdout(replay_out):
                    replay_code = core_cli_main(
                        [
                            "event-replay",
                            "--db",
                            db_path,
                            "--events-file",
                            str(events_path),
                        ]
                    )

            replay_payload = json.loads(replay_out.getvalue())
            approval_request_id = replay_payload["tool_results"][2]["payload"]["approval_request"][
                "approval_request_id"
            ]

            inspect_out = io.StringIO()
            with mock.patch("neurolink_core.cli.FakeUnitToolAdapter", return_value=adapter):
                with redirect_stdout(inspect_out):
                    inspect_code = core_cli_main(
                        [
                            "approval-inspect",
                            "--db",
                            db_path,
                            "--approval-request-id",
                            approval_request_id,
                        ]
                    )

            approve_out = io.StringIO()
            with mock.patch("neurolink_core.cli.FakeUnitToolAdapter", return_value=adapter):
                with redirect_stdout(approve_out):
                    approve_code = core_cli_main(
                        [
                            "approval-decision",
                            "--db",
                            db_path,
                            "--approval-request-id",
                            approval_request_id,
                            "--decision",
                            "approve",
                        ]
                    )

        self.assertEqual(replay_code, 0)
        self.assertEqual(inspect_code, 0)
        self.assertEqual(approve_code, 0)

        inspect_payload = json.loads(inspect_out.getvalue())
        self.assertEqual(
            inspect_payload["approval_context"]["recovery_candidate_summary"]["rollback_decision"],
            "operator_review_required",
        )
        self.assertEqual(
            inspect_payload["approval_context"]["recovery_candidate_summary"]["matching_lease_ids"],
            ["lease-gpio-rollback-cli-001"],
        )
        self.assertEqual(
            inspect_payload["approval_context"]["operator_requirements"]["recovery_candidate_summary"],
            inspect_payload["approval_context"]["recovery_candidate_summary"],
        )
        self.assertEqual(
            inspect_payload["approval_context"]["source_execution_evidence"]["audit_record"]["payload"][
                "activation_health_summary"
            ]["classification"],
            "rollback_required",
        )

        approve_payload = json.loads(approve_out.getvalue())
        self.assertEqual(
            approve_payload["approval_context"]["recovery_candidate_summary"]["app_id"],
            "neuro_demo_gpio",
        )
        self.assertEqual(
            approve_payload["approval_context"]["recovery_candidate_summary"]["matching_lease_ids"],
            ["lease-gpio-rollback-cli-001"],
        )
        self.assertEqual(
            approve_payload["resumed_execution"]["tool_result"]["payload"]["resolved_args"]["lease_id"],
            "lease-gpio-rollback-cli-001",
        )

    def test_cli_approval_decision_rejects_replay_after_terminal_status(self) -> None:
        class LeaseSatisfiedAdapter(FakeUnitToolAdapter):
            def execute(self, tool_name: str, args: dict[str, object]) -> ToolExecutionResult:
                if tool_name == "system_query_leases":
                    contract = self.describe_tool(tool_name)
                    assert contract is not None
                    return ToolExecutionResult(
                        tool_result_id="tool-lease-satisfied-002",
                        tool_name=tool_name,
                        status="ok",
                        payload={
                            "contract": contract.to_dict(),
                            "mode": "fake_no_model",
                            "side_effect_level": contract.side_effect_level.value,
                            "result": {
                                "ok": True,
                                "status": "ok",
                                "payload": {"request_id": "req-lease-002"},
                                "replies": [
                                    {
                                        "ok": True,
                                        "payload": {
                                            "status": "ok",
                                            "leases": [
                                                {
                                                    "resource": "app/neuro_demo_gpio/control",
                                                    "lease_id": "lease-gpio-002",
                                                }
                                            ],
                                        },
                                    }
                                ],
                            },
                        },
                    )
                if tool_name == "system_query_apps":
                    contract = self.describe_tool(tool_name)
                    assert contract is not None
                    return ToolExecutionResult(
                        tool_result_id="tool-app-satisfied-002",
                        tool_name=tool_name,
                        status="ok",
                        payload={
                            "contract": contract.to_dict(),
                            "mode": "fake_no_model",
                            "side_effect_level": contract.side_effect_level.value,
                            "result": {
                                "ok": True,
                                "status": "ok",
                                "payload": {"request_id": "req-app-002"},
                                "replies": [
                                    {
                                        "ok": True,
                                        "payload": {
                                            "status": "ok",
                                            "app_count": 1,
                                            "apps": [{"app_id": "neuro_demo_gpio"}],
                                        },
                                    }
                                ],
                            },
                        },
                    )
                return super().execute(tool_name, cast(dict[str, Any], args))

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "core.db")

            run_out = io.StringIO()
            with redirect_stdout(run_out):
                run_code = core_cli_main(
                    [
                        "agent-run",
                        "--db",
                        db_path,
                        "--input-text",
                        "restart the app now",
                        "--session-id",
                        "approval-session-replay-001",
                    ]
                )

            run_payload = json.loads(run_out.getvalue())
            approval_request_id = run_payload["tool_results"][0]["payload"]["approval_request"][
                "approval_request_id"
            ]

            first_out = io.StringIO()
            with mock.patch(
                "neurolink_core.cli.NeuroCliToolAdapter",
                return_value=LeaseSatisfiedAdapter(),
            ):
                with redirect_stdout(first_out):
                    first_code = core_cli_main(
                        [
                            "approval-decision",
                            "--db",
                            db_path,
                            "--approval-request-id",
                            approval_request_id,
                            "--decision",
                            "approve",
                            "--tool-adapter",
                            "neuro-cli",
                        ]
                    )

            replay_out = io.StringIO()
            with mock.patch(
                "neurolink_core.cli.NeuroCliToolAdapter",
                return_value=LeaseSatisfiedAdapter(),
            ):
                with redirect_stdout(replay_out):
                    replay_code = core_cli_main(
                        [
                            "approval-decision",
                            "--db",
                            db_path,
                            "--approval-request-id",
                            approval_request_id,
                            "--decision",
                            "approve",
                            "--tool-adapter",
                            "neuro-cli",
                        ]
                    )

        self.assertEqual(run_code, 0)
        self.assertEqual(first_code, 0)
        self.assertEqual(replay_code, 2)
        replay_payload = json.loads(replay_out.getvalue())
        self.assertEqual(
            replay_payload["failure_status"],
            "approval_request_not_pending_approved",
        )

    def test_cli_no_model_dry_run_can_use_database_event_slice(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            code = core_cli_main(
                [
                    "no-model-dry-run",
                    "--use-db-events",
                    "--min-priority",
                    "50",
                    "--topic",
                    "unit.callback",
                ]
            )

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["status"], "ok")
        self.assertTrue(payload["query"]["use_db_events"])
        self.assertEqual(payload["query"]["min_priority"], 50)
        self.assertEqual(payload["query"]["topic"], "unit.callback")
        self.assertIn("database_query", payload["steps"])
        self.assertIn("frame_build_from_db", payload["steps"])

    def test_cli_no_model_dry_run_can_use_neuro_cli_adapter(self) -> None:
        def runner(argv: list[str], timeout_seconds: int) -> CommandExecutionResult:
            if "tool-manifest" in argv:
                return CommandExecutionResult(
                    exit_code=0,
                    stdout=json.dumps(
                        {
                            "ok": True,
                            "status": "ok",
                            "schema_version": "1.2.0-tool-manifest-v1",
                            "tools": [
                                {
                                    "name": "system_state_sync",
                                    "description": "state sync",
                                    "argv_template": [
                                        "python",
                                        "neuro_cli/scripts/invoke_neuro_cli.py",
                                        "system",
                                        "state-sync",
                                        "--output",
                                        "json",
                                    ],
                                    "resource": "state sync aggregate",
                                    "required_arguments": ["--node"],
                                    "side_effect_level": "read_only",
                                    "lease_requirements": [],
                                    "timeout_seconds": 10,
                                    "retryable": True,
                                    "approval_required": False,
                                    "cleanup_hints": [],
                                    "output_contract": {"format": "json", "top_level_ok": True},
                                }
                            ],
                        }
                    ),
                )
            return CommandExecutionResult(
                exit_code=0,
                stdout=json.dumps(
                    {
                        "ok": True,
                        "status": "ok",
                        "schema_version": "1.2.0-state-sync-v1",
                        "state": {
                            "device": {"ok": True, "status": "ok", "payload": {"network_state": "NETWORK_READY"}},
                            "apps": {"ok": True, "status": "ok", "payload": {"app_count": 0}},
                            "leases": {"ok": True, "status": "ok", "payload": {"leases": []}},
                        },
                        "recommended_next_actions": [
                            "state sync is clean; read-only delegated reasoning may continue"
                        ],
                    }
                ),
            )

        adapter = NeuroCliToolAdapter(runner=runner)
        out = io.StringIO()
        with mock.patch("neurolink_core.cli.NeuroCliToolAdapter", return_value=adapter):
            with redirect_stdout(out):
                code = core_cli_main(["no-model-dry-run", "--tool-adapter", "neuro-cli"])

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["tool_results"][0]["tool_name"], "system_state_sync")
        self.assertEqual(
            payload["tool_results"][0]["payload"]["state_sync"]["status"], "ok"
        )

    def test_cli_no_model_dry_run_can_ingest_agent_events(self) -> None:
        def runner(argv: list[str], timeout_seconds: int) -> CommandExecutionResult:
            if "agent-events" in argv:
                return CommandExecutionResult(
                    exit_code=0,
                    stdout=json.dumps(
                        {
                            "event_id": "evt-agent-callback-001",
                            "source_kind": "unit_app",
                            "source_node": "unit-01",
                            "source_app": "neuro_demo_gpio",
                            "event_type": "callback",
                            "semantic_topic": "unit.callback",
                            "timestamp_wall": "2026-05-04T00:00:00Z",
                            "priority": 80,
                            "payload": {"callback_enabled": True},
                        }
                    )
                    + "\n"
                    + json.dumps(
                        {
                            "event_id": "evt-agent-tick-001",
                            "source_kind": "clock",
                            "event_type": "time.tick",
                            "semantic_topic": "time.tick",
                            "timestamp_wall": "2026-05-04T00:00:01Z",
                            "priority": 10,
                            "payload": {"period_ms": 1000},
                        }
                    )
                    + "\n",
                )
            if "tool-manifest" in argv:
                return CommandExecutionResult(
                    exit_code=0,
                    stdout=json.dumps(
                        {
                            "ok": True,
                            "status": "ok",
                            "schema_version": "1.2.0-tool-manifest-v1",
                            "tools": [
                                {
                                    "name": "system_state_sync",
                                    "description": "state sync",
                                    "argv_template": ["python", "wrapper.py", "system", "state-sync"],
                                    "resource": "state sync aggregate",
                                    "required_arguments": ["--node"],
                                    "side_effect_level": "read_only",
                                }
                            ],
                        }
                    ),
                )
            return CommandExecutionResult(
                exit_code=0,
                stdout=json.dumps(
                    {
                        "ok": True,
                        "status": "ok",
                        "schema_version": "1.2.0-state-sync-v1",
                        "state": {
                            "device": {"ok": True, "status": "ok", "payload": {"network_state": "NETWORK_READY"}},
                            "apps": {"ok": True, "status": "ok", "payload": {"app_count": 0}},
                            "leases": {"ok": True, "status": "ok", "payload": {"leases": []}},
                        },
                        "recommended_next_actions": [
                            "state sync is clean; read-only delegated reasoning may continue"
                        ],
                    }
                ),
            )

        adapter = NeuroCliToolAdapter(runner=runner)
        out = io.StringIO()
        with mock.patch("neurolink_core.cli.NeuroCliToolAdapter", return_value=adapter):
            with redirect_stdout(out):
                code = core_cli_main(
                    [
                        "no-model-dry-run",
                        "--tool-adapter",
                        "neuro-cli",
                        "--event-source",
                        "neuro-cli-agent-events",
                        "--max-events",
                        "2",
                    ]
                )

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["event_source"], "neuro_cli_agent_events")
        self.assertEqual(payload["events_persisted"], 2)
        self.assertEqual(payload["db_counts"]["perception_events"], 2)
        self.assertEqual(payload["tool_results"][0]["tool_name"], "system_state_sync")
        self.assertEqual(
            payload["execution_evidence"]["execution_span"]["payload"]["event_source"],
            "neuro_cli_agent_events",
        )

    def test_cli_event_replay_loads_json_fixture(self) -> None:
        replay_events = [sample_events()[0], sample_events()[0], sample_events()[1]]

        with tempfile.TemporaryDirectory() as tmpdir:
            fixture_path = Path(tmpdir) / "replay.json"
            fixture_path.write_text(json.dumps({"events": replay_events}), encoding="utf-8")
            out = io.StringIO()
            with redirect_stdout(out):
                code = core_cli_main(
                    [
                        "event-replay",
                        "--events-file",
                        str(fixture_path),
                    ]
                )

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["command"], "event-replay")
        self.assertEqual(payload["event_source"], "replay_file")
        self.assertEqual(
            payload["execution_evidence"]["execution_span"]["payload"]["event_source"],
            "replay_file",
        )
        self.assertEqual(payload["event_replay"]["provided_event_count"], 3)
        self.assertEqual(payload["event_replay"]["duplicate_event_count"], 1)
        self.assertEqual(payload["events_persisted"], 2)

    def test_cli_agent_run_can_ingest_agent_events_with_explicit_provenance(self) -> None:
        def runner(argv: list[str], timeout_seconds: int) -> CommandExecutionResult:
            if "agent-events" in argv:
                return CommandExecutionResult(
                    exit_code=0,
                    stdout=json.dumps(
                        {
                            "event_id": "evt-agent-health-001",
                            "source_kind": "unit",
                            "source_node": "unit-01",
                            "event_type": "health",
                            "semantic_topic": "unit.health.degraded",
                            "timestamp_wall": "2026-05-04T00:00:00Z",
                            "priority": 30,
                            "payload": {"health": "degraded"},
                        }
                    )
                    + "\n"
                    + json.dumps(
                        {
                            "event_id": "evt-agent-online-001",
                            "source_kind": "unit",
                            "source_node": "unit-01",
                            "event_type": "state",
                            "semantic_topic": "unit.state.online",
                            "timestamp_wall": "2026-05-04T00:00:01Z",
                            "priority": 10,
                            "payload": {"status": "online"},
                        }
                    )
                    + "\n",
                )
            if "tool-manifest" in argv:
                return CommandExecutionResult(
                    exit_code=0,
                    stdout=json.dumps(
                        {
                            "ok": True,
                            "status": "ok",
                            "schema_version": "1.2.0-tool-manifest-v1",
                            "tools": [
                                {
                                    "name": "system_state_sync",
                                    "description": "state sync",
                                    "argv_template": ["python", "wrapper.py", "system", "state-sync"],
                                    "resource": "state sync aggregate",
                                    "required_arguments": ["--node"],
                                    "side_effect_level": "read_only",
                                }
                            ],
                        }
                    ),
                )
            return CommandExecutionResult(
                exit_code=0,
                stdout=json.dumps(
                    {
                        "ok": True,
                        "status": "ok",
                        "schema_version": "1.2.0-state-sync-v1",
                        "state": {
                            "device": {"ok": True, "status": "ok", "payload": {"network_state": "NETWORK_READY"}},
                            "apps": {"ok": True, "status": "ok", "payload": {"app_count": 0}},
                            "leases": {"ok": True, "status": "ok", "payload": {"leases": []}},
                        },
                        "recommended_next_actions": [
                            "state sync is clean; read-only delegated reasoning may continue"
                        ],
                    }
                ),
            )

        adapter = NeuroCliToolAdapter(runner=runner)
        out = io.StringIO()
        with mock.patch("neurolink_core.cli.NeuroCliToolAdapter", return_value=adapter):
            with redirect_stdout(out):
                code = core_cli_main(
                    [
                        "agent-run",
                        "--tool-adapter",
                        "neuro-cli",
                        "--event-source",
                        "neuro-cli-agent-events",
                        "--max-events",
                        "2",
                    ]
                )

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["command"], "agent-run")
        self.assertEqual(payload["event_source"], "neuro_cli_agent_events")
        self.assertEqual(payload["events_persisted"], 2)
        self.assertEqual(
            payload["execution_evidence"]["execution_span"]["payload"]["event_source"],
            "neuro_cli_agent_events",
        )
        self.assertEqual(
            payload["agent_run_evidence"]["event_source"],
            "neuro_cli_agent_events",
        )
        self.assertEqual(payload["tool_results"][0]["tool_name"], "system_state_sync")

    def test_cli_event_daemon_loads_batch_fixture(self) -> None:
        callback = sample_events()[0]
        tick = sample_events()[1]

        with tempfile.TemporaryDirectory() as tmpdir:
            fixture_path = Path(tmpdir) / "daemon.json"
            fixture_path.write_text(
                json.dumps({"batches": [[callback], [callback, tick]]}),
                encoding="utf-8",
            )
            out = io.StringIO()
            with redirect_stdout(out):
                code = core_cli_main(
                    [
                        "event-daemon",
                        "--events-file",
                        str(fixture_path),
                        "--session-id",
                        "session-daemon-cli-001",
                    ]
                )

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["command"], "event-daemon")
        self.assertEqual(payload["session_id"], "session-daemon-cli-001")
        self.assertEqual(payload["event_daemon_evidence"]["cycle_count"], 2)
        self.assertEqual(payload["event_daemon_evidence"]["duplicate_event_count"], 1)
        self.assertEqual(payload["db_counts"]["perception_events"], 2)

    def test_cli_agent_run_rejects_real_tool_adapter_gate_with_fake_adapter(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            code = core_cli_main(
                [
                    "agent-run",
                    "--input-text",
                    "check current device status",
                    "--require-real-tool-adapter",
                ]
            )

        self.assertEqual(code, 2)
        payload = json.loads(out.getvalue())
        self.assertFalse(payload["ok"])
        self.assertEqual(
            payload["failure_status"],
            "require_real_tool_adapter_requires_neuro_cli_adapter",
        )

    def test_cli_agent_run_reports_real_tool_adapter_release_gate(self) -> None:
        def runner(argv: list[str], timeout_seconds: int) -> CommandExecutionResult:
            del timeout_seconds
            if "tool-manifest" in argv:
                return CommandExecutionResult(
                    exit_code=0,
                    stdout=json.dumps(
                        {
                            "ok": True,
                            "status": "ok",
                            "schema_version": "1.2.0-tool-manifest-v1",
                            "tools": [
                                {
                                    "name": "system_query_device",
                                    "description": "query device",
                                    "argv_template": [
                                        "python",
                                        "neuro_cli/scripts/invoke_neuro_cli.py",
                                        "query",
                                        "device",
                                        "--output",
                                        "json",
                                    ],
                                    "resource": "device query plane",
                                    "required_arguments": ["--node"],
                                    "side_effect_level": "read_only",
                                }
                            ],
                        }
                    ),
                )
            return CommandExecutionResult(
                exit_code=0,
                stdout=json.dumps(
                    {
                        "ok": True,
                        "status": "ok",
                        "payload": {
                            "request_id": "req-real-adapter-test",
                        },
                        "replies": [
                            {
                                "ok": True,
                                "payload": {
                                    "network_state": "NETWORK_READY",
                                    "status": "ok",
                                },
                            }
                        ],
                    }
                ),
            )

        adapter = NeuroCliToolAdapter(runner=runner)
        out = io.StringIO()
        with mock.patch("neurolink_core.cli.NeuroCliToolAdapter", return_value=adapter):
            with redirect_stdout(out):
                code = core_cli_main(
                    [
                        "agent-run",
                        "--input-text",
                        "check current device status",
                        "--tool-adapter",
                        "neuro-cli",
                        "--require-real-tool-adapter",
                    ]
                )

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        agent_run_evidence = payload["agent_run_evidence"]
        self.assertTrue(agent_run_evidence["release_gate_require_real_tool_adapter"])
        self.assertTrue(agent_run_evidence["real_tool_adapter_present"])
        self.assertTrue(agent_run_evidence["real_tool_execution_succeeded"])
        self.assertEqual(
            agent_run_evidence["tool_adapter_runtime"]["adapter_kind"],
            "neuro-cli",
        )
        self.assertTrue(
            agent_run_evidence["closure_gates"]["real_tool_adapter_present"]
        )
        self.assertTrue(
            agent_run_evidence["closure_gates"]["real_tool_execution_succeeded"]
        )
        self.assertTrue(agent_run_evidence["ok"])

    def test_cli_live_event_smoke_ingests_app_events_with_real_adapter_evidence(self) -> None:
        def runner(argv: list[str], timeout_seconds: int) -> CommandExecutionResult:
            del timeout_seconds
            if "app-events" in argv:
                self.assertIn("--ready-file", argv)
                self.assertIn("/tmp/live-ready", argv)
                return CommandExecutionResult(
                    exit_code=0,
                    stdout=json.dumps(
                        {
                            "ok": True,
                            "subscription": "neuro/unit-01/event/app/neuro_demo_app/**",
                            "listener_mode": "callback",
                            "handler_audit": {"enabled": False, "executed": 0},
                            "events": [
                                {
                                    "event_id": "evt-live-callback-001",
                                    "source_kind": "unit_app",
                                    "source_node": "unit-01",
                                    "source_app": "neuro_demo_app",
                                    "event_type": "callback",
                                    "semantic_topic": "unit.callback",
                                    "timestamp_wall": "2026-05-04T00:00:00Z",
                                    "priority": 80,
                                    "payload": {"callback_enabled": True},
                                }
                            ],
                        }
                    ),
                )
            if "tool-manifest" in argv:
                return CommandExecutionResult(
                    exit_code=0,
                    stdout=json.dumps(
                        {
                            "ok": True,
                            "status": "ok",
                            "schema_version": "1.2.0-tool-manifest-v1",
                            "tools": [
                                {
                                    "name": "system_state_sync",
                                    "description": "state sync",
                                    "argv_template": [
                                        "python",
                                        "neuro_cli/scripts/invoke_neuro_cli.py",
                                        "system",
                                        "state-sync",
                                        "--output",
                                        "json",
                                    ],
                                    "resource": "state sync aggregate",
                                    "required_arguments": ["--node"],
                                    "side_effect_level": "read_only",
                                    "lease_requirements": [],
                                    "timeout_seconds": 10,
                                    "retryable": True,
                                    "approval_required": False,
                                    "cleanup_hints": [],
                                    "output_contract": {"format": "json", "top_level_ok": True},
                                }
                            ],
                        }
                    ),
                )
            return CommandExecutionResult(
                exit_code=0,
                stdout=json.dumps(
                    {
                        "ok": True,
                        "status": "ok",
                        "schema_version": "1.2.0-state-sync-v1",
                        "state": {
                            "device": {"ok": True, "status": "ok", "payload": {"network_state": "NETWORK_READY"}},
                            "apps": {"ok": True, "status": "ok", "payload": {"app_count": 1, "apps": [{"app_id": "neuro_demo_app", "state": "running"}]}},
                            "leases": {"ok": True, "status": "ok", "payload": {"leases": []}},
                        },
                        "recommended_next_actions": [
                            "state sync is clean; read-only delegated reasoning may continue"
                        ],
                    }
                ),
            )

        adapter = NeuroCliToolAdapter(runner=runner)
        out = io.StringIO()
        with mock.patch("neurolink_core.cli.NeuroCliToolAdapter", return_value=adapter):
            with redirect_stdout(out):
                code = core_cli_main(
                    [
                        "live-event-smoke",
                        "--app-id",
                        "neuro_demo_app",
                        "--duration",
                        "1",
                        "--max-events",
                        "1",
                        "--ready-file",
                        "/tmp/live-ready",
                    ]
                )

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["command"], "live-event-smoke")
        self.assertEqual(payload["event_source"], "neuro_cli_app_events_live")
        self.assertEqual(payload["live_event_ingest"]["app_id"], "neuro_demo_app")
        self.assertEqual(payload["live_event_ingest"]["collected_event_count"], 1)
        self.assertEqual(
            payload["live_event_ingest"]["subscription"],
            "neuro/unit-01/event/app/neuro_demo_app/**",
        )
        self.assertEqual(
            payload["execution_evidence"]["execution_span"]["payload"]["event_source"],
            "neuro_cli_app_events_live",
        )
        self.assertEqual(
            payload["agent_run_evidence"]["event_source"],
            "neuro_cli_app_events_live",
        )
        self.assertTrue(payload["agent_run_evidence"]["release_gate_require_real_tool_adapter"])
        self.assertTrue(payload["agent_run_evidence"]["real_tool_adapter_present"])
        self.assertTrue(payload["agent_run_evidence"]["real_tool_execution_succeeded"])
        self.assertEqual(payload["tool_results"][0]["tool_name"], "system_state_sync")

    def test_cli_live_event_smoke_fails_closed_when_no_events_are_collected(self) -> None:
        def runner(argv: list[str], timeout_seconds: int) -> CommandExecutionResult:
            del timeout_seconds
            if "app-events" in argv:
                return CommandExecutionResult(
                    exit_code=0,
                    stdout=json.dumps(
                        {
                            "ok": True,
                            "subscription": "neuro/unit-01/event/app/neuro_demo_app/**",
                            "listener_mode": "callback",
                            "handler_audit": {"enabled": False, "executed": 0},
                            "events": [],
                        }
                    ),
                )
            raise AssertionError("workflow execution should not start when no live events are collected")

        adapter = NeuroCliToolAdapter(runner=runner)
        out = io.StringIO()
        with mock.patch("neurolink_core.cli.NeuroCliToolAdapter", return_value=adapter):
            with redirect_stdout(out):
                code = core_cli_main(
                    [
                        "live-event-smoke",
                        "--app-id",
                        "neuro_demo_app",
                        "--duration",
                        "1",
                        "--max-events",
                        "1",
                    ]
                )

        self.assertEqual(code, 2)
        payload = json.loads(out.getvalue())
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "live_event_ingest_empty")
        self.assertEqual(payload["failure_status"], "no_events_collected")
        self.assertEqual(payload["event_source"], "neuro_cli_app_events_live")
        self.assertEqual(payload["live_event_ingest"]["collected_event_count"], 0)

    def test_cli_live_event_smoke_can_ingest_unit_events_with_explicit_provenance(self) -> None:
        def runner(argv: list[str], timeout_seconds: int) -> CommandExecutionResult:
            del timeout_seconds
            if "events" in argv and "monitor" in argv:
                return CommandExecutionResult(
                    exit_code=0,
                    stdout=json.dumps(
                        {
                            "ok": True,
                            "subscription": "neuro/unit-01/event/**",
                            "listener_mode": "callback",
                            "handler_audit": {"enabled": False, "executed": 0},
                            "events": [
                                {
                                    "keyexpr": "neuro/unit-01/event/health",
                                    "payload": {
                                        "semantic_topic": "unit.health.degraded",
                                        "event_id": "evt-unit-health-001",
                                        "source_kind": "unit",
                                        "source_node": "unit-01",
                                        "event_type": "health",
                                        "timestamp_wall": "2026-05-07T00:00:00Z",
                                        "priority": 30,
                                        "health": "degraded",
                                    },
                                    "payload_encoding": "json",
                                }
                            ],
                        }
                    ),
                )
            if "tool-manifest" in argv:
                return CommandExecutionResult(
                    exit_code=0,
                    stdout=json.dumps(
                        {
                            "ok": True,
                            "status": "ok",
                            "schema_version": "1.2.0-tool-manifest-v1",
                            "tools": [
                                {
                                    "name": "system_state_sync",
                                    "description": "state sync",
                                    "argv_template": ["python", "wrapper.py", "system", "state-sync"],
                                    "resource": "state sync aggregate",
                                    "required_arguments": ["--node"],
                                    "side_effect_level": "read_only",
                                }
                            ],
                        }
                    ),
                )
            if "state-sync" in argv:
                return CommandExecutionResult(
                    exit_code=0,
                    stdout=json.dumps(
                        {
                            "ok": True,
                            "status": "ok",
                            "state": {
                                "device": {"status": "ok", "payload": {"network_state": "NETWORK_READY"}},
                                "apps": {"status": "ok", "payload": {"apps": []}},
                                "leases": {"status": "ok", "payload": {"leases": []}},
                            },
                            "recommended_next_actions": [
                                "state sync is clean; read-only delegated reasoning may continue"
                            ],
                        }
                    ),
                )
            raise AssertionError(f"unexpected argv: {argv}")

        adapter = NeuroCliToolAdapter(runner=runner)
        out = io.StringIO()
        with mock.patch("neurolink_core.cli.NeuroCliToolAdapter", return_value=adapter):
            with redirect_stdout(out):
                code = core_cli_main(
                    [
                        "live-event-smoke",
                        "--event-source",
                        "unit",
                        "--duration",
                        "1",
                        "--max-events",
                        "1",
                    ]
                )

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["command"], "live-event-smoke")
        self.assertEqual(payload["event_source"], "neuro_cli_events_live")
        self.assertEqual(payload["live_event_ingest"]["event_source_kind"], "unit")
        self.assertEqual(payload["live_event_ingest"]["monitor_command"], "events")
        self.assertEqual(payload["live_event_ingest"]["subscription"], "neuro/unit-01/event/**")
        self.assertEqual(payload["live_event_ingest"]["collected_event_count"], 1)
        self.assertEqual(
            payload["execution_evidence"]["execution_span"]["payload"]["event_source"],
            "neuro_cli_events_live",
        )
        self.assertEqual(payload["agent_run_evidence"]["event_source"], "neuro_cli_events_live")

    def test_cli_event_service_persists_bounded_lifecycle_and_checkpoint(self) -> None:
        def runner(argv: list[str], timeout_seconds: int) -> CommandExecutionResult:
            del timeout_seconds
            if "app-events" in argv:
                return CommandExecutionResult(
                    exit_code=0,
                    stdout=json.dumps(
                        {
                            "ok": True,
                            "subscription": "neuro/unit-01/event/app/neuro_demo_app/**",
                            "listener_mode": "callback",
                            "handler_audit": {"enabled": False, "executed": 0},
                            "events": [
                                {
                                    "keyexpr": "neuro/unit-01/event/app/neuro_demo_app/callback/value",
                                    "payload": {
                                        "semantic_topic": "unit.callback",
                                        "event_id": "evt-live-app-001",
                                        "source_kind": "unit_app",
                                        "source_node": "unit-01",
                                        "source_app": "neuro_demo_app",
                                        "event_type": "callback",
                                        "timestamp_wall": "2026-05-09T00:00:00Z",
                                        "priority": 20,
                                    },
                                    "payload_encoding": "json",
                                }
                            ],
                        }
                    ),
                )
            if "tool-manifest" in argv:
                return CommandExecutionResult(
                    exit_code=0,
                    stdout=json.dumps(
                        {
                            "ok": True,
                            "status": "ok",
                            "schema_version": TOOL_MANIFEST_SCHEMA_VERSION,
                            "tools": [
                                {
                                    "name": "system_state_sync",
                                    "description": "state sync",
                                    "argv_template": ["python", "wrapper.py", "system", "state-sync"],
                                    "resource": "state sync aggregate",
                                    "required_arguments": ["--node"],
                                    "side_effect_level": "read_only",
                                }
                            ],
                        }
                    ),
                )
            if "state-sync" in argv:
                return CommandExecutionResult(
                    exit_code=0,
                    stdout=json.dumps(
                        {
                            "ok": True,
                            "status": "ok",
                            "state": {
                                "device": {"status": "ok", "payload": {"network_state": "NETWORK_READY"}},
                                "apps": {"status": "ok", "payload": {"apps": []}},
                                "leases": {"status": "ok", "payload": {"leases": []}},
                            },
                            "recommended_next_actions": [
                                "state sync is clean; read-only delegated reasoning may continue"
                            ],
                        }
                    ),
                )
            raise AssertionError(f"unexpected argv: {argv}")

        adapter = NeuroCliToolAdapter(runner=runner)
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = os.path.join(temp_dir, "event-service.db")
            with mock.patch("neurolink_core.cli.NeuroCliToolAdapter", return_value=adapter):
                with redirect_stdout(out):
                    code = core_cli_main(
                        [
                            "event-service",
                            "--db",
                            db_path,
                            "--app-id",
                            "neuro_demo_app",
                            "--duration",
                            "1",
                            "--max-events",
                            "1",
                        ]
                    )

            self.assertEqual(code, 0)
            payload = json.loads(out.getvalue())
            self.assertEqual(payload["command"], "event-service")
            self.assertEqual(payload["event_source"], "neuro_cli_app_events_live")
            self.assertTrue(payload["event_service"]["bounded_runtime"])
            self.assertEqual(
                payload["event_service"]["checkpoint"]["last_event_id"],
                "liveevt-unit-01-neuro-demo-app-callback-evt-live-app-001",
            )
            service_execution_span_id = payload["event_service"]["execution_span_id"]

            data_store = CoreDataStore(db_path)
            try:
                lifecycle_facts = data_store.get_facts(
                    service_execution_span_id,
                    fact_type="event_service_lifecycle",
                )
                checkpoint_facts = data_store.get_facts(
                    service_execution_span_id,
                    fact_type="event_service_checkpoint",
                )
            finally:
                data_store.close()

        self.assertEqual(
            [fact["payload"]["lifecycle_state"] for fact in lifecycle_facts],
            ["start", "ready", "events_persisted", "clean_shutdown"],
        )
        self.assertEqual(len(checkpoint_facts), 1)
        self.assertEqual(
            checkpoint_facts[0]["payload"]["last_event_id"],
            "liveevt-unit-01-neuro-demo-app-callback-evt-live-app-001",
        )
        self.assertEqual(checkpoint_facts[0]["payload"]["persisted_event_count"], 1)

    def test_cli_event_service_persists_no_events_shutdown_evidence(self) -> None:
        def runner(argv: list[str], timeout_seconds: int) -> CommandExecutionResult:
            del timeout_seconds
            if "app-events" in argv:
                return CommandExecutionResult(
                    exit_code=0,
                    stdout=json.dumps(
                        {
                            "ok": True,
                            "subscription": "neuro/unit-01/event/app/neuro_demo_app/**",
                            "listener_mode": "callback",
                            "handler_audit": {"enabled": False, "executed": 0},
                            "events": [],
                        }
                    ),
                )
            raise AssertionError("workflow execution should not start when no service events are collected")

        adapter = NeuroCliToolAdapter(runner=runner)
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = os.path.join(temp_dir, "event-service-no-events.db")
            with mock.patch("neurolink_core.cli.NeuroCliToolAdapter", return_value=adapter):
                with redirect_stdout(out):
                    code = core_cli_main(
                        [
                            "event-service",
                            "--db",
                            db_path,
                            "--app-id",
                            "neuro_demo_app",
                            "--duration",
                            "1",
                            "--max-events",
                            "1",
                        ]
                    )

            self.assertEqual(code, 2)
            payload = json.loads(out.getvalue())
            self.assertEqual(payload["status"], "event_service_ingest_empty")
            self.assertEqual(payload["failure_status"], "no_events_collected")
            service_execution_span_id = payload["event_service"]["execution_span_id"]

            data_store = CoreDataStore(db_path)
            try:
                lifecycle_facts = data_store.get_facts(
                    service_execution_span_id,
                    fact_type="event_service_lifecycle",
                )
            finally:
                data_store.close()

        self.assertEqual(
            [fact["payload"]["lifecycle_state"] for fact in lifecycle_facts],
            ["start", "ready", "no_events", "clean_shutdown"],
        )

    def test_cli_event_service_persists_no_reply_monitor_failure(self) -> None:
        def runner(argv: list[str], timeout_seconds: int) -> CommandExecutionResult:
            del timeout_seconds
            if "app-events" in argv:
                return CommandExecutionResult(
                    exit_code=0,
                    stdout=json.dumps(
                        {
                            "ok": False,
                            "status": "no_reply",
                        }
                    ),
                )
            raise AssertionError("workflow execution should not start when monitor setup fails")

        adapter = NeuroCliToolAdapter(runner=runner)
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = os.path.join(temp_dir, "event-service-no-reply.db")
            with mock.patch("neurolink_core.cli.NeuroCliToolAdapter", return_value=adapter):
                with redirect_stdout(out):
                    code = core_cli_main(
                        [
                            "event-service",
                            "--db",
                            db_path,
                            "--app-id",
                            "neuro_demo_app",
                            "--duration",
                            "1",
                            "--max-events",
                            "1",
                        ]
                    )

            self.assertEqual(code, 2)
            payload = json.loads(out.getvalue())
            self.assertEqual(payload["status"], "event_service_monitor_failed")
            self.assertEqual(payload["failure_status"], "no_reply")
            self.assertEqual(payload["failure_class"], "event_service_monitor_unreachable")
            service_execution_span_id = payload["event_service"]["execution_span_id"]

            data_store = CoreDataStore(db_path)
            try:
                lifecycle_facts = data_store.get_facts(
                    service_execution_span_id,
                    fact_type="event_service_lifecycle",
                )
            finally:
                data_store.close()

        self.assertEqual(
            [fact["payload"]["lifecycle_state"] for fact in lifecycle_facts],
            ["start", "no_reply", "clean_shutdown"],
        )

    def test_cli_event_service_records_heartbeat_and_stale_endpoint_across_cycles(self) -> None:
        cycle_counter = {"count": 0}

        def runner(argv: list[str], timeout_seconds: int) -> CommandExecutionResult:
            del timeout_seconds
            if "events" in argv and "monitor" in argv:
                cycle_counter["count"] += 1
                if cycle_counter["count"] == 1:
                    return CommandExecutionResult(
                        exit_code=0,
                        stdout=json.dumps(
                            {
                                "ok": True,
                                "subscription": "neuro/unit-01/event/**",
                                "listener_mode": "callback",
                                "handler_audit": {"enabled": False, "executed": 0},
                                "events": [
                                    {
                                        "keyexpr": "neuro/unit-01/event/state",
                                        "payload": {
                                            "semantic_topic": "unit.network.endpoint_drift",
                                            "event_id": "evt-unit-drift-001",
                                            "source_kind": "unit",
                                            "source_node": "unit-01",
                                            "event_type": "state_event",
                                            "timestamp_wall": "2026-05-09T00:00:00Z",
                                            "priority": 40,
                                            "expected_endpoint": "tcp/192.168.2.95:7447",
                                            "observed_endpoint": "tcp/192.168.2.94:7447",
                                        },
                                        "payload_encoding": "json",
                                    }
                                ],
                            }
                        ),
                    )
                if cycle_counter["count"] == 2:
                    return CommandExecutionResult(
                        exit_code=0,
                        stdout=json.dumps(
                            {
                                "ok": True,
                                "subscription": "neuro/unit-01/event/**",
                                "listener_mode": "callback",
                                "handler_audit": {"enabled": False, "executed": 0},
                                "events": [
                                    {
                                        "keyexpr": "neuro/unit-01/event/health",
                                        "payload": {
                                            "semantic_topic": "unit.health.degraded",
                                            "event_id": "evt-unit-health-002",
                                            "source_kind": "unit",
                                            "source_node": "unit-01",
                                            "event_type": "health",
                                            "timestamp_wall": "2026-05-09T00:00:01Z",
                                            "priority": 30,
                                        },
                                        "payload_encoding": "json",
                                    }
                                ],
                            }
                        ),
                    )
            if "tool-manifest" in argv:
                return CommandExecutionResult(
                    exit_code=0,
                    stdout=json.dumps(
                        {
                            "ok": True,
                            "status": "ok",
                            "schema_version": TOOL_MANIFEST_SCHEMA_VERSION,
                            "tools": [
                                {
                                    "name": "system_state_sync",
                                    "description": "state sync",
                                    "argv_template": ["python", "wrapper.py", "system", "state-sync"],
                                    "resource": "state sync aggregate",
                                    "required_arguments": ["--node"],
                                    "side_effect_level": "read_only",
                                }
                            ],
                        }
                    ),
                )
            if "state-sync" in argv:
                return CommandExecutionResult(
                    exit_code=0,
                    stdout=json.dumps(
                        {
                            "ok": True,
                            "status": "ok",
                            "state": {
                                "device": {"status": "ok", "payload": {"network_state": "NETWORK_READY"}},
                                "apps": {"status": "ok", "payload": {"apps": []}},
                                "leases": {"status": "ok", "payload": {"leases": []}},
                            },
                            "recommended_next_actions": [
                                "state sync is clean; read-only delegated reasoning may continue"
                            ],
                        }
                    ),
                )
            raise AssertionError(f"unexpected argv: {argv}")

        adapter = NeuroCliToolAdapter(runner=runner)
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = os.path.join(temp_dir, "event-service-cycles.db")
            with mock.patch("neurolink_core.cli.NeuroCliToolAdapter", return_value=adapter):
                with redirect_stdout(out):
                    code = core_cli_main(
                        [
                            "event-service",
                            "--db",
                            db_path,
                            "--event-source",
                            "unit",
                            "--duration",
                            "1",
                            "--max-events",
                            "1",
                            "--cycles",
                            "2",
                        ]
                    )

            self.assertEqual(code, 0)
            payload = json.loads(out.getvalue())
            self.assertEqual(payload["events_persisted"], 2)
            self.assertEqual(payload["event_service"]["cycle_count"], 2)
            self.assertEqual(payload["event_service"]["duplicate_event_count"], 0)
            self.assertEqual(payload["event_service"]["normalized_event_count"], 2)
            service_execution_span_id = payload["event_service"]["execution_span_id"]

            data_store = CoreDataStore(db_path)
            try:
                lifecycle_facts = data_store.get_facts(
                    service_execution_span_id,
                    fact_type="event_service_lifecycle",
                )
            finally:
                data_store.close()

        self.assertEqual(
            [fact["payload"]["lifecycle_state"] for fact in lifecycle_facts],
            [
                "start",
                "ready",
                "stale_endpoint",
                "events_persisted",
                "heartbeat",
                "ready",
                "events_persisted",
                "clean_shutdown",
            ],
        )

    def test_cli_event_service_restart_uses_seeded_dedupe_without_retrigger(self) -> None:
        def runner(argv: list[str], timeout_seconds: int) -> CommandExecutionResult:
            del timeout_seconds
            if "app-events" in argv:
                return CommandExecutionResult(
                    exit_code=0,
                    stdout=json.dumps(
                        {
                            "ok": True,
                            "subscription": "neuro/unit-01/event/app/neuro_demo_app/**",
                            "listener_mode": "callback",
                            "handler_audit": {"enabled": False, "executed": 0},
                            "events": [
                                {
                                    "keyexpr": "neuro/unit-01/event/app/neuro_demo_app/callback/value",
                                    "payload": {
                                        "semantic_topic": "unit.callback",
                                        "event_id": "evt-live-app-restart-001",
                                        "source_kind": "unit_app",
                                        "source_node": "unit-01",
                                        "source_app": "neuro_demo_app",
                                        "event_type": "callback",
                                        "timestamp_wall": "2026-05-09T00:00:00Z",
                                        "priority": 20,
                                    },
                                    "payload_encoding": "json",
                                }
                            ],
                        }
                    ),
                )
            if "tool-manifest" in argv:
                return CommandExecutionResult(
                    exit_code=0,
                    stdout=json.dumps(
                        {
                            "ok": True,
                            "status": "ok",
                            "schema_version": TOOL_MANIFEST_SCHEMA_VERSION,
                            "tools": [
                                {
                                    "name": "system_state_sync",
                                    "description": "state sync",
                                    "argv_template": ["python", "wrapper.py", "system", "state-sync"],
                                    "resource": "state sync aggregate",
                                    "required_arguments": ["--node"],
                                    "side_effect_level": "read_only",
                                }
                            ],
                        }
                    ),
                )
            if "state-sync" in argv:
                return CommandExecutionResult(
                    exit_code=0,
                    stdout=json.dumps(
                        {
                            "ok": True,
                            "status": "ok",
                            "state": {
                                "device": {"status": "ok", "payload": {"network_state": "NETWORK_READY"}},
                                "apps": {"status": "ok", "payload": {"apps": []}},
                                "leases": {"status": "ok", "payload": {"leases": []}},
                            },
                            "recommended_next_actions": [
                                "state sync is clean; read-only delegated reasoning may continue"
                            ],
                        }
                    ),
                )
            raise AssertionError(f"unexpected argv: {argv}")

        adapter = NeuroCliToolAdapter(runner=runner)
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = os.path.join(temp_dir, "event-service-restart.db")

            out_first = io.StringIO()
            with mock.patch("neurolink_core.cli.NeuroCliToolAdapter", return_value=adapter):
                with redirect_stdout(out_first):
                    first_code = core_cli_main(
                        [
                            "event-service",
                            "--db",
                            db_path,
                            "--app-id",
                            "neuro_demo_app",
                            "--session-id",
                            "event-service-restart-session",
                            "--duration",
                            "1",
                            "--max-events",
                            "1",
                        ]
                    )

            self.assertEqual(first_code, 0)

            out_second = io.StringIO()
            with mock.patch("neurolink_core.cli.NeuroCliToolAdapter", return_value=adapter):
                with redirect_stdout(out_second):
                    second_code = core_cli_main(
                        [
                            "event-service",
                            "--db",
                            db_path,
                            "--app-id",
                            "neuro_demo_app",
                            "--session-id",
                            "event-service-restart-session",
                            "--duration",
                            "1",
                            "--max-events",
                            "1",
                        ]
                    )

            self.assertEqual(second_code, 0)
            second_payload = json.loads(out_second.getvalue())
            self.assertEqual(second_payload["events_persisted"], 0)
            self.assertEqual(second_payload["event_service"]["seeded_dedupe_key_count"], 1)
            service_execution_span_id = second_payload["event_service"]["execution_span_id"]

            data_store = CoreDataStore(db_path)
            try:
                lifecycle_facts = data_store.get_facts(
                    service_execution_span_id,
                    fact_type="event_service_lifecycle",
                )
                perception_event_count = data_store.count("perception_events")
            finally:
                data_store.close()

        self.assertEqual(perception_event_count, 1)
        self.assertEqual(
            [fact["payload"]["lifecycle_state"] for fact in lifecycle_facts],
            ["start", "restart", "ready", "heartbeat", "clean_shutdown"],
        )

    def test_cli_app_build_plan_reports_canonical_neuro_unit_app_paths(self) -> None:
        out = io.StringIO()

        with redirect_stdout(out):
            code = core_cli_main(["app-build-plan"])

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["command"], "app-build-plan")
        self.assertEqual(payload["build_plan"]["preset"], "unit-app")
        self.assertEqual(payload["build_plan"]["app_id"], "neuro_unit_app")
        self.assertEqual(
            payload["build_plan"]["app_source_dir"],
            "applocation/NeuroLink/subprojects/neuro_unit_app",
        )
        self.assertEqual(payload["build_plan"]["unit_build_dir"], "build/neurolink_unit")
        self.assertEqual(payload["build_plan"]["app_build_dir"], "build/neurolink_unit_app")
        self.assertEqual(
            payload["build_plan"]["source_artifact_file"],
            "build/neurolink_unit_app/neuro_unit_app.llext",
        )
        self.assertEqual(
            payload["build_plan"]["staged_artifact_file"],
            "build/neurolink_unit/llext/neuro_unit_app.llext",
        )
        self.assertIn(
            "bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-app --no-c-style-check",
            payload["build_plan"]["build_command"],
        )

    def test_cli_app_build_plan_supports_custom_app_id(self) -> None:
        out = io.StringIO()

        with redirect_stdout(out):
            code = core_cli_main(["app-build-plan", "--app-id", "neuro_demo_gpio"])

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["build_plan"]["app_id"], "neuro_demo_gpio")
        self.assertEqual(
            payload["build_plan"]["app_source_dir"],
            "applocation/NeuroLink/subprojects/neuro_demo_gpio",
        )
        self.assertEqual(
            payload["build_plan"]["app_build_dir"],
            "build/neurolink_unit_neuro_demo_gpio_app",
        )
        self.assertEqual(
            payload["build_plan"]["source_artifact_file"],
            "build/neurolink_unit_neuro_demo_gpio_app/neuro_demo_gpio.llext",
        )
        self.assertEqual(
            payload["build_plan"]["staged_artifact_file"],
            "build/neurolink_unit/llext/neuro_demo_gpio.llext",
        )
        self.assertIn("--app neuro_demo_gpio", payload["build_plan"]["build_command"])

    def test_cli_app_build_plan_rejects_invalid_build_dir(self) -> None:
        out = io.StringIO()

        with redirect_stdout(out):
            code = core_cli_main(["app-build-plan", "--build-dir", "build_bad"])

        self.assertEqual(code, 2)
        payload = json.loads(out.getvalue())
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["command"], "app-build-plan")
        self.assertEqual(payload["failure_class"], "app_build_plan_invalid")
        self.assertEqual(payload["failure_status"], "invalid_app_build_dir")

    def _write_fake_app_source(
        self,
        source_dir: Path,
        *,
        app_id: str,
        app_version: str,
        build_id: str,
    ) -> None:
        source_dir.mkdir(parents=True, exist_ok=True)
        main_c = source_dir / "src" / "main.c"
        main_c.parent.mkdir(parents=True, exist_ok=True)
        major, minor, patch = app_version.split(".")
        main_c.write_text(
            (
                'static const char app_id[] = "{app_id}";\n'
                'static const char app_version[] = "{app_version}";\n'
                'static const char app_build_id[] = "{build_id}";\n'
                'const struct app_runtime_manifest app_runtime_manifest = {{\n'
                '  .version = {{\n'
                '    .major = {major},\n'
                '    .minor = {minor},\n'
                '    .patch = {patch},\n'
                '  }},\n'
                '  .app_name = "{app_id}",\n'
                '}};\n'
            ).format(
                app_id=app_id,
                app_version=app_version,
                build_id=build_id,
                major=major,
                minor=minor,
                patch=patch,
            ),
            encoding="utf-8",
        )

    def _write_fake_llext(
        self,
        artifact_path: Path,
        *,
        app_id: str,
        app_version: str,
        build_id: str,
    ) -> None:
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        elf_ident = b"\x7fELF\x01\x01\x01" + (b"\x00" * 9)
        elf_header = (
            elf_ident
            + (1).to_bytes(2, "little")
            + (94).to_bytes(2, "little")
            + (1).to_bytes(4, "little")
        )
        payload = elf_header + b"\x00" * 32 + app_id.encode("utf-8") + b"\x00" + app_version.encode("utf-8") + b"\x00" + build_id.encode("utf-8") + b"\x00"
        artifact_path.write_bytes(payload)

    def test_cli_app_artifact_admission_reports_identity_and_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            source_dir = Path(tmpdir) / "source"
            artifact_path = Path(tmpdir) / "artifacts" / "neuro_unit_app.llext"
            self._write_fake_app_source(
                source_dir,
                app_id="neuro_unit_app",
                app_version="1.2.2",
                build_id="neuro_unit_app-1.2.2-cbor-v2",
            )
            self._write_fake_llext(
                artifact_path,
                app_id="neuro_unit_app",
                app_version="1.2.2",
                build_id="neuro_unit_app-1.2.2-cbor-v2",
            )
            out = io.StringIO()

            with redirect_stdout(out):
                code = core_cli_main(
                    [
                        "app-artifact-admission",
                        "--app-id",
                        "neuro_unit_app",
                        "--app-source-dir",
                        str(source_dir),
                        "--artifact-file",
                        str(artifact_path),
                    ]
                )

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["command"], "app-artifact-admission")
        self.assertTrue(payload["artifact_admission"]["admitted"])
        self.assertEqual(
            payload["artifact_admission"]["elf_identity"]["machine_name"],
            "xtensa",
        )
        self.assertEqual(
            payload["artifact_admission"]["source_identity"]["manifest_version"],
            "1.2.2",
        )
        self.assertTrue(payload["artifact_admission"]["artifact_contains_app_id_string"])
        self.assertTrue(payload["artifact_admission"]["artifact_contains_build_id_string"])
        self.assertTrue(payload["artifact_admission"]["artifact_contains_version_string"])
        self.assertEqual(len(payload["artifact_admission"]["artifact_sha256"]), 64)

    def test_cli_app_artifact_admission_rejects_invalid_elf_placeholder(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            source_dir = Path(tmpdir) / "source"
            artifact_path = Path(tmpdir) / "artifacts" / "neuro_unit_app.llext"
            self._write_fake_app_source(
                source_dir,
                app_id="neuro_unit_app",
                app_version="1.2.2",
                build_id="neuro_unit_app-1.2.2-cbor-v2",
            )
            artifact_path.parent.mkdir(parents=True, exist_ok=True)
            artifact_path.write_text("fake llext", encoding="utf-8")
            out = io.StringIO()

            with redirect_stdout(out):
                code = core_cli_main(
                    [
                        "app-artifact-admission",
                        "--app-id",
                        "neuro_unit_app",
                        "--app-source-dir",
                        str(source_dir),
                        "--artifact-file",
                        str(artifact_path),
                    ]
                )

        self.assertEqual(code, 2)
        payload = json.loads(out.getvalue())
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["command"], "app-artifact-admission")
        self.assertEqual(payload["failure_class"], "app_artifact_admission_failed")
        self.assertEqual(payload["failure_status"], "artifact_invalid_elf_header")

    def test_cli_app_artifact_admission_rejects_missing_build_id_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            source_dir = Path(tmpdir) / "source"
            artifact_path = Path(tmpdir) / "artifacts" / "neuro_demo_gpio.llext"
            self._write_fake_app_source(
                source_dir,
                app_id="neuro_demo_gpio",
                app_version="1.1.10",
                build_id="neuro_demo_gpio-1.1.10-cbor-v1",
            )
            self._write_fake_llext(
                artifact_path,
                app_id="neuro_demo_gpio",
                app_version="1.1.10",
                build_id="wrong-build-id",
            )
            out = io.StringIO()

            with redirect_stdout(out):
                code = core_cli_main(
                    [
                        "app-artifact-admission",
                        "--app-id",
                        "neuro_demo_gpio",
                        "--app-source-dir",
                        str(source_dir),
                        "--artifact-file",
                        str(artifact_path),
                    ]
                )

        self.assertEqual(code, 2)
        payload = json.loads(out.getvalue())
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["command"], "app-artifact-admission")
        self.assertEqual(payload["failure_class"], "app_artifact_admission_failed")
        self.assertEqual(payload["failure_status"], "artifact_build_id_missing")

    def test_cli_app_deploy_plan_reports_canonical_release_gate_sequence(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            source_dir = Path(tmpdir) / "source"
            artifact_path = Path(tmpdir) / "artifacts" / "neuro_unit_app.llext"
            self._write_fake_app_source(
                source_dir,
                app_id="neuro_unit_app",
                app_version="1.2.2",
                build_id="neuro_unit_app-1.2.2-cbor-v2",
            )
            self._write_fake_llext(
                artifact_path,
                app_id="neuro_unit_app",
                app_version="1.2.2",
                build_id="neuro_unit_app-1.2.2-cbor-v2",
            )
            out = io.StringIO()

            with redirect_stdout(out):
                code = core_cli_main(
                    [
                        "app-deploy-plan",
                        "--app-id",
                        "neuro_unit_app",
                        "--app-source-dir",
                        str(source_dir),
                        "--artifact-file",
                        str(artifact_path),
                        "--start-args",
                        "mode=demo,profile=release",
                    ]
                )

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["command"], "app-deploy-plan")
        self.assertTrue(payload["deploy_plan"]["activation_approval_required"])
        self.assertEqual(
            payload["deploy_plan"]["activation_resource"],
            "update/app/neuro_unit_app/activate",
        )
        self.assertEqual(
            payload["deploy_plan"]["suggested_activate_lease_id"],
            "l-neuro-unit-app-act",
        )
        step_names = [step["name"] for step in payload["deploy_plan"]["steps"]]
        self.assertEqual(
            step_names,
            [
                "preflight",
                "artifact_admission",
                "lease_acquire_activate",
                "deploy_prepare",
                "deploy_verify",
                "activation_approval_gate",
                "deploy_activate",
                "activation_health_guard",
                "query_apps",
                "lease_release_activate",
                "query_leases",
            ],
        )
        self.assertIn(
            "preflight_neurolink_linux.sh --node unit-01",
            payload["deploy_plan"]["steps"][0]["command"],
        )
        self.assertIn(
            "--resource update/app/neuro_unit_app/activate --lease-id l-neuro-unit-app-act",
            payload["deploy_plan"]["steps"][2]["command"],
        )
        self.assertIn(
            "deploy activate --app-id neuro_unit_app --lease-id l-neuro-unit-app-act --start-args mode=demo,profile=release",
            payload["deploy_plan"]["steps"][6]["command"],
        )
        self.assertIn(
            f"{sys.executable} -m neurolink_core.cli activation-health-guard --app-id neuro_unit_app --tool-adapter neuro-cli --output json",
            payload["deploy_plan"]["steps"][7]["command"],
        )

    def test_cli_app_deploy_plan_supports_custom_app_and_source_agent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            source_dir = Path(tmpdir) / "source"
            artifact_path = Path(tmpdir) / "artifacts" / "neuro_demo_gpio.llext"
            self._write_fake_app_source(
                source_dir,
                app_id="neuro_demo_gpio",
                app_version="1.1.10",
                build_id="neuro_demo_gpio-1.1.10-cbor-v1",
            )
            self._write_fake_llext(
                artifact_path,
                app_id="neuro_demo_gpio",
                app_version="1.1.10",
                build_id="neuro_demo_gpio-1.1.10-cbor-v1",
            )
            out = io.StringIO()

            with redirect_stdout(out):
                code = core_cli_main(
                    [
                        "app-deploy-plan",
                        "--app-id",
                        "neuro_demo_gpio",
                        "--app-source-dir",
                        str(source_dir),
                        "--artifact-file",
                        str(artifact_path),
                        "--node",
                        "unit-02",
                        "--source-agent",
                        "skills",
                    ]
                )

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["deploy_plan"]["node_id"], "unit-02")
        self.assertEqual(payload["deploy_plan"]["source_agent"], "skills")
        self.assertEqual(
            payload["deploy_plan"]["activation_resource"],
            "update/app/neuro_demo_gpio/activate",
        )
        self.assertEqual(
            payload["deploy_plan"]["suggested_activate_lease_id"],
            "l-neuro-demo-gpio-act",
        )
        self.assertIn(
            "--node unit-02 --source-agent skills lease acquire --resource update/app/neuro_demo_gpio/activate",
            payload["deploy_plan"]["steps"][2]["command"],
        )

    def test_cli_app_deploy_plan_rejects_invalid_source_agent(self) -> None:
        out = io.StringIO()

        with redirect_stdout(out):
            code = core_cli_main(["app-deploy-plan", "--source-agent", "bad agent"])

        self.assertEqual(code, 2)
        payload = json.loads(out.getvalue())
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["command"], "app-deploy-plan")
        self.assertEqual(payload["failure_class"], "app_deploy_plan_invalid")
        self.assertEqual(payload["failure_status"], "invalid_deploy_source_agent")

    def test_cli_app_deploy_prepare_verify_executes_prepare_verify_and_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            source_dir = Path(tmpdir) / "source"
            artifact_path = Path(tmpdir) / "artifacts" / "neuro_unit_app.llext"
            self._write_fake_app_source(
                source_dir,
                app_id="neuro_unit_app",
                app_version="1.2.2",
                build_id="neuro_unit_app-1.2.2-cbor-v2",
            )
            self._write_fake_llext(
                artifact_path,
                app_id="neuro_unit_app",
                app_version="1.2.2",
                build_id="neuro_unit_app-1.2.2-cbor-v2",
            )
            seen_argv: list[list[str]] = []

            def runner(argv: list[str], timeout_seconds: int) -> CommandExecutionResult:
                del timeout_seconds
                seen_argv.append(list(argv))
                if "preflight_neurolink_linux.sh" in " ".join(argv):
                    return CommandExecutionResult(
                        exit_code=0,
                        stdout=json.dumps({"status": "ready", "query": {"status": "ok"}}),
                    )
                if "lease" in argv and "acquire" in argv:
                    return CommandExecutionResult(
                        exit_code=0,
                        stdout=json.dumps(
                            {
                                "ok": True,
                                "status": "ok",
                                "replies": [
                                    {"payload": {"status": "ok", "lease_id": "l-neuro-unit-app-act"}}
                                ],
                            }
                        ),
                    )
                if "deploy" in argv and "prepare" in argv:
                    return CommandExecutionResult(
                        exit_code=0,
                        stdout=json.dumps(
                            {
                                "ok": True,
                                "status": "ok",
                                "replies": [
                                    {"payload": {"status": "ok", "app_id": "neuro_unit_app", "path": "/SD:/apps/neuro_unit_app.llext"}}
                                ],
                            }
                        ),
                    )
                if "deploy" in argv and "verify" in argv:
                    return CommandExecutionResult(
                        exit_code=0,
                        stdout=json.dumps(
                            {
                                "ok": True,
                                "status": "ok",
                                "replies": [
                                    {"payload": {"status": "ok", "app_id": "neuro_unit_app", "size": 21520}}
                                ],
                            }
                        ),
                    )
                if "lease" in argv and "release" in argv:
                    return CommandExecutionResult(
                        exit_code=0,
                        stdout=json.dumps(
                            {
                                "ok": True,
                                "status": "ok",
                                "replies": [{"payload": {"status": "ok"}}],
                            }
                        ),
                    )
                if "query" in argv and "leases" in argv:
                    return CommandExecutionResult(
                        exit_code=0,
                        stdout=json.dumps(
                            {
                                "ok": True,
                                "status": "ok",
                                "replies": [{"payload": {"status": "ok", "leases": []}}],
                            }
                        ),
                    )
                raise AssertionError(f"unexpected argv: {argv}")

            adapter = NeuroCliToolAdapter(runner=runner, source_agent="rational", node="unit-01")
            out = io.StringIO()
            with mock.patch("neurolink_core.cli.NeuroCliToolAdapter", return_value=adapter):
                with redirect_stdout(out):
                    code = core_cli_main(
                        [
                            "app-deploy-prepare-verify",
                            "--app-id",
                            "neuro_unit_app",
                            "--app-source-dir",
                            str(source_dir),
                            "--artifact-file",
                            str(artifact_path),
                        ]
                    )

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["command"], "app-deploy-prepare-verify")
        self.assertEqual(payload["deploy_execution"]["completed_through"], "deploy_verify")
        self.assertTrue(payload["deploy_execution"]["cleanup_attempted"])
        self.assertEqual(payload["deploy_execution"]["query_leases"]["result"]["replies"][0]["payload"]["leases"], [])
        observed_commands = [" ".join(argv) for argv in seen_argv]
        self.assertTrue(any("preflight_neurolink_linux.sh" in command for command in observed_commands))
        self.assertTrue(any("deploy prepare --app-id neuro_unit_app" in command for command in observed_commands))
        self.assertTrue(any("deploy verify --app-id neuro_unit_app" in command for command in observed_commands))
        self.assertTrue(any("lease release --lease-id l-neuro-unit-app-act" in command for command in observed_commands))

    def test_cli_app_deploy_prepare_verify_accepts_log_prefixed_preflight_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            source_dir = Path(tmpdir) / "source"
            artifact_path = Path(tmpdir) / "artifacts" / "neuro_unit_app.llext"
            self._write_fake_app_source(
                source_dir,
                app_id="neuro_unit_app",
                app_version="1.2.2",
                build_id="neuro_unit_app-1.2.2-cbor-v2",
            )
            self._write_fake_llext(
                artifact_path,
                app_id="neuro_unit_app",
                app_version="1.2.2",
                build_id="neuro_unit_app-1.2.2-cbor-v2",
            )

            def runner(argv: list[str], timeout_seconds: int) -> CommandExecutionResult:
                del timeout_seconds
                if "preflight_neurolink_linux.sh" in " ".join(argv):
                    return CommandExecutionResult(
                        exit_code=0,
                        stdout=(
                            "Looking in indexes: https://pypi.tuna.tsinghua.edu.cn/simple\n"
                            "Requirement already satisfied: eclipse-zenoh==1.9.0\n"
                            + json.dumps({"status": "ready", "query": {"status": "ok"}})
                        ),
                    )
                if "lease" in argv and "acquire" in argv:
                    return CommandExecutionResult(
                        exit_code=0,
                        stdout=json.dumps(
                            {
                                "ok": True,
                                "status": "ok",
                                "replies": [{"payload": {"status": "ok", "lease_id": "l-neuro-unit-app-act"}}],
                            }
                        ),
                    )
                if "deploy" in argv and "prepare" in argv:
                    return CommandExecutionResult(
                        exit_code=0,
                        stdout=json.dumps(
                            {
                                "ok": True,
                                "status": "ok",
                                "replies": [{"payload": {"status": "ok", "app_id": "neuro_unit_app"}}],
                            }
                        ),
                    )
                if "deploy" in argv and "verify" in argv:
                    return CommandExecutionResult(
                        exit_code=0,
                        stdout=json.dumps(
                            {
                                "ok": True,
                                "status": "ok",
                                "replies": [{"payload": {"status": "ok", "app_id": "neuro_unit_app", "size": 21520}}],
                            }
                        ),
                    )
                if "lease" in argv and "release" in argv:
                    return CommandExecutionResult(
                        exit_code=0,
                        stdout=json.dumps(
                            {
                                "ok": True,
                                "status": "ok",
                                "replies": [{"payload": {"status": "ok"}}],
                            }
                        ),
                    )
                if "query" in argv and "leases" in argv:
                    return CommandExecutionResult(
                        exit_code=0,
                        stdout=json.dumps(
                            {
                                "ok": True,
                                "status": "ok",
                                "replies": [{"payload": {"status": "ok", "leases": []}}],
                            }
                        ),
                    )
                raise AssertionError(f"unexpected argv: {argv}")

            adapter = NeuroCliToolAdapter(runner=runner, source_agent="rational", node="unit-01")
            out = io.StringIO()
            with mock.patch("neurolink_core.cli.NeuroCliToolAdapter", return_value=adapter):
                with redirect_stdout(out):
                    code = core_cli_main(
                        [
                            "app-deploy-prepare-verify",
                            "--app-id",
                            "neuro_unit_app",
                            "--app-source-dir",
                            str(source_dir),
                            "--artifact-file",
                            str(artifact_path),
                        ]
                    )

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["deploy_execution"]["preflight"]["result"]["status"], "ready")

    def test_cli_app_deploy_prepare_verify_releases_lease_after_prepare_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            source_dir = Path(tmpdir) / "source"
            artifact_path = Path(tmpdir) / "artifacts" / "neuro_demo_gpio.llext"
            self._write_fake_app_source(
                source_dir,
                app_id="neuro_demo_gpio",
                app_version="1.1.10",
                build_id="neuro_demo_gpio-1.1.10-cbor-v1",
            )
            self._write_fake_llext(
                artifact_path,
                app_id="neuro_demo_gpio",
                app_version="1.1.10",
                build_id="neuro_demo_gpio-1.1.10-cbor-v1",
            )
            seen_argv: list[list[str]] = []

            def runner(argv: list[str], timeout_seconds: int) -> CommandExecutionResult:
                del timeout_seconds
                seen_argv.append(list(argv))
                if "preflight_neurolink_linux.sh" in " ".join(argv):
                    return CommandExecutionResult(exit_code=0, stdout=json.dumps({"status": "ready"}))
                if "lease" in argv and "acquire" in argv:
                    return CommandExecutionResult(
                        exit_code=0,
                        stdout=json.dumps({"ok": True, "status": "ok", "replies": [{"payload": {"status": "ok"}}]}),
                    )
                if "deploy" in argv and "prepare" in argv:
                    return CommandExecutionResult(
                        exit_code=0,
                        stdout=json.dumps(
                            {
                                "ok": True,
                                "status": "ok",
                                "replies": [{"payload": {"status": "error", "message": "prepare failed"}}],
                            }
                        ),
                    )
                if "lease" in argv and "release" in argv:
                    return CommandExecutionResult(
                        exit_code=0,
                        stdout=json.dumps({"ok": True, "status": "ok", "replies": [{"payload": {"status": "ok"}}]}),
                    )
                if "query" in argv and "leases" in argv:
                    return CommandExecutionResult(
                        exit_code=0,
                        stdout=json.dumps({"ok": True, "status": "ok", "replies": [{"payload": {"status": "ok", "leases": []}}]}),
                    )
                raise AssertionError(f"unexpected argv: {argv}")

            adapter = NeuroCliToolAdapter(runner=runner, source_agent="rational", node="unit-01")
            out = io.StringIO()
            with mock.patch("neurolink_core.cli.NeuroCliToolAdapter", return_value=adapter):
                with redirect_stdout(out):
                    code = core_cli_main(
                        [
                            "app-deploy-prepare-verify",
                            "--app-id",
                            "neuro_demo_gpio",
                            "--app-source-dir",
                            str(source_dir),
                            "--artifact-file",
                            str(artifact_path),
                        ]
                    )

        self.assertEqual(code, 2)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["command"], "app-deploy-prepare-verify")
        self.assertEqual(payload["failed_step"], "deploy_prepare")
        self.assertEqual(payload["failure_class"], "app_deploy_prepare_verify_failed")
        self.assertEqual(payload["failure_status"], "error")
        observed_commands = [" ".join(argv) for argv in seen_argv]
        self.assertTrue(any("lease release --lease-id l-neuro-demo-gpio-act" in command for command in observed_commands))
        self.assertTrue(any(command.endswith("query leases") for command in observed_commands))

    def test_cli_app_deploy_activate_requires_explicit_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            source_dir = Path(tmpdir) / "source"
            artifact_path = Path(tmpdir) / "artifacts" / "neuro_unit_app.llext"
            self._write_fake_app_source(
                source_dir,
                app_id="neuro_unit_app",
                app_version="1.2.2",
                build_id="neuro_unit_app-1.2.2-cbor-v2",
            )
            self._write_fake_llext(
                artifact_path,
                app_id="neuro_unit_app",
                app_version="1.2.2",
                build_id="neuro_unit_app-1.2.2-cbor-v2",
            )
            out = io.StringIO()

            with redirect_stdout(out):
                code = core_cli_main(
                    [
                        "app-deploy-activate",
                        "--app-id",
                        "neuro_unit_app",
                        "--app-source-dir",
                        str(source_dir),
                        "--artifact-file",
                        str(artifact_path),
                    ]
                )

        self.assertEqual(code, 2)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["command"], "app-deploy-activate")
        self.assertEqual(payload["status"], "pending_approval")
        self.assertEqual(payload["failure_class"], "activation_approval_required")
        self.assertEqual(payload["activation_decision"]["resolved_lease_id"], "l-neuro-unit-app-act")
        self.assertEqual(payload["activation_decision"]["resolved_app_id"], "neuro_unit_app")

    def test_cli_app_deploy_activate_executes_activate_health_and_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            source_dir = Path(tmpdir) / "source"
            artifact_path = Path(tmpdir) / "artifacts" / "neuro_unit_app.llext"
            self._write_fake_app_source(
                source_dir,
                app_id="neuro_unit_app",
                app_version="1.2.2",
                build_id="neuro_unit_app-1.2.2-cbor-v2",
            )
            self._write_fake_llext(
                artifact_path,
                app_id="neuro_unit_app",
                app_version="1.2.2",
                build_id="neuro_unit_app-1.2.2-cbor-v2",
            )
            seen_argv: list[list[str]] = []
            seen_tools: list[tuple[str, dict[str, Any]]] = []

            class ActivateAdapter:
                def runner(self, argv: list[str], timeout_seconds: int) -> CommandExecutionResult:
                    del timeout_seconds
                    seen_argv.append(list(argv))
                    if "preflight_neurolink_linux.sh" in " ".join(argv):
                        return CommandExecutionResult(exit_code=0, stdout=json.dumps({"status": "ready"}))
                    if "lease" in argv and "acquire" in argv:
                        return CommandExecutionResult(
                            exit_code=0,
                            stdout=json.dumps({"ok": True, "status": "ok", "replies": [{"payload": {"status": "ok"}}]}),
                        )
                    if "deploy" in argv and "prepare" in argv:
                        return CommandExecutionResult(
                            exit_code=0,
                            stdout=json.dumps({"ok": True, "status": "ok", "replies": [{"payload": {"status": "ok"}}]}),
                        )
                    if "deploy" in argv and "verify" in argv:
                        return CommandExecutionResult(
                            exit_code=0,
                            stdout=json.dumps({"ok": True, "status": "ok", "replies": [{"payload": {"status": "ok", "size": 21520}}]}),
                        )
                    if "deploy" in argv and "activate" in argv:
                        return CommandExecutionResult(
                            exit_code=0,
                            stdout=json.dumps({"ok": True, "status": "ok", "replies": [{"payload": {"status": "ok", "app_id": "neuro_unit_app"}}]}),
                        )
                    if "query" in argv and "apps" in argv:
                        return CommandExecutionResult(
                            exit_code=0,
                            stdout=json.dumps(
                                {
                                    "ok": True,
                                    "status": "ok",
                                    "replies": [
                                        {
                                            "payload": {
                                                "status": "ok",
                                                "apps": [
                                                    {"app_id": "neuro_unit_app", "state": "RUNNING"}
                                                ],
                                            }
                                        }
                                    ],
                                }
                            ),
                        )
                    if "lease" in argv and "release" in argv:
                        return CommandExecutionResult(
                            exit_code=0,
                            stdout=json.dumps({"ok": True, "status": "ok", "replies": [{"payload": {"status": "lease_not_found"}}]}),
                        )
                    if "query" in argv and "leases" in argv:
                        return CommandExecutionResult(
                            exit_code=0,
                            stdout=json.dumps({"ok": True, "status": "ok", "replies": [{"payload": {"status": "ok", "leases": []}}]}),
                        )
                    raise AssertionError(f"unexpected argv: {argv}")

                def execute(self, tool_name: str, args: dict[str, Any]) -> ToolExecutionResult:
                    seen_tools.append((tool_name, dict(args)))
                    self.assert_tool_name(tool_name)
                    return ToolExecutionResult(
                        tool_result_id="tool-activate-health-001",
                        tool_name=tool_name,
                        status="ok",
                        payload={
                            "activation_health": {
                                "classification": "healthy",
                                "reason": "target_app_running_after_activate",
                                "app_id": "neuro_unit_app",
                            },
                            "state_sync": {"status": "ok"},
                        },
                    )

                @staticmethod
                def assert_tool_name(tool_name: str) -> None:
                    if tool_name != "system_activation_health_guard":
                        raise AssertionError(f"unexpected tool {tool_name}")

            out = io.StringIO()
            with mock.patch("neurolink_core.cli.NeuroCliToolAdapter", return_value=ActivateAdapter()):
                with redirect_stdout(out):
                    code = core_cli_main(
                        [
                            "app-deploy-activate",
                            "--app-id",
                            "neuro_unit_app",
                            "--app-source-dir",
                            str(source_dir),
                            "--artifact-file",
                            str(artifact_path),
                            "--approval-decision",
                            "approve",
                            "--approval-note",
                            "release gate accepted",
                            "--start-args",
                            "mode=demo",
                        ]
                    )

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["command"], "app-deploy-activate")
        self.assertEqual(payload["activation_decision"]["status"], "approved")
        self.assertEqual(payload["deploy_execution"]["completed_through"], "query_apps")
        self.assertTrue(payload["deploy_execution"]["cleanup_attempted"])
        self.assertEqual(len(seen_tools), 1)
        self.assertEqual(seen_tools[0][0], "system_activation_health_guard")
        observed_commands = [" ".join(argv) for argv in seen_argv]
        self.assertTrue(any("deploy activate --app-id neuro_unit_app --lease-id l-neuro-unit-app-act --start-args mode=demo" in command for command in observed_commands))
        self.assertTrue(any(command.endswith("query apps") for command in observed_commands))
        self.assertTrue(any(command.endswith("query leases") for command in observed_commands))

    def test_cli_app_deploy_activate_surfaces_rollback_candidate_after_health_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            source_dir = Path(tmpdir) / "source"
            artifact_path = Path(tmpdir) / "artifacts" / "neuro_demo_gpio.llext"
            self._write_fake_app_source(
                source_dir,
                app_id="neuro_demo_gpio",
                app_version="1.1.10",
                build_id="neuro_demo_gpio-1.1.10-cbor-v1",
            )
            self._write_fake_llext(
                artifact_path,
                app_id="neuro_demo_gpio",
                app_version="1.1.10",
                build_id="neuro_demo_gpio-1.1.10-cbor-v1",
            )
            seen_argv: list[list[str]] = []
            seen_tools: list[str] = []

            class RollbackRequiredAdapter:
                def runner(self, argv: list[str], timeout_seconds: int) -> CommandExecutionResult:
                    del timeout_seconds
                    seen_argv.append(list(argv))
                    if "preflight_neurolink_linux.sh" in " ".join(argv):
                        return CommandExecutionResult(exit_code=0, stdout=json.dumps({"status": "ready"}))
                    if "lease" in argv and "acquire" in argv:
                        return CommandExecutionResult(exit_code=0, stdout=json.dumps({"ok": True, "status": "ok", "replies": [{"payload": {"status": "ok"}}]}))
                    if "deploy" in argv and "prepare" in argv:
                        return CommandExecutionResult(exit_code=0, stdout=json.dumps({"ok": True, "status": "ok", "replies": [{"payload": {"status": "ok"}}]}))
                    if "deploy" in argv and "verify" in argv:
                        return CommandExecutionResult(exit_code=0, stdout=json.dumps({"ok": True, "status": "ok", "replies": [{"payload": {"status": "ok"}}]}))
                    if "deploy" in argv and "activate" in argv:
                        return CommandExecutionResult(exit_code=0, stdout=json.dumps({"ok": True, "status": "ok", "replies": [{"payload": {"status": "ok", "app_id": "neuro_demo_gpio"}}]}))
                    if "lease" in argv and "release" in argv:
                        return CommandExecutionResult(exit_code=0, stdout=json.dumps({"ok": True, "status": "ok", "replies": [{"payload": {"status": "ok"}}]}))
                    if "query" in argv and "leases" in argv:
                        return CommandExecutionResult(exit_code=0, stdout=json.dumps({"ok": True, "status": "ok", "replies": [{"payload": {"status": "ok", "leases": []}}]}))
                    raise AssertionError(f"unexpected argv: {argv}")

                def execute(self, tool_name: str, args: dict[str, Any]) -> ToolExecutionResult:
                    seen_tools.append(tool_name)
                    if tool_name == "system_activation_health_guard":
                        return ToolExecutionResult(
                            tool_result_id="tool-activate-health-rb-001",
                            tool_name=tool_name,
                            status="ok",
                            payload={
                                "activation_health": {
                                    "classification": "rollback_required",
                                    "reason": "target_app_missing_after_activate",
                                    "ready_for_rollback_consideration": True,
                                    "app_id": "neuro_demo_gpio",
                                    "observed_app_state": "missing",
                                },
                                "state_sync": {"status": "ok"},
                            },
                        )
                    if tool_name == "system_query_leases":
                        return ToolExecutionResult(
                            tool_result_id="tool-rollback-lease-observe-001",
                            tool_name=tool_name,
                            status="ok",
                            payload={
                                "result": {
                                    "ok": True,
                                    "status": "ok",
                                    "replies": [
                                        {
                                            "payload": {
                                                "status": "ok",
                                                "leases": [
                                                    {
                                                        "resource": "update/app/neuro_demo_gpio/rollback",
                                                        "lease_id": "lease-gpio-rollback-act-001",
                                                    }
                                                ],
                                            }
                                        }
                                    ],
                                }
                            },
                        )
                    raise AssertionError(f"unexpected tool {tool_name} with args {args}")

                def describe_tool(self, tool_name: str) -> ToolContract | None:
                    if tool_name == "system_rollback_app":
                        return ToolContract(
                            tool_name="system_rollback_app",
                            description="Rollback staged app after explicit approval.",
                            side_effect_level=SideEffectLevel.APPROVAL_REQUIRED,
                            required_resources=("update_rollback_lease",),
                            approval_required=True,
                            cleanup_hint="confirm rollback evidence, lease ownership, and target app identity before resume",
                        )
                    return None

            out = io.StringIO()
            with mock.patch("neurolink_core.cli.NeuroCliToolAdapter", return_value=RollbackRequiredAdapter()):
                with redirect_stdout(out):
                    code = core_cli_main(
                        [
                            "app-deploy-activate",
                            "--app-id",
                            "neuro_demo_gpio",
                            "--app-source-dir",
                            str(source_dir),
                            "--artifact-file",
                            str(artifact_path),
                            "--approval-decision",
                            "approve",
                        ]
                    )

        self.assertEqual(code, 2)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["command"], "app-deploy-activate")
        self.assertEqual(payload["failed_step"], "activation_health_guard")
        self.assertEqual(payload["failure_status"], "rollback_required")
        self.assertEqual(
            payload["recovery_candidate_summary"]["rollback_decision"],
            "operator_review_required",
        )
        self.assertEqual(
            payload["recovery_candidate_summary"]["matching_lease_ids"],
            ["lease-gpio-rollback-act-001"],
        )
        self.assertEqual(payload["rollback_approval"]["status"], "pending_approval")
        self.assertEqual(
            payload["rollback_approval"]["requested_args"]["lease_id"],
            "lease-gpio-rollback-act-001",
        )
        self.assertEqual(
            payload["deploy_execution"]["rollback_candidate_lease_observation"]["tool_name"],
            "system_query_leases",
        )
        self.assertEqual(
            seen_tools,
            ["system_activation_health_guard", "system_query_leases"],
        )
        observed_commands = [" ".join(argv) for argv in seen_argv]
        self.assertTrue(any("lease release --lease-id l-neuro-demo-gpio-act" in command for command in observed_commands))
        self.assertTrue(any(command.endswith("query leases") for command in observed_commands))

    def test_cli_app_deploy_activate_releases_lease_after_activate_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            source_dir = Path(tmpdir) / "source"
            artifact_path = Path(tmpdir) / "artifacts" / "neuro_demo_gpio.llext"
            self._write_fake_app_source(
                source_dir,
                app_id="neuro_demo_gpio",
                app_version="1.1.10",
                build_id="neuro_demo_gpio-1.1.10-cbor-v1",
            )
            self._write_fake_llext(
                artifact_path,
                app_id="neuro_demo_gpio",
                app_version="1.1.10",
                build_id="neuro_demo_gpio-1.1.10-cbor-v1",
            )
            seen_argv: list[list[str]] = []

            class FailingActivateAdapter:
                def runner(self, argv: list[str], timeout_seconds: int) -> CommandExecutionResult:
                    del timeout_seconds
                    seen_argv.append(list(argv))
                    if "preflight_neurolink_linux.sh" in " ".join(argv):
                        return CommandExecutionResult(exit_code=0, stdout=json.dumps({"status": "ready"}))
                    if "lease" in argv and "acquire" in argv:
                        return CommandExecutionResult(exit_code=0, stdout=json.dumps({"ok": True, "status": "ok", "replies": [{"payload": {"status": "ok"}}]}))
                    if "deploy" in argv and "prepare" in argv:
                        return CommandExecutionResult(exit_code=0, stdout=json.dumps({"ok": True, "status": "ok", "replies": [{"payload": {"status": "ok"}}]}))
                    if "deploy" in argv and "verify" in argv:
                        return CommandExecutionResult(exit_code=0, stdout=json.dumps({"ok": True, "status": "ok", "replies": [{"payload": {"status": "ok"}}]}))
                    if "deploy" in argv and "activate" in argv:
                        return CommandExecutionResult(
                            exit_code=0,
                            stdout=json.dumps({"ok": True, "status": "ok", "replies": [{"payload": {"status": "error", "message": "activate failed"}}]}),
                        )
                    if "lease" in argv and "release" in argv:
                        return CommandExecutionResult(exit_code=0, stdout=json.dumps({"ok": True, "status": "ok", "replies": [{"payload": {"status": "ok"}}]}))
                    if "query" in argv and "leases" in argv:
                        return CommandExecutionResult(exit_code=0, stdout=json.dumps({"ok": True, "status": "ok", "replies": [{"payload": {"status": "ok", "leases": []}}]}))
                    raise AssertionError(f"unexpected argv: {argv}")

                def execute(self, tool_name: str, args: dict[str, Any]) -> ToolExecutionResult:
                    del tool_name, args
                    raise AssertionError("health guard should not run after activate failure")

            out = io.StringIO()
            with mock.patch("neurolink_core.cli.NeuroCliToolAdapter", return_value=FailingActivateAdapter()):
                with redirect_stdout(out):
                    code = core_cli_main(
                        [
                            "app-deploy-activate",
                            "--app-id",
                            "neuro_demo_gpio",
                            "--app-source-dir",
                            str(source_dir),
                            "--artifact-file",
                            str(artifact_path),
                            "--approval-decision",
                            "approve",
                        ]
                    )

        self.assertEqual(code, 2)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["command"], "app-deploy-activate")
        self.assertEqual(payload["failed_step"], "deploy_activate")
        self.assertEqual(payload["failure_class"], "app_deploy_activate_failed")
        self.assertEqual(payload["failure_status"], "error")
        observed_commands = [" ".join(argv) for argv in seen_argv]
        self.assertTrue(any("lease release --lease-id l-neuro-demo-gpio-act" in command for command in observed_commands))
        self.assertTrue(any(command.endswith("query leases") for command in observed_commands))

    def test_cli_app_deploy_rollback_requires_explicit_approval(self) -> None:
        out = io.StringIO()

        with redirect_stdout(out):
            code = core_cli_main(
                [
                    "app-deploy-rollback",
                    "--app-id",
                    "neuro_demo_gpio",
                ]
            )

        self.assertEqual(code, 2)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["command"], "app-deploy-rollback")
        self.assertEqual(payload["status"], "pending_approval")
        self.assertEqual(payload["failure_class"], "rollback_approval_required")
        self.assertEqual(payload["rollback_decision"]["resolved_app_id"], "neuro_demo_gpio")

    def test_cli_app_deploy_rollback_reports_denied_approval_state(self) -> None:
        out = io.StringIO()

        with redirect_stdout(out):
            code = core_cli_main(
                [
                    "app-deploy-rollback",
                    "--app-id",
                    "neuro_demo_gpio",
                    "--approval-decision",
                    "deny",
                ]
            )

        self.assertEqual(code, 2)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["command"], "app-deploy-rollback")
        self.assertEqual(payload["status"], "denied")
        self.assertEqual(payload["failure_class"], "rollback_approval_denied")
        self.assertEqual(payload["failure_status"], "denied")
        self.assertEqual(payload["rollback_decision"]["decision"], "denied")

    def test_cli_app_deploy_rollback_reports_expired_approval_state(self) -> None:
        out = io.StringIO()

        with redirect_stdout(out):
            code = core_cli_main(
                [
                    "app-deploy-rollback",
                    "--app-id",
                    "neuro_demo_gpio",
                    "--approval-decision",
                    "expire",
                ]
            )

        self.assertEqual(code, 2)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["command"], "app-deploy-rollback")
        self.assertEqual(payload["status"], "expired")
        self.assertEqual(payload["failure_class"], "rollback_approval_expired")
        self.assertEqual(payload["failure_status"], "expired")
        self.assertEqual(payload["rollback_decision"]["decision"], "expired")

    def test_cli_app_deploy_rollback_executes_resume_and_observes_state(self) -> None:
        seen_tools: list[tuple[str, dict[str, Any]]] = []

        class RollbackAdapter:
            def execute(self, tool_name: str, args: dict[str, Any]) -> ToolExecutionResult:
                seen_tools.append((tool_name, dict(args)))
                if tool_name == "system_rollback_app":
                    return ToolExecutionResult(
                        tool_result_id="tool-rollback-001",
                        tool_name=tool_name,
                        status="ok",
                        payload={
                            "resolved_args": {
                                "app_id": "neuro_demo_gpio",
                                "app": "neuro_demo_gpio",
                                "lease_id": "lease-rb-001",
                                "reason": "guarded_rollback_after_activation_health_failure",
                            },
                            "result": {
                                "ok": True,
                                "status": "ok",
                                "replies": [
                                    {"payload": {"status": "ok", "app_id": "neuro_demo_gpio", "action": "rollback"}}
                                ],
                            },
                        },
                    )
                if tool_name == "system_query_apps":
                    return ToolExecutionResult(
                        tool_result_id="tool-query-apps-001",
                        tool_name=tool_name,
                        status="ok",
                        payload={
                            "result": {
                                "ok": True,
                                "status": "ok",
                                "replies": [
                                    {"payload": {"status": "ok", "apps": []}}
                                ],
                            },
                        },
                    )
                if tool_name == "system_query_leases":
                    return ToolExecutionResult(
                        tool_result_id="tool-query-leases-001",
                        tool_name=tool_name,
                        status="ok",
                        payload={
                            "result": {
                                "ok": True,
                                "status": "ok",
                                "replies": [
                                    {"payload": {"status": "ok", "leases": []}}
                                ],
                            },
                        },
                    )
                raise AssertionError(f"unexpected tool {tool_name} with args {args}")

            def describe_tool(self, tool_name: str) -> ToolContract | None:
                del tool_name
                return None

        out = io.StringIO()
        with mock.patch("neurolink_core.cli.NeuroCliToolAdapter", return_value=RollbackAdapter()):
            with redirect_stdout(out):
                code = core_cli_main(
                    [
                        "app-deploy-rollback",
                        "--app-id",
                        "neuro_demo_gpio",
                        "--approval-decision",
                        "approve",
                    ]
                )

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["command"], "app-deploy-rollback")
        self.assertEqual(payload["rollback_decision"]["status"], "approved")
        self.assertEqual(payload["rollback_execution"]["completed_through"], "query_leases")
        observed_tool_names = [tool_name for tool_name, _args in seen_tools]
        self.assertEqual(
            observed_tool_names,
            ["system_rollback_app", "system_query_apps", "system_query_leases"],
        )
        self.assertEqual(
            payload["rollback_execution"]["rollback"]["result"]["resolved_args"]["lease_id"],
            "lease-rb-001",
        )

    def test_cli_app_deploy_rollback_reports_unresolved_rollback_args(self) -> None:
        class RollbackArgsUnresolvedAdapter:
            def execute(self, tool_name: str, args: dict[str, Any]) -> ToolExecutionResult:
                if tool_name == "system_rollback_app":
                    return ToolExecutionResult(
                        tool_result_id="tool-rollback-fail-001",
                        tool_name=tool_name,
                        status="error",
                        payload={
                            "failure_status": "rollback_args_unresolved",
                            "failure_class": "dynamic_argument_resolution_failed",
                            "requested_args": dict(args),
                        },
                    )
                raise AssertionError(f"unexpected tool {tool_name} with args {args}")

            def describe_tool(self, tool_name: str) -> ToolContract | None:
                del tool_name
                return None

        out = io.StringIO()
        with mock.patch("neurolink_core.cli.NeuroCliToolAdapter", return_value=RollbackArgsUnresolvedAdapter()):
            with redirect_stdout(out):
                code = core_cli_main(
                    [
                        "app-deploy-rollback",
                        "--app-id",
                        "neuro_demo_gpio",
                        "--approval-decision",
                        "approve",
                    ]
                )

        self.assertEqual(code, 2)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["command"], "app-deploy-rollback")
        self.assertEqual(payload["failed_step"], "rollback")
        self.assertEqual(payload["failure_class"], "app_deploy_rollback_failed")
        self.assertEqual(payload["failure_status"], "rollback_args_unresolved")
        self.assertEqual(
            payload["rollback_failure_summary"]["failure_category"],
            "argument_resolution",
        )

    def test_cli_app_deploy_rollback_reports_missing_rollback_lease(self) -> None:
        def runner(argv: list[str], timeout_seconds: int) -> CommandExecutionResult:
            del timeout_seconds
            if "tool-manifest" in argv:
                return CommandExecutionResult(
                    exit_code=0,
                    stdout=json.dumps(
                        {
                            "ok": True,
                            "status": "ok",
                            "schema_version": TOOL_MANIFEST_SCHEMA_VERSION,
                            "tools": [
                                {
                                    "name": "system_query_leases",
                                    "description": "query leases",
                                    "argv_template": ["python", "wrapper.py", "query", "leases"],
                                    "resource": "lease inventory",
                                    "required_arguments": [],
                                    "side_effect_level": "read_only",
                                },
                                {
                                    "name": "system_query_apps",
                                    "description": "query apps",
                                    "argv_template": ["python", "wrapper.py", "query", "apps"],
                                    "resource": "app inventory",
                                    "required_arguments": [],
                                    "side_effect_level": "read_only",
                                },
                                {
                                    "name": "system_rollback_app",
                                    "description": "rollback app",
                                    "argv_template": ["python", "wrapper.py", "deploy", "rollback"],
                                    "resource": "update rollback lease",
                                    "required_arguments": ["--app-id", "--lease-id"],
                                    "side_effect_level": "approval_required",
                                },
                            ],
                        }
                    ),
                )
            if "query" in argv and "leases" in argv:
                return CommandExecutionResult(
                    exit_code=0,
                    stdout=json.dumps(
                        {
                            "ok": True,
                            "status": "ok",
                            "replies": [{"ok": True, "payload": {"status": "ok", "leases": []}}],
                        }
                    ),
                )
            raise AssertionError(f"rollback command should not run when rollback lease is missing: {argv}")

        adapter = NeuroCliToolAdapter(runner=runner)
        out = io.StringIO()
        with mock.patch("neurolink_core.cli.NeuroCliToolAdapter", return_value=adapter):
            with redirect_stdout(out):
                code = core_cli_main(
                    [
                        "app-deploy-rollback",
                        "--app-id",
                        "neuro_demo_gpio",
                        "--approval-decision",
                        "approve",
                    ]
                )

        self.assertEqual(code, 2)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["command"], "app-deploy-rollback")
        self.assertEqual(payload["failure_status"], "lease_not_found")
        self.assertEqual(payload["failed_step"], "rollback")
        self.assertEqual(
            payload["rollback_failure_summary"]["failure_category"],
            "lease_resolution",
        )
        self.assertEqual(
            payload["rollback_failure_summary"]["recommended_next_actions"],
            ["query rollback leases and confirm update/app/<app_id>/rollback is held before retry"],
        )

    def test_cli_app_deploy_rollback_surfaces_lease_holder_mismatch_summary(self) -> None:
        class RollbackLeaseHolderMismatchAdapter:
            def execute(self, tool_name: str, args: dict[str, Any]) -> ToolExecutionResult:
                if tool_name == "system_rollback_app":
                    return ToolExecutionResult(
                        tool_result_id="tool-rollback-holder-mismatch-001",
                        tool_name=tool_name,
                        status="error",
                        payload={
                            "failure_status": "lease_holder_mismatch",
                            "failure_class": "rollback_failed",
                            "resolved_args": {
                                "app_id": "neuro_demo_gpio",
                                "app": "neuro_demo_gpio",
                                "lease_id": str(args.get("lease_id") or "lease-rb-003"),
                                "reason": str(args.get("reason") or ""),
                            },
                        },
                    )
                raise AssertionError(f"unexpected tool {tool_name} with args {args}")

            def describe_tool(self, tool_name: str) -> ToolContract | None:
                del tool_name
                return None

        out = io.StringIO()
        with mock.patch("neurolink_core.cli.NeuroCliToolAdapter", return_value=RollbackLeaseHolderMismatchAdapter()):
            with redirect_stdout(out):
                code = core_cli_main(
                    [
                        "app-deploy-rollback",
                        "--app-id",
                        "neuro_demo_gpio",
                        "--approval-decision",
                        "approve",
                    ]
                )

        self.assertEqual(code, 2)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["failure_status"], "lease_holder_mismatch")
        self.assertEqual(payload["failed_step"], "rollback")
        self.assertEqual(
            payload["rollback_failure_summary"]["failure_category"],
            "lease_ownership",
        )
        self.assertEqual(
            payload["rollback_failure_summary"]["resolved_lease_id"],
            "lease-rb-003",
        )

    def test_cli_app_deploy_rollback_surfaces_no_reply_summary(self) -> None:
        class RollbackNoReplyAdapter:
            def execute(self, tool_name: str, args: dict[str, Any]) -> ToolExecutionResult:
                if tool_name == "system_rollback_app":
                    return ToolExecutionResult(
                        tool_result_id="tool-rollback-no-reply-001",
                        tool_name=tool_name,
                        status="error",
                        payload={
                            "failure_status": "no_reply",
                            "failure_class": "rollback_cli_failed",
                            "resolved_args": {
                                "app_id": "neuro_demo_gpio",
                                "app": "neuro_demo_gpio",
                                "lease_id": str(args.get("lease_id") or "lease-rb-004"),
                                "reason": str(args.get("reason") or ""),
                            },
                            "stderr": "neuro_cli wrapper failure: no_reply",
                        },
                    )
                raise AssertionError(f"unexpected tool {tool_name} with args {args}")

            def describe_tool(self, tool_name: str) -> ToolContract | None:
                del tool_name
                return None

        out = io.StringIO()
        with mock.patch("neurolink_core.cli.NeuroCliToolAdapter", return_value=RollbackNoReplyAdapter()):
            with redirect_stdout(out):
                code = core_cli_main(
                    [
                        "app-deploy-rollback",
                        "--app-id",
                        "neuro_demo_gpio",
                        "--approval-decision",
                        "approve",
                    ]
                )

        self.assertEqual(code, 2)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["failure_status"], "no_reply")
        self.assertEqual(payload["failed_step"], "rollback")
        self.assertEqual(
            payload["rollback_failure_summary"]["failure_category"],
            "transport",
        )
        self.assertEqual(
            payload["rollback_failure_summary"]["tool_failure_class"],
            "rollback_cli_failed",
        )

    def test_cli_app_deploy_rollback_fails_when_app_still_running_after_rollback(self) -> None:
        class RollbackAppStillRunningAdapter:
            def execute(self, tool_name: str, args: dict[str, Any]) -> ToolExecutionResult:
                if tool_name == "system_rollback_app":
                    return ToolExecutionResult(
                        tool_result_id="tool-rollback-running-001",
                        tool_name=tool_name,
                        status="ok",
                        payload={
                            "result": {
                                "ok": True,
                                "status": "ok",
                                "replies": [{"payload": {"status": "ok"}}],
                            },
                        },
                    )
                if tool_name == "system_query_apps":
                    return ToolExecutionResult(
                        tool_result_id="tool-query-apps-running-001",
                        tool_name=tool_name,
                        status="ok",
                        payload={
                            "result": {
                                "ok": True,
                                "status": "ok",
                                "replies": [
                                    {
                                        "payload": {
                                            "status": "ok",
                                            "apps": [
                                                {
                                                    "app_id": "neuro_demo_gpio",
                                                    "state": "RUNNING_ACTIVE",
                                                }
                                            ],
                                        }
                                    }
                                ],
                            },
                        },
                    )
                if tool_name == "system_query_leases":
                    return ToolExecutionResult(
                        tool_result_id="tool-query-leases-running-001",
                        tool_name=tool_name,
                        status="ok",
                        payload={
                            "result": {
                                "ok": True,
                                "status": "ok",
                                "replies": [{"payload": {"status": "ok", "leases": []}}],
                            },
                        },
                    )
                raise AssertionError(f"unexpected tool {tool_name} with args {args}")

            def describe_tool(self, tool_name: str) -> ToolContract | None:
                del tool_name
                return None

        out = io.StringIO()
        with mock.patch("neurolink_core.cli.NeuroCliToolAdapter", return_value=RollbackAppStillRunningAdapter()):
            with redirect_stdout(out):
                code = core_cli_main(
                    [
                        "app-deploy-rollback",
                        "--app-id",
                        "neuro_demo_gpio",
                        "--approval-decision",
                        "approve",
                    ]
                )

        self.assertEqual(code, 2)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["command"], "app-deploy-rollback")
        self.assertEqual(payload["failed_step"], "query_apps")
        self.assertEqual(payload["failure_status"], "app_still_running_after_rollback")
        self.assertEqual(
            payload["rollback_execution"]["query_apps"]["observed_app_state"],
            "RUNNING_ACTIVE",
        )

    def test_cli_app_deploy_rollback_fails_when_rollback_lease_still_held(self) -> None:
        class RollbackLeaseStillHeldAdapter:
            def execute(self, tool_name: str, args: dict[str, Any]) -> ToolExecutionResult:
                if tool_name == "system_rollback_app":
                    return ToolExecutionResult(
                        tool_result_id="tool-rollback-lease-001",
                        tool_name=tool_name,
                        status="ok",
                        payload={
                            "result": {
                                "ok": True,
                                "status": "ok",
                                "replies": [{"payload": {"status": "ok"}}],
                            },
                        },
                    )
                if tool_name == "system_query_apps":
                    return ToolExecutionResult(
                        tool_result_id="tool-query-apps-lease-001",
                        tool_name=tool_name,
                        status="ok",
                        payload={
                            "result": {
                                "ok": True,
                                "status": "ok",
                                "replies": [{"payload": {"status": "ok", "apps": []}}],
                            },
                        },
                    )
                if tool_name == "system_query_leases":
                    return ToolExecutionResult(
                        tool_result_id="tool-query-leases-lease-001",
                        tool_name=tool_name,
                        status="ok",
                        payload={
                            "result": {
                                "ok": True,
                                "status": "ok",
                                "replies": [
                                    {
                                        "payload": {
                                            "status": "ok",
                                            "leases": [
                                                {
                                                    "lease_id": "lease-rb-002",
                                                    "resource": "update/app/neuro_demo_gpio/rollback",
                                                }
                                            ],
                                        }
                                    }
                                ],
                            },
                        },
                    )
                raise AssertionError(f"unexpected tool {tool_name} with args {args}")

            def describe_tool(self, tool_name: str) -> ToolContract | None:
                del tool_name
                return None

        out = io.StringIO()
        with mock.patch("neurolink_core.cli.NeuroCliToolAdapter", return_value=RollbackLeaseStillHeldAdapter()):
            with redirect_stdout(out):
                code = core_cli_main(
                    [
                        "app-deploy-rollback",
                        "--app-id",
                        "neuro_demo_gpio",
                        "--approval-decision",
                        "approve",
                    ]
                )

        self.assertEqual(code, 2)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["command"], "app-deploy-rollback")
        self.assertEqual(payload["failed_step"], "query_leases")
        self.assertEqual(payload["failure_status"], "rollback_lease_still_held_after_rollback")
        self.assertEqual(
            payload["rollback_execution"]["query_leases"]["matching_lease_ids"],
            ["lease-rb-002"],
        )

    def test_cli_app_deploy_activate_persists_release_gate_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "core.db")
            source_dir = Path(tmpdir) / "source"
            artifact_path = Path(tmpdir) / "artifacts" / "neuro_unit_app.llext"
            self._write_fake_app_source(
                source_dir,
                app_id="neuro_unit_app",
                app_version="1.2.2",
                build_id="neuro_unit_app-1.2.2-cbor-v2",
            )
            self._write_fake_llext(
                artifact_path,
                app_id="neuro_unit_app",
                app_version="1.2.2",
                build_id="neuro_unit_app-1.2.2-cbor-v2",
            )

            class PersistentActivateAdapter:
                def runner(self, argv: list[str], timeout_seconds: int) -> CommandExecutionResult:
                    del timeout_seconds
                    if "preflight_neurolink_linux.sh" in " ".join(argv):
                        return CommandExecutionResult(exit_code=0, stdout=json.dumps({"status": "ready"}))
                    if "lease" in argv and "acquire" in argv:
                        return CommandExecutionResult(exit_code=0, stdout=json.dumps({"ok": True, "status": "ok", "replies": [{"payload": {"status": "ok"}}]}))
                    if "deploy" in argv and "prepare" in argv:
                        return CommandExecutionResult(exit_code=0, stdout=json.dumps({"ok": True, "status": "ok", "replies": [{"payload": {"status": "ok"}}]}))
                    if "deploy" in argv and "verify" in argv:
                        return CommandExecutionResult(exit_code=0, stdout=json.dumps({"ok": True, "status": "ok", "replies": [{"payload": {"status": "ok"}}]}))
                    if "deploy" in argv and "activate" in argv:
                        return CommandExecutionResult(exit_code=0, stdout=json.dumps({"ok": True, "status": "ok", "replies": [{"payload": {"status": "ok", "app_id": "neuro_unit_app"}}]}))
                    if "query" in argv and "apps" in argv:
                        return CommandExecutionResult(exit_code=0, stdout=json.dumps({"ok": True, "status": "ok", "replies": [{"payload": {"status": "ok", "apps": [{"app_id": "neuro_unit_app", "state": "RUNNING"}]}}]}))
                    if "lease" in argv and "release" in argv:
                        return CommandExecutionResult(exit_code=0, stdout=json.dumps({"ok": True, "status": "ok", "replies": [{"payload": {"status": "ok"}}]}))
                    if "query" in argv and "leases" in argv:
                        return CommandExecutionResult(exit_code=0, stdout=json.dumps({"ok": True, "status": "ok", "replies": [{"payload": {"status": "ok", "leases": []}}]}))
                    raise AssertionError(f"unexpected argv: {argv}")

                def execute(self, tool_name: str, args: dict[str, Any]) -> ToolExecutionResult:
                    del args
                    if tool_name != "system_activation_health_guard":
                        raise AssertionError(f"unexpected tool {tool_name}")
                    return ToolExecutionResult(
                        tool_result_id="tool-activate-health-persist-001",
                        tool_name=tool_name,
                        status="ok",
                        payload={
                            "activation_health": {
                                "classification": "healthy",
                                "reason": "target_app_running_after_activate",
                                "app_id": "neuro_unit_app",
                                "observed_app_state": "RUNNING",
                            },
                        },
                    )

            out = io.StringIO()
            with mock.patch("neurolink_core.cli.NeuroCliToolAdapter", return_value=PersistentActivateAdapter()):
                with redirect_stdout(out):
                    code = core_cli_main(
                        [
                            "app-deploy-activate",
                            "--app-id",
                            "neuro_unit_app",
                            "--app-source-dir",
                            str(source_dir),
                            "--artifact-file",
                            str(artifact_path),
                            "--approval-decision",
                            "approve",
                            "--db",
                            db_path,
                        ]
                    )

            self.assertEqual(code, 0)
            payload = json.loads(out.getvalue())
            evidence = payload["release_gate_evidence"]
            data_store = CoreDataStore(db_path)
            try:
                execution_span = data_store.get_execution_span(evidence["execution_span_id"])
                audit_record = data_store.get_audit_record(evidence["audit_id"])
                activation_decisions = data_store.get_facts(
                    evidence["execution_span_id"],
                    fact_type="activation_decision",
                )
                activation_health = data_store.get_facts(
                    evidence["execution_span_id"],
                    fact_type="activation_health_observation",
                )
            finally:
                data_store.close()

        self.assertIsNotNone(execution_span)
        self.assertIsNotNone(audit_record)
        self.assertEqual(execution_span["payload"]["command"], "app-deploy-activate")
        self.assertEqual(audit_record["payload"]["command"], "app-deploy-activate")
        self.assertEqual(len(activation_decisions), 1)
        self.assertEqual(activation_decisions[0]["payload"]["status"], "approved")
        self.assertEqual(len(activation_health), 1)
        self.assertEqual(activation_health[0]["payload"]["classification"], "healthy")

    def test_cli_app_deploy_rollback_persists_release_gate_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "core.db")

            class PersistentRollbackAdapter:
                def execute(self, tool_name: str, args: dict[str, Any]) -> ToolExecutionResult:
                    if tool_name == "system_rollback_app":
                        return ToolExecutionResult(
                            tool_result_id="tool-rollback-persist-001",
                            tool_name=tool_name,
                            status="ok",
                            payload={
                                "resolved_args": {
                                    "app_id": "neuro_demo_gpio",
                                    "app": "neuro_demo_gpio",
                                    "lease_id": str(args.get("lease_id") or "lease-rb-001"),
                                    "reason": str(args.get("reason") or ""),
                                },
                                "result": {
                                    "ok": True,
                                    "status": "ok",
                                    "replies": [{"payload": {"status": "ok", "app_id": "neuro_demo_gpio"}}],
                                },
                            },
                        )
                    if tool_name == "system_query_apps":
                        return ToolExecutionResult(
                            tool_result_id="tool-query-apps-persist-001",
                            tool_name=tool_name,
                            status="ok",
                            payload={
                                "result": {
                                    "ok": True,
                                    "status": "ok",
                                    "replies": [{"payload": {"status": "ok", "apps": []}}],
                                },
                            },
                        )
                    if tool_name == "system_query_leases":
                        return ToolExecutionResult(
                            tool_result_id="tool-query-leases-persist-001",
                            tool_name=tool_name,
                            status="ok",
                            payload={
                                "result": {
                                    "ok": True,
                                    "status": "ok",
                                    "replies": [{"payload": {"status": "ok", "leases": []}}],
                                },
                            },
                        )
                    raise AssertionError(f"unexpected tool {tool_name} with args {args}")

                def describe_tool(self, tool_name: str) -> ToolContract | None:
                    del tool_name
                    return None

            out = io.StringIO()
            with mock.patch("neurolink_core.cli.NeuroCliToolAdapter", return_value=PersistentRollbackAdapter()):
                with redirect_stdout(out):
                    code = core_cli_main(
                        [
                            "app-deploy-rollback",
                            "--app-id",
                            "neuro_demo_gpio",
                            "--approval-decision",
                            "approve",
                            "--db",
                            db_path,
                        ]
                    )

            self.assertEqual(code, 0)
            payload = json.loads(out.getvalue())
            evidence = payload["release_gate_evidence"]
            data_store = CoreDataStore(db_path)
            try:
                audit_record = data_store.get_audit_record(evidence["audit_id"])
                rollback_decisions = data_store.get_facts(
                    evidence["execution_span_id"],
                    fact_type="rollback_decision",
                )
                rollback_results = data_store.get_facts(
                    evidence["execution_span_id"],
                    fact_type="rollback_result",
                )
            finally:
                data_store.close()

        self.assertIsNotNone(audit_record)
        self.assertEqual(audit_record["payload"]["command"], "app-deploy-rollback")
        self.assertEqual(len(rollback_decisions), 1)
        self.assertEqual(rollback_decisions[0]["payload"]["status"], "approved")
        self.assertEqual(len(rollback_results), 1)
        self.assertEqual(
            rollback_results[0]["payload"]["resolved_args"]["app_id"],
            "neuro_demo_gpio",
        )

    def test_cli_app_deploy_rollback_persists_failure_summary_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "core.db")

            class PersistentRollbackFailureAdapter:
                def execute(self, tool_name: str, args: dict[str, Any]) -> ToolExecutionResult:
                    if tool_name == "system_rollback_app":
                        return ToolExecutionResult(
                            tool_result_id="tool-rollback-persist-failure-001",
                            tool_name=tool_name,
                            status="error",
                            payload={
                                "failure_status": "no_reply",
                                "failure_class": "rollback_cli_failed",
                                "resolved_args": {
                                    "app_id": "neuro_demo_gpio",
                                    "app": "neuro_demo_gpio",
                                    "lease_id": str(args.get("lease_id") or "lease-rb-005"),
                                    "reason": str(args.get("reason") or ""),
                                },
                            },
                        )
                    raise AssertionError(f"unexpected tool {tool_name} with args {args}")

                def describe_tool(self, tool_name: str) -> ToolContract | None:
                    del tool_name
                    return None

            out = io.StringIO()
            with mock.patch("neurolink_core.cli.NeuroCliToolAdapter", return_value=PersistentRollbackFailureAdapter()):
                with redirect_stdout(out):
                    code = core_cli_main(
                        [
                            "app-deploy-rollback",
                            "--app-id",
                            "neuro_demo_gpio",
                            "--approval-decision",
                            "approve",
                            "--db",
                            db_path,
                        ]
                    )

            self.assertEqual(code, 2)
            payload = json.loads(out.getvalue())
            evidence = payload["release_gate_evidence"]
            data_store = CoreDataStore(db_path)
            try:
                failure_summaries = data_store.get_facts(
                    evidence["execution_span_id"],
                    fact_type="rollback_failure_summary",
                )
            finally:
                data_store.close()

        self.assertEqual(len(failure_summaries), 1)
        self.assertEqual(failure_summaries[0]["payload"]["failure_status"], "no_reply")
        self.assertEqual(failure_summaries[0]["payload"]["failure_category"], "transport")

    def test_cli_live_event_smoke_maps_raw_state_event_to_operational_wake_topic(self) -> None:
        def runner(argv: list[str], timeout_seconds: int) -> CommandExecutionResult:
            del timeout_seconds
            if "events" in argv and "monitor" in argv:
                return CommandExecutionResult(
                    exit_code=0,
                    stdout=json.dumps(
                        {
                            "ok": True,
                            "subscription": "neuro/unit-01/event/**",
                            "listener_mode": "callback",
                            "handler_audit": {"enabled": False, "executed": 0},
                            "events": [
                                {
                                    "keyexpr": "neuro/unit-01/event/state",
                                    "payload": {
                                        "message_kind": "state_event",
                                        "health": "degraded",
                                        "timestamp_wall": "2026-05-07T00:00:00Z",
                                        "priority": 30,
                                    },
                                    "payload_encoding": "cbor-v2",
                                }
                            ],
                        }
                    ),
                )
            if "tool-manifest" in argv:
                return CommandExecutionResult(
                    exit_code=0,
                    stdout=json.dumps(
                        {
                            "ok": True,
                            "status": "ok",
                            "schema_version": "1.2.0-tool-manifest-v1",
                            "tools": [
                                {
                                    "name": "system_state_sync",
                                    "description": "state sync",
                                    "argv_template": ["python", "wrapper.py", "system", "state-sync"],
                                    "resource": "state sync aggregate",
                                    "required_arguments": ["--node"],
                                    "side_effect_level": "read_only",
                                }
                            ],
                        }
                    ),
                )
            if "state-sync" in argv:
                return CommandExecutionResult(
                    exit_code=0,
                    stdout=json.dumps(
                        {
                            "ok": True,
                            "status": "ok",
                            "state": {
                                "device": {"status": "ok", "payload": {"network_state": "NETWORK_READY"}},
                                "apps": {"status": "ok", "payload": {"apps": []}},
                                "leases": {"status": "ok", "payload": {"leases": []}},
                            },
                            "recommended_next_actions": [
                                "state sync is clean; read-only delegated reasoning may continue"
                            ],
                        }
                    ),
                )
            raise AssertionError(f"unexpected argv: {argv}")

        adapter = NeuroCliToolAdapter(runner=runner)
        out = io.StringIO()
        with mock.patch("neurolink_core.cli.NeuroCliToolAdapter", return_value=adapter):
            with redirect_stdout(out):
                code = core_cli_main(
                    [
                        "live-event-smoke",
                        "--event-source",
                        "unit",
                        "--duration",
                        "1",
                        "--max-events",
                        "1",
                    ]
                )

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["event_source"], "neuro_cli_events_live")
        self.assertEqual(payload["final_response"]["topics"], ["unit.health.degraded"])
        self.assertEqual(payload["final_response"]["salience"], 85)
        self.assertEqual(payload["db_counts"]["facts"], 6)

    def test_data_store_query_and_topic_index_follow_priority_and_topic_filters(self) -> None:
        data_store = CoreDataStore()
        workflow = NoModelCoreWorkflow(data_store=data_store)

        workflow.run(sample_events())

        filtered = data_store.query_events(min_priority=50, topic="unit.callback")
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["event_id"], "evt-demo-callback-001")
        self.assertEqual(data_store.get_recent_topics(limit=2), ["time.tick", "unit.callback"])

        frame = data_store.build_frame(filtered)
        self.assertEqual(frame["event_ids"], ("evt-demo-callback-001",))
        self.assertEqual(frame["highest_priority"], 80)
        self.assertEqual(frame["topics"], ("unit.callback",))
        data_store.close()

    def test_workflow_can_rebuild_frame_from_database_slice(self) -> None:
        data_store = CoreDataStore()
        workflow = NoModelCoreWorkflow(data_store=data_store)

        result = workflow.run(
            sample_events(),
            use_db_events=True,
            min_priority=50,
            topic="unit.callback",
        )

        self.assertEqual(result.status, "ok")
        self.assertTrue(result.delegated)
        self.assertIn("database_query", result.steps)
        self.assertIn("frame_build_from_db", result.steps)
        self.assertEqual(len(result.tool_results), 1)
        self.assertEqual(result.tool_results[0]["tool_name"], "system_state_sync")
        self.assertEqual(
            result.tool_results[0]["payload"]["state_sync"]["status"], "ok"
        )
        data_store.close()

    def test_audit_record_preserves_state_sync_failure_summary(self) -> None:
        def runner(argv: list[str], timeout_seconds: int) -> CommandExecutionResult:
            if "tool-manifest" in argv:
                return CommandExecutionResult(
                    exit_code=0,
                    stdout=json.dumps(
                        {
                            "ok": True,
                            "status": "ok",
                            "schema_version": "1.2.0-tool-manifest-v1",
                            "tools": [
                                {
                                    "name": "system_state_sync",
                                    "description": "state sync",
                                    "argv_template": [
                                        "python",
                                        "neuro_cli/scripts/invoke_neuro_cli.py",
                                        "system",
                                        "state-sync",
                                    ],
                                    "resource": "state sync aggregate",
                                    "required_arguments": ["--node"],
                                    "side_effect_level": "read_only",
                                }
                            ],
                        }
                    ),
                )
            return CommandExecutionResult(
                exit_code=2,
                stdout=json.dumps(
                    {
                        "ok": False,
                        "status": "no_reply",
                        "recommended_next_actions": [
                            "rerun query device and verify router or Unit reachability before delegated control"
                        ],
                    }
                ),
                stderr="neuro_cli wrapper failure: no_reply",
            )

        data_store = CoreDataStore()
        workflow = NoModelCoreWorkflow(
            data_store=data_store,
            tool_adapter=NeuroCliToolAdapter(runner=runner, source_agent="rational"),
        )

        result = workflow.run(sample_events())
        audit_record = data_store.get_audit_record(result.audit_id)

        self.assertIsNotNone(audit_record)
        assert audit_record is not None
        self.assertEqual(result.tool_results[0]["status"], "error")
        self.assertEqual(
            audit_record["payload"]["adapter_runtime"]["adapter_kind"], "neuro-cli"
        )
        self.assertEqual(
            audit_record["payload"]["state_sync_summary"]["failure_status"], "no_reply"
        )
        self.assertEqual(
            audit_record["payload"]["state_sync_summary"]["failure_class"],
            "top_level_status_failure",
        )
        self.assertEqual(
            audit_record["payload"]["state_sync_summary"]["recommended_next_actions"],
            [
                "rerun query device and verify router or Unit reachability before delegated control"
            ],
        )
        data_store.close()


if __name__ == "__main__":
    unittest.main()