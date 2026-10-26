import { TestTag } from "../../components/feedback/TestTag/TestTag.jsx";
import { Dialog } from "../../components/ui/Dialog/Dialog.jsx";
import { Icon } from "../../components/ui/Icon/Icon.jsx";
import { cx } from "../../lib/cx.js";
import { ProfileForm } from "../profile/ProfileForm.jsx";
import { SettingsSections } from "../settings/SettingsSections.jsx";
import styles from "./AccountDialog.module.css";

const TABS = [
  { id: "settings", label: "Settings", icon: "settings", subtitle: "Configuration of SENSAI on this machine." },
  { id: "profile", label: "Profile", icon: "users", subtitle: "This information is added to the context of every new chat." },
];

export function AccountDialog({ tab, onTab, onClose }) {
  const current = TABS.find((item) => item.id === tab);

  return (
    <Dialog title={current.label} onClose={onClose}>
      <nav className={styles.tabs} aria-label="Account">
        {TABS.map((item) => (
          <button key={item.id} type="button" className={cx(styles.tab, item.id === tab && styles.selected)}
            aria-current={item.id === tab ? "page" : undefined} onClick={() => onTab(item.id)}>
            <Icon name={item.icon} size={16} />{item.label}
          </button>
        ))}
      </nav>
      <div className={styles.content}>
        <header className={styles.header}>
          <h2 className={cx("text-heading", styles.title)}>{current.label}{tab === "profile" && <TestTag />}</h2>
          <p className="text-small text-secondary">{current.subtitle}</p>
        </header>
        {tab === "settings" ? <SettingsSections /> : <ProfileForm onCancel={onClose} />}
      </div>
    </Dialog>
  );
}
