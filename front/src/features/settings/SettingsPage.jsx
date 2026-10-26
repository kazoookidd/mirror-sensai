import { Button } from "../../components/ui/Button/Button.jsx";
import { useApp } from "../../context/AppContext.jsx";
import { AppShell } from "../../layout/AppShell.jsx";
import { Page, PageHeader } from "../../layout/Page.jsx";
import { SettingsSections } from "./SettingsSections.jsx";
import { Section } from "./Section.jsx";
import styles from "./SettingsPage.module.css";

export function SettingsPage() {
  const { user, logout } = useApp();

  return (
    <AppShell nav={{ active: "settings", mobile: "back", title: "Settings", back: "/chat", tabs: false }} scroll>
      <Page width="narrow">
        <div className="desktop-only">
          <PageHeader title="Settings" subtitle="Configuration of SENSAI on this machine." />
        </div>
        <SettingsSections />
        <div className={styles.account}>
          <Section title="Account" description={`Logged in as ${user.user_id}.`}>
            <div className={styles.accountActions}>
              <Button to="/profile" block>Profile</Button>
              <Button variant="danger" block onClick={logout}>Log out</Button>
            </div>
          </Section>
        </div>
      </Page>
    </AppShell>
  );
}
