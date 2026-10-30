import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { cx } from "../../../lib/cx.js";
import styles from "./Dropdown.module.css";

const OPTION_HEIGHT = 40;

function moveFocus(menu, step) {
  const options = [...menu.querySelectorAll("[role=option]")];
  const index = options.indexOf(document.activeElement);
  options[(index + step + options.length) % options.length]?.focus();
}

function floatingPosition(anchor, align, placement, count) {
  const box = anchor.getBoundingClientRect();
  const height = count * OPTION_HEIGHT;
  const up = placement === "top" || (box.bottom + height > window.innerHeight && box.top > height);
  return {
    position: "fixed",
    ...(up ? { top: "auto", bottom: window.innerHeight - box.top + 4 } : { top: box.bottom + 4 }),
    ...(align === "right" ? { right: window.innerWidth - box.right } : { left: box.left }),
  };
}

export function Dropdown({ trigger, items, align = "left", placement = "bottom", compact, block, floating, className }) {
  const [open, setOpen] = useState(false);
  const anchor = useRef(null);
  const menu = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    (menu.current.querySelector("[aria-selected=true]") ?? menu.current.querySelector("[role=option]"))?.focus();
    const onPointer = (event) => {
      if (!anchor.current.contains(event.target) && !menu.current?.contains(event.target)) setOpen(false);
    };
    const onScroll = (event) => {
      if (floating && !menu.current?.contains(event.target)) setOpen(false);
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
    window.addEventListener("scroll", onScroll, true);
    window.addEventListener("resize", onScroll);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("scroll", onScroll, true);
      window.removeEventListener("resize", onScroll);
    };
  }, [open, floating]);

  const choose = (item) => {
    setOpen(false);
    item.onSelect();
  };

  const list = open && (
    <div ref={menu} className={cx(styles.menu, styles[align], styles[placement], compact && styles.compact)} role="listbox"
      style={floating ? floatingPosition(anchor.current, align, placement, items.length) : undefined}>
      {items.map((item, index) => {
        if (item === "separator")
          return <div key={index} className={styles.separator} role="separator" />;
        if (item.footer)
          return <div key={index} className={styles.footer}>{item.footer}</div>;
        if (item.heading)
          return <div key={index} className={styles.heading}>{item.heading}</div>;
        return (
          <button key={index} className={cx(styles.option, item.danger && styles.danger)} type="button" role="option" title={item.hint}
            aria-selected={Boolean(item.selected)} onClick={() => choose(item)}>
            <span className={styles.name}>{item.icon}<span className="truncate">{item.label}</span></span>
            {item.meta && <span className={styles.meta}>{item.meta}</span>}
          </button>
        );
      })}
    </div>
  );

  return (
    <div className={cx(styles.anchor, block && styles.block, className)} ref={anchor}>
      {trigger({ open, toggle: () => setOpen((value) => !value) })}
      {floating && list ? createPortal(list, document.body) : list}
    </div>
  );
}
