import { Button } from "../../../components/ui/Button/Button.jsx";
import { Icon } from "../../../components/ui/Icon/Icon.jsx";
import styles from "./Messages.module.css";

export function ConfirmationCard({ title, plan, busy, onConfirm, onCancel }) {
  return (
    <section className={styles.confirmation} aria-label={title}>
      <p className={styles.confirmationTitle}><Icon name="alert" size={16} />{title}</p>
      <pre className={styles.output}>{plan}</pre>
      <footer className={styles.confirmationFooter}>
        <p className={styles.confirmationHint}>Nothing is done until you confirm.</p>
        <div className={styles.confirmationButtons}>
          <Button disabled={busy} onClick={onCancel}>Cancel</Button>
          <Button variant="primary" icon="check" iconSize={14} disabled={busy} onClick={onConfirm}>Confirm</Button>
        </div>
      </footer>
    </section>
  );
}
