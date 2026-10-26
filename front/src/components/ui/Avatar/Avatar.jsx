import { forwardRef } from "react";
import styles from "./Avatar.module.css";

export function initials(name) {
  const parts = String(name).split(/[\s._@-]+/).filter(Boolean);
  const letters = parts.length > 1 ? parts[0][0] + parts[1][0] : String(name).slice(0, 2);
  return letters.toUpperCase();
}

export const Avatar = forwardRef(function Avatar({ name, ...props }, ref) {
  return (
    <button ref={ref} className={styles.avatar} type="button" title={name} {...props}>
      {initials(name)}
    </button>
  );
});
