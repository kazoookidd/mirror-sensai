import { useState } from "react";
import { Button } from "../../../components/ui/Button/Button.jsx";
import { Icon } from "../../../components/ui/Icon/Icon.jsx";
import { IconButton } from "../../../components/ui/IconButton/IconButton.jsx";
import styles from "./Messages.module.css";

function Versions({ version, onVersion, busy }) {
  const { current, conversations } = version;
  const go = (step) => onVersion(conversations[current - 1 + step]);
  return (
    <span className={styles.versions}>
      <IconButton icon="chevron-left" label="Previous version" disabled={busy || current === 1} onClick={() => go(-1)} />
      <span className={styles.versionCount}>{current}/{conversations.length}</span>
      <IconButton icon="chevron-left" label="Next version" className={styles.next}
        disabled={busy || current === conversations.length} onClick={() => go(1)} />
    </span>
  );
}

function Editor({ text, onCancel, onSend }) {
  const [value, setValue] = useState(text);
  const send = () => value.trim() && onSend(value.trim());
  return (
    <div className={styles.editor}>
      <textarea className={styles.editorInput} value={value} rows={3} autoFocus aria-label="Edit your message"
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Escape") onCancel();
          if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
            event.preventDefault();
            send();
          }
        }} />
      <div className={styles.editorActions}>
        <span className={styles.editorHint}><Icon name="history" size={18} display={14} />Continues in a new branch</span>
        <Button onClick={onCancel}>Cancel</Button>
        <Button variant="primary" disabled={!value.trim() || value.trim() === text} onClick={send}>Send</Button>
      </div>
    </div>
  );
}

export function UserMessage({ message, version, busy, offline, onEdit, onVersion }) {
  const [editing, setEditing] = useState(false);

  if (editing) {
    return <Editor text={message.text} onCancel={() => setEditing(false)}
      onSend={(text) => { setEditing(false); onEdit(message, text); }} />;
  }
  return (
    <div className={styles.userRow}>
      <p className={styles.bubble}>{message.text}</p>
      {(message.saved || version) && (
        <div className={styles.userTools}>
          {version && <Versions version={version} onVersion={onVersion} busy={busy} />}
          {message.saved && <IconButton icon="pencil" label="Edit" disabled={busy || offline} onClick={() => setEditing(true)} />}
        </div>
      )}
    </div>
  );
}
