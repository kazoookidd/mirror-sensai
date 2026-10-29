import { StatusBadge } from "../../components/ui/Badge/Badge.jsx";
import { Checkbox } from "../../components/ui/Checkbox/Checkbox.jsx";
import { fileType, formatDate, formatSize } from "../../lib/format.js";
import { DocumentMenu } from "./DocumentButtons.jsx";
import { FileName } from "./FileName.jsx";
import styles from "./FileTable.module.css";

export function FileTable({ items, selection, onToggle, onToggleAll, actions }) {
  return (
    <div className={`${styles.table} desktop-only`} role="table" aria-label="Imported documents">
      <div className={`${styles.row} ${styles.head}`} role="row">
        <span role="columnheader"><Checkbox checked={selection.size === items.length} onChange={onToggleAll} aria-label="Select all" /></span>
        <span role="columnheader">Name</span>
        <span role="columnheader" className={styles.type}>Type</span>
        <span role="columnheader">Imported</span>
        <span role="columnheader">Status</span>
        <span role="columnheader"><span className="sr-only">Actions</span></span>
      </div>
      {items.map((item) => {
        const selected = selection.has(item.source);
        return (
          <div key={item.source} className={styles.row} role="row" data-selected={selected}>
            <span role="cell"><Checkbox checked={selected} onChange={() => onToggle(item.source)} aria-label={`Select ${item.source}`} /></span>
            <span role="cell"><FileName source={item.source} meta={formatSize(item.size)} iconSize={16}
              editing={actions.renaming === `table:${item.source}`} onRenamed={(name) => actions.rename(item, name)} /></span>
            <span role="cell" className={`${styles.cell} ${styles.type}`}>{fileType(item.source)}</span>
            <span role="cell" className={styles.cell}>{formatDate(new Date(item.modified * 1000))}</span>
            <span role="cell"><StatusBadge status={item.status} /></span>
            <span role="cell"><DocumentMenu item={item} view="table" actions={actions} /></span>
          </div>
        );
      })}
    </div>
  );
}
