"""Static checks on the GitHub Pages front page: accessibility basics, links, and wiring.
These read the source files, so they run in CI without Node or a browser."""
import re
import subprocess
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
HTML = (SITE / "index.html").read_text(encoding="utf-8")
GAME = (SITE / "public" / "game" / "index.html").read_text(encoding="utf-8")


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

    def test_connect_your_coding_app_section_and_docs_link_exist(self):
        self.assertIn('id="connect-apps"', HTML)
        for app in ("VS Code", "Continue", "Terminal agents", "Antigravity", "Gemini CLI", "Your own code"):
            self.assertIn(f"<strong>{app}:</strong>", HTML, app)
        self.assertIn("docs/coding-apps.html", HTML)
        self.assertIn("built-in Ollama provider is deprecated", HTML)
        game = (SITE / "public" / "game" / "index.html").read_text(encoding="utf-8")
        self.assertIn("docs/coding-apps.html", game)
        self.assertTrue((SITE.parent / "docs" / "coding-apps.md").is_file())

    def test_coding_apps_are_taught_on_the_page_itself(self):
        self.assertIn('id="coding-apps"', HTML)
        self.assertIn('<a href="#coding-apps">Coding apps</a>', HTML)
        section = HTML[HTML.index('id="coding-apps"'):HTML.index('id="architecture"')]
        self.assertEqual(section.count("<details"), 6)
        for needle in ("Ollama.ollama", "apiBase: http://localhost:11434", "LiteLLM", "localhost:11434/v1"):
            self.assertIn(needle, section, needle)
        step4 = HTML[HTML.index('data-step="4"'):HTML.index('data-step="5"')]
        for agent in ("--agent pi", "--agent opencode", "--agent codex"):
            self.assertIn(agent, step4, agent)
        step8 = HTML[HTML.index('data-step="8"'):HTML.index('id="coding-apps"')]
        self.assertIn("Continue", step8)
        self.assertIn("Cline", step8)
        self.assertGreaterEqual(HTML.count("docs/zero-to-coding.html"), 2)  # v1.2.5: the guide is rendered on Pages, not linked on GitHub
        self.assertIn("litert-lm", HTML)
        game = (SITE / "public" / "game" / "index.html").read_text(encoding="utf-8")
        self.assertIn("#coding-apps", game)

    def test_game_checkpoints_are_the_eight_home_steps_in_order(self):
        home = []
        for n in range(1, 9):
            start = HTML.index(f'data-step="{n}"')
            home.append(re.search(r"<h3>(.*?)</h3>", HTML[start:]).group(1))
            self.assertIn(f'id="step-{n}"', HTML)
        game = (SITE / "public" / "game" / "index.html").read_text(encoding="utf-8")
        block = game[game.index("var HOPS=["):game.index("var ORDER=")]
        shorts = re.findall(r"\{short:'([^']*)'", block)
        self.assertEqual(shorts, home)
        self.assertEqual(re.findall(r"step:(\d)", block), [str(n) for n in range(1, 9)])
        self.assertNotIn("of 9", game)
        self.assertIn("../#step-", game)


WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
         "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12}


def latest_tag():
    try:
        out = subprocess.run(["git", "describe", "--tags", "--abbrev=0"], cwd=ROOT,
                             capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    return out.stdout.strip()


class TextOverDrawing(unittest.TestCase):
    css = (SITE / "src" / "styles.css").read_text(encoding="utf-8")
    js = (SITE / "src" / "main.js").read_text(encoding="utf-8")

    def test_text_sections_sit_on_a_solid_sheet(self):
        rule = re.search(r"([^{}]*)\{\s*background: var\(--sheet\)[^}]*\}", self.css[self.css.index("Text-heavy sections"):])
        for sel in (".guide", ".arch", ".faq"):  # .faq also covers #coding-apps
            self.assertIn(sel, rule.group(1))

    def test_stage_dims_for_every_text_section_but_is_never_hidden(self):
        for sel in ('".guide"', '"#coding-apps"', '"#architecture"'):
            self.assertIn("dimWhile(" + sel, self.js)
        self.assertRegex(self.css, r"body\.dim-stage #stage \{ opacity: 0\.[1-9]")

    def test_only_the_hero_slides_the_drawing_sideways(self):
        self.assertNotIn("slide(0.2)", self.js)  # the old guide slide
        for sel in ('dimWhile(".guide"', 'dimWhile("#coding-apps"', 'dimWhile("#architecture"'):
            line = next(l for l in self.js.splitlines() if sel in l)
            self.assertNotRegex(line, r"slide\(-?0\.[1-9]")
        hero = next(l for l in self.js.splitlines() if 'trigger: ".hero"' in l)
        self.assertIn("slide(-0.24)", hero)


class OrbitHint(unittest.TestCase):
    def test_hint_matches_the_pass_through_behaviour(self):
        css = (SITE / "src" / "styles.css").read_text(encoding="utf-8")
        scene = (SITE / "src" / "scene.js").read_text(encoding="utf-8")
        hint = re.search(r'class="stack-note">([^<]*)', HTML).group(1)
        self.assertIn("empty space", hint)
        self.assertRegex(css, r"main, footer \{ pointer-events: none; \}")  # wrappers let drags through
        self.assertIn("main :is(a, button, summary", css)  # things you can click keep their pointer events
        self.assertIn('canvas.addEventListener("pointerdown"', scene)  # the handler the hint promises
        self.assertIn("ctrlKey", scene)


class StepLinksToGuide(unittest.TestCase):
    DOCS = (SITE / "docs" / "index.html")

    def test_claude_in_the_terminal_agents_line_points_at_the_claude_card(self):
        self.assertIn('<a href="#agent-claude"><code>claude</code></a>', HTML)
        self.assertEqual(HTML.count('id="agent-claude"'), 1)

    def test_each_step_links_a_guide_section_that_exists_in_the_built_hub(self):
        for topic in ("manual-setup-optional-alternative", "common-gotchas--troubleshooting", "unicodeencodeerror",
                      "step-6-test-your-agent", "serve-it-search-ui", "advanced-using-custom-research-harnesses", "stop--clean-up-teardown"):
            self.assertRegex(HTML, r'docs/#[a-z0-9-]*' + topic, topic)
        if self.DOCS.is_file():  # built by `npm run docs`; CI builds it before this runs where it matters
            built = self.DOCS.read_text(encoding="utf-8")
            for slug in set(re.findall(r'docs/#([a-z0-9-]+)', HTML)):
                self.assertIn('id="%s"' % slug, built, slug)


class SiteFacts(unittest.TestCase):
    def home_steps(self):
        return len(re.findall(r'<li class="step"[^>]*\sdata-step="\d+"', HTML))

    def game_hops(self):
        body = GAME[GAME.index("var HOPS=["):]
        body = body[:body.index("\n];")]
        return len(re.findall(r"\bscene:'", body))

    def test_home_steps_equal_game_hops(self):
        self.assertGreater(self.home_steps(), 0)
        self.assertEqual(self.home_steps(), self.game_hops())

    def test_same_n_steps_sentence_names_the_real_count(self):
        found = re.findall(r"walks the same (\w+) steps", HTML)
        self.assertEqual(len(found), 1, "expected exactly one 'same N steps' sentence")
        self.assertIn(found[0], WORDS, "write the number as a word")
        self.assertEqual(WORDS[found[0]], self.home_steps())

    def test_no_other_step_count_word_disagrees_with_the_page(self):
        # "Eight steps, in order." style claims in the home page must match too.
        for word in re.findall(r"\b(" + "|".join(w.capitalize() for w in WORDS) + r") steps,", HTML):
            self.assertEqual(WORDS[word.lower()], self.home_steps(), word)

    def test_version_label_is_the_latest_git_tag_and_no_stale_1_0_0(self):
        tag = latest_tag()
        if not tag:
            self.skipTest("no git tags in this checkout (shallow clone?); fetch tags to run this check")
        version = tag.lstrip("v")
        labels = re.findall(r"Version (\d+\.\d+\.\d+)\.|Local Antigravity (\d+\.\d+\.\d+),|releases/tag/v(\d+\.\d+\.\d+)", HTML)
        flat = [v for row in labels for v in row if v]
        self.assertGreaterEqual(len(flat), 3, "version label, release link and footer should all be found")
        for v in flat:
            self.assertEqual(v, version)
        self.assertNotIn("1.0.0", HTML)


if __name__ == "__main__":
    unittest.main()
