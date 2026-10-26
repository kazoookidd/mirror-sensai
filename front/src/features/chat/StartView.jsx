import { ErrorBanner } from "../../components/feedback/ErrorBanner/ErrorBanner.jsx";
import { Icon } from "../../components/ui/Icon/Icon.jsx";
import { useApp } from "../../context/AppContext.jsx";
import { cx } from "../../lib/cx.js";
import { RetryButton, host } from "./failures.jsx";
import styles from "./StartView.module.css";

const SUGGESTIONS = [
  { label: "Summarize the collective agreement", icon: "file-text" },
  { label: "Remote work rules", icon: "home" },
  { label: "Prepare an annual review", icon: "users" },
];

export function StartView({ composer, onSuggestion }) {
  const { ollama, refreshStatus } = useApp();
  return (
    <div className={styles.start}>
      <div className={styles.hero}>
        <h1 className="text-display">Hello, how can I help you?</h1>
        <p className={styles.subtitle}>Ask your HR questions or search the company documents.</p>
      </div>
      {!ollama.online && (
        <div className={styles.banner}>
          <ErrorBanner title="Ollama is unavailable" action={<RetryButton onClick={refreshStatus} />}>
            Check that the service is running on {host(ollama.url)}.
          </ErrorBanner>
        </div>
      )}
      <div className={styles.composer}>{composer}</div>
      <div className={cx(styles.suggestions, !ollama.online && styles.disabled)}>
        {SUGGESTIONS.map((item) => (
          <button key={item.label} className={styles.suggestion} type="button" onClick={() => onSuggestion(item.label)}>
            <Icon name={item.icon} size={16} />{item.label}
          </button>
        ))}
      </div>
      <p className={`privacy-note ${styles.privacy}`}>
        <Icon name="cpu" size={14} />
        <span className="desktop-only">Local model · HR data stays on your machine</span>
        <span className="mobile-only">Local model · HR data stays on this device</span>
      </p>
    </div>
  );
}
