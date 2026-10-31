import { useState } from "react";
import { Markdown } from "../../../lib/markdown.jsx";
import { Brand } from "../../../components/ui/Brand/Brand.jsx";
import { Icon } from "../../../components/ui/Icon/Icon.jsx";
import { AgentTrace } from "./AgentTrace.jsx";
import { ConfirmationCard } from "./ConfirmationCard.jsx";
import { MessageActions } from "./MessageActions.jsx";
import { MessageSources } from "./MessageSources.jsx";
import { StreamingIndicator } from "./StreamingIndicator.jsx";
import styles from "./Messages.module.css";

export function AssistantMessage({ model, text, steps, sources, showSources, streaming, stopped, busy, readOnly, confirmation, onRegenerate, onCommand }) {
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const shown = showSources && !readOnly ? sources?.length ?? 0 : 0;
  return (
    <article className={styles.assistant}>
      <header className={styles.header}>
        <Brand small />
        {model && <span className={styles.model}>{model}</span>}
      </header>
      {steps?.length > 0 && <AgentTrace steps={steps} streaming={streaming} />}
      {confirmation
        ? <ConfirmationCard {...confirmation} busy={busy} onConfirm={() => onCommand("/confirm")} onCancel={() => onCommand("/cancel")} />
        : text && <Markdown text={text} />}
      {stopped && (
        <p className={styles.stopped}>
          <Icon name="stop" size={16} display={12} />
          {text ? "Answer stopped" : "Answer stopped before any text: nothing was saved."}
        </p>
      )}
      {streaming ? <StreamingIndicator /> : text && !readOnly && !confirmation && (
        <MessageActions text={text} busy={busy} onRegenerate={onRegenerate}
          sources={shown} sourcesOpen={sourcesOpen} onSources={() => setSourcesOpen(!sourcesOpen)} />
      )}
      {sourcesOpen && shown > 0 && !streaming && <MessageSources sources={sources} />}
    </article>
  );
}
