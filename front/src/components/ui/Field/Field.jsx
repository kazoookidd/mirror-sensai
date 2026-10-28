import { forwardRef, useState } from "react";
import { cx } from "../../../lib/cx.js";
import { Icon } from "../Icon/Icon.jsx";
import styles from "./Field.module.css";

export const InputBox = forwardRef(function InputBox({ leading, small, mono, error, className, trailing, ...props }, ref) {
  return (
    <label className={cx(styles.box, small && styles.small, error && styles.error, className)}>
      {leading && <Icon name={leading[0]} size={leading[1]} display={leading[2] ?? leading[1]} />}
      <input ref={ref} className={cx(styles.control, mono && styles.mono)} aria-invalid={Boolean(error)} {...props} />
      {trailing}
    </label>
  );
});

export const Field = forwardRef(function Field({ label, id, leading, reveal, type = "text", error, help, ...props }, ref) {
  const [shown, setShown] = useState(false);
  const toggle = reveal && (
    <button className={styles.trailing} type="button" onClick={() => setShown((value) => !value)}
      aria-label={shown ? "Hide password" : "Show password"}>
      <Icon name={shown ? "eye-off" : "eye"} size={20} display={16} />
    </button>
  );
  return (
    <div className={styles.field}>
      <label className={styles.label} htmlFor={id}>{label}</label>
      <InputBox ref={ref} id={id} leading={leading} error={error} trailing={toggle}
        type={reveal && shown ? "text" : type} aria-describedby={help ? `${id}-help` : undefined} {...props} />
      {help && <p id={`${id}-help`} className={cx(styles.help, error && styles.helpError)}>{help}</p>}
    </div>
  );
});

export function FieldLabel({ htmlFor, children, aside }) {
  return (
    <div className={styles.labelRow}>
      <label className={styles.label} htmlFor={htmlFor}>{children}</label>
      {aside}
    </div>
  );
}

export function FieldHelp({ children }) {
  return <p className={styles.help}>{children}</p>;
}
