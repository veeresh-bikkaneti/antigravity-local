// Script for the rendered guide pages (docs/*.html): fonts, site styles, and the Copy buttons.
import "@fontsource/shippori-mincho/latin-500.css";
import "@fontsource/atkinson-hyperlegible-next/400.css";
import "@fontsource/atkinson-hyperlegible-next/700.css";
import "./styles.css";
import "./docs.css";

for (const box of document.querySelectorAll(".code")) {
  const btn = box.querySelector(".copy");
  const code = box.querySelector("code");
  if (!btn || !code) continue;
  btn.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(code.textContent.trim());
      btn.textContent = "Copied";
    } catch {
      const range = document.createRange();
      range.selectNodeContents(code);
      const sel = getSelection();
      sel.removeAllRanges();
      sel.addRange(range);
      btn.textContent = "Selected";
    }
    setTimeout(() => { btn.textContent = "Copy"; }, 1600);
  });
}
