import { Button } from "../../components/ui/Button/Button.jsx";
import { Dropdown } from "../../components/ui/Dropdown/Dropdown.jsx";
import { ErrorBanner } from "../../components/feedback/ErrorBanner/ErrorBanner.jsx";
import { useModelItems } from "../ollama/ModelSelect/ModelSelect.jsx";
import { useApp } from "../../context/AppContext.jsx";
import styles from "./failures.module.css";

export function host(url) {
  try {
    return new URL(url).host;
  } catch {
    return "localhost:11434";
  }
}

export function RetryButton({ onClick }) {
  return <Button icon="refresh" onClick={onClick}>Retry</Button>;
}

function ModelChooser({ onRetry }) {
  const items = useModelItems(() => onRetry()).filter((item) => item !== "separator" && !item.footer);
  return (
    <Dropdown align="right" items={items} trigger={({ open, toggle }) => (
      <Button icon="cpu" aria-haspopup="listbox" aria-expanded={open} onClick={toggle}>Change model</Button>
    )} />
  );
}

export function FailureBanner({ kind, onRetry }) {
  const { ollama, model, refreshStatus } = useApp();

  if (kind === "ollama") {
    return (
      <ErrorBanner title="Ollama is unavailable"
        action={<RetryButton onClick={async () => { if (await refreshStatus()) onRetry(); }} />}>
        Check that the service is running on {host(ollama.url)}.
      </ErrorBanner>
    );
  }
  if (kind === "model") {
    return (
      <div className={styles.failure}>
        <ErrorBanner title={`The model ${model} was not found`} action={<ModelChooser onRetry={onRetry} />}>
          Install it with <code>ollama pull {model}</code> or choose another model.
        </ErrorBanner>
        <p className={styles.kept}>Your message is kept. It will be sent to the new model.</p>
      </div>
    );
  }
  if (kind === "limit") {
    return (
      <ErrorBanner title="This conversation is too long"
        action={<Button icon="plus" to="/chat">New chat</Button>}>
        The context is over the token limit, even after summarizing. Continue in a new chat.
      </ErrorBanner>
    );
  }
  return (
    <ErrorBanner title="The answer could not be generated" action={<RetryButton onClick={onRetry} />}>
      Network error. Your message is kept.
    </ErrorBanner>
  );
}
