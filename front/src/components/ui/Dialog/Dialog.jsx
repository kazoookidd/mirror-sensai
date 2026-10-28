import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { cx } from "../../../lib/cx.js";
import { IconButton } from "../IconButton/IconButton.jsx";
import styles from "./Dialog.module.css";

const FOCUSABLE = "a[href], button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex='-1'])";

export function Dialog({ title, onClose, className, children }) {
  const panel = useRef(null);
  const close = useRef(onClose);
  close.current = onClose;

  useEffect(() => {
    const opener = document.activeElement;
    panel.current.querySelector(FOCUSABLE)?.focus();
    const onKey = (event) => {
      // An open dropdown inside the dialog closes first.
      if (document.activeElement?.closest("[role=listbox]")) return;
      if (event.key === "Escape") close.current();
      if (event.key !== "Tab") return;
      const items = [...panel.current.querySelectorAll(FOCUSABLE)];
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      opener?.focus?.();
    };
  }, []);

  return createPortal(
    <div className={styles.overlay} onPointerDown={(event) => event.target === event.currentTarget && close.current()}>
      <div ref={panel} className={cx(styles.panel, className)} role="dialog" aria-modal="true" aria-label={title}>
        <IconButton icon="x" label="Close" className={styles.close} onClick={onClose} />
        {children}
      </div>
    </div>,
    document.body,
  );
}
