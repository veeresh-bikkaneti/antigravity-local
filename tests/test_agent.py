"""Tests for agl/app/agent.py (Phase 5b)."""
import unittest

import agl.app.agent


class AntigravityExecutionError(Exception):
    pass


class OtherError(Exception):
    pass


class TestAgent(unittest.TestCase):
    def test_is_harness_error_with_antigravity_execution_error(self):
        exc = AntigravityExecutionError("harness failed")
        self.assertTrue(agl.app.agent._is_harness_error(exc))

    def test_is_harness_error_with_other_error(self):
        exc = OtherError("generic failure")
        self.assertFalse(agl.app.agent._is_harness_error(exc))

    def test_run_shell_uses_custom_input_fn(self):
        import asyncio
        from unittest import mock

        class FakeAgent:
            def __init__(self, config):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        class FakeConfig:
            model = "test-model"

        pkg = mock.Mock()
        pkg.Agent = FakeAgent

        leave = {"left": False}
        inputs = ["exit"]
        out = mock.Mock()
        ports = mock.Mock()

        with mock.patch.dict("sys.modules", {"google.antigravity": pkg}):
            asyncio.run(
                agl.app.agent._run_shell(
                    "test-model",
                    FakeConfig(),
                    leave,
                    ports=ports,
                    out=out,
                    input_fn=lambda prompt: inputs.pop(0),
                )
            )
        self.assertTrue(leave["left"])


if __name__ == "__main__":
    unittest.main()
