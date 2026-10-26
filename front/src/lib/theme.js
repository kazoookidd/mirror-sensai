const STORAGE_KEY = "sensai.theme";
const THEMES = ["light", "dark", "system"];
const systemDark = window.matchMedia("(prefers-color-scheme: dark)");

export function getTheme() {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    return THEMES.includes(saved) ? saved : "system";
  } catch {
    return "system";
  }
}

function apply(choice) {
  const dark = choice === "dark" || (choice === "system" && systemDark.matches);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
}

export function setTheme(choice) {
  try {
    localStorage.setItem(STORAGE_KEY, choice);
  } catch {
    // Private browsing: the choice still applies to this visit.
  }
  apply(choice);
}

export function watchSystemTheme() {
  systemDark.addEventListener("change", () => apply(getTheme()));
}
