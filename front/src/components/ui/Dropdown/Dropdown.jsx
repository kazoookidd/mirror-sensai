import { useEffect, useRef, useState } from "react";
import { cx } from "../../../lib/cx.js";
import styles from "./Dropdown.module.css";

function moveFocus(menu, step) {
  const options = [...menu.querySelectorAll("[role=option]")];
  const index = options.indexOf(document.activeElement);
  options[(index + step + options.length) % options.length]?.focus();
}

export function Dropdown({ trigger, items, align = "left", placement = "bottom", compact, block, className }) {
  const [open, setOpen] = useState(false);
  const anchor = useRef(null);
  const menu = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    (menu.current.querySelector("[aria-selected=true]") ?? menu.current.querySelector("[role=option]"))?.focus();
    const onPointer = (event) => {
      if (!anchor.current.contains(event.target)) setOpen(false);
    };
    const onKey = (event) => {
      if (event.key === "Escape") {
        setOpen(false);
        anchor.current.querySelector("button")?.focus();
      }
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        moveFocus(menu.current, event.key === "ArrowDown" ? 1 : -1);
      }
    };
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const choose = (item) => {
    setOpen(false);
    item.onSelect();
  };

  return (
    <div className={cx(styles.anchor, block && styles.block, className)} ref={anchor}>
      {trigger({ open, toggle: () => setOpen((value) => !value) })}
      {open && (
        <div ref={menu} className={cx(styles.menu, styles[align], styles[placement], compact && styles.compact)} role="listbox">
          {items.map((item, index) => {
            if (item === "separator") return <div key={index} className={styles.separator} role="separator" />;
            if (item.footer) return <div key={index} className={styles.footer}>{item.footer}</div>;
            if (item.heading) return <div key={index} className={styles.heading}>{item.heading}</div>;
            return (
              <button key={index} className={cx(styles.option, item.danger && styles.danger)} type="button" role="option"
                aria-selected={Boolean(item.selected)} onClick={() => choose(item)}>
                <span className={styles.name}>{item.icon}<span className="truncate">{item.label}</span></span>
                {item.meta && <span className={styles.meta}>{item.meta}</span>}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
