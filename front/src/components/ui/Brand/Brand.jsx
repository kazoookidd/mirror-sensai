import { cx } from "../../../lib/cx.js";
import styles from "./Brand.module.css";

export function Brand({ small }) {
  return (
    <span className={cx(styles.brand, small && styles.small)}>
      SENSAI<span className={styles.mark}>_</span>
    </span>
  );
}
