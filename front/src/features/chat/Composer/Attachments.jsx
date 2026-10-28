import { Icon } from "../../../components/ui/Icon/Icon.jsx";
import styles from "./Composer.module.css";

export function Attachments({ attachments, attaching }) {
  if (!attachments.length && !attaching.name && !attaching.error) return null;
  return (
    <div className={styles.attachments} aria-label="Files attached to this chat">
      {attachments.map((item) => (
        <span key={item.source} className={styles.attachment} title={`${item.source}: only used in this chat`}>
          <Icon name="file-text" size={14} /><span className="truncate">{item.source}</span>
        </span>
      ))}
      {attaching.name && (
        <span className={`${styles.attachment} ${styles.reading}`} role="status">
          <Icon name="file-text" size={14} /><span className="truncate">Reading {attaching.name}...</span>
        </span>
      )}
      {attaching.error && <p className={styles.attachError} role="alert">{attaching.error}</p>}
    </div>
  );
}
