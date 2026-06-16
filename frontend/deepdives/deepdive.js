document.querySelectorAll(".copy-link").forEach((btn) => {
  btn.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      const orig = btn.textContent;
      btn.textContent = "Link copied";
      setTimeout(() => { btn.textContent = orig; }, 1000);
    } catch {
      const orig = btn.textContent;
      btn.textContent = "Copy failed";
      setTimeout(() => { btn.textContent = orig; }, 1000);
    }
  });
});
