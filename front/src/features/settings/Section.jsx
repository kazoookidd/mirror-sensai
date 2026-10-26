import { cx } from "../../lib/cx.js";
import styles from "./Section.module.css";

export function Section({ title, description, children }) {
  return (
    <section className={styles.card}>
      <header className={styles.header}>
        <h2 className="text-heading">{title}</h2>
        {description && <p className={styles.description}>{description}</p>}
      </header>
      {children}
    </section>
  );
}

export function Setting({ name, description, inline, className, children }) {
  return (
    <div className={cx(styles.setting, inline && styles.inline, className)}>
      {name && (
        <div className={styles.label}>
          <p className={styles.name}>{name}</p>
          {description && <p className={styles.description}>{description}</p>}
        </div>
      )}
      <div className={styles.control}>{children}</div>
    </div>
  );
}
