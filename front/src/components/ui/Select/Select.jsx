import { cx } from "../../../lib/cx.js";
import { Dropdown } from "../Dropdown/Dropdown.jsx";
import { Icon } from "../Icon/Icon.jsx";
import styles from "./Select.module.css";

// `floating`: the list is drawn over the page, for a Select inside a box that clips (overflow: hidden).
export function Select({ label, value, leading, items, variant = "sm", align = "left", placement, block, floating, attention, onOpen }) {
  return (
    <Dropdown align={align} placement={placement} block={block} floating={floating} items={items} trigger={({ open, toggle }) => (
      <button
        type="button"
        className={cx(styles.select, styles[variant], block && styles.block, (open || attention) && styles.attention)}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={label}
        onClick={async () => {
          await onOpen?.();
          toggle();
        }}
      >
        <span className={styles.value}>
          {leading}
          <span className="truncate">{value}</span>
        </span>
        <Icon name="chevron-down" size={variant === "chip" ? 14 : 16} />
      </button>
    )} />
  );
}
