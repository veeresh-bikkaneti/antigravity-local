// The drawing behind the page: a hologram workbench. You stand at your desk —
// monitor with code, keyboard, mug, PC tower — and pull each part of the setup
// out of that workspace, blown up into a big vertical stack that grows upward
// as the guide scrolls: Ollama, the model, the repo launcher, the terminal,
// the agent, the gated job, the editor. The cloud sits outside, dashed,
// and never connects. Each guide step lands one layer on top of the stack
// and lights it; scrolling back unwinds it. Drag orbits, Ctrl+scroll zooms.
import * as THREE from "three";
import { gsap } from "gsap";

// Guide order: focus key, step name, short label, nameplate, source in the workspace.
const STEPS = [
  { key: "ollama", name: "Install Ollama", short: "Ollama", plate: "OLLAMA" },
  { key: "model", name: "Choose a model", short: "Qwen model", plate: "QWEN2.5-CODER:14B" },
  { key: "repo", name: "Clone the repo and run setup", short: "Repo · run.bat", plate: "REPO · RUN.BAT" },
  { key: "venv", name: "Activate the virtual environment", short: ".venv terminal", plate: ".VENV · TERMINAL" },
  { key: "agent", name: "Chat with your agent", short: "Agent", plate: "ANTIGRAVITY AGENT" },
  { key: "job", name: "Give it one job", short: "One job · Gate", plate: "HARNESS · POLICY GATE" },
  { key: "editor", name: "Use it from your editor or the browser", short: "Editor", plate: "EDITOR </>" },
];
const STEP_KEYS = STEPS.map((s) => s.key);

const FLOOR = -1.5;
const CORE = new THREE.Vector3(0.75, -1.15, -0.2); // base of the vertical stack
const LAYER_H = 0.6;
const slot = (i) => new THREE.Vector3(CORE.x, CORE.y + i * LAYER_H, CORE.z);
const HAND = new THREE.Vector3(-0.85, -0.05, 0.8); // his presenting hand: the flight path bends through it
// Where each piece is pulled from in his workspace.
const SOURCES = [
  new THREE.Vector3(-2.5, 0.15, -0.7),   // monitor — Ollama
  new THREE.Vector3(-2.5, 0.3, -0.6),    // monitor download — the model
  new THREE.Vector3(-1.6, -0.3, -0.55),  // files folder on the desk — the repo
  new THREE.Vector3(-2.0, -0.3, 0.1),    // keyboard — the terminal
  new THREE.Vector3(-2.5, 0.2, -0.6),    // monitor — the agent
  new THREE.Vector3(-1.05, -0.2, 0.7),   // through his hand — the job
  new THREE.Vector3(-2.5, 0.25, -0.65),  // monitor code — the editor
];
const PERSON_POS = new THREE.Vector3(-1.35, FLOOR, 0.95);
const CLOUD_POS = new THREE.Vector3(2.7, 2.9, -1.7);
const DESK_POS = new THREE.Vector3(-1.6, -0.3, -0.55); // tag anchor: the files on the desk

// Camera position, look-at target, pieces shown, and which tags glow, per focus.
const FOCUS = {
  overview: { cam: [8.2, 3.4, 9.4], look: [-0.5, 0.1, -0.1], count: 0, on: [] },
  person: { cam: [2.4, 0.9, 6.8], look: [-1.35, -0.7, 0.9], count: 0, on: ["person"] },
  pillars: { cam: [6.8, 3.4, 8.6], look: [1.4, 1.8, -0.9], count: 0, on: ["cloud"] },
  ollama: { cam: [3.4, -0.2, 4.6], look: [0.75, -1.0, -0.2], count: 1, on: ["ollama"] },
  model: { cam: [3.2, 0.3, 4.4], look: [0.75, -0.5, -0.2], count: 2, on: ["model"] },
  repo: { cam: [3.2, 0.8, 4.4], look: [0.75, 0.1, -0.2], count: 3, on: ["repo"] },
  venv: { cam: [3.2, 1.3, 4.4], look: [0.75, 0.7, -0.2], count: 4, on: ["venv"] },
  agent: { cam: [3.2, 1.8, 4.4], look: [0.75, 1.3, -0.2], count: 5, on: ["agent"] },
  job: { cam: [3.2, 2.3, 4.4], look: [0.75, 1.9, -0.2], count: 6, on: ["job"] },
  editor: { cam: [3.4, 2.9, 4.6], look: [0.75, 2.5, -0.2], count: 7, on: ["editor"] },
  assembly: { cam: [7.6, 3.8, 9.6], look: [0.4, 0.6, -0.2], count: 7, on: [] },
  cloud: { cam: [6.4, 3.6, 8.2], look: [1.6, 1.6, -0.8], count: 7, on: ["cloud"] },
  showcase: { cam: [8.6, 4.2, 9.8], look: [0.4, 0.6, -0.2], count: 7, on: [] },
};

const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

export function start({ canvas, tags, isPaused, onStack }) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: "low-power" });
  renderer.setClearColor(0x000000, 0);
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(36, 1, 0.1, 80);
  const view = { ox: -0.24 };
  let needsRender = true;
  let width = 1, height = 1;

  const colors = { line: new THREE.Color(), signal: new THREE.Color(), flag: new THREE.Color() };
  const readColors = () => {
    colors.line.set(cssVar("--line"));
    colors.signal.set(cssVar("--signal"));
    colors.flag.set(cssVar("--flag"));
    needsRender = true;
  };
  readColors();

  const world = new THREE.Group();
  scene.add(world);

  // --- themed materials: linework follows the site's CSS vars, light and dark.
  const lineMats = [], signalMats = [], flagMats = [];
  const reg = (list, mat, base) => { mat.userData.base = base ?? mat.opacity; list.push(mat); return mat; };
  const wire = (geo, opacity = 0.9) => new THREE.LineSegments(new THREE.EdgesGeometry(geo), reg(lineMats, new THREE.LineBasicMaterial({ transparent: true, opacity }), opacity));
  const fill = (geo, opacity = 0.16) => new THREE.Mesh(geo, reg(lineMats, new THREE.MeshBasicMaterial({ transparent: true, opacity, depthWrite: false }), opacity));
  const fillSignal = (geo, opacity = 0.85) => new THREE.Mesh(geo, reg(signalMats, new THREE.MeshBasicMaterial({ transparent: true, opacity, depthWrite: false }), opacity));
  const at = (obj, x, y, z) => { obj.position.set(x, y, z); return obj; };

  // --- code on a screen: dark terminal, bars of code in the site's colours.
  function codeTexture(lines) {
    const c = document.createElement("canvas");
    c.width = 512; c.height = 320;
    const x = c.getContext("2d");
    x.fillStyle = "#101820"; x.fillRect(0, 0, 512, 320);
    x.fillStyle = "rgba(255,255,255,.08)"; x.fillRect(0, 0, 512, 26);
    ["#ff5f57", "#febc2e", "#28c840"].forEach((col, i) => { x.fillStyle = col; x.beginPath(); x.arc(16 + i * 20, 13, 5, 0, 7); x.fill(); });
    const cols = ["#ee6a5c", "#e4ddcf", "#a8281e", "#d9d2c2", "#ee6a5c", "#b4ad9c"];
    lines.forEach((n, i) => {
      const y = 44 + i * 24;
      x.fillStyle = cols[i % cols.length];
      const len = 40 + ((i * 67 + n * 31) % 150);
      x.fillRect(14 + (i % 3) * 16, y, len, 9);
      if (i % 2) { x.fillStyle = cols[(i + 2) % cols.length]; x.fillRect(30 + len, y, 50, 9); }
    });
    return new THREE.CanvasTexture(c);
  }

  // --- nameplate: the piece's name on its front, so stacked layers never
  // cover each other's names. Redrawn when the colour scheme changes.
  const plates = [];
  function drawPlate(cv, text) {
    const x = cv.getContext("2d");
    x.clearRect(0, 0, cv.width, cv.height);
    x.fillStyle = cssVar("--panel") || "rgba(236,230,216,0.92)";
    x.strokeStyle = cssVar("--signal") || "#a8281e";
    x.lineWidth = 4;
    const r = 26;
    x.beginPath();
    x.roundRect(6, 14, cv.width - 12, cv.height - 28, r);
    x.fill(); x.stroke();
    x.font = "700 52px 'Atkinson Hyperlegible Next', system-ui, sans-serif";
    x.textAlign = "center"; x.textBaseline = "middle";
    x.fillStyle = cssVar("--signal") || "#a8281e";
    x.fillText(text, cv.width / 2, cv.height / 2 + 2);
  }
  function makePlate(text) {
    const cv = document.createElement("canvas");
    cv.width = 1024; cv.height = 112;
    drawPlate(cv, text);
    const tex = new THREE.CanvasTexture(cv);
    const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true, depthWrite: false }));
    sp.scale.set(1.7, 0.19, 1);
    sp.position.set(0, -0.44, 0.48);
    plates.push({ cv, text, tex });
    return sp;
  }
  function redrawPlates() { for (const p of plates) { drawPlate(p.cv, p.text); p.tex.needsUpdate = true; } }
  matchMedia("(prefers-color-scheme: light)").addEventListener("change", () => { readColors(); redrawPlates(); applyAll(); });

  // --- floor + the bench the stack grows on
  const floor = new THREE.GridHelper(11, 11, 0xffffff, 0xffffff);
  floor.position.y = FLOOR;
  floor.material.transparent = true;
  floor.material.opacity = 0.22;
  world.add(floor);
  const benchDisc = at(fill(new THREE.CylinderGeometry(1.5, 1.5, 0.08, 48), 0.08), CORE.x, FLOOR + 0.06, CORE.z);
  const benchEdge = at(wire(new THREE.CylinderGeometry(1.5, 1.5, 0.08, 48), 0.5), CORE.x, FLOOR + 0.06, CORE.z);
  world.add(benchDisc, benchEdge);
  const pedestal = at(fillSignal(new THREE.CylinderGeometry(0.95, 1.05, 0.12, 36), 0.18), CORE.x, FLOOR + 0.16, CORE.z);
  world.add(pedestal);
  const guidePts = [new THREE.Vector3(CORE.x, FLOOR + 0.4, CORE.z - 0.95), new THREE.Vector3(CORE.x, CORE.y + 6 * LAYER_H + 0.55, CORE.z - 0.95)];
  const guideLine = new THREE.Line(new THREE.BufferGeometry().setFromPoints(guidePts), reg(lineMats, new THREE.LineDashedMaterial({ dashSize: 0.14, gapSize: 0.1, transparent: true, opacity: 0.6 }), 0.6));
  guideLine.computeLineDistances();
  world.add(guideLine);

  // --- the developer workspace: desk, monitor with code, keyboard, mug, PC tower
  const workspace = new THREE.Group();
  world.add(workspace);
  const deskTop = at(fill(new THREE.BoxGeometry(2.6, 0.08, 1.2), 0.12), -2.3, -0.5, -0.6);
  const deskEdge = at(wire(new THREE.BoxGeometry(2.6, 0.08, 1.2), 0.7), -2.3, -0.5, -0.6);
  workspace.add(deskTop, deskEdge);
  for (const [lx, lz] of [[-3.5, -1.1], [-3.5, -0.1], [-1.1, -1.1], [-1.1, -0.1]]) {
    workspace.add(at(wire(new THREE.BoxGeometry(0.08, 1.0, 0.08), 0.7), lx, -1.0, lz));
  }
  // monitor: stand, frame, and a screen full of code
  const monitor = new THREE.Group();
  monitor.position.set(-2.5, -0.46, -0.85);
  monitor.rotation.y = 0.35;
  workspace.add(monitor);
  monitor.add(at(wire(new THREE.BoxGeometry(0.34, 0.3, 0.06), 0.8), 0, 0.15, -0.05));
  monitor.add(at(fill(new THREE.BoxGeometry(1.42, 0.92, 0.06), 0.2), 0, 0.78, 0));
  monitor.add(at(wire(new THREE.BoxGeometry(1.42, 0.92, 0.06), 0.9), 0, 0.78, 0));
  const screen = new THREE.Mesh(new THREE.PlaneGeometry(1.3, 0.8), new THREE.MeshBasicMaterial({ map: codeTexture([3, 5, 2, 6, 4, 3, 5, 2, 4, 6, 3]) }));
  screen.position.set(0, 0.78, 0.035);
  monitor.add(screen);
  // keyboard: base plus a grid of real keys, in front of the monitor
  const keyboard = new THREE.Group();
  keyboard.position.set(-2.0, -0.44, 0.05);
  keyboard.rotation.y = 0.3;
  keyboard.rotation.x = -0.06;
  workspace.add(keyboard);
  keyboard.add(at(fill(new THREE.BoxGeometry(0.98, 0.05, 0.36), 0.2), 0, 0, 0));
  keyboard.add(at(wire(new THREE.BoxGeometry(0.98, 0.05, 0.36), 0.8), 0, 0, 0));
  for (let kr = 0; kr < 3; kr++) for (let kc = 0; kc < 11; kc++) {
    keyboard.add(at(wire(new THREE.BoxGeometry(0.07, 0.03, 0.07), 0.6), -0.42 + kc * 0.084, 0.035, -0.11 + kr * 0.1));
  }
  keyboard.add(at(wire(new THREE.BoxGeometry(0.4, 0.03, 0.07), 0.6), 0, 0.035, 0.12));
  // mouse, mug, a folder of files, PC tower with a glowing strip
  const mouse = at(fill(new THREE.SphereGeometry(0.075, 12, 10), 0.25), -1.45, -0.44, 0.1);
  mouse.scale.set(1, 0.55, 1.35);
  workspace.add(mouse);
  const mug = at(fillSignal(new THREE.CylinderGeometry(0.07, 0.06, 0.14, 14), 0.85), -3.15, -0.39, -0.15);
  workspace.add(mug);
  const folder = at(fill(new THREE.BoxGeometry(0.46, 0.05, 0.34), 0.25), -1.6, -0.44, -0.55);
  folder.rotation.y = -0.3;
  workspace.add(folder, at(wire(new THREE.BoxGeometry(0.46, 0.05, 0.34), 0.8), -1.6, -0.44, -0.55));
  const tower = new THREE.Group();
  tower.position.set(-3.35, -1.04, -0.7);
  workspace.add(tower);
  tower.add(at(fill(new THREE.BoxGeometry(0.42, 0.92, 0.85), 0.2), 0, 0, 0));
  tower.add(at(wire(new THREE.BoxGeometry(0.42, 0.92, 0.85), 0.9), 0, 0, 0));
  tower.add(at(fillSignal(new THREE.BoxGeometry(0.03, 0.8, 0.06), 0.9), 0.22, 0, 0.18));

  // --- the cloud: dashed and disconnected on purpose
  const cloud = new THREE.Group();
  cloud.position.copy(CLOUD_POS);
  world.add(cloud);
  const cloudPts = [];
  for (let a = 0; a <= 64; a++) { const t = (a / 64) * Math.PI * 2; cloudPts.push(new THREE.Vector3(Math.cos(t) * 0.62, Math.sin(t) * 0.42, 0)); }
  const cloudRing = new THREE.Line(new THREE.BufferGeometry().setFromPoints(cloudPts), reg(flagMats, new THREE.LineDashedMaterial({ dashSize: 0.12, gapSize: 0.09, transparent: true, opacity: 0.85 }), 0.85));
  cloudRing.computeLineDistances();
  cloud.add(cloudRing);
  cloud.add(at(wire(new THREE.SphereGeometry(0.3, 10, 8), 0.35), 0, 0, 0));

  // --- the man from the photo: short brown hair, big eyes, warm smile, blue
  // polo with a small white chest badge, blue jeans, blue sneakers. One hand
  // presents the stack; the other rests on his hip. Flat colours, like the
  // rest of the drawing — the polo blue is the one object colour, so he reads
  // as the man, not as another wireframe.
  const matSkin = new THREE.MeshBasicMaterial({ color: 0xe8b48c });
  const matHair = new THREE.MeshBasicMaterial({ color: 0x6e452a });
  const matPolo = new THREE.MeshBasicMaterial({ color: 0x2f6fb2 });
  const matPoloDark = new THREE.MeshBasicMaterial({ color: 0x25598f });
  const matJeans = new THREE.MeshBasicMaterial({ color: 0x4e6f8e });
  const matJeansDark = new THREE.MeshBasicMaterial({ color: 0x3f5d78 });
  const matShoe = new THREE.MeshBasicMaterial({ color: 0x2f6fb2 });
  const matWhite = new THREE.MeshBasicMaterial({ color: 0xf4efe3 });
  const matDark = new THREE.MeshBasicMaterial({ color: 0x2b211c });
  const matCheek = new THREE.MeshBasicMaterial({ color: 0xf5a183, transparent: true, opacity: 0.55 });
  const person = new THREE.Group();
  person.position.copy(PERSON_POS);
  person.rotation.y = 1.25; // facing the stack, open to the camera
  world.add(person);
  const part = (parent, geo, mat, x = 0, y = 0, z = 0) => { const m = new THREE.Mesh(geo, mat); m.position.set(x, y, z); parent.add(m); return m; };
  const limb = (r, len, mat) => { const m = new THREE.Mesh(new THREE.CylinderGeometry(r, r * 0.86, len, 12), mat); m.position.y = -len / 2; const g = new THREE.Group(); g.add(m); return g; };
  for (const x of [-0.13, 0.13]) {
    part(person, new THREE.CylinderGeometry(0.088, 0.08, 0.86, 12), matJeans, x, 0.55, 0);
    part(person, new THREE.CylinderGeometry(0.086, 0.086, 0.09, 12), matJeansDark, x, 0.155, 0);
    const shoe = new THREE.Group();
    shoe.position.set(x, 0, 0.03);
    person.add(shoe);
    part(shoe, new THREE.BoxGeometry(0.19, 0.055, 0.36), matWhite, 0, 0.028, 0.03);
    part(shoe, new THREE.BoxGeometry(0.18, 0.1, 0.3), matShoe, 0, 0.1, 0);
    const toe = part(shoe, new THREE.SphereGeometry(0.088, 12, 10), matShoe, 0, 0.085, 0.15);
    toe.scale.set(1, 0.72, 1);
  }
  part(person, new THREE.CylinderGeometry(0.285, 0.27, 0.24, 16), matJeans, 0, 1.02, 0).scale.z = 0.82;
  const torso = part(person, new THREE.CylinderGeometry(0.27, 0.315, 0.68, 18), matPolo, 0, 1.44, 0);
  torso.scale.z = 0.8;
  part(person, new THREE.SphereGeometry(0.27, 18, 12), matPolo, 0, 1.76, 0).scale.set(1, 0.55, 0.8);
  part(person, new THREE.CylinderGeometry(0.318, 0.318, 0.07, 18), matPoloDark, 0, 1.12, 0).scale.z = 0.8;
  part(person, new THREE.BoxGeometry(0.05, 0.24, 0.014), matPoloDark, 0, 1.64, 0.222);
  part(person, new THREE.CylinderGeometry(0.015, 0.015, 0.012, 10), matWhite, 0, 1.7, 0.228).rotation.x = Math.PI / 2;
  part(person, new THREE.CylinderGeometry(0.015, 0.015, 0.012, 10), matWhite, 0, 1.595, 0.232).rotation.x = Math.PI / 2;
  const colL = part(person, new THREE.BoxGeometry(0.17, 0.05, 0.02), matPoloDark, -0.075, 1.815, 0.175);
  colL.rotation.set(-0.35, 0.25, 0.55);
  const colR = part(person, new THREE.BoxGeometry(0.17, 0.05, 0.02), matPoloDark, 0.075, 1.815, 0.175);
  colR.rotation.set(-0.35, -0.25, -0.55);
  part(person, new THREE.BoxGeometry(0.3, 0.05, 0.02), matPoloDark, 0, 1.83, -0.185);
  const badge = part(person, new THREE.CircleGeometry(0.062, 24), matWhite, 0.145, 1.55, 0.198);
  badge.rotation.y = 0.62; badge.rotation.x = -0.06;
  const badgeDot = part(person, new THREE.CircleGeometry(0.028, 18), matPolo, 0.152, 1.55, 0.208);
  badgeDot.rotation.y = 0.62; badgeDot.rotation.x = -0.06;
  part(person, new THREE.CylinderGeometry(0.085, 0.095, 0.14, 12), matSkin, 0, 1.86, 0);
  const headGroup = new THREE.Group();
  headGroup.position.y = 2.04;
  person.add(headGroup);
  const head = part(headGroup, new THREE.SphereGeometry(0.24, 24, 20), matSkin, 0, 0, 0);
  head.scale.set(0.96, 1.06, 0.94);
  part(headGroup, new THREE.SphereGeometry(0.055, 10, 8), matSkin, -0.225, 0, 0).scale.set(0.55, 1, 0.8);
  part(headGroup, new THREE.SphereGeometry(0.055, 10, 8), matSkin, 0.225, 0, 0).scale.set(0.55, 1, 0.8);
  part(headGroup, new THREE.SphereGeometry(0.045, 10, 8), matSkin, 0, -0.015, 0.215).scale.set(0.8, 0.7, 0.7);
  for (const x of [-0.088, 0.088]) {
    const ew = part(headGroup, new THREE.SphereGeometry(0.056, 14, 12), matWhite, x, 0.055, 0.195);
    ew.scale.set(0.82, 1.2, 0.55);
    part(headGroup, new THREE.SphereGeometry(0.027, 10, 8), matDark, x, 0.05, 0.228);
    part(headGroup, new THREE.SphereGeometry(0.01, 8, 6), matWhite, x + 0.01, 0.068, 0.248);
    const brow = part(headGroup, new THREE.BoxGeometry(0.105, 0.02, 0.014), matHair, x, 0.155, 0.205);
    brow.rotation.z = x < 0 ? 0.14 : -0.14;
  }
  const smile = part(headGroup, new THREE.TorusGeometry(0.072, 0.014, 8, 24, Math.PI), matDark, 0, -0.045, 0.208);
  smile.rotation.z = Math.PI; smile.rotation.x = -0.12;
  part(headGroup, new THREE.SphereGeometry(0.038, 10, 8), matCheek, -0.135, -0.045, 0.185).scale.set(1, 0.7, 0.4);
  part(headGroup, new THREE.SphereGeometry(0.038, 10, 8), matCheek, 0.135, -0.045, 0.185).scale.set(1, 0.7, 0.4);
  const hair = part(headGroup, new THREE.SphereGeometry(0.248, 24, 16, 0, Math.PI * 2, 0, 1.3), matHair, 0, 0.045, 0);
  hair.scale.set(0.98, 1.02, 0.96);
  const quiff = part(headGroup, new THREE.SphereGeometry(0.2, 18, 12), matHair, 0.035, 0.175, 0.085);
  quiff.scale.set(1.05, 0.52, 0.85); quiff.rotation.z = -0.18;
  part(headGroup, new THREE.BoxGeometry(0.03, 0.11, 0.16), matHair, -0.225, 0.085, 0.01);
  part(headGroup, new THREE.BoxGeometry(0.03, 0.11, 0.16), matHair, 0.225, 0.085, 0.01);
  // right arm presents the stack; left hand rests on his hip
  const armR = limb(0.088, 0.3, matPolo);
  armR.position.set(0.37, 1.7, 0.02);
  armR.rotation.set(-1.1, 0, 0.25);
  person.add(armR);
  const foreR = limb(0.058, 0.34, matSkin);
  foreR.position.y = -0.3;
  foreR.rotation.set(-0.35, 0, 0);
  armR.add(foreR);
  const handR = new THREE.Group();
  handR.position.y = -0.38;
  foreR.add(handR);
  const palm = part(handR, new THREE.SphereGeometry(0.085, 14, 10), matSkin, 0, 0, 0);
  palm.scale.set(1.2, 0.42, 1.35);
  [-0.055, -0.018, 0.018, 0.055].forEach((x, i) => {
    const f = part(handR, new THREE.CylinderGeometry(0.015, 0.013, 0.085, 8), matSkin, x, -0.01, 0.125);
    f.rotation.x = Math.PI / 2.25; f.rotation.z = (i - 1.5) * 0.14;
  });
  const thumb = part(handR, new THREE.CylinderGeometry(0.015, 0.013, 0.07, 8), matSkin, 0.105, 0, 0.03);
  thumb.rotation.z = -1.1; thumb.rotation.x = 0.4;
  const armL = limb(0.088, 0.3, matPolo);
  armL.position.set(-0.37, 1.7, 0.02);
  armL.rotation.set(0.08, 0, -0.6);
  person.add(armL);
  const foreL = limb(0.058, 0.34, matSkin);
  foreL.position.y = -0.3;
  foreL.rotation.set(0.15, 0, 1.5);
  armL.add(foreL);
  part(foreL, new THREE.SphereGeometry(0.072, 12, 10), matSkin, 0, -0.36, 0).scale.set(1, 0.8, 1.15);

  // --- the seven pieces: one vertical column. Every layer shares the same
  // x/z — each new piece lands directly on top of the previous one.
  const PIECE_SCALE = 1;
  const pieces = [];
  const holo = (p, geo, x = 0, y = 0, z = 0, op = 0.3, kind = "line") => {
    const m = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ transparent: true, opacity: op, depthWrite: false }));
    m.material.userData.base = op;
    m.material.userData.kind = kind;
    const e = new THREE.LineSegments(new THREE.EdgesGeometry(geo), new THREE.LineBasicMaterial({ transparent: true, opacity: 0.85 }));
    e.material.userData.base = 0.85;
    e.material.userData.kind = kind;
    m.position.set(x, y, z);
    e.position.copy(m.position);
    p.g.add(m, e);
    p.mats.push(m.material, e.material);
    return m;
  };
  const buildPiece = (i) => {
    const g = new THREE.Group();
    const p = { g, mats: [], v: 0, landed: 0 };
    if (i === 0) { // OLLAMA — the llama mark in 3D: head, ears, snout, neck
      holo(p, new THREE.CylinderGeometry(0.13, 0.17, 0.36, 12), 0, -0.3, 0, 0.35);
      const hd = holo(p, new THREE.SphereGeometry(0.27, 12, 10), 0, 0.1, 0, 0.35);
      hd.scale.set(0.85, 1, 0.9);
      const sn = holo(p, new THREE.SphereGeometry(0.135, 10, 8), 0, -0.03, 0.2, 0.35);
      sn.scale.set(1, 0.75, 1.15);
      for (const s of [-1, 1]) {
        const ear = holo(p, new THREE.ConeGeometry(0.07, 0.24, 8), s * 0.17, 0.4, 0, 0.35);
        ear.rotation.z = -s * 0.45;
        const eye = new THREE.Mesh(new THREE.SphereGeometry(0.032, 10, 8), new THREE.MeshBasicMaterial({ color: 0x0b222e }));
        eye.position.set(s * 0.105, 0.17, 0.205);
        g.add(eye);
      }
      const tuft = holo(p, new THREE.SphereGeometry(0.11, 10, 8), 0, 0.36, 0.05, 0.35);
      tuft.scale.set(1.2, 0.6, 1);
      const portD = holo(p, new THREE.CylinderGeometry(0.3, 0.3, 0.07, 20), 0, -0.55, 0.1);
      portD.rotation.x = 0.5;
    } else if (i === 1) { // MODEL — a processor chip, pins all round
      holo(p, new THREE.BoxGeometry(0.54, 0.54, 0.16), 0, 0, 0, 0.28);
      holo(p, new THREE.BoxGeometry(0.34, 0.34, 0.2), 0, 0, 0, 0.35);
      for (let k = 0; k < 4; k++) {
        const off = -0.18 + k * 0.12;
        holo(p, new THREE.BoxGeometry(0.05, 0.14, 0.05), off, 0.34, 0);
        holo(p, new THREE.BoxGeometry(0.05, 0.14, 0.05), off, -0.34, 0);
        holo(p, new THREE.BoxGeometry(0.14, 0.05, 0.05), 0.34, off, 0);
        holo(p, new THREE.BoxGeometry(0.14, 0.05, 0.05), -0.34, off, 0);
      }
    } else if (i === 2) { // REPO — a folder of workspace files with run.bat's play launcher
      holo(p, new THREE.BoxGeometry(0.64, 0.48, 0.04), 0, 0.02, -0.07);
      holo(p, new THREE.BoxGeometry(0.24, 0.09, 0.045), -0.18, 0.29, -0.07);
      holo(p, new THREE.BoxGeometry(0.52, 0.4, 0.02), 0, 0.08, 0, 0.35);
      const frontF = holo(p, new THREE.BoxGeometry(0.68, 0.42, 0.04), 0, -0.05, 0.09);
      frontF.rotation.x = -0.1;
      const tri = new THREE.Mesh(new THREE.CylinderGeometry(0.13, 0.13, 0.06, 3), new THREE.MeshBasicMaterial({ color: 0xffffff }));
      tri.material.userData.base = 1;
      tri.material.userData.kind = "signal";
      tri.rotation.x = Math.PI / 2; tri.rotation.z = -Math.PI / 2;
      tri.position.set(0, -0.05, 0.14);
      g.add(tri);
      p.mats.push(tri.material);
    } else if (i === 3) { // VENV — a terminal window with a typed prompt
      holo(p, new THREE.BoxGeometry(0.7, 0.52, 0.05), 0, 0, 0, 0.28);
      const ts = new THREE.Mesh(new THREE.PlaneGeometry(0.62, 0.36), new THREE.MeshBasicMaterial({ map: codeTexture([4, 2, 5, 3, 6, 2, 4]) }));
      ts.position.set(0, -0.05, 0.032);
      g.add(ts);
      holo(p, new THREE.BoxGeometry(0.7, 0.09, 0.055), 0, 0.235, 0, 0.45);
    } else if (i === 4) { // AGENT — the "A", four brand dots, harness lead
      const legL = holo(p, new THREE.BoxGeometry(0.12, 0.62, 0.12), -0.15, 0, 0, 0.35);
      legL.rotation.z = 0.38;
      const legR = holo(p, new THREE.BoxGeometry(0.12, 0.62, 0.12), 0.15, 0, 0, 0.35);
      legR.rotation.z = -0.38;
      holo(p, new THREE.BoxGeometry(0.32, 0.09, 0.12), 0, -0.06, 0, 0.35);
      holo(p, new THREE.SphereGeometry(0.07, 12, 10), 0, 0.36, 0, 0.5);
      [0x4285f4, 0xea4335, 0xfbbc05, 0x34a853].forEach((gc, k) => {
        const d = new THREE.Mesh(new THREE.SphereGeometry(0.045, 10, 8), new THREE.MeshBasicMaterial({ color: gc }));
        d.position.set(-0.33 + k * 0.22, -0.42, 0);
        g.add(d);
      });
      const lead = new THREE.Mesh(new THREE.TorusGeometry(0.3, 0.022, 8, 32, Math.PI), new THREE.MeshBasicMaterial({ transparent: true, opacity: 0.8 }));
      lead.material.userData.base = 0.8;
      lead.material.userData.kind = "line";
      lead.position.set(0, -0.48, 0);
      lead.rotation.z = Math.PI;
      g.add(lead);
      p.mats.push(lead.material);
    } else if (i === 5) { // ONE JOB — harness plug + the job file, through the Policy Gate
      const sheet = holo(p, new THREE.BoxGeometry(0.36, 0.46, 0.03), -0.1, 0.05, -0.1, 0.35);
      sheet.rotation.z = 0.08;
      holo(p, new THREE.BoxGeometry(0.3, 0.24, 0.24), 0.08, -0.05, 0.1, 0.35);
      for (const dx of [-0.06, 0.06]) {
        const prong = holo(p, new THREE.CylinderGeometry(0.022, 0.022, 0.18, 8), 0.08 + dx, -0.05, 0.3, 0.6);
        prong.rotation.x = Math.PI / 2;
      }
      const cable = new THREE.Mesh(new THREE.TorusGeometry(0.26, 0.03, 8, 32, Math.PI * 1.2), new THREE.MeshBasicMaterial({ transparent: true, opacity: 0.8 }));
      cable.material.userData.base = 0.8;
      cable.material.userData.kind = "line";
      cable.position.set(0.08, -0.05, -0.02);
      cable.rotation.y = Math.PI / 2; cable.rotation.z = 0.6;
      g.add(cable);
      p.mats.push(cable.material);
      const gate = holo(p, new THREE.TorusGeometry(0.44, 0.025, 8, 40), 0, 0, 0, 0.7, "signal");
      gate.rotation.x = 0.3;
    } else { // EDITOR — a code editor window, sidebar + code
      holo(p, new THREE.BoxGeometry(0.76, 0.56, 0.05), 0, 0, 0, 0.25);
      const es = new THREE.Mesh(new THREE.PlaneGeometry(0.52, 0.44), new THREE.MeshBasicMaterial({ map: codeTexture([5, 3, 6, 2, 4, 5, 3, 6, 4, 2, 5]) }));
      es.position.set(0.09, -0.03, 0.032);
      g.add(es);
      holo(p, new THREE.BoxGeometry(0.16, 0.56, 0.055), -0.3, 0, 0, 0.4);
      holo(p, new THREE.BoxGeometry(0.76, 0.09, 0.055), 0, 0.245, 0, 0.45);
    }
    g.add(makePlate(STEPS[i].plate));
    g.position.copy(SOURCES[i]);
    g.visible = false;
    g.scale.setScalar(PIECE_SCALE);
    world.add(g);
    return p;
  };
  for (let i = 0; i < 7; i++) pieces.push(buildPiece(i));

  // Ghost rings: flat rings marking the empty slots of the stack.
  const ghosts = pieces.map((p, i) => {
    const gh = new THREE.Mesh(new THREE.TorusGeometry(0.62, 0.012, 8, 44), new THREE.MeshBasicMaterial({ transparent: true, opacity: 0.3 }));
    gh.material.userData.base = 0.3;
    gh.position.copy(slot(i));
    gh.rotation.x = Math.PI / 2;
    world.add(gh);
    return gh;
  });
  // Highlight ring that always sits on the current top layer.
  const stackRing = new THREE.Mesh(new THREE.TorusGeometry(0.68, 0.025, 10, 48), new THREE.MeshBasicMaterial({ transparent: true, opacity: 0 }));
  stackRing.rotation.x = Math.PI / 2;
  world.add(stackRing);
  const flash = new THREE.Mesh(new THREE.TorusGeometry(0.62, 0.02, 8, 48), new THREE.MeshBasicMaterial({ transparent: true, opacity: 0 }));
  flash.rotation.x = Math.PI / 2;
  world.add(flash);
  let flashT = 1;

  // --- colours follow state; the top layer glows, settled layers sit dimmer
  function applyAll() {
    for (const p of pieces) {
      const ghost = 0.12 + 0.88 * p.landed;
      for (const m of p.mats) {
        if (m.userData.kind === "signal") m.color.copy(colors.signal);
        else m.color.copy(colors.line).lerp(colors.signal, p.v);
        m.opacity = m.userData.base * ghost * (0.8 + 0.35 * p.v);
      }
    }
    for (const m of lineMats) { m.color.copy(colors.line); m.opacity = m.userData.base; }
    for (const m of signalMats) { m.color.copy(colors.signal); m.opacity = m.userData.base; }
    for (const m of flagMats) { m.color.copy(colors.flag); m.opacity = m.userData.base; }
    floor.material.color.copy(colors.line);
    for (const g of ghosts) g.material.color.copy(colors.line);
    stackRing.material.color.copy(colors.signal);
    flash.material.color.copy(colors.signal);
    needsRender = true;
  }

  // --- camera rig: scripted position + target, with the visitor's orbit
  // and zoom composed on top in the render loop
  const rig = { dist: 12, az: 0, el: 0.3, tx: 0, ty: 0, tz: 0 };
  function rigFrom(cam, look) {
    const c = new THREE.Vector3(...cam), l = new THREE.Vector3(...look);
    const d = c.clone().sub(l);
    return { dist: d.length(), az: Math.atan2(d.x, d.z), el: Math.asin(d.y / d.length()), tx: l.x, ty: l.y, tz: l.z };
  }
  function motionScale() { return isPaused() ? 0 : 1; }
  function flyTo(f) {
    const r = rigFrom(f.cam, f.look);
    gsap.to(rig, { ...r, duration: 1.8 * motionScale(), ease: "sine.inOut", overwrite: "auto", onUpdate: () => { needsRender = true; } });
  }
  function settleView() {
    if (assembledCount === 0 || isPaused()) return;
    const topY = CORE.y + (assembledCount - 1) * LAYER_H;
    const midY = (CORE.y + topY) / 2;
    gsap.to(rig, { dist: 7.6 + assembledCount * 0.5, az: -0.15, el: 0.3, tx: 0.55, ty: midY, tz: -0.2, duration: 1.4, ease: "sine.inOut", overwrite: "auto", onUpdate: () => { needsRender = true; } });
  }
  function scheduleSettle(name) {
    settleCall?.kill();
    settleCall = gsap.delayedCall(1.5, () => { if (current === name && !isPaused()) settleView(); });
  }

  // --- assembly state
  let current = "overview";
  let assembledCount = 0;
  let landing = -1;
  let playing = false;
  let playTimer = null;
  let settleCall = null;
  function cancelPlay() { playing = false; if (playTimer) { clearTimeout(playTimer); playTimer = null; } }
  function emitStack(event) {
    onStack?.({ count: assembledCount, top: assembledCount - 1, landing, playing, event });
  }
  function killPieceTweens(p) {
    const idx = pieces.indexOf(p);
    if (landing === idx) landing = -1;
    gsap.killTweensOf(p.g.position);
    gsap.killTweensOf(p.g.rotation);
    gsap.killTweensOf(p.g.scale);
    gsap.killTweensOf(p);
    if (p.prog) gsap.killTweensOf(p.prog);
  }
  function placeInstant(i) {
    const p = pieces[i];
    killPieceTweens(p);
    p.g.position.copy(slot(i));
    p.g.rotation.set(0, 0, 0);
    p.g.scale.setScalar(PIECE_SCALE);
    p.g.visible = true;
    p.landed = 1; p.placed = true; p.flying = false;
    applyAll();
  }
  function hidePiece(i, instant) {
    const p = pieces[i];
    killPieceTweens(p);
    p.placed = false; p.flying = false;
    if (instant) {
      p.g.visible = false;
      p.landed = 0;
      applyAll();
      return;
    }
    gsap.to(p.g.scale, { x: 0.001, y: 0.001, z: 0.001, duration: 0.35, ease: "power2.in", onUpdate: () => { needsRender = true; }, onComplete: () => { p.g.visible = false; p.g.scale.setScalar(PIECE_SCALE); } });
    gsap.to(p, { landed: 0, duration: 0.35, onUpdate: applyAll });
  }
  function updateHighlight() {
    const top = assembledCount - 1;
    const ms = motionScale();
    for (let i = 0; i < pieces.length; i++) {
      gsap.to(pieces[i], { v: i === top ? 1 : 0, duration: 0.4 * ms, onUpdate: applyAll });
    }
  }
  // He reaches for the piece being placed, then relaxes back to presenting.
  function reachFor() {
    if (isPaused()) return;
    gsap.to(armR.rotation, { x: -1.5, z: 0.1, duration: 0.5, ease: "sine.out", overwrite: "auto" });
    gsap.to(armR.rotation, { x: -1.1, z: 0.25, duration: 0.8, delay: 1.2, ease: "sine.inOut", overwrite: false });
    gsap.to(foreR.rotation, { x: -0.6, duration: 0.5, ease: "sine.out", overwrite: "auto" });
    gsap.to(foreR.rotation, { x: -0.35, duration: 0.8, delay: 1.2, ease: "sine.inOut", overwrite: false });
  }
  function landPiece(i, delay = 0) {
    const p = pieces[i];
    killPieceTweens(p);
    const home = slot(i);
    const ms = motionScale();
    reachFor();
    if (ms === 0) { placeInstant(i); return; }
    landing = i;
    p.flying = true; p.placed = false; p.landed = 0;
    p.g.visible = true;
    p.g.position.copy(SOURCES[i]);
    p.g.rotation.set(1.2, 0.4, 0.8);
    p.g.scale.setScalar(0.55);
    const dur = 1.15;
    const prog = { t: 0 };
    p.prog = prog;
    const q0 = SOURCES[i].clone(), q1 = HAND.clone(), q2 = home.clone();
    gsap.to(prog, {
      t: 1, duration: dur, delay, ease: "power1.inOut",
      onUpdate: () => {
        const t = prog.t;
        const a = q0.clone().lerp(q1, t), b = q1.clone().lerp(q2, t);
        p.g.position.copy(a.lerp(b, t));
        needsRender = true;
      },
      onComplete: () => finishLand(i),
    });
    gsap.to(p.g.rotation, { x: 0, y: 0, z: 0, duration: dur, delay, ease: "power3.out" });
    gsap.to(p.g.scale, { x: PIECE_SCALE, y: PIECE_SCALE, z: PIECE_SCALE, duration: dur, delay, ease: "back.out(1.4)" });
    gsap.to(p, { landed: 1, duration: 0.9, delay, ease: "sine.inOut", onUpdate: applyAll });
  }
  function finishLand(i) {
    const p = pieces[i];
    p.g.position.copy(slot(i));
    p.g.rotation.set(0, 0, 0);
    p.g.scale.setScalar(PIECE_SCALE);
    p.landed = 1; p.placed = true; p.flying = false;
    if (landing === i) landing = -1;
    flash.position.copy(slot(i));
    flashT = 0;
    applyAll();
    updateHighlight();
    emitStack("landed");
    if (playing) {
      if (assembledCount < 7) playTimer = setTimeout(() => { if (playing) stepTo(assembledCount + 1, { viaPlay: true }); }, isPaused() ? 80 : 700);
      else { playing = false; emitStack("play-end"); }
    }
  }
  function setCount(n, opts = {}) {
    n = Math.max(0, Math.min(7, n));
    if (!opts.viaPlay) cancelPlay();
    const prev = assembledCount;
    if (n === prev) return;
    const instant = opts.instant || isPaused();
    if (n > prev) {
      for (let j = prev; j < n; j++) {
        if (j === n - 1 && !instant) landPiece(j, 0);
        else placeInstant(j);
      }
    } else {
      for (let j = prev - 1; j >= n; j--) hidePiece(j, instant);
    }
    assembledCount = n;
    updateHighlight();
    emitStack(n > prev ? "placed" : "hidden");
  }

  // --- focus + controls: page scroll and the hero buttons share goTo(),
  // so the hologram always matches the count — whoever asked last
  function setActiveTags(on) {
    for (const t of tags) t.classList.toggle("is-active", on.includes(t.dataset.anchor));
  }
  function goTo(name, opts = {}) {
    const f = FOCUS[name] || FOCUS.overview;
    if (!opts.viaPlay) cancelPlay();
    current = name;
    if (!isPaused() || opts.forceCount) setCount(f.count, opts);
    flyTo(f);
    setActiveTags(f.on);
    if (STEP_KEYS.includes(name) && !isPaused()) scheduleSettle(name);
    else { settleCall?.kill(); settleCall = null; }
  }
  function focus(name) { goTo(name); }
  function stepTo(n, opts = {}) {
    n = Math.max(0, Math.min(7, n));
    if (n === assembledCount) return;
    goTo(n > 0 ? STEP_KEYS[n - 1] : "overview", { ...opts, forceCount: true });
  }
  function play() {
    if (playing) { cancelPlay(); emitStack("stopped"); return; }
    playing = true;
    setCount(0, { viaPlay: true, instant: true });
    goTo("overview", { viaPlay: true });
    emitStack("play-start");
    playTimer = setTimeout(() => { if (playing) stepTo(1, { viaPlay: true }); }, isPaused() ? 60 : 350);
  }
  function replay() {
    if (assembledCount === 0) return;
    cancelPlay();
    const i = assembledCount - 1;
    hidePiece(i, true);
    if (isPaused()) placeInstant(i);
    else { landPiece(i, 0); flyTo(FOCUS[STEP_KEYS[i]]); scheduleSettle(STEP_KEYS[i]); }
    emitStack("replay");
  }
  function reset() {
    cancelPlay();
    orbit.tx = 0; orbit.tp = 0; userZoom.tgt = 1;
    setCount(0, { instant: true });
    goTo("overview");
    emitStack("reset");
  }

  // --- free orbit + zoom, composing on top of the scripted camera.
  // Plain wheel must scroll the page — scroll is what drives the pieces,
  // so the stage never traps it. Zoom is Ctrl/Cmd + wheel.
  const orbit = { theta: 0, phi: 0, tx: 0, tp: 0, drag: false, lx: 0, ly: 0 };
  const userZoom = { cur: 1, tgt: 1 };
  canvas.addEventListener("pointerdown", (e) => { orbit.drag = true; orbit.lx = e.clientX; orbit.ly = e.clientY; });
  addEventListener("pointerup", () => { orbit.drag = false; });
  addEventListener("pointercancel", () => { orbit.drag = false; });
  addEventListener("pointermove", (e) => {
    if (!orbit.drag) return;
    orbit.tx += (e.clientX - orbit.lx) * 0.006;
    orbit.tp += (e.clientY - orbit.ly) * 0.003;
    orbit.tp = Math.max(-0.22, Math.min(0.34, orbit.tp));
    orbit.lx = e.clientX; orbit.ly = e.clientY;
    needsRender = true;
  });
  canvas.addEventListener("wheel", (e) => {
    if (!(e.ctrlKey || e.metaKey)) return;
    e.preventDefault();
    userZoom.tgt = Math.max(0.5, Math.min(2.1, userZoom.tgt * (e.deltaY > 0 ? 1.13 : 0.885)));
    needsRender = true;
  }, { passive: false });

  // --- sizing: the page tells us where the drawing should sit
  const wide = matchMedia("(min-width: 62em)");
  function applyView() {
    camera.aspect = width / height;
    const ox = wide.matches ? view.ox : 0;
    camera.setViewOffset(width, height, ox * width, 0, width, height);
    camera.updateProjectionMatrix();
    needsRender = true;
  }
  function resize() {
    width = Math.max(1, innerWidth); height = Math.max(1, innerHeight);
    renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 2));
    renderer.setSize(width, height, false);
    applyView();
  }
  addEventListener("resize", resize);
  wide.addEventListener("change", applyView);
  resize();

  // --- labels follow their 3D anchors; only the active piece's shows
  const v3 = new THREE.Vector3();
  const tmpV = new THREE.Vector3();
  function placeTags() {
    for (const t of tags) {
      const key = t.dataset.anchor;
      if (key === "person") v3.copy(PERSON_POS).add(tmpV.set(0, 2.35, 0));
      else if (key === "workspace") v3.copy(DESK_POS).add(tmpV.set(0, 0.6, 0));
      else if (key === "cloud") v3.copy(CLOUD_POS);
      else {
        const idx = STEP_KEYS.indexOf(key);
        if (idx < 0) continue;
        v3.copy(pieces[idx].g.position);
        v3.y += 0.55;
      }
      v3.project(camera);
      const x = (v3.x * 0.5 + 0.5) * width, y = (-v3.y * 0.5 + 0.5) * height;
      t.style.transform = `translate(${x.toFixed(1)}px, ${y.toFixed(1)}px) translate(-50%, ${key === "cloud" ? "0" : "-100%"})`;
      const show = v3.z < 1 && x > 0 && x < width && y > 0 && y < height && (t.classList.contains("is-active") || key === "cloud");
      t.classList.toggle("is-visible", show);
    }
  }

  // --- loop: renders only when something moves, and never while the tab is hidden
  let last = performance.now() / 1000;
  let elapsed = 0;
  const headLook = new THREE.Vector3().copy(CORE);
  const lookTarget = new THREE.Vector3();
  function frame() {
    requestAnimationFrame(frame);
    const now = performance.now() / 1000;
    const dt = Math.min(now - last, 0.05);
    last = now;
    if (document.hidden) return;
    const live = !isPaused();
    if (live) {
      elapsed += dt;
      orbit.theta += (orbit.tx - orbit.theta) * 0.06;
      orbit.phi += (orbit.tp - orbit.phi) * 0.06;
      userZoom.cur += (userZoom.tgt - userZoom.cur) * 0.09;
      cloud.rotation.y += dt * 0.15;
      const nextSlot = pieces.findIndex((p) => !p.placed && !p.flying);
      ghosts.forEach((g, i) => {
        g.visible = !pieces[i].placed && !pieces[i].flying;
        g.material.opacity = (i === nextSlot) ? 0.55 + Math.sin(elapsed * 3.2) * 0.2 : 0.2;
      });
      // The stack bobs as one column — layers never drift apart once settled.
      const stackBob = Math.sin(elapsed * 1.3) * 0.02;
      const top = assembledCount - 1;
      pieces.forEach((p, i) => {
        if (p.placed && !(landing === i)) {
          p.g.position.y = slot(i).y + stackBob;
          const ts = (i === top) ? 1 + Math.sin(elapsed * 3.4) * 0.03 : 1;
          p.g.scale.setScalar(ts * PIECE_SCALE);
        }
      });
      if (top >= 0) {
        stackRing.visible = true;
        stackRing.position.copy(pieces[top].g.position);
        stackRing.material.opacity = landing >= 0 ? 0.95 : 0.55 + Math.sin(elapsed * 3.4) * 0.25;
        const rs = landing >= 0 ? 1.15 : 1 + Math.sin(elapsed * 3.4) * 0.05;
        stackRing.scale.set(rs, rs, rs);
      } else stackRing.visible = false;
      if (flashT < 1) {
        flashT = Math.min(1, flashT + dt * 1.4);
        const s = 0.6 + flashT * 1.6;
        flash.scale.set(s, s, s);
        flash.material.opacity = 0.85 * (1 - flashT);
      }
      if (landing >= 0) lookTarget.copy(pieces[landing].g.position);
      else if (STEP_KEYS.includes(current)) lookTarget.copy(slot(STEP_KEYS.indexOf(current)));
      else lookTarget.copy(CORE);
      headLook.lerp(lookTarget, 0.07);
      headGroup.lookAt(headLook.x, headLook.y, headLook.z);
      torso.scale.y = 1 + Math.sin(elapsed * 1.4) * 0.012;
      needsRender = true;
    }
    if (!needsRender) return;
    const az = rig.az + orbit.theta + (live && current === "showcase" ? Math.sin(elapsed * 0.12) * 0.35 : 0);
    const el = rig.el + orbit.phi;
    const dd = rig.dist * userZoom.cur;
    camera.position.set(
      rig.tx + Math.sin(az) * Math.cos(el) * dd,
      rig.ty + Math.sin(el) * dd,
      rig.tz + Math.cos(az) * Math.cos(el) * dd,
    );
    camera.lookAt(rig.tx, rig.ty, rig.tz);
    renderer.render(scene, camera);
    placeTags();
    needsRender = false;
  }

  const r0 = rigFrom(FOCUS.overview.cam, FOCUS.overview.look);
  Object.assign(rig, r0);
  camera.position.set(...FOCUS.overview.cam);
  camera.lookAt(-0.5, 0.1, -0.1);
  applyAll();
  // Reduced motion (or paused at load): the assembled state, no animation.
  // Scrolling still moves the camera; the stack itself stays assembled.
  if (isPaused()) setCount(7, { instant: true, viaPlay: true });
  goTo("overview");
  canvas.addEventListener("webglcontextlost", (e) => { e.preventDefault(); canvas.style.display = "none"; });
  frame();

  return {
    focus,
    view,
    refresh: () => { applyView(); needsRender = true; },
    redraw: () => { needsRender = true; },
    stepTo,
    play,
    replay,
    reset,
    getCount: () => assembledCount,
    isPlaying: () => playing,
  };
}
