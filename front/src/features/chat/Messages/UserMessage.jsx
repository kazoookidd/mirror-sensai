import styles from "./Messages.module.css";

export function UserMessage({ text }) {
  return (
    <div className={styles.userRow}>
      <p className={styles.bubble}>{text}</p>
    </div>
  );
}
