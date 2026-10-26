import { Icon } from "../../ui/Icon/Icon.jsx";
import styles from "./ErrorBanner.module.css";

export function ErrorBanner({ title, children, action }) {
  return (
    <div className={styles.banner} role="alert">
      <div className={styles.content}>
        <Icon name="alert" size={16} className={styles.icon} />
        <div className={styles.text}>
          <p className={styles.title}>{title}</p>
          <p className={styles.description}>{children}</p>
        </div>
      </div>
      {action}
    </div>
  );
}
