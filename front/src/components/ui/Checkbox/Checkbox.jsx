import styles from "./Checkbox.module.css";

export function Checkbox(props) {
  return <input className={styles.checkbox} type="checkbox" {...props} />;
}
