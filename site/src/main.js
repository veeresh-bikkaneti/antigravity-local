import "@fontsource/shippori-mincho/latin-500.css";
import "@fontsource/atkinson-hyperlegible-next/400.css";
import "@fontsource/atkinson-hyperlegible-next/700.css";
import "./styles.css";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(ScrollTrigger);

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const root = document.documentElement;
const status = $("#status");
const say = (msg) => { status.textContent = ""; requestAnimationFrame(() => { status.textContent = msg; }); };

/* ---- motion: respects the OS setting, and the visitor can pause or resume at any time ---- */
const reduce = matchMedia("(prefers-reduced-motion: reduce)");
const state = { paused: reduce.matches };
const isPaused = () => state.paused;
const toggle = $("#motion-toggle");
let scene = null;
function renderMotion() {
  toggle.setAttribute("aria-pressed", String(state.paused));
  root.classList.toggle("motion-off", state.paused);
  scene?.redraw();
}
toggle.addEventListener("click", () => { state.paused = !state.paused; renderMotion(); say(state.paused ? "Motion paused" : "Motion playing"); });
reduce.addEventListener("change", (e) => { state.paused = e.matches; renderMotion(); });
renderMotion();

/* ---- copy buttons ---- */
for (const box of $$(".code")) {
  const btn = $(".copy", box);
  const code = $("code", box);
  btn.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(code.textContent.trim());
      btn.textContent = "Copied";
      say("Copied to clipboard");
    } catch {
      const range = document.createRange();
      range.selectNodeContents(code);
      const sel = getSelection();
      sel.removeAllRanges();
      sel.addRange(range);
      btn.textContent = "Selected";
      say("Selected. Press Ctrl+C or Cmd+C to copy");
    }
    setTimeout(() => { btn.textContent = "Copy"; }, 1600);
  });
}

/* ---- architecture tabs: a diagram loads only when the section is near the screen ---- */
const tabs = $$('[role="tab"]');
const frame = $("#diagram");
const panel = $("#panel");
const note = $("#diagram-note");
const openLink = $("#diagram-open");
let selected = tabs[0];
let frameLoaded = false;

function selectTab(tab, moveFocus = false) {
  selected = tab;
  for (const t of tabs) {
    const on = t === tab;
    t.setAttribute("aria-selected", String(on));
    t.tabIndex = on ? 0 : -1;
  }
  panel.setAttribute("aria-labelledby", tab.id);
  frame.title = `${tab.dataset.title} diagram`;
  note.textContent = tab.dataset.note;
  openLink.href = tab.dataset.src;
  if (frameLoaded) frame.src = tab.dataset.src;
  if (moveFocus) tab.focus();
}
tabs.forEach((tab, i) => {
  tab.addEventListener("click", () => selectTab(tab));
  tab.addEventListener("keydown", (e) => {
    const next = { ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: tabs.length - 1 }[e.key];
    if (next === undefined) return;
    e.preventDefault();
    selectTab(tabs[(next + tabs.length) % tabs.length], true);
  });
});
new IntersectionObserver((entries, obs) => {
  if (entries.some((e) => e.isIntersecting)) {
    frameLoaded = true;
    frame.src = selected.dataset.src;
    obs.disconnect();
  }
}, { rootMargin: "900px 0px" }).observe($("#architecture"));

/* ---- scroll story: the page works without any of this; it only adds the highlighting ---- */
const steps = $$(".step");
function activate(step) {
  $$(".step.is-active").forEach((s) => s.classList.remove("is-active"));
  step?.classList.add("is-active");
  scene?.focus(step ? step.dataset.focus : "overview");
}
const slide = (ox) => {
  if (!scene) return;
  gsap.to(scene.view, { ox, duration: isPaused() ? 0 : 1.8, ease: "sine.inOut", onUpdate: scene.refresh });
};

for (const step of steps) {
  ScrollTrigger.create({ trigger: step, start: "top 62%", end: "bottom 38%", onToggle: (self) => { if (self.isActive) activate(step); } });
}
/* ---- section zoom: as each block comes into view, the camera zooms to the part
   of the machine it is about. The guide steps above still win inside the guide.
   Each trigger fires once when the section top crosses the line, so two sections
   never fight over the camera. With motion paused (or reduced motion), focus()
   jumps instead of gliding, so the text stays readable with no animation at all. ---- */
const sectionFocus = [
  ["#game", "person", 0],
  [".pillars", "machine", 0],
  ["#limits", "agent", 0],
  ["#faq", "chat", 0],
  ["footer", "overview", -0.24],
];
for (const [sel, focusName, ox] of sectionFocus) {
  const zoom = () => { $$(".step.is-active").forEach((s) => s.classList.remove("is-active")); scene?.focus(focusName); slide(ox); };
  ScrollTrigger.create({ trigger: sel, start: "top 55%", onEnter: zoom, onEnterBack: zoom });
}
ScrollTrigger.create({ trigger: ".hero", start: "top top", end: "bottom 55%", onToggle: (self) => { if (self.isActive) { activate(null); slide(-0.24); } } });
ScrollTrigger.create({ trigger: ".guide", start: "top 70%", end: "bottom 30%", onToggle: (self) => { if (self.isActive) slide(0.2); } });
ScrollTrigger.create({ trigger: "#architecture", start: "top 85%", end: "bottom 30%", onToggle: (self) => { document.body.classList.toggle("dim-stage", self.isActive); if (self.isActive) { activate(null); slide(0); } } });

/* ---- the 3D drawing loads after the page has painted ---- */
async function boot() {
  const canvas = $("#stage");
  try {
    const { start } = await import("./scene.js");
    scene = start({ canvas, tags: $$(".tag"), isPaused });
    const rect = $(".guide").getBoundingClientRect();
    const inGuide = rect.top < innerHeight * 0.7 && rect.bottom > innerHeight * 0.3;
    scene.view.ox = inGuide ? 0.2 : -0.24;
    scene.refresh();
    scene.focus($(".step.is-active")?.dataset.focus ?? "overview");
    ScrollTrigger.refresh();
  } catch (err) {
    console.warn("The 3D drawing is unavailable; the page still works without it.", err);
    canvas.remove();
    $("#labels")?.remove();
  }
}
if ("requestIdleCallback" in window) requestIdleCallback(boot, { timeout: 1500 });
else setTimeout(boot, 300);
