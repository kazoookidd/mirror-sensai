import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Icon } from "../../components/ui/Icon/Icon.jsx";
import { cx } from "../../lib/cx.js";
import { historyDate, parseUtc, plainText } from "../../lib/format.js";
import { EditableTitle } from "./EditableTitle.jsx";
import { useSwipe } from "./useSwipe.js";
import styles from "./HistoryItem.module.css";

export function HistoryItem({ conversation, actions }) {
  const navigate = useNavigate();
  const swipe = useSwipe();
  const [editing, setEditing] = useState(false);

  return (
    <li className={cx(styles.item, swipe.dragging && styles.dragging)} data-swipe-ignore="">
      <div className={styles.actions}>
        <button className={styles.action} type="button" onClick={() => { swipe.close(); setEditing(true); }}>
          <Icon name="pencil" size={18} />Rename
        </button>
        <button className={cx(styles.action, styles.danger)} type="button" onClick={() => actions.remove(conversation)}>
          <Icon name="trash" size={18} />Delete
        </button>
      </div>
      <div className={styles.content} style={{ transform: `translateX(${swipe.offset}px)` }} {...swipe.handlers}
        onClick={() => { if (!swipe.wasSwipe() && !editing && !swipe.offset) navigate(`/chat/${conversation.id}`); }}>
        <EditableTitle className={styles.title} title={conversation.title} editing={editing}
          onDone={(title) => { setEditing(false); if (title) actions.rename(conversation, title); }} />
        <p className={styles.preview}>{plainText(conversation.preview)}</p>
        <p className={styles.meta}>{historyDate(parseUtc(conversation.updated_at))}{conversation.model && ` · ${conversation.model}`}</p>
      </div>
    </li>
  );
}
