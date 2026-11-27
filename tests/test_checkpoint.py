"""Tests for agl.core.checkpoint: the template, pointer block, cap and .gitignore rule. Pure, no files touched."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agl.core import checkpoint as ck  # noqa: E402

NOW = "2026-11-27T10:00:00+00:00"


class CheckpointCoreTests(unittest.TestCase):
    def test_template_matches_the_approved_mockup(self):
        expected = "\n".join([
            "# Checkpoint", "", ck.MARKER, f"updated: {NOW}", "",
            "## Plan", "", "- The goal in one or two lines, in the user's own words.",
            "- The steps, in order, as short checkboxes.", "",
            "## Done", "", "- [x] Step that is finished, with the commit or file that proves it.", "",
            "## Next", "", "- [ ] The one step to start with when the app wakes up.", "",
            "## Files", "", "- `path/to/file.py`: what changed and why, in one line.", "",
            "## Notes", "", "- Open questions for the user.", "- Gotchas the next session must not repeat.", "",
        ])
        self.assertEqual(ck.render(ck.TEMPLATE, NOW), expected)

    def test_pointer_block_matches_the_approved_mockup(self):
        expected = "\n".join([
            "<!-- agl-checkpoint:begin -->",
            "Before you start, read `.agl/checkpoint.md`. It holds the plan, what is done, and what is next.",
            "Before you stop, update it: plan, done, next, files, notes, and the `updated:` line.",
            "Keep it under about 1,500 tokens. If `HANDOFF.md` exists, read it too for extra context.",
            "Do not merge HANDOFF.md into the checkpoint and do not rename it.",
            "<!-- agl-checkpoint:end -->",
        ])
        self.assertEqual(ck.POINTER, expected)

    def test_parse_reads_back_what_render_wrote(self):
        updated, sections = ck.parse(ck.render(ck.TEMPLATE, NOW))
        self.assertEqual(updated, NOW)
        self.assertEqual(sections["Next"], ["[ ] The one step to start with when the app wakes up."])

    def test_merge_pointer_adds_once_and_keeps_user_lines(self):
        first = ck.merge_pointer("# My rules\n")
        self.assertTrue(first.startswith("# My rules\n\n" + ck.POINTER))
        self.assertEqual(ck.merge_pointer(first), first)
        edited = first.replace("# My rules", "# My rules (edited)")
        self.assertEqual(ck.merge_pointer(edited), edited)

    def test_one_marker_is_refused(self):
        with self.assertRaises(ck.PointerError):
            ck.merge_pointer(ck.BEGIN + "\nno end marker here\n")

    def test_oversize_done_list_is_capped_and_next_is_kept(self):
        sections = {
            "Plan": ["Ship C3."],
            "Done": [f"Step {i} " + "x" * 200 for i in range(500)],
            "Next": ["Write the tests."],
        }
        text = ck.capped(sections, NOW)
        self.assertLessEqual(ck.tokens(text), ck.CAP_TOKENS)
        self.assertIn("- Write the tests.", text)
        self.assertIn("earlier steps trimmed", text)
        self.assertIn("- Step 499 ", text)
        self.assertEqual(ck.next_text(text, NOW), text)

    def test_with_ignore_adds_agl_once(self):
        once = ck.with_ignore("node_modules/")
        self.assertEqual(once, "node_modules/\n.agl/\n")
        self.assertEqual(ck.with_ignore(once), once)
        self.assertEqual(ck.with_ignore("/.agl\n"), "/.agl\n")


if __name__ == "__main__":
    unittest.main()
