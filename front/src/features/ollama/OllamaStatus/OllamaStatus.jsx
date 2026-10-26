import { useApp } from "../../../context/AppContext.jsx";
import { cx } from "../../../lib/cx.js";
import { Dot } from "../../../components/ui/Badge/Badge.jsx";
import styles from "./OllamaStatus.module.css";

export function OllamaStatus({ online = "Ollama", offline = "Ollama offline", className }) {
  const { ollama } = useApp();
  return (
    <span className={cx(styles.status, !ollama.online && styles.offline, className)} role="status">
      <Dot tone={ollama.online ? "success" : "error"} />
      {ollama.online ? online : offline}
    </span>
  );
}
