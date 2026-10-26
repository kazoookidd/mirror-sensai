import styles from "./Messages.module.css";

export function StreamingIndicator({ label = "Generating" }) {
  return (
    <div className={styles.streaming} role="status">
      <span className={styles.dots} aria-hidden="true"><span /><span /><span /></span>
      {label}
    </div>
  );
}
