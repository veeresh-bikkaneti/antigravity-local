// Browser gate: serve site/dist, open the guide pages and #coding-apps at desktop and phone size,
// take screenshots, check that every link and summary can really be clicked (nothing sits on top
// of it) and that the console stays quiet. Run `npm run build` first, then `npm run gate`.
// Set GATE_CHANNEL=msedge (or chrome) to use a browser you already have instead of Playwright's own.
import { createServer } from "node:http";
import { readFile, mkdir } from "node:fs/promises";
import { existsSync } from "node:fs";
import { extname, join, resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const here = dirname(fileURLToPath(import.meta.url));
const dist = resolve(here, "../dist");
const shots = resolve(here, "../gate-shots"); // gitignored
if (!existsSync(join(dist, "index.html"))) throw new Error("site/dist is missing; run `npm run build` first");

const TYPES = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml",
  ".png": "image/png", ".woff2": "font/woff2", ".woff": "font/woff", ".json": "application/json", ".mp4": "video/mp4" };
const server = createServer(async (req, res) => {
  let p = decodeURIComponent(new URL(req.url, "http://x").pathname);
  if (p.endsWith("/")) p += "index.html";
  try {
    const file = resolve(dist, "." + p);
    if (!file.startsWith(dist)) throw new Error("outside dist");
    const body = await readFile(file); // read first, so a missing file is a clean 404
    res.writeHead(200, { "content-type": TYPES[extname(file)] || "application/octet-stream" });
    res.end(body);
  } catch { if (!res.headersSent) res.writeHead(404); res.end("not found"); }
});
await new Promise((ok) => server.listen(0, "127.0.0.1", ok));
const base = `http://127.0.0.1:${server.address().port}`;

const PAGES = [
  { name: "home-coding-apps", path: "/index.html#coding-apps", scope: "#coding-apps" },
  { name: "guide-hub", path: "/docs/index.html", scope: "body" },
  { name: "guide-zero-to-coding", path: "/docs/zero-to-coding.html", scope: "body" },
  { name: "guide-coding-apps", path: "/docs/coding-apps.html", scope: "body" },
];
const VIEWPORTS = [{ name: "desktop", width: 1440, height: 900 }, { name: "phone", width: 390, height: 844 }];

await mkdir(shots, { recursive: true });
const browser = await chromium.launch({ channel: process.env.GATE_CHANNEL || undefined });
const problems = [];

for (const vp of VIEWPORTS) {
  const ctx = await browser.newContext({ viewport: { width: vp.width, height: vp.height } });
  for (const pg of PAGES) {
    const page = await ctx.newPage();
    const tag = `${pg.name}@${vp.name}`;
    page.on("console", (m) => { if (m.type() === "error") problems.push(`${tag}: console error: ${m.text()}`); });
    page.on("pageerror", (e) => problems.push(`${tag}: page error: ${e.message}`));
    page.on("response", (r) => { if (r.status() >= 400) problems.push(`${tag}: HTTP ${r.status()} ${r.url()}`); });
    await page.goto(base + pg.path, { waitUntil: "networkidle" });
    await page.evaluate(() => document.querySelectorAll("details").forEach((d) => (d.open = true)));
    await page.screenshot({ path: join(shots, `${tag}.png`), fullPage: true });

    const targets = await page.locator(`${pg.scope} :is(a[href], summary)`).elementHandles();
    let checked = 0;
    for (const el of targets) {
      const label = await el.evaluate((n) => `${n.tagName.toLowerCase()} "${(n.textContent || "").trim().slice(0, 40)}" ${n.getAttribute("href") || ""}`);
      const visible = await el.evaluate((n) => { const r = n.getBoundingClientRect(); const s = getComputedStyle(n); return r.width > 0 && r.height > 0 && s.visibility !== "hidden" && s.display !== "none" && !n.classList.contains("skip"); });
      if (!visible) continue; // skip-links and the like; hidden things cannot be covered
      await el.evaluate((n) => n.scrollIntoView({ block: "center", inline: "nearest", behavior: "instant" }));
      await page.evaluate(() => new Promise((ok) => requestAnimationFrame(() => requestAnimationFrame(ok)))); // let content-visibility sections lay out
      const ok = await el.evaluate((n) => {
        const r = n.getBoundingClientRect();
        // Test the middle of the first line box, which is where a person clicks.
        const rect = n.getClientRects()[0] || r;
        const hit = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2);
        return !!hit && (hit === n || n.contains(hit));
      });
      checked++;
      if (!ok) problems.push(`${tag}: something covers ${label}`);
    }
    if (checked === 0) problems.push(`${tag}: found no clickable links or summaries; the selector or page is wrong`);
    console.log(`${tag}: ${checked} links/summaries checked`);
    await page.close();
  }
  await ctx.close();
}
await browser.close();
server.close();

if (problems.length) { console.error(`\nBrowser gate FAILED (${problems.length}):\n- ` + problems.join("\n- ")); process.exit(1); }
console.log(`\nBrowser gate passed. Screenshots in ${shots}`);
