import { defineConfig } from "vite";
import { cpSync, existsSync, mkdirSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));

// Copies the Archify diagrams from docs/diagrams into the build, so the page and the repo share one source.
function copyDiagrams() {
  return {
    name: "copy-archify-diagrams",
    closeBundle() {
      const from = resolve(here, "../docs/diagrams");
      const to = resolve(here, "dist/diagrams");
      if (!existsSync(from)) throw new Error("docs/diagrams not found; run the build from the repo checkout");
      mkdirSync(to, { recursive: true });
      cpSync(from, to, { recursive: true, filter: (src) => !src.endsWith(".json") });
    },
  };
}

export default defineConfig({
  // Relative base: the site is served from /antigravity-local/ on GitHub Pages.
  base: "./",
  build: { outDir: "dist", emptyOutDir: true, target: "es2022", chunkSizeWarningLimit: 700 },
  plugins: [copyDiagrams()],
});
