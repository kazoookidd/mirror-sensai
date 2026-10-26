import { Markdown } from "../../../lib/markdown.jsx";
import { Brand } from "../../../components/ui/Brand/Brand.jsx";
import { MessageActions } from "./MessageActions.jsx";
import { StreamingIndicator } from "./StreamingIndicator.jsx";
import styles from "./Messages.module.css";

export function AssistantMessage({ model, text, streaming }) {
  return (
    <article className={styles.assistant}>
      <header className={styles.header}>
        <Brand small />
        {model && <span className={styles.model}>{model}</span>}
      </header>
      {text && <Markdown text={text} />}
      {streaming ? <StreamingIndicator /> : <MessageActions text={text} />}
    </article>
  );
}
