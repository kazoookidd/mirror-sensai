import { useApp } from "../../../context/AppContext.jsx";
import { cx } from "../../../lib/cx.js";
import { formatTokens } from "../../../lib/format.js";
import styles from "./ContextGauge.module.css";

const HIGH_USAGE = 0.85;

export function ContextGauge() {
  const { context } = useApp();
  if (!context.budget)
    return null;
  const ratio = Math.min(context.tokens / context.budget, 1);
  return (
    <span className={cx(styles.gauge, ratio > HIGH_USAGE && styles.high)}
      title={`Context: about ${context.tokens} of ${context.budget} tokens`}>
      <span className={styles.track}><span className={styles.used} style={{ width: `${ratio * 100}%` }} /></span>
      <span className={styles.label}>{formatTokens(context.tokens)} / {formatTokens(context.budget)}</span>
    </span>
  );
}
