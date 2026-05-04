import unittest

from neurolink_core.common import PerceptionFrame
from neurolink_core.maf import (
    MAF_RUNTIME_SCHEMA_VERSION,
    MAF_PROVIDER_SMOKE_SCHEMA_VERSION,
    MafAffectiveAgentAdapter,
    MafRationalAgentAdapter,
    build_maf_runtime_profile,
    maf_provider_smoke_status,
)
from neurolink_core.cli import main as core_cli_main
from neurolink_core.workflow import run_no_model_dry_run

import io
import json
from contextlib import redirect_stdout


class TestMafRuntimeBoundary(unittest.TestCase):
    def test_runtime_profile_defaults_to_deterministic_fake_provider(self) -> None:
        profile = build_maf_runtime_profile()
        payload = profile.to_dict()

        self.assertEqual(payload["schema_version"], MAF_RUNTIME_SCHEMA_VERSION)
        self.assertEqual(payload["framework"], "microsoft_agent_framework")
        self.assertEqual(payload["workflow_api"], "functional_workflow_compatible")
        self.assertEqual(payload["provider_mode"], "deterministic_fake")
        self.assertFalse(payload["real_provider_enabled"])
        self.assertFalse(payload["requires_model_credentials"])
        self.assertEqual(payload["agent_roles"], ["affective", "rational"])

    def test_deterministic_maf_adapters_delegate_to_fake_agents(self) -> None:
        frame = PerceptionFrame(
            frame_id="frame-test",
            event_ids=("evt-1",),
            highest_priority=80,
            topics=("unit.callback",),
        )
        affective = MafAffectiveAgentAdapter()
        rational = MafRationalAgentAdapter()

        decision = affective.decide(frame, [])
        plan = rational.plan(decision, frame)

        self.assertTrue(decision.delegated)
        self.assertIsNotNone(plan)
        assert plan is not None
        self.assertEqual(plan.tool_name, "system_state_sync")
        self.assertEqual(plan.args["event_ids"], ["evt-1"])
        self.assertEqual(affective.runtime_metadata()["agent_role"], "affective")
        self.assertEqual(rational.runtime_metadata()["agent_role"], "rational")

    def test_no_model_dry_run_reports_maf_runtime_metadata(self) -> None:
        payload = run_no_model_dry_run()

        self.assertEqual(
            payload["maf_runtime"]["schema_version"],
            MAF_RUNTIME_SCHEMA_VERSION,
        )

    def test_provider_smoke_reports_skip_or_ready_without_model_call(self) -> None:
        payload = maf_provider_smoke_status()

        self.assertEqual(payload["schema_version"], MAF_PROVIDER_SMOKE_SCHEMA_VERSION)
        self.assertTrue(payload["ok"])
        self.assertIn(payload["status"], ("ready", "skipped"))
        self.assertFalse(payload["executes_model_call"])
        if payload["status"] == "skipped":
            self.assertIn(
                payload["reason"],
                (
                    "agent_framework_package_not_installed",
                    "model_credentials_not_configured",
                ),
            )

    def test_cli_maf_provider_smoke_outputs_json(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            code = core_cli_main(["maf-provider-smoke"])

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["schema_version"], MAF_PROVIDER_SMOKE_SCHEMA_VERSION)
        self.assertIn(payload["status"], ("ready", "skipped"))
        self.assertEqual(payload["maf_runtime"]["provider_mode"], "deterministic_fake")
        self.assertEqual(
            {item["agent_role"] for item in payload["maf_runtime"]["agent_adapters"]},
            {"affective", "rational"},
        )


if __name__ == "__main__":
    unittest.main()
