import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock


THIS_DIR = Path(__file__).resolve().parent
NEURO_CLI_DIR = THIS_DIR.parent
ROOT = NEURO_CLI_DIR.parent
WRAPPER_PATH = NEURO_CLI_DIR / "scripts" / "invoke_neuro_cli.py"
SKILL_PATH = ROOT / ".github" / "skills" / "neuro-cli" / "SKILL.md"


def load_wrapper():
    spec = importlib.util.spec_from_file_location("invoke_neuro_cli", WRAPPER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class TestInvokeNeuroCliWrapper(unittest.TestCase):
    def test_adds_json_output_and_common_metadata_before_cli_args(self) -> None:
        wrapper = load_wrapper()
        completed = subprocess.CompletedProcess(
            args=[], returncode=0, stdout='{"ok": true, "status": "ready"}', stderr=""
        )

        with mock.patch.object(sys, "argv", ["invoke_neuro_cli.py", "system", "init"]), \
            mock.patch.object(subprocess, "run", return_value=completed) as run:
            out = io.StringIO()
            with redirect_stdout(out):
                code = wrapper.main()

        self.assertEqual(code, 0)
        cmd = run.call_args.args[0]
        self.assertIn("--output", cmd)
        self.assertIn("json", cmd)
        self.assertLess(cmd.index("--output"), cmd.index("system"))
        payload = json.loads(out.getvalue())
        self.assertTrue(payload["ok"])

    def test_payload_status_error_fails_even_with_zero_process_exit(self) -> None:
        wrapper = load_wrapper()
        completed = subprocess.CompletedProcess(
            args=[], returncode=0, stdout='{"ok": false, "status": "error"}', stderr=""
        )

        with mock.patch.object(sys, "argv", ["invoke_neuro_cli.py", "query", "device"]), \
            mock.patch.object(subprocess, "run", return_value=completed):
            err = io.StringIO()
            with redirect_stdout(io.StringIO()), redirect_stderr(err):
                code = wrapper.main()

        self.assertEqual(code, wrapper.EXIT_COMMAND_FAILED)
        self.assertIn("error", err.getvalue())

    def test_not_implemented_maps_to_skill_capability_gap_exit(self) -> None:
        wrapper = load_wrapper()
        completed = subprocess.CompletedProcess(
            args=[], returncode=0, stdout='{"ok": false, "status": "not_implemented"}', stderr=""
        )

        with mock.patch.object(sys, "argv", ["invoke_neuro_cli.py", "gateway"]), \
            mock.patch.object(subprocess, "run", return_value=completed):
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                code = wrapper.main()

        self.assertEqual(code, wrapper.EXIT_NOT_IMPLEMENTED)

    def test_invalid_json_stdout_becomes_machine_readable_failure(self) -> None:
        wrapper = load_wrapper()
        completed = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="not json", stderr=""
        )

        with mock.patch.object(sys, "argv", ["invoke_neuro_cli.py", "system", "init"]), \
            mock.patch.object(subprocess, "run", return_value=completed):
            out = io.StringIO()
            with redirect_stdout(out), redirect_stderr(io.StringIO()):
                code = wrapper.main()

        self.assertEqual(code, wrapper.EXIT_COMMAND_FAILED)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["status"], "invalid_json_stdout")


class TestProjectSharedNeuroCliSkill(unittest.TestCase):
    def test_skill_frontmatter_and_resources_are_discoverable(self) -> None:
        text = SKILL_PATH.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\n"))
        frontmatter = text.split("---", 2)[1]
        self.assertIn("name: neuro-cli", frontmatter)
        self.assertIn("description:", frontmatter)
        self.assertIn("Zephyr", frontmatter)
        self.assertIn("callback", frontmatter)
        self.assertTrue((SKILL_PATH.parent / "references" / "workflows.md").is_file())
        self.assertTrue((SKILL_PATH.parent / "assets" / "callback_handler.py").is_file())
        self.assertTrue((SKILL_PATH.parent / "assets" / "neuro_unit_app_template.c").is_file())


if __name__ == "__main__":
    unittest.main()