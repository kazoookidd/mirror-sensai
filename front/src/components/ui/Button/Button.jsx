import { Link } from "react-router-dom";
import { cx } from "../../../lib/cx.js";
import { Icon } from "../Icon/Icon.jsx";
import styles from "./Button.module.css";

export function Button({ variant = "secondary", large, block, icon, iconSize = 16, to, className, children, ...props }) {
  const classes = cx(styles.button, styles[variant], large && styles.large, block && styles.block, className);
  const content = <>{icon && <Icon name={icon} size={iconSize} />}{children}</>;
  if (to) return <Link className={classes} to={to} {...props}>{content}</Link>;
  return <button className={classes} type="button" {...props}>{content}</button>;
}
