import { useState } from "react";
import { IconButton } from "../../components/ui/IconButton/IconButton.jsx";
import { setTheme } from "../../lib/theme.js";

const isDark = () => document.documentElement.dataset.theme === "dark";

export function ThemeToggle({ className }) {
  const [dark, setDark] = useState(isDark);
  return (
    <IconButton icon={dark ? "sun" : "moon"} iconSize={14} label={dark ? "Light theme" : "Dark theme"}
      variant="outline" className={className}
      onClick={() => {
        setTheme(dark ? "light" : "dark");
        setDark(!dark);
      }} />
  );
}
