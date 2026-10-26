import { useLayoutEffect, useRef } from "react";
import { Icon } from "../../components/ui/Icon/Icon.jsx";
import { AssistantMessage } from "./Messages/AssistantMessage.jsx";
import { CommandResult } from "./Messages/CommandResult.jsx";
import { UserMessage } from "./Messages/UserMessage.jsx";
import { FailureBanner } from "./failures.jsx";
import styles from "./ThreadView.module.css";

const STICK_DISTANCE = 160;

export function ThreadView({ messages, composer, onRetry }) {
  const scroller = useRef(null);
  const stick = useRef(true);

  useLayoutEffect(() => {
    if (stick.current) scroller.current.scrollTop = scroller.current.scrollHeight;
  }, [messages]);

  const onScroll = () => {
    const element = scroller.current;
    stick.current = element.scrollHeight - element.scrollTop - element.clientHeight < STICK_DISTANCE;
  };

  return (
    <div className={styles.chat}>
      <div ref={scroller} className={styles.thread} onScroll={onScroll}>
        <div className={styles.messages} role="log" aria-live="polite">
          {messages.map((message) => {
            if (message.role === "user") return <UserMessage key={message.id} text={message.text} />;
            if (message.role === "failure") return <FailureBanner key={message.id} kind={message.kind} onRetry={() => onRetry(message)} />;
            if (message.role === "command") return <CommandResult key={message.id} {...message} />;
            return <AssistantMessage key={message.id} model={message.model} text={message.text} streaming={message.streaming} />;
          })}
        </div>
      </div>
      <div className={styles.dock}>
        <div className={styles.column}>{composer}</div>
        <p className="privacy-note desktop-only"><Icon name="cpu" size={14} />Local model · HR data stays on your machine</p>
      </div>
    </div>
  );
}
