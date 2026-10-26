import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Icon } from "../../components/ui/Icon/Icon.jsx";
import { IconButton } from "../../components/ui/IconButton/IconButton.jsx";
import { TestTag } from "../../components/feedback/TestTag/TestTag.jsx";
import { historyDate, parseUtc, plainText } from "../../lib/format.js";
import { EditableTitle } from "./EditableTitle.jsx";
import styles from "./HistoryRow.module.css";

export function HistoryRow({ conversation, actions }) {
  const navigate = useNavigate();
  const [editing, setEditing] = useState(false);
  const stop = (handler) => (event) => {
    event.stopPropagation();
    handler();
  };

  return (
    <li className={styles.row} onClick={() => !editing && navigate(`/chat/${conversation.id}`)}>
      <div className={styles.content}>
        <EditableTitle as="a" href={`#/chat/${conversation.id}`} className={styles.title} title={conversation.title}
          editing={editing} onDone={(title) => { setEditing(false); if (title) actions.rename(conversation, title); }} />
        <p className={styles.preview}>{plainText(conversation.preview)}</p>
      </div>
      <div className={styles.model} title="[TEST] The model used is not saved yet">
        <Icon name="cpu" size={14} /><TestTag />
      </div>
      <p className={styles.date}>{historyDate(parseUtc(conversation.updated_at))}</p>
      <div className={styles.actions}>
        <IconButton icon="pencil" label={`Rename ${conversation.title}`} onClick={stop(() => setEditing(true))} />
        <IconButton icon="trash" label={`Delete ${conversation.title}`} onClick={stop(() => actions.remove(conversation))} />
      </div>
    </li>
  );
}
