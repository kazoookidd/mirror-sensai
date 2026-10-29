import { cx } from "../../../lib/cx.js";
import styles from "./Badge.module.css";

const STATUSES = {
  indexed: { label: "Indexed", tone: "success" },
  outdated: { label: "Outdated", tone: "neutral" },
  not_indexed: { label: "Not indexed", tone: "neutral" },
  pending: { label: "Pending", tone: "accent" },  // leave requests [M1]
  approved: { label: "Approved", tone: "success" },
  refused: { label: "Refused", tone: "danger" },
  cancelled: { label: "Cancelled", tone: "neutral" },
};

export function Dot({ tone = "success" }) {
  return <span className={cx(styles.dot, styles[`dot_${tone}`])} />;
}

export function StatusBadge({ status }) {
  const badge = STATUSES[status] ?? STATUSES.not_indexed;
  return (
    <span className={cx(styles.badge, styles[badge.tone])}>
      <Dot tone={badge.tone} />
      {badge.label}
    </span>
  );
}

export function RoleBadge({ className }) {
  return <span className={cx(styles.badge, styles.accent, className)} title="HR account">HR</span>;
}
