import { Markdown } from "../../../lib/markdown.jsx";
import { Brand } from "../../../components/ui/Brand/Brand.jsx";
import { Icon } from "../../../components/ui/Icon/Icon.jsx";
import { MessageActions } from "./MessageActions.jsx";
import { StreamingIndicator } from "./StreamingIndicator.jsx";
import styles from "./Messages.module.css";

export function AssistantMessage({ model, text, streaming, stopped, busy, onRegenerate }) {
  return (
    <article className={styles.assistant}>
      <header className={styles.header}>
        <Brand small />
        {model && <span className={styles.model}>{model}</span>}
      </header>
      {text && <Markdown text={text} />}
      {stopped && (
        <p className={styles.stopped}>
          <Icon name="stop" size={16} display={12} />
          {text ? "Answer stopped" : "Answer stopped before any text: nothing was saved."}
        </p>
      )}
      {streaming ? <StreamingIndicator /> : text && <MessageActions text={text} busy={busy} onRegenerate={onRegenerate} />}
    </article>
  );
}
