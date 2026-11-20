// Drift checker for the 8 guide steps. src/steps.js is the single source of
// truth; this script fails the build whenever the step data embedded anywhere
// else drifts from it: the hero labels and stack readout in site/index.html,
// and the checkpoint list (HOPS) in site/public/game/index.html. It also
// fails if scene.js or main.js ever declare their own step arrays again
// instead of importing steps.js. Node built-ins only; no dependencies.
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const siteRoot = dirname(dirname(fileURLToPath(import.meta.url)));
const read = (...parts) => readFileSync(join(siteRoot, ...parts), "utf8");
const problems = [];
const expect = (ok, message) => { if (!ok) problems.push(message); };

// --- the source of truth ---
const { STEPS } = await import(pathToFileURL(join(siteRoot, "src", "steps.js")).href);
const stepAnchors = STEPS.map((s) => s.anchor);

// scene.js and main.js must derive their step data from steps.js.
for (const file of ["src/scene.js", "src/main.js"]) {
  expect(/import\s+[^;]*steps\.js/.test(read(file)),
    `site/${file}: no "steps.js" import - step arrays must come from src/steps.js, not be declared again`);
}

// --- site/index.html: the hero labels and the stack readout ---
const indexHtml = read("index.html");

// Hero labels: the .tag spans. The 8 step anchors must appear in guide
// order, and each tag's label must be the step's short.
const labelsStart = indexHtml.indexOf('<div id="labels"');
if (labelsStart < 0) problems.push('site/index.html: the hero labels block (<div id="labels">) was not found');
else {
  const labelsHtml = indexHtml.slice(labelsStart, indexHtml.indexOf("</div>", labelsStart));
  const stepTags = [...labelsHtml.matchAll(/<span class="tag[^"]*" data-anchor="([^"]+)">([^<]*)<\/span>/g)]
    .filter((m) => stepAnchors.includes(m[1]))
    .map((m) => ({ anchor: m[1], label: m[2] }));
  expect(stepTags.length === STEPS.length,
    `site/index.html: found ${stepTags.length} step data-anchor hero tags, but steps.js has ${STEPS.length} steps`);
  STEPS.forEach((step, i) => {
    const tag = stepTags[i];
    if (!tag) return;
    expect(tag.anchor === step.anchor,
      `site/index.html: hero data-anchor ${i + 1} is "${tag.anchor}", but steps.js step ${i + 1} anchors to "${step.anchor}"`);
    expect(tag.label === step.short,
      `site/index.html: hero label for anchor "${step.anchor}" is "${tag.label}", but steps.js short is "${step.short}"`);
  });
}

// Stack readout: one .stack-item per step, layers counted top-down (8..1),
// each .lname carrying the step's short.
const listStart = indexHtml.indexOf('<ol class="stack-list"');
if (listStart < 0) problems.push('site/index.html: the stack readout (<ol class="stack-list">) was not found');
else {
  const listHtml = indexHtml.slice(listStart, indexHtml.indexOf("</ol>", listStart));
  const stackItems = [...listHtml.matchAll(/<li class="stack-item" data-layer="(\d+)"><span class="lnum">\d+<\/span><span class="lname">([^<]*)<\/span>/g)]
    .map((m) => ({ layer: Number(m[1]), lname: m[2] }));
  expect(stackItems.length === STEPS.length,
    `site/index.html: stack-list has ${stackItems.length} layers, but steps.js has ${STEPS.length} steps`);
  const wantedLayers = STEPS.map((_, i) => STEPS.length - i).join(","); // 8,7,...,1: top of the stack first
  expect(stackItems.map((s) => s.layer).join(",") === wantedLayers,
    `site/index.html: stack-list data-layer order is [${stackItems.map((s) => s.layer).join(",")}], but steps.js guide order wants [${wantedLayers}]`);
  stackItems.forEach((item) => {
    const step = STEPS[item.layer - 1];
    if (!step) return;
    expect(item.lname === step.short,
      `site/index.html: stack-list lname for layer ${item.layer} is "${item.lname}", but steps.js short is "${step.short}"`);
  });
}

// --- site/public/game/index.html: the HOPS checkpoint list ---
const gameHtml = read("public", "game", "index.html");
const hopsStart = gameHtml.indexOf("var HOPS=");
const orderStart = gameHtml.indexOf("var ORDER=");
if (hopsStart < 0 || orderStart <= hopsStart) {
  problems.push('site/public/game/index.html: the HOPS block ("var HOPS=..." up to "var ORDER=") was not found');
} else {
  const hopsBlock = gameHtml.slice(hopsStart, orderStart);
  const hops = [...hopsBlock.matchAll(/\{\s*short:\s*'([^']*)'\s*,\s*step:\s*(\d+)\s*,/g)]
    .map((m) => ({ short: m[1], step: Number(m[2]) }));
  expect(hops.length === STEPS.length,
    `site/public/game/index.html: HOPS has ${hops.length} checkpoints, but steps.js has ${STEPS.length} steps`);
  // Steps 1 and 2 keep the game's own approved on-screen phrasings.
  const gameShorts = { 1: "Install Python, Git and Ollama", 2: "Choose a model (optional)" };
  hops.forEach((hop, i) => {
    const step = STEPS[i];
    if (!step) return;
    expect(hop.step === i + 1,
      `site/public/game/index.html: HOPS entry ${i + 1} is step ${hop.step}, but steps.js guide order wants step ${i + 1} there`);
    const wanted = gameShorts[i + 1] ?? step.name;
    expect(hop.short === wanted,
      `site/public/game/index.html: HOPS step ${hop.step} short is "${hop.short}", but expected "${wanted}"`);
  });
}

// --- verdict ---
if (problems.length) {
  console.error(`check-steps: ${problems.length} drift problem(s) with the guide steps:`);
  for (const problem of problems) console.error(`  - ${problem}`);
  process.exitCode = 1;
} else {
  console.log(`check-steps: the ${STEPS.length} guide steps match across src/steps.js, src/scene.js, src/main.js, site/index.html and the game HOPS.`);
}
