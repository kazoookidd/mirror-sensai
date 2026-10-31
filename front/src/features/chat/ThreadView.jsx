import { useLayoutEffect, useRef } from "react";
import { Icon } from "../../components/ui/Icon/Icon.jsx";
import { useApp } from "../../context/AppContext.jsx";
import { AssistantMessage } from "./Messages/AssistantMessage.jsx";
import { CommandResult } from "./Messages/CommandResult.jsx";
import { UserMessage } from "./Messages/UserMessage.jsx";
import { FailureBanner } from "./failures.jsx";
import styles from "./ThreadView.module.css";

const STICK_DISTANCE = 160;

export function ThreadView({ messages, versions, busy, offline, composer, toolbar, onRetry, onEdit, onRegenerate, onVersion, onCommand }) {
  const scroller = useRef(null);
  const versionAt = Object.fromEntries(versions.map((version) => [version.index, version]));
  const stick = useRef(true);

  useLayoutEffect(() => {
    if (stick.current) scroller.current.scrollTop = scroller.current.scrollHeight;
  }, [messages]);

  const onScroll = () => {
    const element = scroller.current;
    stick.current = element.scrollHeight - element.scrollTop - element.clientHeight < STICK_DISTANCE;
  };

  const { showSources } = useApp();
  return (
    <div className={styles.chat}>
      {toolbar && <div className={styles.toolbar}>{toolbar}</div>}
      <div ref={scroller} className={styles.thread} onScroll={onScroll}>
        <div className={styles.messages} role="log" aria-live="polite">
          {messages.map((message) => {
            if (message.role === "user") {
              return <UserMessage key={message.id} message={message} busy={busy} offline={offline} onEdit={onEdit} onVersion={onVersion}
                version={message.saved ? versionAt[message.position] : undefined} />;
            }
            if (message.role === "failure") return <FailureBanner key={message.id} kind={message.kind} onRetry={() => onRetry(message)} />;
            if (message.role === "command") return <CommandResult key={message.id} {...message} />;
            return <AssistantMessage key={message.id} model={message.model} text={message.text} steps={message.steps} sources={message.sources} showSources={showSources} busy={busy || offline}
              streaming={message.streaming} stopped={message.stopped} confirmation={message.confirmation} onCommand={onCommand}
              onRegenerate={message.saved ? () => onRegenerate(message) : undefined} />;
          })}
        </div>
      </div>
      <div className={styles.dock}>
        <div className={styles.column}>{composer}</div>
        <p className="privacy-note desktop-only"><Icon name="cpu" size={14} />Local model · chats and documents stay on this machine</p>
      </div>
    </div>
  );
}
