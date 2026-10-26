import styles from "./Switch.module.css";

export function Switch(props) {
  return <input className={styles.switch} type="checkbox" role="switch" {...props} />;
}
