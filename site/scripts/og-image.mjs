// Builds public/og.png (the link-preview card) with Satori and resvg. Runs before every build.
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import satori from "satori";
import { Resvg } from "@resvg/resvg-js";

const here = dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
const filesOf = (pkg) => join(dirname(require.resolve(`${pkg}/package.json`)), "files");
const body = (w) => readFileSync(join(filesOf("@fontsource/atkinson-hyperlegible-next"), `atkinson-hyperlegible-next-latin-${w}-normal.woff`));
const serif = readFileSync(join(filesOf("@fontsource/shippori-mincho"), "shippori-mincho-latin-500-normal.woff"));

const SAND = "#e4ddcf", CHARCOAL = "#26262a", SOFT = "#5a564d", MAPLE = "#a8281e";
const el = (type, style, children) => ({ type, props: { style: { display: "flex", ...style }, children } });

const card = el("div", { width: 1200, height: 630, background: SAND, position: "relative", padding: 80, flexDirection: "column", justifyContent: "space-between", fontFamily: "Atkinson" }, [
  el("div", { alignItems: "center", gap: 16, color: CHARCOAL, fontSize: 30, fontFamily: "Shippori" }, [
    el("div", { width: 18, height: 18, background: MAPLE }, ""),
    "Local Antigravity",
  ]),
  el("div", { flexDirection: "column", gap: 28 }, [
    el("div", { color: CHARCOAL, fontSize: 88, lineHeight: 1.1, maxWidth: 900, fontFamily: "Shippori" }, "Your coding agent, on your own machine"),
    el("div", { color: SOFT, fontSize: 32, lineHeight: 1.4, maxWidth: 780 }, "Runs the Google Antigravity SDK on a local model with Ollama. One command to set up."),
  ]),
  el("div", { color: MAPLE, fontSize: 26, fontWeight: 700 }, "veeresh-bikkaneti.github.io/antigravity-local"),
  // the machine boundary: a thin box, with one small maple square inside it
  el("div", { position: "absolute", right: 80, top: 100, width: 240, height: 160, border: `2px solid ${CHARCOAL}`, opacity: 0.5 }, ""),
  el("div", { position: "absolute", right: 128, top: 142, width: 56, height: 56, border: `3px solid ${MAPLE}` }, ""),
]);

const svg = await satori(card, {
  width: 1200,
  height: 630,
  fonts: [
    { name: "Atkinson", data: body(400), weight: 400, style: "normal" },
    { name: "Atkinson", data: body(700), weight: 700, style: "normal" },
    { name: "Shippori", data: serif, weight: 400, style: "normal" },
  ],
});
const png = new Resvg(svg, { fitTo: { mode: "width", value: 1200 } }).render().asPng();
const out = resolve(here, "../public");
mkdirSync(out, { recursive: true });
writeFileSync(join(out, "og.png"), png);
console.log(`og.png written (${png.length} bytes)`);
