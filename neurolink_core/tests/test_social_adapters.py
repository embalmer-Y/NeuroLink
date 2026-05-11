import asyncio
import io
import json
import os
from pathlib import Path
import threading
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from typing import Any
from unittest import mock
from urllib import request

import websockets

from neurolink_core.cli import main as core_cli_main
from neurolink_core.social_adapters import onebot_direct_message_sample
from neurolink_core.social_adapters import onebot_group_message_no_mention_sample
from neurolink_core.social_adapters import onebot_group_message_sample
from neurolink_core.social_adapters import qq_official_direct_message_sample
from neurolink_core.social_adapters import qq_official_group_message_no_mention_sample
from neurolink_core.social_adapters import qq_official_group_message_sample
from neurolink_core.social_adapters import qq_openclaw_direct_message_sample
from neurolink_core.social_adapters import qq_openclaw_group_message_no_mention_sample
from neurolink_core.social_adapters import qq_openclaw_group_message_sample
from neurolink_core.social_adapters import wechat_ilink_direct_message_sample
from neurolink_core.social_adapters import wechat_ilink_group_message_no_mention_sample
from neurolink_core.social_adapters import wechat_ilink_group_message_sample
from neurolink_core.social_adapters import wecom_direct_message_sample
from neurolink_core.social_adapters import wecom_group_message_no_mention_sample
from neurolink_core.social_adapters import wecom_group_message_sample
from neurolink_core.social_adapters import registry as social_registry_module
from neurolink_core.social_adapters.onebot_qq import OneBotQQSocialAdapter
from neurolink_core.social_adapters.qq_openclaw import QQOpenClawSocialAdapter
from neurolink_core.social_adapters.qq_official import QQOfficialSocialAdapter
from neurolink_core.social_adapters.qq_official_webhook import qq_official_validation_response
from neurolink_core.social_adapters.registry import SOCIAL_ADAPTER_TEST_SCHEMA_VERSION
from neurolink_core.social_adapters.registry import social_adapter_config_update
from neurolink_core.social_adapters.registry import social_adapter_list
from neurolink_core.social_adapters.registry import social_adapter_registry
from neurolink_core.social_adapters.registry import social_adapter_test
from neurolink_core.social_adapters.wechat_ilink import WeChatILinkSocialAdapter
from neurolink_core.social_adapters.wecom import WeComSocialAdapter


class TestSocialAdapterRegistry(unittest.TestCase):
    def test_registry_reports_qq_and_onebot_profiles_without_secret_values(self) -> None:
        registry = social_adapter_registry(env={})

        qq_profile = registry.get_profile("qq_official")
        onebot_profile = registry.get_profile("onebot_qq")
        wecom_profile = registry.get_profile("wecom")
        wechat_profile = registry.get_profile("wechat_ilink")
        qq_openclaw_profile = registry.get_profile("qq_openclaw")

        self.assertIsNotNone(qq_profile)
        self.assertIsNotNone(onebot_profile)
        self.assertIsNotNone(wecom_profile)
        self.assertIsNotNone(wechat_profile)
        self.assertIsNotNone(qq_openclaw_profile)
        self.assertIn("credential_reference", qq_profile.missing_requirements())
        self.assertIn("compliance_acknowledgement", onebot_profile.missing_requirements())
        self.assertIn("endpoint_reference", wecom_profile.missing_requirements())
        self.assertIn("compliance_acknowledgement", wechat_profile.missing_requirements())
        self.assertIn(
            "plugin_package_coordinate",
            qq_openclaw_profile.missing_requirements(),
        )
        self.assertNotIn("credential_values", qq_profile.to_dict())
        self.assertEqual(qq_profile.to_dict()["credential_values_masked"], [])

    def test_qq_openclaw_requires_host_endpoint_and_compliance(self) -> None:
        registry = social_adapter_registry(env={"QQ_OPENCLAW_TOKEN": "secret"})

        qq_openclaw_profile = registry.get_profile("qq_openclaw")
        self.assertIsNotNone(qq_openclaw_profile)
        self.assertFalse(qq_openclaw_profile.ready_for_live_io)
        self.assertIn(
            "host_endpoint_reference",
            qq_openclaw_profile.missing_requirements(),
        )
        self.assertIn(
            "plugin_package_coordinate",
            qq_openclaw_profile.missing_requirements(),
        )
        self.assertIn(
            "compliance_acknowledgement",
            qq_openclaw_profile.missing_requirements(),
        )
        self.assertEqual(qq_openclaw_profile.runtime_host, "openclaw")
        self.assertEqual(qq_openclaw_profile.transport_kind, "openclaw_gateway")

    def test_config_update_can_mark_qq_openclaw_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "social_adapter_profiles.json"
            social_adapter_config_update(
                adapter_name="qq_openclaw",
                config_path=str(config_file),
                host_url="ws://127.0.0.1:8811/openclaw",
                credential_env_vars=["QQ_OPENCLAW_TOKEN"],
                plugin_package="operator-supplied-qq-openclaw-package",
                installer_package="operator-supplied-qq-openclaw-installer",
                plugin_installed=True,
                account_session_ready=True,
                enabled=True,
                compliance_acknowledged=True,
                live_network_allowed=True,
            )
            payload = social_adapter_list(
                env={"QQ_OPENCLAW_TOKEN": "token"},
                config_path=str(config_file),
            )

        qq_openclaw_profile = next(
            profile for profile in payload["profiles"] if profile["name"] == "qq_openclaw"
        )
        self.assertTrue(qq_openclaw_profile["ready_for_live_io"])
        self.assertEqual(qq_openclaw_profile["runtime_host"], "openclaw")
        self.assertEqual(
            qq_openclaw_profile["plugin_package"],
            "operator-supplied-qq-openclaw-package",
        )

    def test_config_update_enables_wecom_readiness_from_env_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "social_adapter_profiles.json"
            social_adapter_config_update(
                adapter_name="wecom",
                config_path=str(config_file),
                credential_env_vars=["WECOM_BOT_TOKEN"],
                endpoint_url="wss://qyapi.weixin.qq.com/cgi-bin/webhook/connect",
                enabled=True,
                active=True,
            )
            payload = social_adapter_list(
                env={"WECOM_BOT_TOKEN": "token"},
                config_path=str(config_file),
            )

        wecom_profile = next(
            profile for profile in payload["profiles"] if profile["name"] == "wecom"
        )
        self.assertEqual(payload["active_adapter"], "wecom")
        self.assertTrue(wecom_profile["ready_for_live_io"])
        self.assertEqual(wecom_profile["credential_values_masked"], ["***"])
        self.assertEqual(wecom_profile["transport_kind"], "websocket")
        self.assertEqual(wecom_profile["mention_policy"], "mention_or_direct")

    def test_wechat_ilink_requires_compliance_acknowledgement(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "social_adapter_profiles.json"
            social_adapter_config_update(
                adapter_name="wechat_ilink",
                config_path=str(config_file),
                host_url="ws://127.0.0.1:8811/openclaw",
                endpoint_url="https://wechat.example.invalid/ilink",
                credential_env_vars=["WECHAT_ILINK_TOKEN"],
                plugin_package="@tencent/openclaw-weixin",
                installer_package="@tencent-weixin/openclaw-weixin-cli",
                plugin_installed=True,
                account_session_ready=True,
                enabled=True,
                compliance_acknowledged=False,
            )
            registry = social_adapter_registry(
                env={"WECHAT_ILINK_TOKEN": "secret"},
                config_path=str(config_file),
            )

        wechat_profile = registry.get_profile("wechat_ilink")
        self.assertIsNotNone(wechat_profile)
        self.assertFalse(wechat_profile.ready_for_live_io)
        self.assertIn("compliance_acknowledgement", wechat_profile.missing_requirements())
        self.assertEqual(wechat_profile.transport_kind, "openclaw_gateway")
        self.assertEqual(wechat_profile.runtime_host, "openclaw")

    def test_wechat_ilink_openclaw_profile_requires_host_and_plugin_evidence(self) -> None:
        registry = social_adapter_registry(env={"WECHAT_ILINK_TOKEN": "secret"})

        wechat_profile = registry.get_profile("wechat_ilink")
        self.assertIsNotNone(wechat_profile)
        self.assertIn("host_endpoint_reference", wechat_profile.missing_requirements())
        self.assertIn("plugin_installed_evidence", wechat_profile.missing_requirements())
        self.assertIn("account_session_ready", wechat_profile.missing_requirements())
        self.assertEqual(wechat_profile.plugin_package, "@tencent/openclaw-weixin")

    def test_config_update_can_mark_wechat_ilink_openclaw_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "social_adapter_profiles.json"
            social_adapter_config_update(
                adapter_name="wechat_ilink",
                config_path=str(config_file),
                host_url="ws://127.0.0.1:8811/openclaw",
                credential_env_vars=["WECHAT_ILINK_TOKEN"],
                plugin_package="@tencent/openclaw-weixin",
                installer_package="@tencent-weixin/openclaw-weixin-cli",
                plugin_installed=True,
                account_session_ready=True,
                enabled=True,
                compliance_acknowledged=True,
                live_network_allowed=True,
            )
            payload = social_adapter_list(
                env={"WECHAT_ILINK_TOKEN": "token"},
                config_path=str(config_file),
            )

        wechat_profile = next(
            profile for profile in payload["profiles"] if profile["name"] == "wechat_ilink"
        )
        self.assertTrue(wechat_profile["ready_for_live_io"])
        self.assertEqual(wechat_profile["runtime_host"], "openclaw")
        self.assertEqual(wechat_profile["host_url"], "ws://127.0.0.1:8811/openclaw")
        self.assertEqual(wechat_profile["transport_kind"], "openclaw_gateway")

    def test_config_update_enables_qq_official_readiness_from_env_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "social_adapter_profiles.json"
            social_adapter_config_update(
                adapter_name="qq_official",
                config_path=str(config_file),
                credential_env_vars=["QQ_BOT_TOKEN", "QQ_BOT_SECRET"],
                endpoint_url="https://api.sgroup.qq.com",
                enabled=True,
                active=True,
            )
            payload = social_adapter_list(
                env={"QQ_BOT_TOKEN": "token", "QQ_BOT_SECRET": "secret"},
                config_path=str(config_file),
            )

        qq_profile = next(
            profile for profile in payload["profiles"] if profile["name"] == "qq_official"
        )
        self.assertEqual(payload["active_adapter"], "qq_official")
        self.assertTrue(qq_profile["ready_for_live_io"])
        self.assertEqual(qq_profile["credential_values_masked"], ["***", "***"])
        self.assertEqual(qq_profile["transport_kind"], "https")
        self.assertEqual(qq_profile["mention_policy"], "mention_or_direct")

    def test_onebot_requires_compliance_acknowledgement(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "social_adapter_profiles.json"
            social_adapter_config_update(
                adapter_name="onebot_qq",
                config_path=str(config_file),
                endpoint_url="ws://127.0.0.1:3001",
                credential_env_vars=["ONEBOT_ACCESS_TOKEN"],
                enabled=True,
                compliance_acknowledged=False,
            )
            registry = social_adapter_registry(
                env={"ONEBOT_ACCESS_TOKEN": "secret"},
                config_path=str(config_file),
            )

        onebot_profile = registry.get_profile("onebot_qq")
        self.assertIsNotNone(onebot_profile)
        self.assertFalse(onebot_profile.ready_for_live_io)
        self.assertIn("compliance_acknowledgement", onebot_profile.missing_requirements())
        self.assertEqual(onebot_profile.transport_kind, "reverse_websocket")

    def test_social_adapter_test_runs_deterministic_normalization_without_live_network(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "social_adapter_profiles.json"
            social_adapter_config_update(
                adapter_name="qq_official",
                config_path=str(config_file),
                credential_env_vars=["QQ_BOT_TOKEN", "QQ_BOT_SECRET"],
                endpoint_url="https://api.sgroup.qq.com",
                enabled=True,
            )
            payload = social_adapter_test(
                adapter_name="qq_official",
                env={"QQ_BOT_TOKEN": "token", "QQ_BOT_SECRET": "secret"},
                config_path=str(config_file),
            )

        self.assertEqual(payload["schema_version"], SOCIAL_ADAPTER_TEST_SCHEMA_VERSION)
        self.assertFalse(payload["executes_live_network"])
        self.assertFalse(payload["probe_requested"])
        self.assertEqual(payload["sample_scenario"], "group")
        self.assertEqual(payload["ready_count"], 1)
        self.assertEqual(payload["deterministic_ready_count"], 1)
        result = payload["results"][0]
        self.assertTrue(result["closure_gates"]["social_ingress_normalized"])
        self.assertEqual(result["social_envelope"]["adapter_kind"], "qq_official")
        self.assertEqual(result["profile"]["transport_kind"], "https")
        self.assertEqual(
            payload["evidence_summary"]["transport_reachability"]["status_counts"],
            {"not_requested": 1},
        )

    def test_social_adapter_test_blocks_probe_without_live_network_opt_in(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "social_adapter_profiles.json"
            social_adapter_config_update(
                adapter_name="qq_official",
                config_path=str(config_file),
                credential_env_vars=["QQ_BOT_TOKEN", "QQ_BOT_SECRET"],
                endpoint_url="https://api.sgroup.qq.com",
                enabled=True,
                live_network_allowed=False,
            )
            payload = social_adapter_test(
                adapter_name="qq_official",
                env={"QQ_BOT_TOKEN": "token", "QQ_BOT_SECRET": "secret"},
                config_path=str(config_file),
                probe_transport=True,
            )

        self.assertTrue(payload["probe_requested"])
        self.assertTrue(payload["executes_live_network"])
        result = payload["results"][0]
        self.assertEqual(result["transport_probe"]["status"], "skipped")
        self.assertEqual(
            result["transport_probe"]["reason"],
            "transport_probe_blocked_by_policy",
        )
        self.assertFalse(result["closure_gates"]["transport_probe_policy_respected"])

    def test_social_adapter_test_can_run_mocked_transport_probe_when_opted_in(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "social_adapter_profiles.json"
            social_adapter_config_update(
                adapter_name="onebot_qq",
                config_path=str(config_file),
                endpoint_url="ws://127.0.0.1:6199",
                credential_env_vars=["ONEBOT_ACCESS_TOKEN"],
                enabled=True,
                live_network_allowed=True,
                compliance_acknowledged=True,
            )
            with mock.patch.object(social_registry_module, "_tcp_probe", return_value=None):
                payload = social_adapter_test(
                    adapter_name="onebot_qq",
                    env={"ONEBOT_ACCESS_TOKEN": "secret"},
                    config_path=str(config_file),
                    sample_scenario="group_no_mention",
                    probe_transport=True,
                    timeout_seconds=0.25,
                )

        self.assertTrue(payload["probe_requested"])
        self.assertTrue(payload["executes_live_network"])
        result = payload["results"][0]
        self.assertEqual(result["transport_probe"]["status"], "ready")
        self.assertEqual(result["transport_probe"]["port"], 6199)
        self.assertEqual(result["sample_scenario"], "group_no_mention")
        self.assertTrue(result["closure_gates"]["transport_probe_policy_respected"])
        self.assertTrue(result["closure_gates"]["transport_probe_recorded"])
        self.assertEqual(
            payload["evidence_summary"]["transport_reachability"]["status_counts"],
            {"ready": 1},
        )


class TestProtocolNormalization(unittest.TestCase):
    def test_qq_official_validation_response_signs_plain_token(self) -> None:
        response = qq_official_validation_response(
            app_secret="secret-for-test",
            plain_token="plain-token-001",
            event_ts="1725442341",
        )

        self.assertEqual(response["plain_token"], "plain-token-001")
        self.assertEqual(len(response["signature"]), 128)

    def test_qq_official_payload_normalizes_group_message(self) -> None:
        adapter = QQOfficialSocialAdapter()
        payload = qq_official_group_message_sample()
        payload["content"] = "hello group"
        payload["mentions"] = [{"id": "bot-neurolink"}]
        envelope = adapter.envelope_from_event(payload)
        event = adapter.to_perception_event(envelope)

        self.assertEqual(envelope.adapter_kind, "qq_official")
        self.assertEqual(envelope.channel_kind, "group")
        self.assertEqual(envelope.principal_id, "qq_official:alice")
        self.assertEqual(event["semantic_topic"], "user.input.social.group")
        self.assertIn("adapter_qq_official", envelope.policy_tags)
        self.assertEqual(envelope.metadata["mention_policy"], "mention_or_direct")
        self.assertEqual(envelope.metadata["transport_kind"], "https")
        self.assertEqual(envelope.metadata["session_scope"], "shared_group")
        self.assertEqual(envelope.metadata["mentioned_user_ids"], ["bot-neurolink"])

    def test_qq_official_payload_normalizes_direct_message(self) -> None:
        adapter = QQOfficialSocialAdapter()
        envelope = adapter.envelope_from_event(qq_official_direct_message_sample())

        self.assertEqual(envelope.channel_kind, "direct")
        self.assertEqual(envelope.channel_id, "direct-dm-qq-001")
        self.assertEqual(envelope.metadata["group_scene"], "direct")
        self.assertEqual(envelope.metadata["session_scope"], "per_user")

    def test_qq_official_group_without_mention_stays_per_user(self) -> None:
        adapter = QQOfficialSocialAdapter()
        envelope = adapter.envelope_from_event(qq_official_group_message_no_mention_sample())

        self.assertEqual(envelope.channel_kind, "group")
        self.assertEqual(envelope.metadata["mentioned_user_ids"], [])
        self.assertEqual(envelope.metadata["session_scope"], "per_user")

    def test_onebot_payload_normalizes_text_segments(self) -> None:
        adapter = OneBotQQSocialAdapter()
        envelope = adapter.envelope_from_event(onebot_group_message_sample())

        self.assertEqual(envelope.adapter_kind, "onebot_qq")
        self.assertEqual(envelope.channel_kind, "group")
        self.assertEqual(envelope.text, "please check current status")
        self.assertEqual(envelope.metadata["source_payload_kind"], "onebot_v11")
        self.assertIn("lab_bridge", envelope.policy_tags)
        self.assertEqual(envelope.metadata["transport_kind"], "reverse_websocket")
        self.assertTrue(envelope.metadata["share_session_in_group"])
        self.assertEqual(envelope.metadata["session_scope"], "shared_group")
        self.assertEqual(envelope.metadata["mentioned_user_ids"], ["2002"])

    def test_onebot_payload_normalizes_direct_message(self) -> None:
        adapter = OneBotQQSocialAdapter()
        envelope = adapter.envelope_from_event(onebot_direct_message_sample())

        self.assertEqual(envelope.channel_kind, "direct")
        self.assertEqual(envelope.channel_id, "1001")
        self.assertEqual(envelope.metadata["session_scope"], "per_user")
        self.assertEqual(envelope.metadata["mentioned_user_ids"], [])

    def test_onebot_group_without_mention_stays_per_user(self) -> None:
        adapter = OneBotQQSocialAdapter()
        envelope = adapter.envelope_from_event(onebot_group_message_no_mention_sample())

        self.assertEqual(envelope.channel_kind, "group")
        self.assertEqual(envelope.text, "please check current status")
        self.assertFalse(envelope.metadata["share_session_in_group"])
        self.assertEqual(envelope.metadata["mentioned_user_ids"], [])
        self.assertEqual(envelope.metadata["session_scope"], "per_user")

    def test_wecom_payload_normalizes_group_message(self) -> None:
        adapter = WeComSocialAdapter()
        envelope = adapter.envelope_from_event(wecom_group_message_sample())

        self.assertEqual(envelope.adapter_kind, "wecom")
        self.assertEqual(envelope.channel_kind, "group")
        self.assertEqual(envelope.principal_id, "wecom:alice")
        self.assertEqual(envelope.metadata["transport_kind"], "websocket")
        self.assertEqual(envelope.metadata["session_scope"], "shared_group")
        self.assertEqual(envelope.metadata["mentioned_user_ids"], ["neuro_bot"])

    def test_wecom_payload_normalizes_direct_message(self) -> None:
        adapter = WeComSocialAdapter()
        envelope = adapter.envelope_from_event(wecom_direct_message_sample())

        self.assertEqual(envelope.channel_kind, "direct")
        self.assertEqual(envelope.channel_id, "direct-alice")
        self.assertEqual(envelope.metadata["group_scene"], "direct")
        self.assertEqual(envelope.metadata["session_scope"], "per_user")

    def test_wecom_group_without_mention_stays_per_user(self) -> None:
        adapter = WeComSocialAdapter()
        envelope = adapter.envelope_from_event(wecom_group_message_no_mention_sample())

        self.assertEqual(envelope.channel_kind, "group")
        self.assertEqual(envelope.metadata["mentioned_user_ids"], [])
        self.assertEqual(envelope.metadata["session_scope"], "per_user")

    def test_wechat_ilink_payload_normalizes_group_message(self) -> None:
        adapter = WeChatILinkSocialAdapter()
        envelope = adapter.envelope_from_event(wechat_ilink_group_message_sample())

        self.assertEqual(envelope.adapter_kind, "wechat_ilink")
        self.assertEqual(envelope.channel_kind, "group")
        self.assertEqual(envelope.metadata["runtime_host"], "openclaw")
        self.assertEqual(envelope.metadata["transport_kind"], "openclaw_gateway")
        self.assertEqual(
            envelope.metadata["social_contract_schema_version"],
            "2.2.3-openclaw-social-contract-v1",
        )
        self.assertEqual(
            envelope.metadata["plugin_package"],
            "@tencent/openclaw-weixin",
        )
        self.assertTrue(envelope.metadata["share_session_in_group"])
        self.assertEqual(envelope.metadata["session_scope"], "shared_group")

    def test_wechat_ilink_payload_normalizes_direct_message(self) -> None:
        adapter = WeChatILinkSocialAdapter()
        envelope = adapter.envelope_from_event(wechat_ilink_direct_message_sample())

        self.assertEqual(envelope.channel_kind, "direct")
        self.assertEqual(envelope.channel_id, "direct-alice")
        self.assertEqual(envelope.metadata["plugin_id"], "wechat_ilink")
        self.assertEqual(
            envelope.metadata["installer_package"],
            "@tencent-weixin/openclaw-weixin-cli",
        )
        self.assertEqual(envelope.metadata["session_scope"], "per_user")

    def test_wechat_ilink_group_without_mention_stays_per_user(self) -> None:
        adapter = WeChatILinkSocialAdapter()
        envelope = adapter.envelope_from_event(
            wechat_ilink_group_message_no_mention_sample()
        )

        self.assertEqual(envelope.channel_kind, "group")
        self.assertFalse(envelope.metadata["share_session_in_group"])
        self.assertEqual(envelope.metadata["session_scope"], "per_user")

    def test_qq_openclaw_payload_normalizes_group_message(self) -> None:
        adapter = QQOpenClawSocialAdapter()
        envelope = adapter.envelope_from_event(qq_openclaw_group_message_sample())

        self.assertEqual(envelope.adapter_kind, "qq_openclaw")
        self.assertEqual(envelope.channel_kind, "group")
        self.assertEqual(envelope.metadata["runtime_host"], "openclaw")
        self.assertEqual(envelope.metadata["platform_kind"], "qq")
        self.assertEqual(envelope.metadata["plugin_id"], "qq_openclaw")
        self.assertTrue(envelope.metadata["share_session_in_group"])
        self.assertEqual(envelope.metadata["session_scope"], "shared_group")

    def test_qq_openclaw_payload_normalizes_direct_message(self) -> None:
        adapter = QQOpenClawSocialAdapter()
        envelope = adapter.envelope_from_event(qq_openclaw_direct_message_sample())

        self.assertEqual(envelope.channel_kind, "direct")
        self.assertEqual(envelope.channel_id, "direct-alice")
        self.assertEqual(
            envelope.metadata["plugin_package"],
            "operator-supplied-qq-openclaw-package",
        )
        self.assertEqual(envelope.metadata["session_scope"], "per_user")

    def test_qq_openclaw_group_without_mention_stays_per_user(self) -> None:
        adapter = QQOpenClawSocialAdapter()
        envelope = adapter.envelope_from_event(
            qq_openclaw_group_message_no_mention_sample()
        )

        self.assertEqual(envelope.channel_kind, "group")
        self.assertFalse(envelope.metadata["share_session_in_group"])
        self.assertEqual(envelope.metadata["session_scope"], "per_user")


class TestSocialAdapterCli(unittest.TestCase):
    def test_cli_social_adapter_list_outputs_registry(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            code = core_cli_main(["social-adapter-list"])

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["command"], "social-adapter-list")
        self.assertIn("qq_official", {profile["name"] for profile in payload["profiles"]})
        self.assertIn("onebot_qq", {profile["name"] for profile in payload["profiles"]})
        self.assertIn("wecom", {profile["name"] for profile in payload["profiles"]})
        self.assertIn("wechat_ilink", {profile["name"] for profile in payload["profiles"]})
        self.assertIn("qq_openclaw", {profile["name"] for profile in payload["profiles"]})

    def test_cli_social_adapter_test_supports_wecom_direct_sample_scenario(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "social_adapter_profiles.json"
            core_cli_main(
                [
                    "social-adapter-config",
                    "--config-file",
                    str(config_file),
                    "--adapter",
                    "wecom",
                    "--endpoint-url",
                    "wss://qyapi.weixin.qq.com/cgi-bin/webhook/connect",
                    "--transport-kind",
                    "websocket",
                    "--credential-env-var",
                    "WECOM_BOT_TOKEN",
                    "--enable",
                ]
            )
            out = io.StringIO()
            with mock.patch.dict(os.environ, {"WECOM_BOT_TOKEN": "token"}, clear=False):
                with redirect_stdout(out):
                    code = core_cli_main(
                        [
                            "social-adapter-test",
                            "--config-file",
                            str(config_file),
                            "--adapter",
                            "wecom",
                            "--sample-scenario",
                            "direct",
                        ]
                    )

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["sample_scenario"], "direct")
        self.assertEqual(payload["results"][0]["social_envelope"]["adapter_kind"], "wecom")
        self.assertEqual(payload["results"][0]["social_envelope"]["channel_kind"], "direct")

    def test_cli_social_adapter_test_supports_wechat_ilink_group_scenario(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "social_adapter_profiles.json"
            core_cli_main(
                [
                    "social-adapter-config",
                    "--config-file",
                    str(config_file),
                    "--adapter",
                    "wechat_ilink",
                    "--endpoint-url",
                    "https://wechat.example.invalid/ilink",
                    "--transport-kind",
                    "long_poll",
                    "--share-session-in-group",
                    "true",
                    "--compliance-acknowledged",
                    "true",
                    "--credential-env-var",
                    "WECHAT_ILINK_TOKEN",
                    "--enable",
                ]
            )
            out = io.StringIO()
            with mock.patch.dict(os.environ, {"WECHAT_ILINK_TOKEN": "token"}, clear=False):
                with redirect_stdout(out):
                    code = core_cli_main(
                        [
                            "social-adapter-test",
                            "--config-file",
                            str(config_file),
                            "--adapter",
                            "wechat_ilink",
                            "--sample-scenario",
                            "group",
                        ]
                    )

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["results"][0]["social_envelope"]["adapter_kind"], "wechat_ilink")
        self.assertEqual(payload["results"][0]["social_envelope"]["channel_kind"], "group")
        self.assertEqual(payload["results"][0]["profile"]["transport_kind"], "long_poll")

    def test_cli_social_adapter_test_supports_qq_openclaw_group_scenario(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "social_adapter_profiles.json"
            core_cli_main(
                [
                    "social-adapter-config",
                    "--config-file",
                    str(config_file),
                    "--adapter",
                    "qq_openclaw",
                    "--host-url",
                    "ws://127.0.0.1:8811/openclaw",
                    "--transport-kind",
                    "openclaw_gateway",
                    "--share-session-in-group",
                    "true",
                    "--compliance-acknowledged",
                    "true",
                    "--credential-env-var",
                    "QQ_OPENCLAW_TOKEN",
                    "--plugin-id",
                    "qq_openclaw",
                    "--plugin-package",
                    "operator-supplied-qq-openclaw-package",
                    "--installer-package",
                    "operator-supplied-qq-openclaw-installer",
                    "--plugin-installed",
                    "true",
                    "--account-session-ready",
                    "true",
                    "--enable",
                ]
            )
            out = io.StringIO()
            with mock.patch.dict(os.environ, {"QQ_OPENCLAW_TOKEN": "token"}, clear=False):
                with redirect_stdout(out):
                    code = core_cli_main(
                        [
                            "social-adapter-test",
                            "--config-file",
                            str(config_file),
                            "--adapter",
                            "qq_openclaw",
                            "--sample-scenario",
                            "group",
                        ]
                    )

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(
            payload["results"][0]["social_envelope"]["adapter_kind"],
            "qq_openclaw",
        )
        self.assertEqual(payload["results"][0]["social_envelope"]["channel_kind"], "group")
        self.assertEqual(
            payload["results"][0]["profile"]["transport_kind"],
            "openclaw_gateway",
        )

    def test_cli_social_adapter_config_and_test_use_config_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "social_adapter_profiles.json"
            config_out = io.StringIO()
            with redirect_stdout(config_out):
                config_code = core_cli_main(
                    [
                        "social-adapter-config",
                        "--config-file",
                        str(config_file),
                        "--adapter",
                        "qq_official",
                        "--credential-env-var",
                        "QQ_BOT_TOKEN",
                        "--credential-env-var",
                        "QQ_BOT_SECRET",
                        "--endpoint-url",
                        "https://api.sgroup.qq.com",
                        "--mention-policy",
                        "mention_or_direct",
                        "--transport-kind",
                        "https",
                        "--enable",
                        "--active",
                    ]
                )
            test_out = io.StringIO()
            with mock.patch.dict(
                os.environ,
                {"QQ_BOT_TOKEN": "token", "QQ_BOT_SECRET": "secret"},
                clear=False,
            ):
                with redirect_stdout(test_out):
                    test_code = core_cli_main(
                        [
                            "social-adapter-test",
                            "--config-file",
                            str(config_file),
                            "--adapter",
                            "qq_official",
                        ]
                    )

        self.assertEqual(config_code, 0)
        self.assertEqual(test_code, 0)
        config_payload = json.loads(config_out.getvalue())
        test_payload = json.loads(test_out.getvalue())
        self.assertEqual(config_payload["updated_adapter"], "qq_official")
        qq_profile = next(
            profile
            for profile in config_payload["social_adapter_registry"]["profiles"]
            if profile["name"] == "qq_official"
        )
        self.assertEqual(qq_profile["mention_policy"], "mention_or_direct")
        self.assertEqual(qq_profile["transport_kind"], "https")
        self.assertEqual(test_payload["ready_count"], 1)
        self.assertEqual(test_payload["results"][0]["social_envelope"]["adapter_kind"], "qq_official")

    def test_cli_social_adapter_config_supports_onebot_shared_group_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "social_adapter_profiles.json"
            out = io.StringIO()
            with redirect_stdout(out):
                code = core_cli_main(
                    [
                        "social-adapter-config",
                        "--config-file",
                        str(config_file),
                        "--adapter",
                        "onebot_qq",
                        "--endpoint-url",
                        "ws://127.0.0.1:6199",
                        "--transport-kind",
                        "reverse_websocket",
                        "--share-session-in-group",
                        "true",
                        "--compliance-acknowledged",
                        "true",
                        "--credential-env-var",
                        "ONEBOT_ACCESS_TOKEN",
                        "--enable",
                    ]
                )

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        onebot_profile = next(
            profile
            for profile in payload["social_adapter_registry"]["profiles"]
            if profile["name"] == "onebot_qq"
        )
        self.assertTrue(onebot_profile["share_session_in_group"])
        self.assertEqual(onebot_profile["transport_kind"], "reverse_websocket")

    def test_cli_social_adapter_test_supports_opt_in_probe(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "social_adapter_profiles.json"
            core_cli_main(
                [
                    "social-adapter-config",
                    "--config-file",
                    str(config_file),
                    "--adapter",
                    "onebot_qq",
                    "--endpoint-url",
                    "ws://127.0.0.1:6199",
                    "--transport-kind",
                    "reverse_websocket",
                    "--share-session-in-group",
                    "true",
                    "--compliance-acknowledged",
                    "true",
                    "--live-network-allowed",
                    "true",
                    "--credential-env-var",
                    "ONEBOT_ACCESS_TOKEN",
                    "--enable",
                ]
            )
            out = io.StringIO()
            with mock.patch.dict(os.environ, {"ONEBOT_ACCESS_TOKEN": "secret"}, clear=False):
                with mock.patch.object(social_registry_module, "_tcp_probe", return_value=None):
                    with redirect_stdout(out):
                        code = core_cli_main(
                            [
                                "social-adapter-test",
                                "--config-file",
                                str(config_file),
                                "--adapter",
                                "onebot_qq",
                                "--probe-transport",
                                "--probe-timeout-seconds",
                                "0.25",
                            ]
                        )

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertTrue(payload["probe_requested"])
        self.assertTrue(payload["executes_live_network"])
        self.assertEqual(payload["results"][0]["transport_probe"]["status"], "ready")

    def test_cli_social_adapter_test_supports_direct_sample_scenario(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            code = core_cli_main(
                [
                    "social-adapter-test",
                    "--adapter",
                    "qq_official",
                    "--sample-scenario",
                    "direct",
                ]
            )

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["sample_scenario"], "direct")
        self.assertEqual(payload["results"][0]["social_envelope"]["channel_kind"], "direct")
        self.assertEqual(
            payload["evidence_summary"]["deterministic_normalization"]["tested_count"],
            1,
        )

    def test_cli_qq_official_webhook_server_validates_and_dispatches(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "social_adapter_profiles.json"
            ready_file = Path(tmpdir) / "qq-webhook-ready.json"
            db_file = Path(tmpdir) / "qq-webhook.db"
            social_adapter_config_update(
                adapter_name="qq_official",
                config_path=str(config_file),
                credential_env_vars=["QQ_BOT_APP_ID", "QQ_BOT_APP_SECRET"],
                endpoint_url="https://api.sgroup.qq.com",
                enabled=True,
                active=True,
                live_network_allowed=True,
            )
            out = io.StringIO()

            def run_server() -> None:
                with mock.patch.dict(
                    os.environ,
                    {
                        "QQ_BOT_APP_ID": "1903339424",
                        "QQ_BOT_APP_SECRET": "test-secret-value",
                    },
                    clear=False,
                ):
                    with redirect_stdout(out):
                        code = core_cli_main(
                            [
                                "qq-official-webhook-server",
                                "--config-file",
                                str(config_file),
                                "--db",
                                str(db_file),
                                "--host",
                                "127.0.0.1",
                                "--port",
                                "0",
                                "--path",
                                "/qq/callback",
                                "--duration",
                                "5",
                                "--max-events",
                                "1",
                                "--ready-file",
                                str(ready_file),
                            ]
                        )
                self.assertEqual(code, 0)

            thread = threading.Thread(target=run_server)
            thread.start()
            for _ in range(50):
                if ready_file.exists():
                    break
                time.sleep(0.1)
            self.assertTrue(ready_file.exists())
            ready_payload = json.loads(ready_file.read_text(encoding="utf-8"))
            base_url = (
                f"http://{ready_payload['host']}:{ready_payload['port']}{ready_payload['path']}"
            )

            validation_request = request.Request(
                base_url,
                data=json.dumps(
                    {
                        "op": 13,
                        "d": {
                            "plain_token": "plain-token-001",
                            "event_ts": "1725442341",
                        },
                    }
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with request.urlopen(validation_request, timeout=2) as response:
                validation_payload = json.loads(response.read().decode("utf-8"))
            self.assertEqual(validation_payload["plain_token"], "plain-token-001")

            dispatch_request = request.Request(
                base_url,
                data=json.dumps(
                    {
                        "op": 0,
                        "t": "C2C_MESSAGE_CREATE",
                        "d": {
                            "id": "qq-direct-live-001",
                            "author": {"id": "alice"},
                            "content": "hello from live ingress",
                        },
                    }
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with request.urlopen(dispatch_request, timeout=2) as response:
                dispatch_payload = json.loads(response.read().decode("utf-8"))
            self.assertEqual(dispatch_payload["op"], 12)

            thread.join(timeout=10)
            self.assertFalse(thread.is_alive())
            payload = json.loads(out.getvalue())
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["validation_request_count"], 1)
            self.assertEqual(payload["dispatch_event_count"], 1)
            self.assertEqual(payload["events"][0]["event_type"], "C2C_MESSAGE_CREATE")
            self.assertEqual(payload["events"][0]["channel_kind"], "direct")
            self.assertEqual(payload["core_results"][0]["events_persisted"], 1)

    def test_cli_qq_official_gateway_client_identifies_and_dispatches(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "social_adapter_profiles.json"
            ready_file = Path(tmpdir) / "qq-gateway-ready.json"
            db_file = Path(tmpdir) / "qq-gateway.db"
            social_adapter_config_update(
                adapter_name="qq_official",
                config_path=str(config_file),
                credential_env_vars=["QQ_BOT_APP_ID", "QQ_BOT_APP_SECRET"],
                endpoint_url="https://api.sgroup.qq.com",
                enabled=True,
                active=True,
                live_network_allowed=True,
            )

            server_ready: dict[str, Any] = {}
            stop_event = threading.Event()

            async def gateway_handler(websocket: Any) -> None:
                await websocket.send(json.dumps({"op": 10, "d": {"heartbeat_interval": 50}}))
                identify_payload = json.loads(await asyncio.wait_for(websocket.recv(), timeout=2))
                server_ready["identify"] = identify_payload
                await websocket.send(
                    json.dumps(
                        {
                            "op": 0,
                            "s": 1,
                            "t": "READY",
                            "d": {
                                "version": 1,
                                "session_id": "qq-gateway-session-001",
                                "user": {"id": "bot-qq-001", "username": "neurolink-bot", "bot": True},
                                "shard": [0, 0],
                            },
                        }
                    )
                )
                await websocket.send(
                    json.dumps(
                        {
                            "op": 0,
                            "s": 2,
                            "t": "C2C_MESSAGE_CREATE",
                            "d": {
                                "id": "qq-gateway-live-001",
                                "author": {"id": "alice"},
                                "content": "hello from gateway ingress",
                            },
                        }
                    )
                )
                await asyncio.sleep(0.05)

            def run_gateway_server() -> None:
                async def main() -> None:
                    async with websockets.serve(gateway_handler, "127.0.0.1", 0) as server:
                        port = server.sockets[0].getsockname()[1]
                        server_ready["url"] = f"ws://127.0.0.1:{port}"
                        while not stop_event.is_set():
                            await asyncio.sleep(0.05)

                asyncio.run(main())

            server_thread = threading.Thread(target=run_gateway_server)
            server_thread.start()
            for _ in range(50):
                if server_ready.get("url"):
                    break
                time.sleep(0.1)
            self.assertTrue(server_ready.get("url"))

            out = io.StringIO()
            with mock.patch.dict(
                os.environ,
                {
                    "QQ_BOT_APP_ID": "1903993368",
                    "QQ_BOT_APP_SECRET": "test-gateway-secret",
                },
                clear=False,
            ):
                with mock.patch(
                    "neurolink_core.social_adapters.qq_official_gateway.qq_official_fetch_access_token",
                    return_value={"access_token": "gateway-access-token-001", "expires_in": 7200},
                ):
                    with redirect_stdout(out):
                        code = core_cli_main(
                            [
                                "qq-official-gateway-client",
                                "--config-file",
                                str(config_file),
                                "--db",
                                str(db_file),
                                "--gateway-url",
                                str(server_ready["url"]),
                                "--duration",
                                "5",
                                "--max-events",
                                "1",
                                "--ready-file",
                                str(ready_file),
                            ]
                        )
            stop_event.set()
            server_thread.join(timeout=5)

            self.assertEqual(code, 0)
            self.assertTrue(ready_file.exists())
            payload = json.loads(out.getvalue())
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["hello_count"], 1)
            self.assertEqual(payload["ready_event_count"], 1)
            self.assertEqual(payload["dispatch_event_count"], 1)
            self.assertEqual(payload["events"][0]["event_type"], "C2C_MESSAGE_CREATE")
            self.assertEqual(payload["events"][0]["channel_kind"], "direct")
            self.assertEqual(payload["core_results"][0]["events_persisted"], 1)
            identify_payload = server_ready["identify"]
            self.assertEqual(identify_payload["op"], 2)
            self.assertEqual(identify_payload["d"]["token"], "QQBot gateway-access-token-001")

    def test_cli_wecom_gateway_client_authenticates_and_dispatches(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "social_adapter_profiles.json"
            ready_file = Path(tmpdir) / "wecom-gateway-ready.json"
            db_file = Path(tmpdir) / "wecom-gateway.db"
            social_adapter_config_update(
                adapter_name="wecom",
                config_path=str(config_file),
                credential_env_vars=["WECOM_BOT_TOKEN"],
                endpoint_url="wss://qyapi.weixin.qq.com/cgi-bin/webhook/connect",
                enabled=True,
                active=True,
                live_network_allowed=True,
            )

            server_ready: dict[str, Any] = {}
            stop_event = threading.Event()

            async def gateway_handler(websocket: Any) -> None:
                auth_payload = json.loads(await asyncio.wait_for(websocket.recv(), timeout=2))
                server_ready["auth"] = auth_payload
                await websocket.send(
                    json.dumps(
                        {
                            "event": "READY",
                            "bot_user_id": "wecom-bot-001",
                        }
                    )
                )
                await websocket.send(
                    json.dumps(
                        {
                            "event": "message",
                            "data": {
                                "msgid": "wecom-live-001",
                                "conversation_type": "single",
                                "from": "alice",
                                "text": "hello from wecom gateway",
                                "mentioned_list": [],
                            },
                        }
                    )
                )
                await asyncio.sleep(0.05)

            def run_gateway_server() -> None:
                async def main() -> None:
                    async with websockets.serve(gateway_handler, "127.0.0.1", 0) as server:
                        port = server.sockets[0].getsockname()[1]
                        server_ready["url"] = f"ws://127.0.0.1:{port}"
                        while not stop_event.is_set():
                            await asyncio.sleep(0.05)

                asyncio.run(main())

            server_thread = threading.Thread(target=run_gateway_server)
            server_thread.start()
            for _ in range(50):
                if server_ready.get("url"):
                    break
                time.sleep(0.1)
            self.assertTrue(server_ready.get("url"))

            out = io.StringIO()
            with mock.patch.dict(
                os.environ,
                {
                    "WECOM_BOT_TOKEN": "test-wecom-token",
                },
                clear=False,
            ):
                with redirect_stdout(out):
                    code = core_cli_main(
                        [
                            "wecom-gateway-client",
                            "--config-file",
                            str(config_file),
                            "--db",
                            str(db_file),
                            "--gateway-url",
                            str(server_ready["url"]),
                            "--duration",
                            "5",
                            "--max-events",
                            "1",
                            "--ready-file",
                            str(ready_file),
                        ]
                    )
            stop_event.set()
            server_thread.join(timeout=5)

            self.assertEqual(code, 0)
            self.assertFalse(server_thread.is_alive())
            self.assertTrue(ready_file.exists())
            auth_payload = server_ready["auth"]
            self.assertEqual(auth_payload["op"], "auth")
            self.assertEqual(auth_payload["d"]["token"], "test-wecom-token")

            payload = json.loads(out.getvalue())
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["ready_event_count"], 1)
            self.assertEqual(payload["dispatch_event_count"], 1)
            self.assertEqual(payload["events"][0]["event_type"], "message")
            self.assertEqual(payload["events"][0]["channel_kind"], "direct")
            self.assertEqual(payload["core_results"][0]["events_persisted"], 1)

    def test_cli_openclaw_gateway_client_binds_and_dispatches_wechat_ilink(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "social_adapter_profiles.json"
            ready_file = Path(tmpdir) / "openclaw-gateway-ready.json"
            db_file = Path(tmpdir) / "openclaw-gateway.db"
            social_adapter_config_update(
                adapter_name="wechat_ilink",
                config_path=str(config_file),
                host_url="ws://127.0.0.1:8811/openclaw",
                endpoint_url="https://wechat.example.invalid/ilink",
                credential_env_vars=["WECHAT_ILINK_TOKEN"],
                plugin_package="@tencent/openclaw-weixin",
                installer_package="@tencent-weixin/openclaw-weixin-cli",
                plugin_installed=True,
                account_session_ready=True,
                enabled=True,
                active=True,
                compliance_acknowledged=True,
                live_network_allowed=True,
            )

            server_ready: dict[str, Any] = {}
            stop_event = threading.Event()

            async def gateway_handler(websocket: Any) -> None:
                bind_payload = json.loads(await asyncio.wait_for(websocket.recv(), timeout=2))
                server_ready["bind"] = bind_payload
                await websocket.send(
                    json.dumps(
                        {
                            "event": "READY",
                            "host_version": "0.9.1",
                            "plugin": {
                                "id": "wechat_ilink",
                                "package": "@tencent/openclaw-weixin",
                                "ready": True,
                            },
                        }
                    )
                )
                await websocket.send(
                    json.dumps(
                        {
                            "event": "message",
                            "data": {
                                "msg_id": "wechat-openclaw-live-001",
                                "scene": "direct",
                                "from_user": "alice",
                                "text": "hello from openclaw gateway",
                                "mentioned_list": [],
                            },
                        }
                    )
                )
                await asyncio.sleep(0.05)

            def run_gateway_server() -> None:
                async def main() -> None:
                    async with websockets.serve(gateway_handler, "127.0.0.1", 0) as server:
                        port = server.sockets[0].getsockname()[1]
                        server_ready["url"] = f"ws://127.0.0.1:{port}"
                        while not stop_event.is_set():
                            await asyncio.sleep(0.05)

                asyncio.run(main())

            server_thread = threading.Thread(target=run_gateway_server)
            server_thread.start()
            for _ in range(50):
                if server_ready.get("url"):
                    break
                time.sleep(0.1)
            self.assertTrue(server_ready.get("url"))

            out = io.StringIO()
            with mock.patch.dict(
                os.environ,
                {
                    "WECHAT_ILINK_TOKEN": "test-openclaw-token",
                },
                clear=False,
            ):
                with redirect_stdout(out):
                    code = core_cli_main(
                        [
                            "openclaw-gateway-client",
                            "--config-file",
                            str(config_file),
                            "--db",
                            str(db_file),
                            "--adapter",
                            "wechat_ilink",
                            "--gateway-url",
                            str(server_ready["url"]),
                            "--duration",
                            "5",
                            "--max-events",
                            "1",
                            "--ready-file",
                            str(ready_file),
                        ]
                    )
            stop_event.set()
            server_thread.join(timeout=5)

            self.assertEqual(code, 0)
            self.assertFalse(server_thread.is_alive())
            self.assertTrue(ready_file.exists())
            bind_payload = server_ready["bind"]
            self.assertEqual(bind_payload["op"], "bind")
            self.assertEqual(bind_payload["d"]["token"], "test-openclaw-token")
            self.assertEqual(bind_payload["d"]["adapter"], "wechat_ilink")

            payload = json.loads(out.getvalue())
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["ready_event_count"], 1)
            self.assertEqual(payload["dispatch_event_count"], 1)
            self.assertEqual(payload["events"][0]["adapter_kind"], "wechat_ilink")
            self.assertEqual(payload["events"][0]["channel_kind"], "direct")
            self.assertEqual(payload["events"][0]["plugin_package"], "@tencent/openclaw-weixin")
            self.assertEqual(payload["core_results"][0]["events_persisted"], 1)

    def test_cli_openclaw_gateway_client_binds_and_dispatches_qq_openclaw(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "social_adapter_profiles.json"
            ready_file = Path(tmpdir) / "qq-openclaw-gateway-ready.json"
            db_file = Path(tmpdir) / "qq-openclaw-gateway.db"
            social_adapter_config_update(
                adapter_name="qq_openclaw",
                config_path=str(config_file),
                host_url="ws://127.0.0.1:8811/openclaw",
                credential_env_vars=["QQ_OPENCLAW_TOKEN"],
                plugin_id="qq_openclaw",
                plugin_package="operator-supplied-qq-openclaw-package",
                installer_package="operator-supplied-qq-openclaw-installer",
                plugin_installed=True,
                account_session_ready=True,
                enabled=True,
                active=True,
                compliance_acknowledged=True,
                live_network_allowed=True,
            )

            server_ready: dict[str, Any] = {}
            stop_event = threading.Event()

            async def gateway_handler(websocket: Any) -> None:
                bind_payload = json.loads(await asyncio.wait_for(websocket.recv(), timeout=2))
                server_ready["bind"] = bind_payload
                await websocket.send(
                    json.dumps(
                        {
                            "event": "READY",
                            "host_version": "0.9.2",
                            "plugin": {
                                "id": "qq_openclaw",
                                "package": "operator-supplied-qq-openclaw-package",
                                "ready": True,
                            },
                        }
                    )
                )
                await websocket.send(
                    json.dumps(
                        {
                            "event": "message",
                            "data": {
                                "msg_id": "qq-openclaw-live-001",
                                "scene": "direct",
                                "from_user": "alice",
                                "text": "hello from qq openclaw gateway",
                                "mentioned_list": [],
                            },
                        }
                    )
                )
                await asyncio.sleep(0.05)

            def run_gateway_server() -> None:
                async def main() -> None:
                    async with websockets.serve(gateway_handler, "127.0.0.1", 0) as server:
                        port = server.sockets[0].getsockname()[1]
                        server_ready["url"] = f"ws://127.0.0.1:{port}"
                        while not stop_event.is_set():
                            await asyncio.sleep(0.05)

                asyncio.run(main())

            server_thread = threading.Thread(target=run_gateway_server)
            server_thread.start()
            for _ in range(50):
                if server_ready.get("url"):
                    break
                time.sleep(0.1)
            self.assertTrue(server_ready.get("url"))

            out = io.StringIO()
            with mock.patch.dict(
                os.environ,
                {
                    "QQ_OPENCLAW_TOKEN": "test-openclaw-token",
                },
                clear=False,
            ):
                with redirect_stdout(out):
                    code = core_cli_main(
                        [
                            "openclaw-gateway-client",
                            "--config-file",
                            str(config_file),
                            "--db",
                            str(db_file),
                            "--adapter",
                            "qq_openclaw",
                            "--gateway-url",
                            str(server_ready["url"]),
                            "--duration",
                            "5",
                            "--max-events",
                            "1",
                            "--ready-file",
                            str(ready_file),
                        ]
                    )
            stop_event.set()
            server_thread.join(timeout=5)

            self.assertEqual(code, 0)
            self.assertFalse(server_thread.is_alive())
            self.assertTrue(ready_file.exists())
            bind_payload = server_ready["bind"]
            self.assertEqual(bind_payload["op"], "bind")
            self.assertEqual(bind_payload["d"]["token"], "test-openclaw-token")
            self.assertEqual(bind_payload["d"]["adapter"], "qq_openclaw")

            payload = json.loads(out.getvalue())
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["ready_event_count"], 1)
            self.assertEqual(payload["dispatch_event_count"], 1)
            self.assertEqual(payload["events"][0]["adapter_kind"], "qq_openclaw")
            self.assertEqual(payload["events"][0]["channel_kind"], "direct")
            self.assertEqual(
                payload["events"][0]["plugin_package"],
                "operator-supplied-qq-openclaw-package",
            )
            self.assertEqual(payload["core_results"][0]["events_persisted"], 1)

    def test_cli_qq_official_gateway_client_resumes_after_disconnect(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "social_adapter_profiles.json"
            session_state_file = Path(tmpdir) / "qq-gateway-session.json"
            db_file = Path(tmpdir) / "qq-gateway-resume.db"
            social_adapter_config_update(
                adapter_name="qq_official",
                config_path=str(config_file),
                credential_env_vars=["QQ_BOT_APP_ID", "QQ_BOT_APP_SECRET"],
                endpoint_url="https://api.sgroup.qq.com",
                enabled=True,
                active=True,
                live_network_allowed=True,
            )

            server_state: dict[str, Any] = {"connections": 0, "messages": []}
            stop_event = threading.Event()

            async def gateway_handler(websocket: Any) -> None:
                server_state["connections"] = int(server_state["connections"]) + 1
                connection_id = int(server_state["connections"])
                await websocket.send(json.dumps({"op": 10, "d": {"heartbeat_interval": 50}}))
                client_payload = json.loads(await asyncio.wait_for(websocket.recv(), timeout=2))
                server_state["messages"].append(client_payload)
                if connection_id == 1:
                    await websocket.send(
                        json.dumps(
                            {
                                "op": 0,
                                "s": 1,
                                "t": "READY",
                                "d": {
                                    "version": 1,
                                    "session_id": "qq-gateway-session-resume-001",
                                    "user": {"id": "bot-qq-001", "username": "neurolink-bot", "bot": True},
                                    "shard": [0, 0],
                                },
                            }
                        )
                    )
                    await websocket.close()
                    return

                await websocket.send(json.dumps({"op": 0, "s": 2, "t": "RESUMED", "d": {}}))
                await websocket.send(
                    json.dumps(
                        {
                            "op": 0,
                            "s": 3,
                            "t": "C2C_MESSAGE_CREATE",
                            "d": {
                                "id": "qq-gateway-resume-live-001",
                                "author": {"id": "alice"},
                                "content": "hello after resume",
                            },
                        }
                    )
                )
                await asyncio.sleep(0.05)

            def run_gateway_server() -> None:
                async def main() -> None:
                    async with websockets.serve(gateway_handler, "127.0.0.1", 0) as server:
                        port = server.sockets[0].getsockname()[1]
                        server_state["url"] = f"ws://127.0.0.1:{port}"
                        while not stop_event.is_set():
                            await asyncio.sleep(0.05)

                asyncio.run(main())

            server_thread = threading.Thread(target=run_gateway_server)
            server_thread.start()
            for _ in range(50):
                if server_state.get("url"):
                    break
                time.sleep(0.1)
            self.assertTrue(server_state.get("url"))

            out = io.StringIO()
            with mock.patch.dict(
                os.environ,
                {
                    "QQ_BOT_APP_ID": "1903993368",
                    "QQ_BOT_APP_SECRET": "test-gateway-secret",
                },
                clear=False,
            ):
                with mock.patch(
                    "neurolink_core.social_adapters.qq_official_gateway.qq_official_fetch_access_token",
                    return_value={"access_token": "gateway-access-token-001", "expires_in": 7200},
                ):
                    with redirect_stdout(out):
                        code = core_cli_main(
                            [
                                "qq-official-gateway-client",
                                "--config-file",
                                str(config_file),
                                "--db",
                                str(db_file),
                                "--gateway-url",
                                str(server_state["url"]),
                                "--duration",
                                "5",
                                "--max-events",
                                "1",
                                "--session-state-file",
                                str(session_state_file),
                                "--max-resume-attempts",
                                "2",
                                "--reconnect-backoff-seconds",
                                "0.01",
                            ]
                        )
            stop_event.set()
            server_thread.join(timeout=5)

            self.assertEqual(code, 0)
            payload = json.loads(out.getvalue())
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["hello_count"], 2)
            self.assertEqual(payload["ready_event_count"], 1)
            self.assertEqual(payload["resumed_event_count"], 1)
            self.assertEqual(payload["resume_attempt_count"], 1)
            self.assertEqual(payload["resume_success_count"], 1)
            self.assertEqual(payload["reconnect_count"], 1)
            self.assertEqual(payload["dispatch_event_count"], 1)
            self.assertTrue(payload["session_state_persisted"])
            self.assertTrue(session_state_file.exists())
            session_payload = json.loads(session_state_file.read_text(encoding="utf-8"))
            self.assertEqual(session_payload["session_id"], "qq-gateway-session-resume-001")
            self.assertEqual(session_payload["sequence"], 3)
            self.assertTrue(session_payload["can_resume"])
            self.assertEqual(server_state["messages"][0]["op"], 2)
            self.assertEqual(server_state["messages"][1]["op"], 6)
            self.assertEqual(server_state["messages"][1]["d"]["session_id"], "qq-gateway-session-resume-001")
            self.assertEqual(server_state["messages"][1]["d"]["seq"], 1)

    def test_cli_social_chat_accepts_qq_official_adapter_kind_in_deterministic_mode(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            code = core_cli_main(
                [
                    "social-chat",
                    "--output",
                    "json",
                    "--message",
                    "please check current status",
                    "--social-adapter-kind",
                    "qq_official",
                    "--social-channel-id",
                    "group-qq-001",
                    "--social-channel-kind",
                    "group",
                    "--social-user-id",
                    "alice",
                ]
            )

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["command"], "social-chat")
        self.assertEqual(payload["agent_run_evidence"]["event_source"], "mock_social")
        self.assertEqual(payload["events_persisted"], 1)
        self.assertEqual(payload["final_response"]["speaker"], "affective")

    def test_cli_social_adapter_smoke_reports_registry_and_protocol_gates(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            code = core_cli_main(["social-adapter-smoke"])

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["command"], "social-adapter-smoke")
        self.assertTrue(payload["closure_gates"]["social_adapter_registry_gate"])
        self.assertTrue(payload["closure_gates"]["qq_social_gate"])
        self.assertTrue(payload["closure_gates"]["onebot_social_gate"])
        self.assertTrue(payload["closure_gates"]["social_compliance_gate"])
        self.assertIn("qq_official", payload["evidence_summary"]["ready_adapter_names"])
