"""Tests for agl.core.steps. Pure, no files."""

import unittest

from agl.core import checkpoint, steps

STEP_LIST = ["Read the parser", "Add the cap", "Write the tests", "Wire the menu", "Ship it"]


def _items(text, section):
    return [item for item in checkpoint.parse(text)[1][section] if item != "(none yet)"]


def _planned(base=None):
    base = checkpoint.render(checkpoint.TEMPLATE, "t") if base is None else base
    return steps.with_plan(base, STEP_LIST, "t")


class StepsTest(unittest.TestCase):
    def test_with_plan_lists_all_steps_in_order(self):
        text = _planned()
        self.assertEqual(steps.open_steps(text), STEP_LIST)
        self.assertEqual(steps.position(text), (1, 5))

    def test_goal_line_survives(self):
        text = _planned(checkpoint.render({"Plan": ["The goal: x"]}, "t"))
        for step in STEP_LIST[:3]:
            text = steps.mark_done(text, step, "t")
            self.assertIn("The goal: x", _items(text, "Plan"))

    def test_notes_line_survives_every_call(self):
        text = _planned(checkpoint.render({"Notes": ["User: keep it short"]}, "t"))
        self.assertIn("User: keep it short", _items(text, "Notes"))
        for step in STEP_LIST:
            text = steps.mark_done(text, step, "t")
            self.assertIn("User: keep it short", _items(text, "Notes"))

    def test_two_steps_done(self):
        text = steps.mark_done(_planned(), STEP_LIST[0], "t")
        text = steps.mark_done(text, STEP_LIST[1], "t")
        self.assertEqual(steps.position(text), (3, 5))
        self.assertEqual(steps.done_steps(text), STEP_LIST[:2])
        self.assertEqual(_items(text, "Next"), ["[ ] " + STEP_LIST[2]])

    def test_skipped_step_is_marked(self):
        text = steps.mark_done(_planned(), STEP_LIST[0], "t", skipped=True)
        self.assertIn("[x] (skipped) " + STEP_LIST[0], _items(text, "Done"))
        self.assertEqual(steps.done_steps(text), ["(skipped) " + STEP_LIST[0]])

    def test_all_done_clears_position_and_next(self):
        text = _planned()
        for step in STEP_LIST:
            text = steps.mark_done(text, step, "t")
        self.assertIsNone(steps.position(text))
        self.assertEqual(_items(text, "Next"), [])

    def test_step_prompt_fits_or_returns_none(self):
        text = _planned()
        prompt = steps.step_prompt(text, STEP_LIST[0], window=8192, system_tokens=665)
        self.assertIsNotNone(prompt)
        self.assertIn(STEP_LIST[0], prompt)
        self.assertIsNone(steps.step_prompt(text, STEP_LIST[0], window=1000, system_tokens=665))

    def test_string_results_fit_the_cap(self):
        text = _planned()
        results = [
            text,
            steps.mark_done(text, STEP_LIST[0], "t"),
            steps.mark_done(text, STEP_LIST[0], "t", skipped=True),
            steps.step_prompt(text, STEP_LIST[0], window=8192, system_tokens=665),
        ]
        for result in results:
            self.assertLessEqual(checkpoint.tokens(result), checkpoint.CAP_TOKENS)

    def test_trimmed_sample_line_is_not_counted(self):
        boxes = ["[ ] " + step for step in STEP_LIST]
        sections = dict(checkpoint.TEMPLATE, Plan=checkpoint.TEMPLATE["Plan"] + boxes, Next=boxes[:1], Notes=[""])
        pad = checkpoint.CAP_TOKENS * 4 + 20 - len(checkpoint.render(sections, "t"))
        full = checkpoint.render(dict(sections, Notes=["x" * pad]), "t")  # just over the cap, sample line included
        planned = steps.with_plan(full, STEP_LIST, "t")
        self.assertEqual(steps.position(planned), (1, 5))
        self.assertEqual(steps.position(steps.mark_done(full, STEP_LIST[0], "t")), (2, 5))

    def test_duplicate_steps_are_marked_one_at_a_time(self):
        text = steps.with_plan(checkpoint.render(checkpoint.TEMPLATE, "t"), ["Run tests", "Run tests"], "t")
        text = steps.mark_done(text, "Run tests", "t")
        self.assertEqual(steps.open_steps(text), ["Run tests"])
        self.assertEqual(steps.position(text), (2, 2))

    def test_unknown_or_repeat_mark_changes_nothing(self):
        text = _planned()
        before = (steps.position(text), steps.done_steps(text))
        unknown = steps.mark_done(text, "zzz", "t")
        self.assertEqual((steps.position(unknown), steps.done_steps(unknown)), before)
        once = steps.mark_done(text, STEP_LIST[0], "t")
        twice = steps.mark_done(once, STEP_LIST[0], "t")
        self.assertEqual((steps.position(twice), steps.done_steps(twice)), (steps.position(once), steps.done_steps(once)))
        self.assertEqual(steps.done_steps(twice), [STEP_LIST[0]])


if __name__ == "__main__":
    unittest.main()
