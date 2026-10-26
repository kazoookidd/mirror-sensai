import { Icon } from "../../components/ui/Icon/Icon.jsx";
import { TestTag } from "../../components/feedback/TestTag/TestTag.jsx";
import styles from "./DropZone.module.css";

const TEST_HINT = "[TEST] Not available yet";

export function DropZone() {
  return (
    <div className={`${styles.zone} desktop-only`} title={TEST_HINT}>
      <span className={styles.icon}><Icon name="upload" size={18} /></span>
      <span className={styles.text}>
        <span className={styles.title}>Drop your files here <TestTag /></span>
        <span className="text-small text-secondary">Agreements, policies, internal rules, procedures: PDF, TXT or Markdown</span>
      </span>
    </div>
  );
}

export function EmptyBase() {
  return (
    <>
      <div className={`${styles.zone} ${styles.empty}`} title={TEST_HINT}>
        <span className={styles.icon}><Icon name="upload" size={20} /></span>
        <span className={styles.text}>
          <span className="text-heading">No document imported</span>
          <span className="text-small text-secondary">
            Drop your agreements, policies, internal rules or procedures here.<br />PDF, TXT or Markdown.
          </span>
        </span>
      </div>
      <p className="info-note">
        <Icon name="database" size={16} />
        While the base is empty, SENSAI answers only with the general knowledge of the model, without citing any source.
      </p>
    </>
  );
}
