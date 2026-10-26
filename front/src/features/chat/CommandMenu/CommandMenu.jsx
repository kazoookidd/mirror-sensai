import { useEffect, useRef } from "react";
import { cx } from "../../../lib/cx.js";
import styles from "./CommandMenu.module.css";

export function CommandMenu({ commands, highlighted, onChoose, onHighlight }) {
  const list = useRef(null);

  useEffect(() => {
    list.current?.children[highlighted]?.scrollIntoView({ block: "nearest" });
  }, [highlighted]);

  return (
    <div className={styles.menu}>
      <p className={styles.label}>Commands</p>
      <ul ref={list} className={styles.list} role="listbox" aria-label="Commands">
        {commands.map((command, index) => (
          <li key={command.name} role="option" aria-selected={index === highlighted}
            className={cx(styles.item, index === highlighted && styles.highlighted)}
            onMouseEnter={() => onHighlight(index)}
            onMouseDown={(event) => { event.preventDefault(); onChoose(command); }}>
            <span className={styles.name}>
              {command.name}{command.args && <span className={styles.args}> {command.args}</span>}
            </span>
            <span className={styles.description}>{command.description}</span>
          </li>
        ))}
      </ul>
      <p className={styles.hint}>↑ ↓ to move · Enter to run · Tab to complete · Esc to close</p>
    </div>
  );
}
