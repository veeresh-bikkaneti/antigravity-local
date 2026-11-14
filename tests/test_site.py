"""Static checks on the GitHub Pages front page: accessibility basics, links, and wiring.
These read the source files, so they run in CI without Node or a browser."""
import re
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
HTML = (SITE / "index.html").read_text(encoding="utf-8")


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids, self.hrefs, self.headings, self.iframes, self.buttons, self.canvases = [], [], [], [], [], []
        self.lang = self.viewport = None
        self.title = ""
        self.focus_values = []
        self.tab_sources = []
        self._tag = None
        self._text = []
        self._attrs = {}

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self._tag, self._attrs, self._text = tag, a, []
        if "id" in a:
            self.ids.append(a["id"])
        if tag == "html":
            self.lang = a.get("lang")
        if tag == "meta" and a.get("name") == "viewport":
            self.viewport = a.get("content")
        if tag == "a" and a.get("href"):
            self.hrefs.append(a["href"])
        if tag == "iframe":
            self.iframes.append(a)
        if tag == "canvas":
            self.canvases.append(a)
        if "data-focus" in a:
            self.focus_values.append(a["data-focus"])
        if a.get("role") == "tab":
            self.tab_sources.append(a.get("data-src"))

    def handle_data(self, data):
        self._text.append(data)

    def handle_endtag(self, tag):
        text = " ".join("".join(self._text).split())
        if tag == "title":
            self.title = text
        if tag in ("h1", "h2", "h3"):
            self.headings.append((int(tag[1]), text))
        if tag == "button":
            self.buttons.append((self._attrs, text))
        self._tag = None


page = Page()
page.feed(HTML)


class SitePage(unittest.TestCase):
    def test_basics(self):
        self.assertEqual(page.lang, "en")
        self.assertIn("width=device-width", page.viewport or "")
        self.assertTrue(page.title)

    def test_no_em_dashes_anywhere_in_site_source(self):
        for f in [SITE / "index.html", *(SITE / "src").glob("*")]:
            self.assertNotIn("—", f.read_text(encoding="utf-8"), f.name)

    def test_one_h1_and_no_skipped_heading_levels(self):
        levels = [lvl for lvl, _ in page.headings]
        self.assertEqual(levels.count(1), 1)
        for prev, cur in zip(levels, levels[1:]):
            self.assertLessEqual(cur - prev, 1, f"heading jumps from h{prev} to h{cur}")

    def test_ids_are_unique_and_fragment_links_resolve(self):
        self.assertEqual(len(page.ids), len(set(page.ids)))
        for href in page.hrefs:
            if href.startswith("#"):
                self.assertIn(href[1:], page.ids, href)

    def test_iframes_and_canvas_are_labelled_correctly(self):
        self.assertTrue(page.iframes)
        for f in page.iframes:
            self.assertTrue(f.get("title"), "iframe needs a title")
        for c in page.canvases:
            self.assertEqual(c.get("aria-hidden"), "true", "the decorative canvas must be hidden from assistive tech")

    def test_every_button_has_an_accessible_name(self):
        self.assertTrue(page.buttons)
        for attrs, text in page.buttons:
            self.assertTrue(text or attrs.get("aria-label"), attrs)

    def test_copy_buttons_say_what_they_copy(self):
        for attrs, _ in page.buttons:
            if "copy" in (attrs.get("class") or ""):
                self.assertTrue((attrs.get("aria-label") or "").startswith("Copy"), attrs)

    def test_skip_link_is_first_and_points_at_the_guide(self):
        self.assertIn('<a class="skip" href="#guide">', HTML)
        self.assertLess(HTML.index('class="skip"'), HTML.index("<header"))

    def test_motion_and_focus_rules_exist_in_css(self):
        css = (SITE / "src" / "styles.css").read_text(encoding="utf-8")
        self.assertIn("prefers-reduced-motion", css)
        self.assertIn(":focus-visible", css)
        self.assertIn("prefers-color-scheme: dark", css)  # light by default, dark variant follows the OS

    def test_every_step_focus_exists_in_the_scene(self):
        scene = (SITE / "src" / "scene.js").read_text(encoding="utf-8")
        for value in set(page.focus_values):
            self.assertRegex(scene, r'(^|\s)"?%s"?:\s*\{' % re.escape(value), value)

    def test_diagram_tabs_point_at_real_files(self):
        self.assertEqual(len(page.tab_sources), 4)
        for src in page.tab_sources:
            self.assertTrue((ROOT / "docs" / src.replace("diagrams/", "diagrams/")).exists(), src)

    def test_external_links_open_the_real_repo(self):
        self.assertIn("https://github.com/veeresh-bikkaneti/antigravity-local", HTML)

    def test_limits_stay_visible(self):
        self.assertIn("What it cannot do yet", HTML)
        self.assertIn("none of 14 attempts", HTML)

    def test_hero_has_a_flat_drawing_that_works_without_webgl(self):
        self.assertIn('class="hero-art" aria-hidden="true"', HTML)
        self.assertIn("<svg", HTML[HTML.index('class="hero-art"'):])
        main = (SITE / "src" / "main.js").read_text(encoding="utf-8")
        self.assertIn('classList.add("has-3d")', main)
        self.assertIn('classList.add("no-3d")', main)
        css = (SITE / "src" / "styles.css").read_text(encoding="utf-8")
        self.assertIn("html.no-3d .hero-controls", css)  # no dead buttons when the 3D scene cannot start

    def test_request_flow_lists_five_labelled_steps(self):
        flow = HTML[HTML.index('<ol class="flow"'):HTML.index("</ol>", HTML.index('<ol class="flow"'))]
        self.assertIn("aria-label=", flow.split(">", 1)[0])
        self.assertEqual(flow.count('class="flow-node'), 5)

    def test_new_motion_stops_for_reduced_motion_and_the_pause_button(self):
        css = (SITE / "src" / "styles.css").read_text(encoding="utf-8")
        for sel in (".ha-layer", ".flow-node::after", "[data-reveal]"):
            self.assertIn("html.motion-off", css[css.index("Visual polish"):])
            self.assertIn(sel, css[css.rindex("prefers-reduced-motion"):], sel)

    def test_stack_items_are_not_dimmed_with_opacity(self):
        css = (SITE / "src" / "styles.css").read_text(encoding="utf-8")
        rule = css[css.index(".stack-item {"):css.index("}", css.index(".stack-item {"))]
        self.assertNotIn("opacity: 0.45", rule)  # 0.45 opacity text fell below 4.5:1 contrast


if __name__ == "__main__":
    unittest.main()
