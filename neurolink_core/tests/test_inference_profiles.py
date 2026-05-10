import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

from neurolink_core.cli import main as core_cli_main
from neurolink_core.inference import MODEL_PROFILE_SMOKE_SCHEMA_VERSION
from neurolink_core.inference import build_provider_runtime_env
from neurolink_core.inference import model_profile_smoke
from neurolink_core.inference import provider_profile_registry


class TestProviderProfileRegistry(unittest.TestCase):
    def test_registry_masks_secret_values_and_marks_ready_openai_profile(self) -> None:
        env = {
            "OPENAI_BASE_URL": "https://provider.example/v1",
            "OPENAI_API_KEY": "secret-value-that-must-not-leak",
            "OPENAI_MODEL": "gpt-4.1-mini",
        }

        registry = provider_profile_registry(env=env)
        payload = registry.to_dict()

        encoded = json.dumps(payload, sort_keys=True)
        self.assertNotIn("secret-value-that-must-not-leak", encoded)
        openai_profile = registry.get_profile("openai_compatible")
        self.assertIsNotNone(openai_profile)
        assert openai_profile is not None
        self.assertTrue(openai_profile.ready_for_model_call)
        self.assertEqual(openai_profile.configured_model, "gpt-4.1-mini")
        self.assertEqual(openai_profile.to_dict()["credential_value_masked"], "***")

    def test_model_profile_smoke_fails_closed_without_credentials(self) -> None:
        payload = model_profile_smoke(env={})

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["schema_version"], MODEL_PROFILE_SMOKE_SCHEMA_VERSION)
        self.assertEqual(payload["status"], "configured_fail_closed")
        self.assertFalse(payload["executes_model_call"])
        self.assertTrue(payload["closure_gates"]["missing_requirements_recorded"])
        self.assertIn("openai_compatible", payload["missing_requirements"])

    def test_model_profile_smoke_marks_ready_when_active_profile_is_configured(self) -> None:
        payload = model_profile_smoke(
            env={
                "OPENAI_API_KEY": "secret",
                "OPENAI_MODEL": "gpt-4.1-mini",
            }
        )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "ready")
        self.assertTrue(payload["evidence_summary"]["active_profiles_ready"])

    def test_cli_provider_list_outputs_registry_json(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            code = core_cli_main(["provider-list"])

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(
            payload["schema_version"],
            "2.2.1-provider-profile-registry-v1",
        )
        self.assertEqual(payload["active_affective_profile"], "openai_compatible")

    def test_cli_model_profile_smoke_outputs_fail_closed_json(self) -> None:
        out = io.StringIO()
        with mock.patch.dict("os.environ", {}, clear=True):
            with redirect_stdout(out):
                code = core_cli_main(["model-profile-smoke"])

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["schema_version"], MODEL_PROFILE_SMOKE_SCHEMA_VERSION)
        self.assertEqual(payload["status"], "configured_fail_closed")
        self.assertTrue(payload["closure_gates"]["no_model_call_executed"])

    def test_cli_provider_config_persists_updates_and_provider_list_reads_them(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "runtime_provider_profiles.json"

            config_out = io.StringIO()
            with redirect_stdout(config_out):
                config_code = core_cli_main(
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
                        "--credential-env-var",
                        "OPENAI_API_KEY",
                        "--supports-model-discovery",
                        "true",
                    ]
                )

            list_out = io.StringIO()
            with redirect_stdout(list_out):
                list_code = core_cli_main(
                    [
                        "provider-list",
                        "--config-file",
                        str(config_file),
                    ]
                )

            config_exists = config_file.exists()

        self.assertEqual(config_code, 0)
        self.assertEqual(list_code, 0)
        config_payload = json.loads(config_out.getvalue())
        list_payload = json.loads(list_out.getvalue())
        self.assertTrue(config_payload["ok"])
        self.assertTrue(config_exists)
        openai_profile = next(
            item for item in list_payload["profiles"] if item["name"] == "openai_compatible"
        )
        self.assertEqual(openai_profile["endpoint_url"], "https://provider.example/v1")
        self.assertEqual(openai_profile["configured_model"], "gpt-4.1-mini")
        self.assertEqual(list_payload["config_path"], str(config_file))

    def test_cli_model_set_active_and_model_list_reflect_persisted_slots(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "runtime_provider_profiles.json"

            core_cli_main(
                [
                    "provider-config",
                    "--config-file",
                    str(config_file),
                    "--profile",
                    "azure_openai",
                    "--credential-env-var",
                    "AZURE_OPENAI_API_KEY",
                    "--configured-deployment",
                    "gpt-4.1-mini",
                ]
            )
            affective_out = io.StringIO()
            with redirect_stdout(affective_out):
                affective_code = core_cli_main(
                    [
                        "model-set-active",
                        "--config-file",
                        str(config_file),
                        "--slot",
                        "affective",
                        "--profile",
                        "azure_openai",
                    ]
                )
            core_cli_main(
                [
                    "model-set-active",
                    "--config-file",
                    str(config_file),
                    "--slot",
                    "rational",
                    "--profile",
                    "azure_openai",
                ]
            )
            model_list_out = io.StringIO()
            with redirect_stdout(model_list_out):
                model_list_code = core_cli_main(
                    [
                        "model-list",
                        "--config-file",
                        str(config_file),
                    ]
                )
            smoke_out = io.StringIO()
            with mock.patch.dict(
                "os.environ",
                {"AZURE_OPENAI_API_KEY": "secret"},
                clear=True,
            ):
                with redirect_stdout(smoke_out):
                    smoke_code = core_cli_main(
                        [
                            "model-profile-smoke",
                            "--config-file",
                            str(config_file),
                        ]
                    )

        self.assertEqual(affective_code, 0)
        self.assertEqual(model_list_code, 0)
        self.assertEqual(smoke_code, 0)
        affective_payload = json.loads(affective_out.getvalue())
        model_list_payload = json.loads(model_list_out.getvalue())
        smoke_payload = json.loads(smoke_out.getvalue())
        self.assertEqual(affective_payload["slot"], "affective")
        self.assertEqual(model_list_payload["active_affective_profile"], "azure_openai")
        self.assertEqual(model_list_payload["active_rational_profile"], "azure_openai")
        self.assertEqual(smoke_payload["status"], "ready")
        self.assertTrue(smoke_payload["evidence_summary"]["active_profiles_ready"])

    def test_build_provider_runtime_env_projects_configured_identifier_into_canonical_env(self) -> None:
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

            runtime_env = build_provider_runtime_env(
                env={"OPENAI_API_KEY": "secret"},
                config_path=str(config_file),
            )

        self.assertEqual(runtime_env["OPENAI_API_KEY"], "secret")
        self.assertEqual(runtime_env["OPENAI_BASE_URL"], "https://provider.example/v1")
        self.assertEqual(runtime_env["OPENAI_MODEL"], "gpt-4.1-mini")


if __name__ == "__main__":
    unittest.main()