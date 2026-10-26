import { EmptyState } from "../../components/feedback/EmptyState/EmptyState.jsx";
import { AppShell } from "../../layout/AppShell.jsx";
import styles from "./NotFoundPage.module.css";

export function NotFoundPage() {
  return (
    <AppShell nav={{ active: "not-found", mobile: "back", title: "Page not found", back: "/chat", tabs: false }}>
      <div className={styles.page}>
        <span className={styles.code}>404</span>
        <EmptyState icon="search" iconSize={16} title="Page not found"
          action={{ label: "New chat", to: "/chat" }}>
          This address does not exist, or the conversation was deleted. Your other chats are in History.
        </EmptyState>
      </div>
    </AppShell>
  );
}
