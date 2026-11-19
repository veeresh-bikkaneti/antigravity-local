"""The docs hub: README, Zero to coding and the coding-apps doc are rendered onto Pages at build time."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
HOME = (SITE / "index.html").read_text(encoding="utf-8")


class DocsHub(unittest.TestCase):
    def test_build_script_renders_the_three_guides_and_fails_loudly_when_one_is_missing(self):
        script = (SITE / "scripts" / "build-docs.mjs").read_text(encoding="utf-8")
        for src in ("README.md", "ZERO_TO_CODING.md", "docs/coding-apps.md"):
            self.assertIn(src, script)
            self.assertTrue((ROOT / src).is_file(), src)
        self.assertIn("throw new Error", script)

    def test_build_runs_the_docs_step_before_vite_and_vite_has_the_pages_as_inputs(self):
        pkg = (SITE / "package.json").read_text(encoding="utf-8")
        self.assertLess(pkg.index("build-docs.mjs", pkg.index('"build"')), pkg.index("vite build"))
        vite = (SITE / "vite.config.js").read_text(encoding="utf-8")
        for page in ("docs/index.html", "docs/zero-to-coding.html", "docs/coding-apps.html"):
            self.assertIn(page, vite)

    def test_pages_workflow_redeploys_when_a_guide_changes(self):
        wf = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")
        paths = re.findall(r"paths: \[(.*?)\]", wf)
        self.assertEqual(len(paths), 2)  # push and pull_request
        for p in paths:
            for needle in ("README.md", "ZERO_TO_CODING.md", "docs/*.md"):
                self.assertIn(needle, p)

    def test_home_page_has_no_readme_links_and_points_at_the_docs_hub(self):
        self.assertNotIn("antigravity-local#", HOME)
        self.assertNotIn("README", HOME)
        self.assertIn('href="docs/"', HOME)
        self.assertIn("docs/zero-to-coding.html", HOME)
        self.assertIn("docs/coding-apps.html", HOME)
        self.assertIn("docs/#common-gotchas--troubleshooting", HOME)
        self.assertIn("python run.py --agent claude", HOME)

    def test_game_page_links_the_pages_docs_not_github_markdown(self):
        game = (SITE / "public" / "game" / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("blob/main/docs/coding-apps.md", game)
        self.assertIn("../docs/coding-apps.html", game)

    def test_readme_points_at_the_website_version(self):
        self.assertIn("Read this guide on the website: https://veeresh-bikkaneti.github.io/antigravity-local/docs/",
                      (ROOT / "README.md").read_text(encoding="utf-8"))

    def test_generated_pages_are_not_committed(self):
        self.assertIn("/site/docs/", (ROOT / ".gitignore").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
