import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { shares } from "../../api/shares.js";
import { EmptyState } from "../../components/feedback/EmptyState/EmptyState.jsx";
import { Brand } from "../../components/ui/Brand/Brand.jsx";
import { Button } from "../../components/ui/Button/Button.jsx";
import { Icon } from "../../components/ui/Icon/Icon.jsx";
import { formatDate, parseUtc } from "../../lib/format.js";
import { ThemeToggle } from "../auth/ThemeToggle.jsx";
import { AssistantMessage } from "../chat/Messages/AssistantMessage.jsx";
import { UserMessage } from "../chat/Messages/UserMessage.jsx";
import styles from "./SharedPage.module.css";

export function SharedPage() {
  const { token } = useParams();
  const [shared, setShared] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    setShared(null);
    setError("");
    shares.open(token).then(setShared, (failure) => setError(failure.message));
  }, [token]);

  return (
    <div className={styles.page}>
      <header className={styles.bar}>
        <Link to="/chat" aria-label="SENSAI, home"><Brand /></Link>
        <div className={styles.barActions}>
          <ThemeToggle />
          <Button to="/chat">Open SENSAI</Button>
        </div>
      </header>
      <main className={styles.scroll}>
        {error && (
          <div className={styles.state}>
            <EmptyState icon="link" iconSize={16} title="Shared chat unavailable">{error}</EmptyState>
          </div>
        )}
        {shared && (
          <article className={styles.column}>
            <header className={styles.header}>
              <p className={styles.kicker}><Icon name="link" size={16} display={14} />Shared chat · read only</p>
              <h1 className="text-display">{shared.title}</h1>
              <p className={styles.meta}>
                Shared on {formatDate(parseUtc(shared.created_at))} · link expires on {formatDate(parseUtc(shared.expires_at))}
              </p>
            </header>
            <div className={styles.messages}>
              {shared.messages.map((message, index) => (message.role === "user"
                ? <UserMessage key={index} message={{ text: message.content }} />
                : <AssistantMessage key={index} text={message.content} readOnly />))}
            </div>
            <p className="privacy-note"><Icon name="cpu" size={14} />Answered by a local model with SENSAI</p>
          </article>
        )}
      </main>
    </div>
  );
}
