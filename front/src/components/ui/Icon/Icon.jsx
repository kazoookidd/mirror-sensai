import styles from "./Icon.module.css";

export function Icon({ name, size = 16, display = size, className = "" }) {
  return (
    <span
      className={`${styles.icon} ${className}`.trim()}
      aria-hidden="true"
      style={{ "--icon": `url("/assets/icons/${name}-${size}.svg")`, "--icon-size": `${display}px` }}
    />
  );
}
