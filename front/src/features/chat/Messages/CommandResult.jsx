import { cx } from "../../../lib/cx.js";
import { StreamingIndicator } from "./StreamingIndicator.jsx";
import styles from "./Messages.module.css";

export function CommandResult({ text, output, error, pending }) {
  return (
    <div className={styles.command}>
      <p className={styles.commandLine}><span className={styles.prompt}>&gt;</span> {text}</p>
      {pending
        ? <StreamingIndicator label="Running" />
        : <pre className={cx(styles.output, error && styles.outputError)}>{error ?? (output || "Done.")}</pre>}
    </div>
  );
}
