// Renders the repo's guide markdown into Pages-ready HTML, so the site always shows exactly what the markdown says.
// Reads README.md, ZERO_TO_CODING.md and docs/coding-apps.md from the repo root. A missing file fails the build.
// Writes site/docs/*.html (git-ignored). Vite then picks them up as extra inputs (see vite.config.js).
import { readFileSync, writeFileSync, mkdirSync, existsSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { Marked } from "marked";

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "../..");
const outDir = resolve(here, "../docs");
const REPO = "https://github.com/veeresh-bikkaneti/antigravity-local";

export const PAGES = [
  { src: "README.md", out: "index.html", title: "Full guide", blurb: "Everything in the README, rendered from the markdown at build time." },
  { src: "ZERO_TO_CODING.md", out: "zero-to-coding.html", title: "Zero to coding", blurb: "From nothing installed to your first real coding recipes." },
  { src: "docs/coding-apps.md", out: "coding-apps.html", title: "Connect your coding app", blurb: "VS Code, Continue, terminal agents, Antigravity, Gemini CLI and your own code." },
];

// Markdown file (as it appears in a link, without ./ or ../) -> the Pages page that replaces it.
const PAGE_OF = new Map([
  ["README.md", "index.html"],
  ["ZERO_TO_CODING.md", "zero-to-coding.html"],
  ["docs/coding-apps.md", "coding-apps.html"],
  ["coding-apps.md", "coding-apps.html"],
]);

const escapeHtml = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

// GitHub's heading slug: lowercase, drop punctuation, each space becomes a hyphen, repeats get -1, -2.
export function slugger() {
  const seen = new Map();
  return (text) => {
    const base = text.toLowerCase().replace(/<[^>]*>/g, "").replace(/&[a-z#0-9]+;/g, "")
      .replace(/[^\p{L}\p{N}\- _]/gu, "").replace(/ /g, "-");
    const n = seen.get(base) ?? 0;
    seen.set(base, n + 1);
    return n ? `${base}-${n}` : base;
  };
}

// Where a link in the markdown should go on the site.
export function rewriteHref(href) {
  if (!href || /^([a-z][a-z0-9+.-]*:|\/\/|#)/i.test(href)) return href; // absolute URL, mailto, same-page anchor
  const [path, hash] = href.replace(/^(\.\/)+/, "").split("#");
  const page = PAGE_OF.get(path);
  if (page) return page + (hash ? `#${hash}` : "");
  return `${REPO}/blob/main/${path}${hash ? `#${hash}` : ""}`; // code, wiki and other repo files stay on GitHub
}

function rewriteSrc(src) {
  if (!src || /^([a-z][a-z0-9+.-]*:|\/\/)/i.test(src)) return src;
  return `${REPO}/raw/main/${src.replace(/^(\.\/)+/, "")}`;
}

export function render(markdown) {
  const slug = slugger();
  const toc = [];
  const marked = new Marked({
    renderer: {
      heading({ tokens, depth }) {
        const inner = this.parser.parseInline(tokens);
        const id = slug(inner);
        if (depth === 2 || depth === 3) toc.push({ depth, id, text: inner.replace(/<[^>]*>/g, "") });
        return `<h${depth} id="${id}">${inner}</h${depth}>\n`;
      },
      link({ href, title, tokens }) {
        const t = title ? ` title="${escapeHtml(title)}"` : "";
        return `<a href="${escapeHtml(rewriteHref(href))}"${t}>${this.parser.parseInline(tokens)}</a>`;
      },
      image({ href, title, text }) {
        const t = title ? ` title="${escapeHtml(title)}"` : "";
        return `<img src="${escapeHtml(rewriteSrc(href))}" alt="${escapeHtml(text)}"${t} loading="lazy">`;
      },
      code({ text, lang }) {
        const cls = lang ? ` class="language-${escapeHtml(lang.split(/\s/)[0])}"` : "";
        const label = `Copy this ${lang ? escapeHtml(lang.split(/\s/)[0]) + " " : ""}code block`;
        return `<div class="code"><pre><code${cls}>${escapeHtml(text)}</code></pre><button class="copy" type="button" aria-label="${label}">Copy</button></div>\n`;
      },
      table(token) {
        const head = token.header.map((c, i) => this.tablecell(c)).join("");
        const rows = token.rows.map((r) => `<tr>${r.map((c) => this.tablecell(c)).join("")}</tr>`).join("\n");
        return `<div class="tablewrap" tabindex="0" role="region" aria-label="Table, scrolls sideways"><table><thead><tr>${head}</tr></thead><tbody>\n${rows}</tbody></table></div>\n`;
      },
      tablecell(token) {
        const tag = token.header ? "th" : "td";
        const align = token.align ? ` style="text-align:${token.align}"` : "";
        return `<${tag}${align}>${this.parser.parseInline(token.tokens)}</${tag}>`;
      },
    },
  });
  return { html: marked.parse(markdown), toc };
}

function nav(current) {
  const links = PAGES.map((p) => `<a href="${p.out}"${p.out === current ? ' aria-current="page"' : ""}>${p.title}</a>`).join("");
  return `<a href="../index.html">Home</a>${links}<a href="${REPO}">GitHub</a>`;
}

function template(page, { html, toc }) {
  const items = toc.map((t) => `<li class="d${t.depth}"><a href="#${t.id}">${t.text}</a></li>`).join("\n");
  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>${page.title} | Local Antigravity</title>
  <meta name="description" content="${escapeHtml(page.blurb)}">
  <meta name="color-scheme" content="dark light">
  <meta name="theme-color" content="#e4ddcf" media="(prefers-color-scheme: light)">
  <meta name="theme-color" content="#1d1d20" media="(prefers-color-scheme: dark)">
</head>
<body class="docs-page">
  <a class="skip" href="#doc">Skip to the guide</a>
  <header class="bar">
    <a class="mark" href="../index.html"><span class="seal" aria-hidden="true"></span>Local Antigravity</a>
    <nav aria-label="Guides">${nav(page.out)}</nav>
  </header>
  <main class="doc-wrap">
    <details class="toc" open>
      <summary>On this page</summary>
      <ol>
${items}
      </ol>
    </details>
    <article class="doc" id="doc">
${html}
    </article>
  </main>
  <footer class="doc-foot">
    <p>Source: <a href="${REPO}/blob/main/${page.src}">${page.src}</a> on GitHub. Edited on GitHub, rendered here at build.</p>
  </footer>
  <script type="module" src="../src/docs.js"></script>
</body>
</html>
`;
}

export function build() {
  mkdirSync(outDir, { recursive: true });
  for (const page of PAGES) {
    const file = resolve(root, page.src);
    if (!existsSync(file)) throw new Error(`${page.src} not found; run the build from the repo checkout`);
    writeFileSync(resolve(outDir, page.out), template(page, render(readFileSync(file, "utf8"))));
  }
  console.log(`docs: rendered ${PAGES.length} pages into site/docs`);
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) build();
