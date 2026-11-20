// The eight guide steps, in guide order - the single source of truth shared
// by the 3D scene (src/scene.js), the stack readout (src/main.js), and the
// drift checker (scripts/check-steps.mjs). Never re-declare step data in
// those files. Guide order: focus key, step name, short label, nameplate,
// data-anchor tag in site/index.html.
export const STEPS = [
  { key: "ollama", name: "Install Ollama", short: "Ollama", plate: "OLLAMA", anchor: "ollama" },
  { key: "model", name: "Choose a model", short: "Qwen model", plate: "QWEN2.5-CODER:14B", anchor: "model" },
  { key: "repo", name: "Clone the repo and run setup", short: "Repo · run.bat", plate: "REPO · RUN.BAT", anchor: "repo" },
  { key: "app", name: "Use your model in a coding app", short: "Coding app", plate: "CODING APP · OLLAMA LAUNCH", anchor: "app" },
  { key: "venv", name: "Activate the virtual environment", short: ".venv terminal", plate: ".VENV · TERMINAL", anchor: "venv" },
  { key: "agent", name: "Chat with your agent", short: "Agent", plate: "ANTIGRAVITY AGENT", anchor: "agent" },
  { key: "job", name: "Give it one job", short: "One job · Gate", plate: "HARNESS · POLICY GATE", anchor: "job" },
  { key: "editor", name: "Use it from your editor or the browser", short: "Editor", plate: "EDITOR </>", anchor: "editor" },
];
