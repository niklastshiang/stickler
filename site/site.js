// The site's only script (SPEC.md "Website"): what HTML and CSS cannot do. The copy buttons
// copy a command; the overview video holds still when the system asks for less motion.
// Without this script the commands stay selectable and the video keeps its pause button.
(() => {
  const lessMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const holdStill = () => {
    if (!lessMotion.matches) return;
    for (const video of document.querySelectorAll("video[autoplay]")) {
      video.pause();
      const toTheSheet = () => { video.currentTime = Math.max(0, video.duration - 1); };
      if (video.readyState >= 1) toTheSheet();
      else video.addEventListener("loadedmetadata", toTheSheet, { once: true });
    }
  };
  holdStill();
  lessMotion.addEventListener("change", holdStill);

  for (const button of document.querySelectorAll("button[data-copy]")) {
    const command = document.getElementById(button.dataset.copy);
    const status = document.getElementById(button.dataset.status);
    if (!command || !status || !navigator.clipboard) continue;
    button.hidden = false;
    button.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(command.textContent.trim());
        status.textContent = button.dataset.done;
      } catch {
        status.textContent = button.dataset.failed;
      }
    });
  }
})();
