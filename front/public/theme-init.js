// Applies the saved theme before the first paint, so the page never flashes.
(function () {
  var choice = "system";
  try {
    choice = localStorage.getItem("sensai.theme") || "system";
  } catch (error) {
    choice = "system";
  }
  var dark = choice === "dark" || (choice === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
})();
