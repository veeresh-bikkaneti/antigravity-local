// The drawing behind the page: your machine as a wireframe box, with you at the keyboard
// in front of it, Ollama, the agent, your files and an editor inside it. The cloud sits
// outside and never connects. Each guide step lights one part.
import * as THREE from "three";
import { gsap } from "gsap";

const W = 5.2, H = 3, D = 3.4;

const POS = {
  ollama: new THREE.Vector3(1.5, 0.1, -0.2),
  agent: new THREE.Vector3(-0.4, 0.2, 0.6),
  workspace: new THREE.Vector3(-1.7, -0.75, -0.5),
  editor: new THREE.Vector3(-1.5, 0.95, 1.0),
  cloud: new THREE.Vector3(0.6, 2.75, -1.4),
  person: new THREE.Vector3(0.2, -0.75, 1.25),
};

// camera position, look-at target, and which parts glow, per guide focus
const FOCUS = {
  overview: { cam: [7.6, 4.0, 8.9], look: [0, 0, 0], on: [], pulses: ["agent-ollama", "agent-workspace"] },
  person: { cam: [3.2, 0.8, 6.6], look: [0.2, -0.7, 1.2], on: ["person"], pulses: [] },
  ollama: { cam: [5.2, 1.7, 4.8], look: [1.5, 0.1, -0.2], on: ["ollama"], pulses: [] },
  "ollama-core": { cam: [3.9, 1.1, 3.3], look: [1.5, 0.1, -0.2], on: ["ollama"], core: true, pulses: [] },
  machine: { cam: [7.6, 4.3, 8.6], look: [0, 0, 0], on: ["box"], pulses: [] },
  agent: { cam: [1.4, 1.9, 4.6], look: [-0.4, 0.2, 0.6], on: ["agent"], pulses: [] },
  chat: { cam: [3.2, 2.3, 6.2], look: [0.5, 0.1, 0.2], on: ["agent", "ollama"], pulses: ["agent-ollama"] },
  task: { cam: [-0.8, 1.6, 5.4], look: [-1.0, -0.2, 0.0], on: ["agent", "workspace"], pulses: ["agent-workspace"], newFile: true },
  editor: { cam: [0.2, 2.5, 5.2], look: [0.0, 0.6, 0.6], on: ["editor", "ollama"], pulses: ["editor-ollama"] },
};

const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

export function start({ canvas, tags, isPaused }) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: "low-power" });
  renderer.setClearColor(0x000000, 0);
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(36, 1, 0.1, 80);
  const look = new THREE.Vector3();
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
  matchMedia("(prefers-color-scheme: light)").addEventListener("change", () => { readColors(); applyAll(); });

  // --- the machine boundary
  const group = new THREE.Group();
  scene.add(group);
  const boxEdges = new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.BoxGeometry(W, H, D)), new THREE.LineBasicMaterial({ transparent: true, opacity: 0.7 }));
  const boxFaces = new THREE.Mesh(new THREE.BoxGeometry(W, H, D), new THREE.MeshBasicMaterial({ transparent: true, opacity: 0.035, depthWrite: false }));
  const floor = new THREE.GridHelper(W, 10, 0xffffff, 0xffffff);
  floor.position.y = -H / 2;
  floor.scale.z = D / W;
  floor.material.transparent = true;
  floor.material.opacity = 0.25;
  group.add(boxFaces, boxEdges, floor);

  // --- parts: each has a wire shape and a state value v (0 base, 1 glowing)
  const parts = {};
  const mkPart = (name, objects, mats) => { parts[name] = { name, objects, mats, v: 0, g: new THREE.Group() }; objects.forEach((o) => parts[name].g.add(o)); parts[name].g.position.copy(POS[name]); group.add(parts[name].g); };
  const wire = (geo, opacity = 0.9) => new THREE.LineSegments(new THREE.EdgesGeometry(geo), new THREE.LineBasicMaterial({ transparent: true, opacity }));

  // Ollama: a still crystal, not a spinning globe. It only moves when its focus
  // pulses the core (see coreBoost in applyAll).
  const ollamaShell = wire(new THREE.IcosahedronGeometry(0.62, 1));
  const ollamaCore = new THREE.Mesh(new THREE.SphereGeometry(0.2, 20, 14), new THREE.MeshBasicMaterial({ transparent: true, opacity: 0.85 }));
  mkPart("ollama", [ollamaShell, ollamaCore], [ollamaShell.material, ollamaCore.material]);
  parts.ollama.coreBoost = 0; // gsap can only tween a property that already exists

  const agentShell = wire(new THREE.OctahedronGeometry(0.5, 0));
  const agentCore = new THREE.Mesh(new THREE.OctahedronGeometry(0.17, 0), new THREE.MeshBasicMaterial({ transparent: true, opacity: 0.85 }));
  mkPart("agent", [agentShell, agentCore], [agentShell.material, agentCore.material]);

  const files = [0, 1, 2].map((i) => { const f = wire(new THREE.BoxGeometry(0.9, 0.09, 0.6)); f.position.y = i * 0.14; f.rotation.y = (i - 1) * 0.12; return f; });
  const newFile = wire(new THREE.BoxGeometry(0.9, 0.09, 0.6));
  newFile.position.set(0.15, 3 * 0.14, 0);
  newFile.scale.setScalar(0.001);
  mkPart("workspace", [...files, newFile], [...files.map((f) => f.material), newFile.material]);

  const win = wire(new THREE.PlaneGeometry(1.15, 0.75));
  const bar = wire(new THREE.PlaneGeometry(1.15, 0.14), 0.7);
  bar.position.y = 0.305;
  win.rotation.y = 0.35; bar.rotation.y = 0.35;
  mkPart("editor", [win, bar], [win.material, bar.material]);

  // --- you, at the keyboard: a seated person at a desk with a monitor, typing.
  // Same wireframe linework as the rest of the machine. The person faces away
  // from the camera, toward the monitor, so the screen is what they watch.
  // Positions are relative to POS.person (the chair), y up, -z toward the monitor.
  const limb = (a, b, r = 0.045) => {
    const dir = b.clone().sub(a);
    const len = dir.length();
    const geo = new THREE.CylinderGeometry(r, r, len, 6);
    const mesh = new THREE.LineSegments(new THREE.EdgesGeometry(geo), new THREE.LineBasicMaterial({ transparent: true, opacity: 0.9 }));
    mesh.position.copy(a).addScaledVector(dir, 0.5);
    mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir.normalize());
    return mesh;
  };
  const at = (geo, x, y, z, opacity = 0.9) => { const o = wire(geo, opacity); o.position.set(x, y, z); return o; };
  const desk = at(new THREE.BoxGeometry(1.7, 0.07, 0.8), 0, -0.28, -0.15);
  const deskLegL = at(new THREE.BoxGeometry(0.06, 0.46, 0.06), -0.75, -0.53, -0.15);
  const deskLegR = at(new THREE.BoxGeometry(0.06, 0.46, 0.06), 0.75, -0.53, -0.15);
  const screen = at(new THREE.PlaneGeometry(0.95, 0.6), 0, 0.12, -0.5);
  const screenLine1 = at(new THREE.PlaneGeometry(0.7, 0.035), -0.05, 0.28, -0.49, 0.7);
  const screenLine2 = at(new THREE.PlaneGeometry(0.55, 0.035), -0.12, 0.18, -0.49, 0.7);
  const screenLine3 = at(new THREE.PlaneGeometry(0.62, 0.035), -0.09, 0.08, -0.49, 0.7);
  const stand = at(new THREE.BoxGeometry(0.08, 0.22, 0.08), 0, -0.2, -0.5);
  const standBase = at(new THREE.BoxGeometry(0.3, 0.04, 0.2), 0, -0.28, -0.5);
  const keyboard = at(new THREE.BoxGeometry(0.7, 0.04, 0.28), 0, -0.23, 0.05);
  const mug = at(new THREE.CylinderGeometry(0.07, 0.06, 0.12, 8), 0.68, -0.2, -0.3);
  const chairSeat = at(new THREE.BoxGeometry(0.55, 0.07, 0.5), 0, -0.45, 0.45);
  const chairBack = at(new THREE.BoxGeometry(0.55, 0.65, 0.07), 0, -0.12, 0.68);
  const chairLeg = at(new THREE.BoxGeometry(0.07, 0.32, 0.07), 0, -0.63, 0.45);
  const torso = at(new THREE.CylinderGeometry(0.17, 0.23, 0.55, 8), 0, 0.0, 0.3);
  const head = at(new THREE.IcosahedronGeometry(0.21, 0), 0, 0.42, 0.3);
  const armL = limb(new THREE.Vector3(-0.2, 0.15, 0.3), new THREE.Vector3(-0.14, -0.2, 0.05));
  const armR = limb(new THREE.Vector3(0.2, 0.15, 0.3), new THREE.Vector3(0.14, -0.2, 0.05));
  // hands: their own group, so the frame loop can bob them while typing
  const hands = new THREE.Group();
  const handL = wire(new THREE.SphereGeometry(0.06, 8, 6)); handL.position.set(-0.14, -0.2, 0.05);
  const handR = wire(new THREE.SphereGeometry(0.06, 8, 6)); handR.position.set(0.14, -0.2, 0.05);
  hands.add(handL, handR);
  const personObjs = [desk, deskLegL, deskLegR, screen, screenLine1, screenLine2, screenLine3, stand, standBase, keyboard, mug, chairSeat, chairBack, chairLeg, torso, head, armL, armR, hands];
  mkPart("person", personObjs, [...personObjs.filter((o) => o.material).map((o) => o.material), handL.material, handR.material]);
  const personHead = head;
  const personHands = hands;

  // the cloud: dashed and disconnected on purpose
  const cloudRing = new THREE.Line(new THREE.BufferGeometry().setFromPoints(new THREE.EllipseCurve(0, 0, 0.7, 0.45, 0, Math.PI * 2).getPoints(48).map((p) => new THREE.Vector3(p.x, p.y, 0))), new THREE.LineDashedMaterial({ dashSize: 0.1, gapSize: 0.09, transparent: true, opacity: 0.8 }));
  cloudRing.computeLineDistances();
  const cloud = new THREE.Group();
  cloud.add(cloudRing);
  cloud.position.copy(POS.cloud);
  group.add(cloud);

  // --- links and pulses
  const mkLink = (id, a, b, lift) => {
    const mid = a.clone().lerp(b, 0.5); mid.y += lift;
    const curve = new THREE.QuadraticBezierCurve3(a, mid, b);
    const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints(curve.getPoints(40)), new THREE.LineBasicMaterial({ transparent: true, opacity: 0.35 }));
    const pts = new THREE.Points(new THREE.BufferGeometry().setAttribute("position", new THREE.BufferAttribute(new Float32Array(9), 3)), new THREE.PointsMaterial({ size: 8, sizeAttenuation: false, transparent: true, depthWrite: false }));
    group.add(line, pts);
    return { id, curve, line, pts, speed: 0.15, v: 0 };
  };
  const links = [
    mkLink("agent-ollama", POS.agent, POS.ollama, 0.5),
    mkLink("agent-workspace", POS.agent, POS.workspace, -0.2),
    mkLink("editor-ollama", POS.editor, POS.ollama, 0.7),
    mkLink("editor-agent", POS.editor, POS.agent, 0.3),
  ];

  // --- colors follow state
  function applyAll() {
    const flash = parts.ollama.coreBoost || 0;
    for (const p of Object.values(parts)) {
      const c = colors.line.clone().lerp(colors.signal, p.v);
      p.mats.forEach((m) => { m.color.copy(c); });
    }
    const boxC = colors.line.clone().lerp(colors.signal, boxState.v);
    boxEdges.material.color.copy(boxC); boxFaces.material.color.copy(boxC); floor.material.color.copy(colors.line);
    cloudRing.material.color.copy(colors.flag);
    links.forEach((l) => { l.line.material.color.copy(colors.line); l.pts.material.color.copy(colors.signal); });
    ollamaCore.scale.setScalar(1 + flash * 0.5);
    needsRender = true;
  }
  const boxState = { v: 0 };

  // --- camera and focus
  let current = "overview";
  function motionScale() { return isPaused() ? 0 : 1; }

  function focus(name) {
    const f = FOCUS[name] || FOCUS.overview;
    current = name;
    const dur = 1.8 * motionScale();
    gsap.to(camera.position, { x: f.cam[0], y: f.cam[1], z: f.cam[2], duration: dur, ease: "sine.inOut", onUpdate: () => { camera.lookAt(look); needsRender = true; } });
    gsap.to(look, { x: f.look[0], y: f.look[1], z: f.look[2], duration: dur, ease: "sine.inOut", onUpdate: () => { camera.lookAt(look); needsRender = true; } });
    for (const p of Object.values(parts)) gsap.to(p, { v: f.on.includes(p.name) ? 1 : 0, duration: 0.5 * motionScale(), onUpdate: applyAll });
    gsap.to(boxState, { v: f.on.includes("box") ? 1 : 0, duration: 0.5 * motionScale(), onUpdate: applyAll });
    gsap.to(parts.ollama, { coreBoost: f.core ? 1 : 0, duration: 0.6 * motionScale(), onUpdate: applyAll });
    gsap.to(newFile.scale, { x: f.newFile ? 1 : 0.001, y: f.newFile ? 1 : 0.001, z: f.newFile ? 1 : 0.001, duration: 0.7 * motionScale(), ease: "back.out(1.6)", onUpdate: () => { needsRender = true; } });
    links.forEach((l) => { l.active = f.pulses.includes(l.id); gsap.to(l, { v: l.active ? 1 : 0, duration: 0.4 * motionScale(), onUpdate: () => { l.line.material.opacity = 0.3 + 0.5 * l.v; needsRender = true; } }); });
    tags.forEach((t) => { const k = t.dataset.anchor; t.classList.toggle("is-active", (k === "ollama" && f.on.includes("ollama")) || f.on.includes(k)); });
  }

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

  // --- labels follow their 3D anchors
  const v3 = new THREE.Vector3();
  function placeTags() {
    for (const t of tags) {
      const key = t.dataset.anchor;
      const base = key === "cloud" ? POS.cloud : POS[key];
      if (!base) continue;
      v3.copy(base).add(group.position);
      // the person tag sits just above the head, which is up and in front of the chair
      if (key === "person") { v3.y += 0.75; v3.z += 0.3; }
      else v3.y += key === "cloud" ? -0.65 : 0.95;
      v3.applyMatrix4(group.matrixWorld).project(camera);
      const x = (v3.x * 0.5 + 0.5) * width, y = (-v3.y * 0.5 + 0.5) * height;
      t.style.transform = `translate(${x.toFixed(1)}px, ${y.toFixed(1)}px) translate(-50%, ${key === "cloud" ? "0" : "-100%"})`;
      const show = v3.z < 1 && x > 0 && x < width && y > 0 && y < height && (current === "overview" || t.classList.contains("is-active") || key === "cloud");
      t.classList.toggle("is-visible", show);
    }
  }

  // --- loop: renders only when something moves, and never while the tab is hidden
  let last = performance.now() / 1000;
  let elapsed = 0;
  function frame() {
    requestAnimationFrame(frame);
    const now = performance.now() / 1000;
    const dt = Math.min(now - last, 0.05);
    last = now;
    if (document.hidden) return;
    const live = !isPaused();
    if (live) {
      elapsed += dt;
      group.rotation.y += dt * (current === "overview" ? 0.05 : 0.008);
      parts.agent.g.rotation.y -= dt * 0.15;
      // typing: the hands bob on the keyboard and the head nods a little
      personHands.position.y = Math.sin(elapsed * 6) * 0.02;
      personHead.rotation.x = Math.sin(elapsed * 1.4) * 0.06;
      links.forEach((l) => {
        const arr = l.pts.geometry.attributes.position;
        for (let i = 0; i < 3; i++) { const t = ((elapsed * l.speed + i / 3) % 1); l.curve.getPoint(t, v3); arr.setXYZ(i, v3.x, v3.y, v3.z); }
        arr.needsUpdate = true;
        l.pts.visible = l.v > 0.02;
      });
      needsRender = true;
    }
    if (!needsRender) return;
    group.updateMatrixWorld(true);
    renderer.render(scene, camera);
    placeTags();
    needsRender = false;
  }

  camera.position.set(...FOCUS.overview.cam); look.set(0, 0, 0); camera.lookAt(look);
  applyAll();
  focus("overview");
  canvas.addEventListener("webglcontextlost", (e) => { e.preventDefault(); canvas.style.display = "none"; });
  frame();

  return {
    focus,
    view,
    refresh: () => { applyView(); needsRender = true; },
    redraw: () => { needsRender = true; },
  };
}
