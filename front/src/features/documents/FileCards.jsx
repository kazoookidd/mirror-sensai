import { StatusBadge } from "../../components/ui/Badge/Badge.jsx";
import { Checkbox } from "../../components/ui/Checkbox/Checkbox.jsx";
import { fileType, formatShortDate, formatSize } from "../../lib/format.js";
import { DocumentMenu, QueryButton } from "./DocumentButtons.jsx";
import { FileName } from "./FileName.jsx";
import styles from "./FileCards.module.css";

function plural(count) {
  return count > 1 ? "s" : "";
}

export function FileCards({ items, selection, onToggle, actions, onAsk }) {
  return (
    <div className={`${styles.list} mobile-only`}>
      {selection.size > 0 && (
        <div className={styles.selectionBar}>
          {selection.size} document{plural(selection.size)} selected
          <QueryButton label="Ask" onClick={onAsk} />
        </div>
      )}
      <ul className={styles.list}>
        {items.map((item) => {
          const selected = selection.has(item.source);
          const meta = `${fileType(item.source)} · ${formatSize(item.size)} · ${formatShortDate(new Date(item.modified * 1000))}`;
          return (
            <li key={item.source} className={styles.card} data-selected={selected}>
              <Checkbox checked={selected} onChange={() => onToggle(item.source)} aria-label={`Select ${item.source}`} />
              <FileName source={item.source} meta={meta} iconSize={18}
                editing={actions.renaming === `cards:${item.source}`} onRenamed={(name) => actions.rename(item, name)} />
              <span className={styles.status}><StatusBadge status={item.status} /></span>
              <DocumentMenu item={item} view="cards" actions={actions} />
            </li>
          );
        })}
      </ul>
    </div>
  );
}
