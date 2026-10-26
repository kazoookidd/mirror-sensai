import { Button } from "../../ui/Button/Button.jsx";
import { Icon } from "../../ui/Icon/Icon.jsx";
import styles from "./EmptyState.module.css";

export function EmptyState({ icon, iconSize, title, children, action }) {
  return (
    <div className={styles.state}>
      <div className={styles.icon}><Icon name={icon} size={iconSize} /></div>
      <p className="text-heading">{title}</p>
      <p className={styles.description}>{children}</p>
      {action && <Button icon="plus" to={action.to}>{action.label}</Button>}
    </div>
  );
}
