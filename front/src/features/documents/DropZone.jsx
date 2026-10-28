import { useState } from "react";
import { Icon } from "../../components/ui/Icon/Icon.jsx";
import { cx } from "../../lib/cx.js";
import styles from "./DropZone.module.css";

function Zone({ importing, onPick, onDrop, className, iconSize, children }) {
  const [over, setOver] = useState(false);
  return (
    <button type="button" className={cx(styles.zone, over && styles.over, className)} disabled={Boolean(importing)} onClick={onPick}
      onDragOver={(event) => { event.preventDefault(); setOver(true); }}
      onDragLeave={(event) => !event.currentTarget.contains(event.relatedTarget) && setOver(false)}
      onDrop={(event) => { event.preventDefault(); setOver(false); onDrop([...event.dataTransfer.files]); }}>
      <span className={styles.icon}><Icon name="upload" size={iconSize} /></span>
      <span className={styles.text}>
        {importing
          ? <><span className={styles.title}>Importing {importing}...</span>
            <span className="text-small text-secondary">Chunking and embeddings run on this machine.</span></>
          : children}
      </span>
    </button>
  );
}

export function DropZone(props) {
  return (
    <Zone {...props} className="desktop-only" iconSize={18}>
      <span className={styles.title}>Drop your files here, or click to choose them</span>
      <span className="text-small text-secondary">Agreements, policies, internal rules, procedures: PDF, TXT or Markdown, up to 10 MB</span>
    </Zone>
  );
}

export function EmptyBase(props) {
  return (
    <>
      <Zone {...props} className={styles.empty} iconSize={20}>
        <span className="text-heading">No document imported</span>
        <span className="text-small text-secondary">
          Drop your agreements, policies, internal rules or procedures here.<br />PDF, TXT or Markdown, up to 10 MB.
        </span>
      </Zone>
      <p className="info-note">
        <Icon name="database" size={16} />
        While the base is empty, SENSAI answers only with the general knowledge of the model, without citing any source.
      </p>
    </>
  );
}
