import { Link } from "react-router-dom";
import { cx } from "../../../lib/cx.js";
import { Icon } from "../Icon/Icon.jsx";
import styles from "./IconButton.module.css";

export function IconButton({ icon, iconSize = 16, iconDisplay, label, variant = "ghost", active, test, to, className, ...props }) {
  const shared = {
    className: cx(styles.button, styles[variant], active && styles.active, className),
    "aria-label": test ? `${label} (not available yet)` : label,
    title: test ? `[TEST] ${label}: not available yet` : label,
    "data-test-corner": test ? "" : undefined,
  };
  const content = <Icon name={icon} size={iconSize} display={iconDisplay ?? iconSize} />;
  if (to) return <Link to={to} {...shared} {...props}>{content}</Link>;
  return <button type="button" disabled={test} {...shared} {...props}>{content}</button>;
}
