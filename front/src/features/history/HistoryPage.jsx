import { useEffect, useMemo, useState } from "react";
import { Button } from "../../components/ui/Button/Button.jsx";
import { EmptyState } from "../../components/feedback/EmptyState/EmptyState.jsx";
import { InputBox } from "../../components/ui/Field/Field.jsx";
import { Icon } from "../../components/ui/Icon/Icon.jsx";
import { IconButton } from "../../components/ui/IconButton/IconButton.jsx";
import { useApp } from "../../context/AppContext.jsx";
import { AppShell } from "../../layout/AppShell.jsx";
import { Page, PageHeader } from "../../layout/Page.jsx";
import { conversations as conversationsApi } from "./api.js";
import { dayGroup, parseUtc, plainText } from "../../lib/format.js";
import { HistoryItem } from "./HistoryItem.jsx";
import { HistoryRow } from "./HistoryRow.jsx";
import styles from "./HistoryPage.module.css";

function grouped(items) {
  const groups = new Map();
  for (const item of items) {
    const label = dayGroup(parseUtc(item.updated_at));
    if (!groups.has(label)) groups.set(label, []);
    groups.get(label).push(item);
  }
  return [...groups];
}

export function HistoryPage() {
  const { refreshConversations } = useApp();
  const [items, setItems] = useState(null);
  const [failed, setFailed] = useState(false);
  const [query, setQuery] = useState("");
  const [newestFirst, setNewestFirst] = useState(true);

  useEffect(() => {
    conversationsApi.list().then((data) => setItems(data.conversations)).catch(() => setFailed(true));
  }, []);

  const actions = {
    rename: async (conversation, title) => {
      await conversationsApi.rename(conversation.id, title);
      refreshConversations();
      setItems((list) => list.map((item) => (item.id === conversation.id ? { ...item, title } : item)));
    },
    remove: async (conversation) => {
      if (!window.confirm(`Delete "${conversation.title}"? This cannot be undone.`)) return;
      await conversationsApi.remove(conversation.id);
      refreshConversations();
      setItems((list) => list.filter((item) => item.id !== conversation.id));
    },
  };

  const visible = useMemo(() => {
    const search = query.trim().toLowerCase();
    const found = (items ?? []).filter((item) => `${item.title} ${plainText(item.preview)}`.toLowerCase().includes(search));
    return newestFirst ? found : found.reverse();
  }, [items, query, newestFirst]);

  return (
    <AppShell nav={{ active: "history", mobile: "root", tabs: true }} scroll>
      <Page width="medium">
        <PageHeader title="History" subtitle="Conversations saved locally on this machine." subtitleDesktopOnly
          actions={<>
            <Button variant="primary" icon="plus" to="/chat" className="desktop-only">New chat</Button>
            <IconButton icon="plus" label="New chat" variant="primary" to="/chat" className="mobile-only" />
          </>} />
        <div className={styles.toolbar}>
          <InputBox small leading={["search", 16]} type="search" placeholder="Search conversations"
            aria-label="Search conversations" className={styles.search}
            value={query} onChange={(event) => setQuery(event.target.value)} />
          <Button variant="ghostStrong" icon="sort" className="desktop-only" onClick={() => setNewestFirst((value) => !value)}>
            {newestFirst ? "Newest first" : "Oldest first"}
          </Button>
        </div>
        {failed && <p className="info-note"><Icon name="alert" size={16} />Could not load the history.</p>}
        {items && !items.length && (
          <div className={styles.emptyCard}>
            <EmptyState icon="history" iconSize={18} title="No conversations"
              action={{ label: "New chat", to: "/chat" }}>
              Your chats with SENSAI will appear here.
            </EmptyState>
          </div>
        )}
        {items?.length > 0 && !visible.length && (
          <p className="info-note"><Icon name="search" size={16} />No conversation matches this search.</p>
        )}
        {grouped(visible).map(([label, group]) => (
          <section key={label} className={styles.group}>
            <h2 className={styles.groupLabel}>{label}</h2>
            <ul className={`${styles.list} desktop-only`}>
              {group.map((item) => <HistoryRow key={item.id} conversation={item} actions={actions} />)}
            </ul>
            <ul className={`${styles.list} ${styles.mobileList} mobile-only`}>
              {group.map((item) => <HistoryItem key={item.id} conversation={item} actions={actions} />)}
            </ul>
          </section>
        ))}
      </Page>
    </AppShell>
  );
}
