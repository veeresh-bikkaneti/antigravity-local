"""Phase 5a sanity: the pick use case emits text only through out()."""
import unittest

from agl.app import pick

GATE_CALLS = []


class _FakePorts:
    """Only what _pull_with_gate touches: the download plan, the gate's verdict, the run facts, the .env write."""

    def __init__(self):
        self._FACTS = {"source": "installed"}
        self.env_updates = []

    def _plan_download(self, tag, hw, res):
        return {"tag": "q:1", "quant": None, "size_gb": 2.0, "size_source": "catalog", "license": None,
                "gated": False, "free_disk_gb": 99.0, "disk_total_gb": 512.0}

    def update_env_model(self, tag):
        self.env_updates.append(tag)

    class pull_gate:
        """Records each ask_pull call, and the answer is always 'no': nothing is ever downloaded here."""

        @staticmethod
        def ask_pull(plan, interactive):
            GATE_CALLS.append((plan, interactive))
            return "no"


class PickUseCase(unittest.TestCase):
    """Every line the use case says reaches the caller only through the injected out()."""

    def test_pull_with_gate_says_no_through_out_only(self):
        """A refused pull says one line via out() and never writes the .env pick."""
        lines = []
        ports = _FakePorts()
        result = pick._pull_with_gate("q:1", False, {}, {}, ports=ports, out=lines.append)
        self.assertIsNone(result)
        self.assertEqual(lines, ["       Nothing downloaded."])
        self.assertEqual(ports.env_updates, [])  # update_env_model was not called
        self.assertEqual(len(GATE_CALLS), 1)
        self.assertEqual(GATE_CALLS[0][0]["tag"], "q:1")
        self.assertIs(GATE_CALLS[0][1], False)


if __name__ == "__main__":
    unittest.main()
